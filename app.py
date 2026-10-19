import os
from flask import Flask, jsonify
import psycopg2
import time 

app = Flask(__name__)

def read_secret(name, default=None):
    """Önce /run/secrets/<name> dosyasına bakar, yoksa ortam değişkenine düşer."""
    path = f"/app/secrets/{name}"
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return os.environ.get(name.upper(), default)

DATABASE_URL = read_secret(
    "database_url",
    "postgresql://postgres:postgres@localhost:5432/postgres"
)

def get_connection(retries=3, delay=1):
    """Bağlantı koparsa artan bekleme ile tekrar dener."""
    last_error = None
    for attempt in range(retries):
        try:
            return psycopg2.connect(DATABASE_URL, connect_timeout=5)
        except psycopg2.OperationalError as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
    raise last_error

@app.route("/")
def home():
    return jsonify({"message": "Merhaba Docker CI"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/db")
def db_check():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version()")
        result = cur.fetchone()
        cur.close()
        conn.close()
        return jsonify({"database": "connected", "version": result[0][:40]})
    except Exception as e:
        return jsonify({"database": "error", "detail": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
