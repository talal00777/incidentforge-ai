FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv/app
COPY . .
RUN pip install --no-cache-dir . \
    && groupadd --system incidentforge \
    && useradd --system --gid incidentforge --home /srv/app incidentforge \
    && chmod +x /srv/app/scripts/start-api.sh
USER incidentforge
EXPOSE 8000
CMD ["/srv/app/scripts/start-api.sh"]
