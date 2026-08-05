FROM python:3.12-slim@sha256:646fb0bca3dd3ea1bcc6feb72c17ed16eed6e10cffc732fcc1478bd3e7f02d7b AS runtime

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

RUN addgroup --system atep && adduser --system --ingroup atep atep \
    && chown -R atep:atep /app
USER atep

EXPOSE 8000 9101
CMD ["uvicorn", "atep.main:app", "--host", "0.0.0.0", "--port", "8000"]
