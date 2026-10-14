FROM python:3.12-slim AS base

RUN useradd --create-home --uid 1001 appuser

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chown -R appuser:appuser /app

#########################
FROM base AS test

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

USER appuser

CMD ["pytest"]

#########################
FROM base AS final

USER appuser

EXPOSE 5000

CMD ["python", "app.py"]
