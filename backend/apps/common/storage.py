"""올린 파일 지우기 (탈퇴 · 쓰이지 않는 사진 정리)."""

from django.core.files.storage import default_storage


def delete_files(names):
    """파일을 지운다. 이미 없거나 지우지 못한 파일은 넘어간다 (다음 정리에서 다시 보지 않는다)."""
    for name in names:
        if not name:
            continue
        try:
            default_storage.delete(name)
        except OSError:
            pass
