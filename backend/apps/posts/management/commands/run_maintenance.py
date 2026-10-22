"""하루 한 번 하는 정리. GitHub Actions(.github/workflows/maintenance.yml)가 매일 새벽 서버에서 부른다.

출력은 공개 저장소의 Actions 로그에 남는다. 그래서 개수만 쓰고 이메일 · 닉네임 같은 개인정보는 절대 쓰지 않는다
(무엇을 지우는지 보려면 서버에서 직접 delete_expired_signups --dry-run).

- 쓰이지 않는 사진: 올린 지 하루가 지나도 어디에도 쓰이지 않으면 행과 파일을 지운다 (posts/cleanup.py)
- 인증 안 마친 가입: 인증 링크까지 만료된 것 (delete_expired_signups)
- 끝난 로그인 세션 (Django clearsessions)
- 조회 기록: 순위는 최근 24시간만 보므로 VIEW_KEEP 보다 오래된 것 (기록의 조회 수는 그대로)
"""

from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.pending import expired_pending_signups
from apps.posts.cleanup import delete_unused_images
from apps.posts.models import PostView

VIEW_KEEP = timedelta(days=30)


class Command(BaseCommand):
    help = "쓰이지 않는 사진 · 만료된 가입 · 끝난 세션 · 오래된 조회 기록을 정리한다 (하루 한 번)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="지우지 않고 수만 보여 준다")

    def handle(self, *args, dry_run=False, **options):
        images = delete_unused_images(dry_run=dry_run)
        self.stdout.write(f"쓰이지 않는 사진 {images}개" + (" (--dry-run 이라 지우지 않았어요)" if dry_run else ""))
        signups = expired_pending_signups()
        if dry_run:
            self.stdout.write(f"인증 안 마친 가입 {signups.count()}개")
        else:
            ids = list(signups.values_list("pk", flat=True))
            expired_pending_signups().filter(pk__in=ids).delete()
            self.stdout.write(f"인증 안 마친 가입 {len(ids)}개")
        old_views = PostView.objects.filter(viewed_at__lt=timezone.now() - VIEW_KEEP)
        if dry_run:
            self.stdout.write(f"오래된 조회 기록 {old_views.count()}개 (--dry-run 이라 지우지 않았어요)")
            return
        deleted, _ = old_views.delete()
        self.stdout.write(f"오래된 조회 기록 {deleted}개")
        call_command("clearsessions")
        self.stdout.write(self.style.SUCCESS("정리를 마쳤어요"))
