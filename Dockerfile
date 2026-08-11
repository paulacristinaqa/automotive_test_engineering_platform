FROM python:3.15.0rc1-alpine3.24@sha256:4b4340819382ffdbc0d87233b441daf617eec784e43458f8f5cb4d5e3b7d1838 AS runtime

ARG ATEP_SOURCE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/paulacristinaqa/automotive_test_engineering_platform" \
      org.opencontainers.image.revision="$ATEP_SOURCE_REVISION" \
      org.opencontainers.image.title="Automotive Test Engineering Platform Core"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv
WORKDIR /app

COPY pyproject.toml README.md requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --no-deps --no-build-isolation .

COPY alembic.ini ./
COPY migrations ./migrations

RUN addgroup -S atep && adduser -S -G atep -h /home/atep atep \
    && chown -R atep:atep /app
USER atep

EXPOSE 8000 9101
CMD ["uvicorn", "atep.main:app", "--host", "0.0.0.0", "--port", "8000"]
