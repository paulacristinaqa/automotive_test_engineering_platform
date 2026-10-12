FROM python:3.14.8-alpine3.24@sha256:f6a589d43c42b9e7f7dc67a12d37132491f362859a5d750607710cc56da3bc72 AS runtime

ARG ATEP_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/paulacristinaqa/automotive_test_engineering_platform" \
      org.opencontainers.image.revision="$ATEP_SOURCE_REVISION" \
      org.opencontainers.image.title="Automotive Test Engineering Platform Core"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apk upgrade --no-cache
RUN python -m venv /opt/venv
WORKDIR /app

COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
COPY clients/dashboard ./clients/dashboard
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps --no-build-isolation .

COPY alembic.ini ./
COPY migrations ./migrations

RUN addgroup -S atep && adduser -S -G atep -h /home/atep atep \
    && chown -R atep:atep /app
USER atep

EXPOSE 8000 9101
CMD ["uvicorn", "atep.main:app", "--host", "0.0.0.0", "--port", "8000"]
