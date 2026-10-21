from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"
    verbose_name = "회원"

    def ready(self):
        from . import social  # noqa: F401  소셜 계정의 프로필 원본을 비우는 신호
