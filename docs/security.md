Güvenlik Önlemleri
Bu belge, projede uygulanan güvenlik önlemlerini ve gerekçelerini açıklar.
---
1. Güvenlik açığı taraması
İmajlar Trivy ile taranır. CI'da iki ayrı tarama çalışır:
Raporlayan tarama (`exit-code: 0`)
Tüm açıkları seviye ayrımı yapmadan tabloya basar. Görünürlük sağlar, derlemeyi engellemez.
Engelleyici tarama (`exit-code: 1`)
Aşağıdaki filtrelerle çalışır ve bir bulgu varsa imajın yayınlanmasını durdurur:
Ayar	Değer	Gerekçe
`severity`	`HIGH,CRITICAL`	Düşük önemdeki bulgular gürültü yaratıyor
`ignore-unfixed`	`true`	Düzeltmesi olmayan açık için yapılabilecek bir şey yok
`vuln-type`	`os`	Python bağımlılıkları ayrı izleniyor (bkz. bilinen sınırlar)
Öğrenilen: temel imaj sürümü belirleyici
İlk kurulumda `nginx:1.20-alpine` kullanılıyordu ve tarama 58 açık buluyordu (5'i CRITICAL). Alpine 3.14 desteği bittiği için güvenlik yaması almıyordu.
Temel imaj güncellenince işletim sistemi kaynaklı açıklar sıfıra indi.
Çıkarım: açıkların büyük kısmı uygulama kodundan değil, eskimiş temel imajdan gelir.
Öğrenilen: az bulgu güvenli olmak değildir
Eski Alpine sürümünde Trivy "bu OS artık desteklenmiyor, tespit yetersiz olabilir" uyarısı veriyordu. Yani tarayıcı tam çalışamıyordu.
Güncel sürüme geçince daha fazla bulgu çıktı — çünkü tarama artık eksiksizdi.
---
2. Tarama raporlaması
Sonuçlar SARIF formatında üretilip GitHub Security → Code scanning sekmesine yüklenir.
Günlükteki tablo çalıştırma bitince kaybolur; SARIF kayıtları kalıcıdır, filtrelenebilir ve açık kapandığında otomatik işaretlenir.
```yaml
- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  if: always()
```
`if: always()` kritik: engelleyici tarama başarısız olduğunda bile rapor yüklenir. Aksi halde raporun en çok gerektiği durumda rapor oluşmazdı.
Bilinen tuzak: SARIF ve severity filtresi
`format: sarif` kullanıldığında trivy-action `severity` filtresini yok sayar ve tüm seviyeleri rapora dahil eder. Günlükte şu satır görünür:
```
Building SARIF report with all severities
```
`exit-code: 1` ile birleştiğinde LOW/MEDIUM bulgular da derlemeyi durdurur.
Çözüm: iki adıma bölmek.
```yaml
- name: Trivy blocking scan      # format: table, exit-code: 1 → engeller
- name: Trivy SARIF report       # format: sarif, exit-code: 0 → engellemez
```
---
3. İmaj sertleştirme
Ayrıcalıksız kullanıcı
Konteyner varsayılan olarak root ile çalışır. Dockerfile'da ayrıcalıksız bir kullanıcı tanımlanmıştır:
```dockerfile
RUN useradd --create-home --uid 1001 appuser
...
RUN chown -R appuser:appuser /app
USER appuser
```
Sabit UID verilmesinin sebebi: Kubernetes `runAsUser` ayarıyla eşleşmesi gerekiyor.
`USER` satırı `apt-get` adımlarından sonra gelir, aksi halde paket kurulumu yetki hatası verir.
Uygulama 5000 portunu kullandığı için ayrıcalıksız kullanıcı sorun çıkarmaz. 1024 altı portlar `net_bind_service` yeteneği gerektirirdi.
Çok aşamalı derleme
```
base   → ortak taban (Python, bağımlılıklar, kod)
test   → base + curl + pytest
final  → base (test araçları yok)
```
`curl` yalnızca test aşamasındadır. Üretim imajı yalın kalır, saldırı yüzeyi küçülür.
Sürüm sabitleme
Temel imaj: `python:3.12-slim` (etiket sabit, `latest` kullanılmaz)
Bağımlılıklar: `requirements.txt` içinde sürümleriyle sabitlenmiş
---
4. Kubernetes securityContext
Deployment manifestinde iki seviyede kısıt tanımlıdır.
Pod seviyesi
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1001
```
`runAsNonRoot: true` bir kapı görevi görür: imaj root olarak çalışmaya kalkarsa Kubernetes pod'u başlatmaz.
Pratik sonucu: Dockerfile'dan `USER` satırı silinirse smoke test başarısız olur ve imaj yayınlanmaz. Güvenlik ayarı CI tarafından zorlanır, yalnızca bir niyet olarak kalmaz.
Konteyner seviyesi
```yaml
securityContext:
  allowPrivilegeEscalation: false
  capabilities:
    drop: ["ALL"]
  readOnlyRootFilesystem: true
```
Ayar	Etkisi
`allowPrivilegeEscalation: false`	Süreç çalışırken kendine yetki ekleyemez
`capabilities: drop: ALL`	Docker'ın bıraktığı varsayılan yetenekler de alınır
`readOnlyRootFilesystem: true`	Saldırgan içeri girse dosya yazamaz, araç indiremez
Uygulama çalışma anında dosya yazmadığı için salt okunur dosya sistemi sorun çıkarmaz.
---
5. RBAC denetimi
Yapılan denetim
Secret kaynağına erişimi olan ClusterRole'lar listelendi:
```bash
kubectl get clusterroles -o json | jq -r '.items[] | .metadata.name as $n | .rules[]? | select(.resources[]? == "secrets") | "\($n): \(.verbs)"'
```
Bulgu: `traefik-ingress` rolünün `get`, `list`, `watch` yetkisi var. Bu meşru — TLS sertifikaları Kubernetes'te secret olarak saklanır, ingress controller'ın okuması gerekir. Yazma yetkisi yoktur.
Rolün kime bağlandığı doğrulandı:
```bash
kubectl get clusterrolebindings -o wide | grep -i traefik
# → ingress/traefik
```
Tek bir servis hesabına bağlı, geniş bir gruba değil.
Bulunan sorun: RBAC kapalıydı
Varsayılan servis hesabının yetkisi sorgulandığında tam erişim göründü:
```bash
kubectl auth can-i --list --as=system:serviceaccount:default:default
# Resources   Verbs
# *.*         [*]
```
Hiçbir ClusterRoleBinding bunu açıklamıyordu. Sebep: MicroK8s'te RBAC eklentisi varsayılan olarak kapalı geliyor.
Bu, `default` namespace'inde çalışan her pod'un kümedeki tüm secret'lara erişebilmesi demekti.
Düzeltme
```bash
microk8s enable rbac
```
Doğrulama:
```bash
kubectl auth can-i get secrets --as=system:serviceaccount:default:default
# → no
```
Traefik'in meşru erişimi korundu.
---

---

## 6. Ağ erişimi

Uygulama hiçbir port yayınlamadan çalışır. Erişim yalnızca zero trust tüneli
üzerinden, kimliği doğrulanmış cihazlarla mümkündür.

Kurulum, doğrulama ve gerekçeler: [tailscale.md](tailscale.md)


---

## 7. Host yapılandırma denetimi (Docker Bench)

[Docker Bench](https://github.com/docker/docker-bench-security) ile CIS Docker
Benchmark'a göre yaklaşık 86 kontrol çalıştırıldı.

```bash
sudo bash docker-bench-security.sh
```

### Geçen kontroller

Dosya izinleri (Bölüm 3) neredeyse tamamen geçti. Docker soketi, servis
dosyaları ve dizin sahiplikleri standart kurulumla doğru ayarlanmış.

`2.7` — Daemon TCP üzerinden dinlemiyor, yalnızca Unix soketi kullanılıyor.
Uzak erişim SSH context ile yapılıyor.

`4.9` — Dockerfile'da `ADD` yerine `COPY` kullanılıyor.

### Düzeltilen bulgular

**`4.6` HEALTHCHECK eksikti.** Uygulamanın `/health` endpoint'i vardı ama
Dockerfile'da tanımlı değildi. Eklendi:

```dockerfile
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1
```

`curl` yerine Python'un standart kütüphanesi kullanıldı — üretim imajında
`curl` bulunmuyor.

**`5.1` Swarm modu açıktı** ama kullanılmıyordu. Kapatıldı:

```bash
docker swarm leave --force
```

### Kabul edilen bulgular

**Denetim kayıtları (1.1.3 – 1.1.18).** `auditd` ile Docker dosyalarının
izlenmesi isteniyor. Kurumsal uyumluluk gerekliliği; geliştirme ortamında
uygulanmadı.

**`2.9` user namespace kapalı.** Konteynerdeki root'u host'ta ayrıcalıksız bir
kullanıcıya eşler. Docker'da varsayılan olarak kapalı; açmak uyumluluk
sorunları çıkarabiliyor.

**`4.5` content trust kapalı.** İmaj imzalama henüz uygulanmadı.

### Puanlama hakkında

Araç `PASS` sayısından `WARN` sayısını çıkararak puan veriyor. Sıfır veya
negatif puan beklenen bir sonuç — CIS benchmark kurumsal üretim ortamları
için yazılmış. Amaç puanı yükseltmek değil, her maddeyi gözden geçirip bilinçli
bir karar vermek.


---

## 8. Yapılandırma taraması (Trivy misconfig)

Dockerfile ve Kubernetes manifesti ayrıca yapılandırma hatalarına karşı tarandı:

```bash
trivy fs --scanners misconfig .
```

**Dockerfile:** 0 bulgu.

**deployment.yaml:** 10 bulgu → düzeltme sonrası 4.

### Düzeltilenler

**Kaynak sınırları yoktu** (KSV-0011, 0015, 0016, 0018). Cgroup seviyesinde
hizmet reddi koruması sağlıyor — bellek sızıntısı olan bir konteyner node'u
çökertemiyor.

```yaml
resources:
  requests:
    memory: "128Mi"
    cpu: "100m"
  limits:
    memory: "256Mi"
    cpu: "500m"
```

**Seccomp profili belirtilmemişti** (KSV-0030, KSV-0104). Docker varsayılan
olarak uyguluyor ama Kubernetes'te açıkça bildirmek gerekiyor.

```yaml
securityContext:
  seccompProfile:
    type: RuntimeDefault
```

### Kabul edilen bulgular

**KSV-0013** — yanlış pozitif. Tarayıcı `${TESTING_IMAGE}` değişkenini
çözemediği için etiket eksik sanıyor; CI'da `run_id` ile sabit etiket veriliyor.

**KSV-0020 / KSV-0021** — UID ve GID'nin 10000 üstü olması öneriliyor
(host kullanıcı tablosuyla çakışmaması için). Mevcut UID 1001 kullanılıyor.

**KSV-0110** — ayrı namespace önerisi. Smoke test kümesi geçici olduğu için
`default` namespace yeterli.

## 9. İmaj imzalama (Cosign)

İmajlar CI'da imzalanıyor, Kubernetes'e dağıtılmadan önce doğrulanıyor.

**Neden:** Trivy imajda açık var mı diye bakıyor, ama imajın gerçekten bizim
ürettiğimiz imaj olduğunu söylemiyor. Registry'ye sızan biri imajı
değiştirebilir. İmza bunu yakalıyor — digest değişince doğrulama başarısız
oluyor ve dağıtım duruyor.

Keyless mod kullanıldı, saklanacak anahtar yok. Doğrulama hem kimin hem
nereden imzaladığını kontrol ediyor.

---

## 10. Çalışma zamanı izleme (Falco)

Test ortamında denendi, kalıcı kurulum yapılmadı.

**Neden:** Diğer araçlar imajı dağıtımdan önce denetliyor. Falco çalışırken ne
olduğunu izliyor — konteynere kabuk açılması, hassas dosya okunması gibi
şüpheli davranışları kaydediyor.

Engellemiyor, kaydediyor. Değeri bir olay yaşandığında geriye dönüp izleri
takip edebilmekte.


Bilinen sınırlar
Python bağımlılıkları taranmıyor. `vuln-type: 'os'` ayarı nedeniyle engelleyici tarama yalnızca işletim sistemi paketlerine bakar.
Gerekçe: bulunan Python açıklarının tamamı `pip`, `setuptools`, `urllib3` gibi paket kurma araçlarından geliyordu. Bunlar `requirements.txt` değiştirilerek düzeltilemiyor (pip kendi gömülü kopyasını taşıyor) ve uygulama çalışırken kullanılmıyorlar.
Raporlayan tarama bunları hâlâ listeler, yalnızca engelleme kapsamı dışındadırlar.
Yapılması gereken: Dependabot etkinleştirilerek Python bağımlılıkları ayrıca izlenmeli.
Dal koruması yok. `main` dalına doğrudan push yapılabiliyor. Ekip çalışmasına geçildiğinde ruleset tanımlanmalı.
İmaj imzalama yok. Sigstore/cosign ile imaj imzalama ve doğrulama eklenebilir.
---
Denetim yöntemi
RBAC denetiminde izlenen sıra, benzer incelemelerde tekrarlanabilir:
Kim yetkili? — Hangi roller ilgili kaynağa erişiyor
Yetki kime bağlı? — Roller hangi kullanıcı/servis hesabına atanmış
Doğrula — `kubectl auth can-i` ile fiilen test et
---


Çıkarımlar
Varsayılanlar güvenli olmak zorunda değildir. MicroK8s kolay kurulum için RBAC'ı kapalı getiriyordu.
Her bulgu eyleme dönüştürülebilir değildir. `ignore-unfixed` filtresi olmadan 166 uyarı arasında gerçek sorunlar kaybolurdu.
İstisnalar gerekçelendirilmelidir. `.trivyignore` dosyasındaki her satırın yanında neden görmezden gelindiği yazılıdır.
Araçlar beklendiği gibi davranmayabilir. SARIF formatının severity filtresini yok sayması belgelerde öne çıkan bir bilgi değildi; günlükler okunarak teşhis edildi.
