# 한채 이미지: Django + gunicorn 이 API 와 화면 파일(index.html · css · js · assets)을 함께 내보낸다
# 저장소 루트에서 빌드한다: docker build -t hanchae-backend .
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIR=/app/frontend

# mysqlclient 를 빌드하려면 MySQL 클라이언트 라이브러리가 필요하다
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential default-libmysqlclient-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .
# 화면 파일. 어떤 파일이 들어오는지는 루트의 .dockerignore 가 정한다
COPY *.html frontend/
COPY css/ frontend/css/
COPY js/ frontend/js/
COPY assets/ frontend/assets/
RUN DJANGO_SECRET_KEY=collectstatic-only python manage.py collectstatic --noinput

EXPOSE 8000
# 컨테이너가 뜰 때마다 DB 를 최신 마이그레이션으로 맞춘 뒤 서버를 켠다.
# 포트는 PORT 로 바꿀 수 있다 (학교 서버는 호스트 네트워크로 띄워 APP_PORT 에서 바로 받는다)
# exec: gunicorn 이 docker stop 의 신호를 직접 받아, 하던 요청을 마친 뒤 내려간다 (deploy.sh)
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3 --access-logfile - --error-logfile -"]
