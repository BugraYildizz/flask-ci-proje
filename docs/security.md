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
