FROM python:3.14.6-alpine3.24@sha256:26730869004e2b9c4b9ad09cab8625e81d256d1ce97e72df5520e806b1709f92 AS runtime

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
