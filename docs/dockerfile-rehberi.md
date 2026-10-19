İyi Bir Dockerfile Nasıl Olmalı
Aşama aşama kontrol listesi. Her maddede ne yapılacağı ve gerekçesi.
---
1. Temel imaj
`latest` kullanmayın. Sürümü sabitleyin: `python:3.12-slim`, `node:22-slim`.
Her derlemede farklı bir imaj gelebilir. Tekrarlanabilir derleme istiyorsanız
sürüm sabit olmalı.
`slim` varyantını tercih edin. Tam sürümler yüzlerce gereksiz paket taşıyor
— derleyiciler, imagemagick, sürüm kontrol araçları. Bu da yüzlerce CVE demek.
Alpine'a dikkat. Yaygın inancın aksine:
Boyut kazancı abartılı; `slim` varyantlarla fark genelde 50 MB civarı
`apk` paketleri güvenilir şekilde sabitlenemiyor — zamanla derleme bozuluyor
Bazı dillerde (Node.js) resmi destek yalnızca deneysel seviyede
musl libc kaynaklı üretim sorunları bildiriliyor
---
2. Katman sırası ve önbellek
Değişmeyen şeyler üstte, sık değişenler altta:
```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y ...   # nadiren değişir

COPY requirements.txt .                         # ara sıra değişir
RUN pip install -r requirements.txt

COPY . .                                        # her commit'te değişir
```
Kodu değiştirdiğinizde paketlerin yeniden kurulmaması için.
`apt-get update` ve `install` aynı satırda olmalı:
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*
```
Ayrı satırlarda olursa: `install` satırı değiştiğinde yeniden çalışır ama
`update` önbellekten gelir. Sonuçta eski paket listesiyle kurulum yapılır.
İndirdiğinizi aynı satırda temizleyin:
```dockerfile
RUN wget paket.deb \
    && dpkg -i paket.deb \
    && rm paket.deb
```
Katmanlar geri alınamaz. Ayrı satırda silerseniz dosya önceki katmanda kalır ve
imaj boyutuna dahil olur — sadece "yok" diye işaretlenir.
---
3. Çok aşamalı yapı
Beş aşamalı kalıp:
```
base    → ortak taban, üretim bağımlılıkları, kod yok
dev     → base + geliştirme araçları
source  → base + kod
test    → source + dev bağımlılıkları, testler çalışır
final   → source'tan türer, sadece meta veri değişir, EN SONDA
```
Kritik: `final` aşaması `test`'ten değil `source`'tan türemeli.
Böylece ürettiğiniz üretim imajı, test ettiğiniz katmanların birebir aynısı olur.
Hiçbir şey "kaldırılmaz", sadece meta veri eklenir.
En sona yazın. Hedef belirtilmediğinde derleyici varsayılan olarak üretim
imajını üretsin.
Kullanım:
```bash
docker build --target dev .    # yerel geliştirme
docker build --target test .   # CI
docker build .                 # üretim
```
---
4. Güvenlik
Ayrıcalıksız kullanıcı:
```dockerfile
RUN useradd --create-home --uid 1001 appuser
WORKDIR /app
COPY --chown=appuser:appuser . .
USER appuser
```
Sabit UID verin — Kubernetes `runAsUser` ile eşleşmesi gerekiyor
`USER` satırı `apt-get` adımlarından sonra gelmeli, yoksa kurulum yetki
hatası verir
`COPY --chown` kullanın; ayrı bir `RUN chown` fazladan katman oluşturur
Sır gömmeyin. Şifre, token, sertifika, bağlantı dizesi imajda durmamalı.
Çalışma anında secret olarak gelmeli.
Test araçları üretim imajına girmesin. `curl`, test çerçeveleri, hata
ayıklama araçları yalnızca test aşamasında olmalı.
Bağımlılık sürümlerini sabitleyin. Minör sürüm değişikliği bile üretimi
bozabilir — yaygın bir hata kaynağı.
---
5. Çalışma zamanı
HEALTHCHECK ekleyin:
```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl --fail http://localhost:5000/health || exit 1
```
Kubernetes kendi probe'larını kullanır ama bu satır belge niteliği taşır ve
Docker, Compose, Swarm ortamlarında işe yarar.
Init süreci düşünün — `tini` veya `dumb-init`:
```dockerfile
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "app.py"]
```
Linux sinyallerini düzgün işler ve zombi süreçleri toplar. Health check
kullanıyorsanız özellikle önemli.
Süreç yöneticisi kullanmayın — `npm start`, `pm2`, `nodemon`, `forever`.
Sinyalleri dinlemiyorlar, gereksiz süreç ekliyorlar. Replika gerekiyorsa
orkestratör bunun için var.
`EXPOSE` yazın. Belge değeri var.
`CMD`'yi açıkça yazın — temel imajdan gelse bile. Dosyaya bakan kişi ne
çalıştığını görebilmeli.
---
6. Yardımcı dosyalar
`.dockerignore` — en az şunlar:
```
.git/
venv/
__pycache__/
node_modules/
.env
*.pyc
```
Build context'teki her şey paketlenip derleme motoruna gönderilir. Gereksizler
derlemeyi yavaşlatır ve imaja sızabilir.
`COPY` kullanın, `ADD` değil. `ADD` yalnızca internetten indirmek veya arşiv
açmak için. İndirdiğiniz dosya katmanda kalır, silinemez.
---
7. Doğrulama
```bash
trivy image imajiniz                      # bilinen açıklar
trivy fs --scanners misconfig .           # yapılandırma hataları
docker run --rm imajiniz whoami           # root olarak mı çalışıyor
docker history imajiniz                   # katman boyutları
dive imajiniz                             # katman içeriği görsel inceleme
```
---
Hızlı kontrol listesi
[ ] Temel imaj sürümü sabit, `latest` yok
[ ] `slim` veya eşdeğer minimal varyant
[ ] `apt-get update` ve `install` aynı satırda, sonunda temizlik
[ ] Katman sırası önbelleği koruyacak şekilde
[ ] İndirilen dosyalar aynı satırda silinmiş
[ ] Çok aşamalı yapı, `final` aşaması `source`'tan türüyor
[ ] Ayrıcalıksız kullanıcı, sabit UID
[ ] `COPY --chown` kullanılmış
[ ] İmajda sır yok
[ ] Test araçları üretim imajında yok
[ ] Bağımlılık sürümleri sabit
[ ] HEALTHCHECK tanımlı
[ ] `EXPOSE` ve `CMD` açıkça yazılı
[ ] `.dockerignore` mevcut
[ ] Trivy taramasından geçiyor
---
Örnek
```dockerfile
FROM python:3.12-slim AS base

RUN useradd --create-home --uid 1001 appuser

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser . .

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

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

CMD ["python", "app.py"]
```
