from django.core.management.base import BaseCommand

from apps.accounts.pending import expired_pending_signups


class Command(BaseCommand):
    help = "인증 링크가 만료되도록 이메일 인증을 안 마친 가입을 지운다 (이메일을 잘못 쓴 가입 등)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="지우지 않고 대상만 보여 준다")

    def handle(self, *args, dry_run=False, **options):
        users = list(expired_pending_signups().order_by("created_at"))
        for user in users:
            self.stdout.write(f"{user.pk}\t{user.email}\t{user.nickname}\t{user.created_at:%Y-%m-%d %H:%M}")
        if dry_run:
            self.stdout.write(f"지울 가입 {len(users)}개 (--dry-run 이라 지우지 않았어요)")
            return
        expired_pending_signups().filter(pk__in=[u.pk for u in users]).delete()
        self.stdout.write(self.style.SUCCESS(f"인증 안 된 가입 {len(users)}개를 지웠어요"))
