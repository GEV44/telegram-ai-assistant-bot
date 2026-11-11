FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

COPY config ./config
RUN useradd --create-home bot && mkdir -p /app/data && chown -R bot /app/data
USER bot

CMD ["python", "-m", "tg_assistant"]
