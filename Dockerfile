FROM python:3.14.7-alpine3.24@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc AS runtime

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
