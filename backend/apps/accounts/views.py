"""회원 · 로그인 API (API 명세서 4.1, 기능 AUTH-01 ~ AUTH-05)."""

import logging
import smtplib
from datetime import timedelta

from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access import current_sanction
from apps.common.errors import APIError
from apps.common.permissions import EnforceCsrfMixin, IsMember
from apps.posts.images import get_own_image

from .models import User, VerificationMailLog
from .pending import expired_pending_signups, pending_signups, removable_pending_signups
from .serializers import (
    EmailResendSerializer,
    LoginSerializer,
    MeUpdateSerializer,
    NicknameField,
    SignupSerializer,
    me_payload,
)

logger = logging.getLogger(__name__)
# 같은 주소로 인증 메일을 다시 보낼 수 있는 간격
RESEND_INTERVAL = timedelta(seconds=60)


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """GET /api/auth/csrf — CSRF 쿠키를 준다. 앱을 열 때 한 번 부른다."""

    def get(self, request):
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me — 지금 로그인한 사람. 비회원이면 {"user": null}."""

    def get(self, request):
        if not request.user.is_authenticated:
            return Response({"user": None})
        return Response({"user": me_payload(request.user, request)})


class SignupView(EnforceCsrfMixin, APIView):
    """POST /api/auth/signup — 이메일 가입. 인증 메일을 보낸다 (AUTH-01)."""

    def post(self, request):
        serializer = SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # 인증을 안 마친 가입은 자리를 내준다. 닉네임은 바로 (이메일을 잘못 써 끝내 인증할 수 없는 가입일 수 있다),
        # 같은 이메일은 그 주소로 간 링크가 만료된 뒤에만 (그 전에는 메일함의 링크로 마치면 된다)
        removable_pending_signups().filter(nickname=data["nickname"]).exclude(email__iexact=data["email"]).delete()
        expired_pending_signups().filter(email__iexact=data["email"]).delete()

        conflicts = {}
        if pending_signups().filter(email=data["email"]).exists():
            conflicts["email"] = "인증을 기다리는 가입이 있어요. 메일함을 확인하거나 인증 메일을 다시 받아 주세요."
        elif User.objects.filter(email=data["email"]).exists():
            conflicts["email"] = "이미 가입한 이메일이에요."
        if User.objects.filter(nickname=data["nickname"]).exists():
            conflicts["nickname"] = "이미 쓰고 있는 닉네임이에요."
        if conflicts:
            raise APIError(409, "CONFLICT", "이미 쓰고 있는 값이 있어요.", fields=conflicts)

        now = timezone.now()
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    data["email"],
                    data["password"],
                    nickname=data["nickname"],
                    terms_agreed_at=now,
                    privacy_agreed_at=now,
                )
                address = EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=False)
                # 메일을 못 보내면 가입도 되돌린다. 남겨 두면 메일 없이 '이미 가입한 이메일'만 남는다
                address.send_confirmation(request, signup=True)
        except IntegrityError:
            raise APIError(409, "CONFLICT", "이미 쓰고 있는 값이 있어요.")
        except (smtplib.SMTPException, OSError):
            logger.exception("인증 메일을 보내지 못했어요")
            raise APIError(503, "MAIL_FAILED", "인증 메일을 보내지 못했어요. 잠시 뒤 다시 가입해 주세요.")
        return Response({"email_verification_sent": True}, status=status.HTTP_201_CREATED)


class EmailVerifyView(EnforceCsrfMixin, APIView):
    """POST /api/auth/email/verify — 인증 메일의 키로 이메일을 인증한다."""

    def post(self, request):
        key = str(request.data.get("key", "")).strip()
        confirmation = EmailConfirmationHMAC.from_key(key) if key else None
        if confirmation is None or confirmation.confirm(request) is None:
            raise APIError(
                400, "VALIDATION_ERROR", "인증 링크가 만료됐거나 잘못됐어요.", fields={"key": "메일을 다시 받아 주세요."}
            )
        return Response({"verified": True})


class EmailResendView(EnforceCsrfMixin, APIView):
    """POST /api/auth/email/resend — 인증 메일 다시 보내기.

    같은 주소로는 RESEND_INTERVAL 에 한 번만 보낸다. 없는 주소 · 이미 인증한 주소에도 똑같이 '보냈어요'로
    답해, 이 API 로 가입 여부를 하나씩 알아내지 못하게 한다.
    """

    def post(self, request):
        serializer = EmailResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        now = timezone.now()

        with transaction.atomic():
            log, created = VerificationMailLog.objects.select_for_update().get_or_create(
                email=email, defaults={"last_sent_at": now}
            )
            if not created:
                wait = RESEND_INTERVAL - (now - log.last_sent_at)
                if wait.total_seconds() > 0:
                    seconds = int(wait.total_seconds()) + 1
                    raise APIError(
                        429,
                        "TOO_MANY_REQUESTS",
                        f"방금 보냈어요. {seconds}초 뒤에 다시 보낼 수 있어요.",
                        detail={"retry_after": seconds},
                    )
                log.last_sent_at = now
                log.save(update_fields=["last_sent_at"])

        address = (
            EmailAddress.objects.select_related("user")
            .filter(email__iexact=email, verified=False, user__is_active=True)
            .first()
        )
        if address is not None and not EmailAddress.objects.filter(user=address.user, verified=True).exists():
            try:
                address.send_confirmation(request, signup=False)
            except (smtplib.SMTPException, OSError):
                logger.exception("인증 메일을 다시 보내지 못했어요")
                # 실패했으면 바로 다시 시도할 수 있게 기록을 되돌린다
                VerificationMailLog.objects.filter(email=email).update(last_sent_at=now - RESEND_INTERVAL)
                raise APIError(503, "MAIL_FAILED", "인증 메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.")
        return Response({"sent": True})


class LoginView(EnforceCsrfMixin, APIView):
    """POST /api/auth/login — 이메일 로그인 (AUTH-01)."""

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None:
            raise APIError(401, "LOGIN_FAILED", "이메일이나 비밀번호가 맞지 않아요.")

        addresses = EmailAddress.objects.filter(user=user)
        if addresses.exists() and not addresses.filter(verified=True).exists():
            raise APIError(403, "EMAIL_NOT_VERIFIED", "메일함에서 이메일 인증을 먼저 마쳐 주세요.")

        sanction = current_sanction(user)
        if sanction is not None:
            raise APIError(
                403,
                "SUSPENDED",
                "이용이 제한된 계정이에요.",
                detail={"reason": sanction.reason, "ends_at": sanction.ends_at},
            )

        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response({"user": me_payload(user, request)})


class LogoutView(APIView):
    """POST /api/auth/logout (AUTH-02)."""

    permission_classes = [IsMember]

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NicknameAvailableView(APIView):
    """GET /api/auth/nickname-available?nickname= — 닉네임을 쓸 수 있는지 (AUTH-05)."""

    def get(self, request):
        field = NicknameField()
        try:
            nickname = field.run_validation(request.query_params.get("nickname", ""))
        except Exception:
            return Response({"available": False, "reason": "INVALID"})
        taken = User.objects.filter(nickname=nickname)
        if request.user.is_authenticated:
            taken = taken.exclude(pk=request.user.pk)
        if taken.exists():
            return Response({"available": False, "reason": "TAKEN"})
        return Response({"available": True, "reason": None})


class MeUpdateView(APIView):
    """PATCH /api/me — 닉네임 · 프로필 이미지 수정 (AUTH-05)."""

    permission_classes = [IsMember]

    def patch(self, request):
        serializer = MeUpdateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = request.user
        if "nickname" in data:
            user.nickname = data["nickname"]
        if "profile_image_id" in data:
            image_id = data["profile_image_id"]
            user.profile_image = get_own_image(image_id, user).file.name if image_id is not None else None
        try:
            user.save()
        except IntegrityError:
            raise APIError(409, "CONFLICT", "이미 쓰고 있는 닉네임이에요.", fields={"nickname": "이미 쓰고 있는 닉네임이에요."})
        return Response({"user": me_payload(user, request)})
