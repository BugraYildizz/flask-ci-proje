FROM python:3.12-slim AS base

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

#########################
FROM base AS test
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
CMD ["pytest"]

#########################
FROM base AS final

EXPOSE 5000

CMD ["python", "app.py"]
