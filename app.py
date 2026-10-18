import os
from flask import Flask, jsonify
import psycopg2

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

@app.route("/")
def home():
    return jsonify({"message": "Merhaba Docker CI"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/db")
def db_check():
    try:
        conn = psycopg2.connect(DATABASE_URL)
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
