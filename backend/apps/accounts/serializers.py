from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User


def absolute_url(request, field_file):
    """올린 파일의 주소. 호스트 없이 /media/... 로 준다 (도메인 · https 가 바뀌어도 깨지지 않게)."""
    return field_file.url if field_file else None


def alive_blog_address(user):
    blog = user.blogs.filter(deleted_at__isnull=True).only("address").first()
    return blog.address if blog else None


def user_summary(user, request):
    """UserSummary (API 명세서 3.1). 탈퇴한 회원은 '떠난 사람'."""
    if user is None or not user.is_active:
        return {"nickname": None, "profile_image_url": None, "blog_address": None, "withdrawn": True}
    return {
        "nickname": user.nickname,
        "profile_image_url": absolute_url(request, user.profile_image),
        "blog_address": alive_blog_address(user),
    }


def me_payload(user, request):
    """GET /api/auth/me 의 user (API 명세서 4.1)."""
    return {
        "nickname": user.nickname,
        "email": user.email,
        "profile_image_url": absolute_url(request, user.profile_image),
        "role": user.role,
        "blog_address": alive_blog_address(user),
    }


# 비밀번호 검사(settings.AUTH_PASSWORD_VALIDATORS)의 오류 코드마다 화면에 보일 문장
PASSWORD_MESSAGES = {
    "password_too_short": "비밀번호는 8자 이상으로 써 주세요.",
    "password_too_common": "너무 흔한 비밀번호예요. 다른 비밀번호를 써 주세요.",
    "password_entirely_numeric": "숫자로만 된 비밀번호는 쓸 수 없어요.",
    "password_too_similar": "이메일이나 닉네임과 비슷한 비밀번호는 쓸 수 없어요.",
}


def check_new_password(value, user=None):
    """새로 정하는 비밀번호를 검사한다. user 를 주면 이메일 · 닉네임과 비슷한지도 본다."""
    try:
        validate_password(value, user)
    except DjangoValidationError as e:
        raise serializers.ValidationError(PASSWORD_MESSAGES.get(e.error_list[0].code, "다른 비밀번호를 써 주세요."))
    return value


class NicknameField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(min_length=2, max_length=20, trim_whitespace=True, **kwargs)
        self.error_messages.update(
            {
                "min_length": "닉네임은 2~20자로 써 주세요.",
                "max_length": "닉네임은 2~20자로 써 주세요.",
                "blank": "닉네임을 써 주세요.",
                "required": "닉네임을 써 주세요.",
            }
        )


class AgreementValidators:
    """가입할 때 받는 동의 (이메일 가입 · 소셜 가입). 각 시리얼라이저가 agree_terms · agree_privacy · over_14 를 둔다."""

    def validate_agree_terms(self, value):
        if not value:
            raise serializers.ValidationError("이용약관에 동의해야 가입할 수 있어요.")
        return value

    def validate_agree_privacy(self, value):
        if not value:
            raise serializers.ValidationError("개인정보 수집 · 이용에 동의해야 가입할 수 있어요.")
        return value

    def validate_over_14(self, value):
        if not value:
            raise serializers.ValidationError("만 14세 이상만 가입할 수 있어요.")
        return value


class SignupSerializer(AgreementValidators, serializers.Serializer):
    email = serializers.EmailField(max_length=254, error_messages={"invalid": "이메일 형식을 확인해 주세요."})
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    nickname = NicknameField()
    agree_terms = serializers.BooleanField()
    agree_privacy = serializers.BooleanField()
    over_14 = serializers.BooleanField()

    def validate_password(self, value):
        return check_new_password(value)

    def validate(self, data):
        # 이메일 · 닉네임과 비슷한지는 칸마다 검사한 뒤 함께 본다
        try:
            check_new_password(data["password"], User(email=data["email"], nickname=data["nickname"]))
        except serializers.ValidationError as e:
            raise serializers.ValidationError({"password": e.detail})
        return data


class SocialSignupSerializer(AgreementValidators, serializers.Serializer):
    """소셜 계정으로 처음 온 사람의 가입 마무리. 이메일 · 비밀번호는 받지 않는다."""

    nickname = NicknameField()
    agree_terms = serializers.BooleanField()
    agree_privacy = serializers.BooleanField()
    over_14 = serializers.BooleanField()


# 인증 메일 다시 보내기 · 비밀번호 재설정 메일
class EmailResendSerializer(serializers.Serializer):
    email = serializers.EmailField(
        max_length=254, error_messages={"invalid": "이메일 형식을 확인해 주세요.", "required": "이메일을 써 주세요."}
    )


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class EmailVerifySerializer(serializers.Serializer):
    key = serializers.CharField(trim_whitespace=True, error_messages={"blank": "인증 링크가 잘못됐어요.", "required": "인증 링크가 잘못됐어요."})
    password = serializers.CharField(
        trim_whitespace=False, error_messages={"blank": "비밀번호를 써 주세요.", "required": "비밀번호를 써 주세요."}
    )


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(
        trim_whitespace=False, error_messages={"blank": "새 비밀번호를 써 주세요.", "required": "새 비밀번호를 써 주세요."}
    )


class MeUpdateSerializer(serializers.Serializer):
    nickname = NicknameField(required=False)
    profile_image_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_nickname(self, value):
        user = self.context["request"].user
        if User.objects.filter(nickname=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("이미 쓰고 있는 닉네임이에요.")
        return value


class LeaveSerializer(serializers.Serializer):
    """탈퇴: 비밀번호가 있으면 비밀번호, 없으면(소셜로만 가입) 닉네임을 그대로 적어 확인한다."""

    password = serializers.CharField(required=False, allow_blank=True, trim_whitespace=False)
    nickname = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    agree = serializers.BooleanField()

    def validate_agree(self, value):
        if not value:
            raise serializers.ValidationError("위 내용을 확인했다고 체크해 주세요.")
        return value
