"""회원 · 로그인 API (API 명세서 4.1, 기능 AUTH-01 ~ AUTH-05)."""

import hashlib
import logging
import math
import smtplib
from datetime import timedelta

from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress, EmailConfirmationHMAC
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from allauth.socialaccount.internal.flows.signup import (
    clear_pending_signup,
    complete_social_signup,
    get_pending_signup,
)
from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.access import current_sanction
from apps.common.errors import APIError
from apps.common.permissions import EnforceCsrfMixin, IsMember
from apps.posts.images import get_own_image

from . import attempts
from .adapter import SOCIAL_BLOCKED_SESSION_KEY
from .models import User, VerificationMailLog
from .pending import expired_pending_signups, pending_signups, removable_pending_signups
from .serializers import (
    EmailResendSerializer,
    EmailVerifySerializer,
    LoginSerializer,
    MeUpdateSerializer,
    NicknameField,
    PasswordResetConfirmSerializer,
    LeaveSerializer,
    SignupSerializer,
    SocialSignupSerializer,
    check_new_password,
    me_payload,
)
from .social import email_is_trusted, pending_signup_payload, verified_email
from .withdrawal import leave_summary, withdraw

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

    throttle_scope = "signup"

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


def invalid_verify_link():
    return APIError(400, "VALIDATION_ERROR", "인증 링크가 만료됐거나 잘못됐어요.", fields={"key": "메일을 다시 받아 주세요."})


class EmailVerifyView(EnforceCsrfMixin, APIView):
    """POST /api/auth/email/verify — 인증 메일의 키와 가입할 때 정한 비밀번호로 인증을 마치고 로그인한다.

    키만으로 인증하면, 남의 이메일로 먼저 가입해 둔 사람의 비밀번호로 계정이 열린다(메일 주인이 링크를 누르는 순간).
    그래서 비밀번호까지 맞아야 인증한다. 비밀번호를 모르는 메일 주인은 비밀번호 재설정으로 자기 비밀번호를 정하면
    인증도 함께 마친다 (PasswordResetConfirmView).
    """

    throttle_scope = "login"

    def post(self, request):
        serializer = EmailVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        confirmation = EmailConfirmationHMAC.from_key(data["key"])
        address = confirmation.email_address if confirmation is not None else None
        if address is None or address.verified:
            raise invalid_verify_link()

        user = address.user
        attempts.ensure_not_locked(address.email)
        if not user.check_password(data["password"]):
            attempts.record_failure(address.email)
            raise APIError(
                400, "VALIDATION_ERROR", "비밀번호가 맞지 않아요.", fields={"password": "가입할 때 정한 비밀번호를 써 주세요."}
            )
        attempts.clear(address.email)
        if confirmation.confirm(request) is None:
            raise invalid_verify_link()

        # 인증은 마쳤다. 이용 제한 중이면 로그인은 하지 않는다 (로그인 화면에서 사유를 알린다)
        if not user.is_active or current_sanction(user) is not None:
            return Response({"verified": True, "user": None})
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response({"verified": True, "user": me_payload(user, request)})


class EmailResendView(EnforceCsrfMixin, APIView):
    """POST /api/auth/email/resend — 인증 메일 다시 보내기.

    같은 주소로는 RESEND_INTERVAL 에 한 번만 보낸다. 없는 주소 · 이미 인증한 주소에도 똑같이 '보냈어요'로
    답해, 이 API 로 가입 여부를 하나씩 알아내지 못하게 한다.
    """

    throttle_scope = "auth_mail"

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


class PasswordResetView(EnforceCsrfMixin, APIView):
    """POST /api/auth/password/reset — 비밀번호를 새로 정하는 링크를 메일로 보낸다.

    인증 메일 다시 보내기처럼 없는 주소에도 '보냈어요'로 답하고, 같은 주소로는 RESEND_INTERVAL 에 한 번만 보낸다.
    인증을 안 마친 가입에도 보낸다. 메일의 링크로 비밀번호를 정하면 그 주소의 주인이므로 인증도 마친다.
    """

    throttle_scope = "auth_mail"

    def post(self, request):
        serializer = EmailResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        now = timezone.now()

        key = "password-reset-mail:" + hashlib.sha256(email.encode()).hexdigest()
        last_sent_at = cache.get(key)
        if last_sent_at is not None and now - last_sent_at < RESEND_INTERVAL:
            seconds = math.ceil((RESEND_INTERVAL - (now - last_sent_at)).total_seconds())
            raise APIError(
                429,
                "TOO_MANY_REQUESTS",
                f"방금 보냈어요. {seconds}초 뒤에 다시 보낼 수 있어요.",
                detail={"retry_after": seconds},
            )
        cache.set(key, now, int(RESEND_INTERVAL.total_seconds()))

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            adapter = get_adapter(request)
            context = {
                "user": user,
                "reset_url": adapter.get_password_reset_url(request, uid, default_token_generator.make_token(user)),
                "minutes": settings.PASSWORD_RESET_TIMEOUT // 60,
            }
            try:
                adapter.render_mail("account/email/hanchae_password_reset", user.email, context).send()
            except (smtplib.SMTPException, OSError):
                logger.exception("비밀번호 재설정 메일을 보내지 못했어요")
                cache.delete(key)  # 바로 다시 시도할 수 있게
                raise APIError(503, "MAIL_FAILED", "메일을 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.")
        return Response({"sent": True})


class PasswordResetConfirmView(EnforceCsrfMixin, APIView):
    """POST /api/auth/password/reset/confirm — 메일 링크의 uid · token 으로 새 비밀번호를 정한다.

    token 은 지금 비밀번호로 만든 값이라 한 번 쓰면(비밀번호가 바뀌면) 더는 쓸 수 없다.
    비밀번호가 바뀌면 다른 기기의 로그인도 끊긴다 (Django 가 세션마다 비밀번호 해시를 확인한다).
    """

    throttle_scope = "password_reset"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data["uid"])), is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            user = None
        if user is None or not default_token_generator.check_token(user, data["token"]):
            raise APIError(
                400, "VALIDATION_ERROR", "링크가 만료됐거나 잘못됐어요.", fields={"token": "비밀번호 재설정 메일을 다시 받아 주세요."}
            )
        try:
            check_new_password(data["password"], user)
        except ValidationError as e:
            raise ValidationError({"password": e.detail})

        with transaction.atomic():
            user.set_password(data["password"])
            user.save(update_fields=["password", "updated_at"])
            # 메일의 링크를 열었으니 이 주소의 주인이다. 인증을 안 마친 가입이면 여기서 인증도 마친다
            EmailAddress.objects.filter(user=user, email__iexact=user.email).update(verified=True)
        attempts.clear(user.email)
        return Response({"reset": True})


class LoginView(EnforceCsrfMixin, APIView):
    """POST /api/auth/login — 이메일 로그인 (AUTH-01)."""

    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        attempts.ensure_not_locked(email)
        user = authenticate(request, username=email, password=serializer.validated_data["password"])
        if user is None:
            attempts.record_failure(email)
            raise APIError(401, "LOGIN_FAILED", "이메일이나 비밀번호가 맞지 않아요.")
        attempts.clear(email)

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


class SocialStatusView(APIView):
    """GET /api/auth/social — 켜진 소셜 로그인 제공사와, 제공사에서 막 돌아온 사람의 다음 할 일 (AUTH-03).

    signup: 처음 온 사람이 가입을 마무리할 때 보여 줄 값 (없으면 null)
    blocked: 이용 제한으로 소셜 로그인을 막았을 때의 사유 · 기한. 한 번 알리면 지운다 (없으면 null)
    """

    def get(self, request):
        sociallogin = get_pending_signup(request._request)
        return Response(
            {
                "providers": settings.SOCIAL_PROVIDERS,
                "signup": pending_signup_payload(sociallogin) if sociallogin else None,
                "blocked": request.session.pop(SOCIAL_BLOCKED_SESSION_KEY, None),
            }
        )


class SocialSignupView(EnforceCsrfMixin, APIView):
    """POST /api/auth/social/signup — 소셜 계정으로 처음 온 사람의 가입을 마치고 로그인한다 (AUTH-03).

    이메일 가입처럼 닉네임과 약관 · 개인정보 · 만 14세 동의를 받는다. 비밀번호는 없다(필요하면 비밀번호 재설정으로 정한다).
    이메일은 제공사가 인증했다고 알려 준 것만 쓴다. 그 이메일로 인증을 기다리는 가입이 있으면,
    제공사가 이 사람이 메일 주인임을 확인했으므로 그 가입은 자리를 내준다 (확인 여부를 알려 주는 카카오 · 구글만).
    """

    throttle_scope = "signup"

    def post(self, request):
        django_request = request._request
        sociallogin = get_pending_signup(django_request)
        if sociallogin is None:
            raise APIError(409, "SOCIAL_SIGNUP_EXPIRED", "소셜 로그인을 처음부터 다시 해 주세요.")
        serializer = SocialSignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nickname = serializer.validated_data["nickname"]
        email = verified_email(sociallogin)

        # 인증을 안 마친 가입은 이 닉네임 자리를, 이메일을 확인해 주는 제공사면 이메일 자리도 내준다
        taken = Q(nickname=nickname) | Q(email__iexact=email) if email and email_is_trusted(sociallogin) else Q(nickname=nickname)
        removable_pending_signups().filter(taken).delete()

        conflicts = {}
        if email and User.objects.filter(email__iexact=email).exists():
            conflicts["email"] = "이미 가입한 이메일이에요. 이메일로 로그인해 주세요."
        if User.objects.filter(nickname=nickname).exists():
            conflicts["nickname"] = "이미 쓰고 있는 닉네임이에요."
        if conflicts:
            raise APIError(409, "CONFLICT", next(iter(conflicts.values())), fields=conflicts)

        now = timezone.now()
        user = sociallogin.user
        user.email = email
        user.nickname = nickname
        user.terms_agreed_at = now
        user.privacy_agreed_at = now
        # 인증된 그 이메일만 남긴다 (인증되지 않은 주소가 남의 가입을 막지 않게)
        sociallogin.email_addresses = [a for a in sociallogin.email_addresses if a.verified and a.email.lower() == email]
        try:
            with transaction.atomic():
                get_social_adapter(django_request).save_user(django_request, sociallogin)
        except IntegrityError:
            raise APIError(409, "CONFLICT", "이미 쓰고 있는 값이 있어요.")
        clear_pending_signup(django_request)
        complete_social_signup(django_request, sociallogin)
        return Response(
            {"user": me_payload(user, request), "next": sociallogin.get_redirect_url(django_request) or "/"},
            status=status.HTTP_201_CREATED,
        )


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


ADMIN_CANNOT_LEAVE = "마을 관리인은 탈퇴할 수 없어요. 다른 관리인에게 역할을 넘긴 뒤 탈퇴해 주세요."


class LeaveView(EnforceCsrfMixin, APIView):
    """GET · POST /api/me/leave — 탈퇴 (AUTH-06).

    GET: 탈퇴 확인 창에 보일 것 (사라지는 것 · '떠난 사람'으로 남는 것의 수, 확인 방법)
    POST: 비밀번호(없으면 닉네임)와 확인 체크를 받아 탈퇴하고 로그아웃한다. 무엇을 지우고 남기는지는 withdrawal.py
    """

    permission_classes = [IsMember]
    throttle_scope = "login"

    def get(self, request):
        return Response(leave_summary(request.user))

    def post(self, request):
        user = request.user
        serializer = LeaveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if user.role == User.Role.ADMIN:
            raise APIError(403, "FORBIDDEN", ADMIN_CANNOT_LEAVE)

        if user.has_usable_password():
            # 비밀번호를 여러 번 틀리면 로그인처럼 잠시 막는다 (이메일이 없으면 회원 번호로 센다)
            lock_key = user.email or f"user-{user.pk}"
            attempts.ensure_not_locked(lock_key)
            if not user.check_password(data.get("password") or ""):
                attempts.record_failure(lock_key)
                raise APIError(400, "VALIDATION_ERROR", "비밀번호가 맞지 않아요.", fields={"password": "비밀번호가 맞지 않아요."})
        elif (data.get("nickname") or "") != user.nickname:
            raise APIError(400, "VALIDATION_ERROR", "닉네임이 맞지 않아요.", fields={"nickname": "닉네임이 맞지 않아요."})

        withdraw(user)
        logout(request)
        return Response({"left": True})
