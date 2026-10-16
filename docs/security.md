Güvenlik Önlemleri
Projede alınan önlemler, gerekçeleri ve dikkat edilecek noktalar.
---
1. Açık taraması (Trivy)
Ne: İmajlar CI'da iki kez taranıyor. Biri her şeyi raporluyor, diğeri ciddi
bulgularda yayını durduruyor.
Neden: Bilinen açık taşıyan bir imaj yayınlanmasın.
Filtreler: `HIGH,CRITICAL` + `ignore-unfixed`. Düzeltmesi olmayan açık için
yapılacak bir şey yok; her bulguda durursanız hiçbir şey yayınlayamazsınız.
Dikkat: Açıkların çoğu kodunuzdan değil, eski temel imajdan gelir. Eski
`nginx:1.20-alpine` 58 açık veriyordu, sürüm güncellenince sıfıra indi.
Dikkat: Az bulgu güvenli olmak değildir. Eski Alpine'da tarayıcı tam
çalışamıyordu ("bu OS desteklenmiyor" uyarısı veriyordu). Güncelleyince daha
fazla bulgu çıktı — çünkü tarama artık eksiksizdi.
---
2. Rapor (SARIF → GitHub Security)
Ne: Tarama sonuçları Security sekmesine yükleniyor.
Neden: Günlükteki tablo çalıştırma bitince kaybolur. SARIF kayıtları kalıcı,
filtrelenebilir, açık kapandığında işaretlenir.
Dikkat: `format: sarif` kullanıldığında `severity` filtresi yok sayılıyor.
`exit-code: 1` ile birleşince LOW bulgular da derlemeyi durduruyor. Çözüm:
engelleyici tarama ve rapor ayrı adımlar olmalı.
Dikkat: Rapor adımında `if: always()` şart. Yoksa tarama patladığında —
yani rapora en çok ihtiyaç duyulduğunda — rapor oluşmuyor.
---
3. İmaj sertleştirme
Ne: Dockerfile'da ayrıcalıksız kullanıcı (`appuser`, UID 1001) oluşturulup
`USER` ile geçildi. Çok aşamalı yapı kullanıldı: test araçları üretim imajına
girmiyor.
Neden: Uygulamanıza sızan biri root'sa konteyner içinde her şeyi yapabilir.
Ayrıcalıksız kullanıcıyla çok daha kısıtlı kalır. Konteynerden kaçma ihtimali
de azalır.
Dikkat: `USER` satırı `apt-get` adımlarından sonra gelmeli, yoksa paket
kurulumu yetki hatası verir.
Dikkat: Dosya sahipliğini `chown` ile devretmek gerekiyor. Uygulama diske
yazıyorsa izinler doğru değilse çalışmaz.
---
4. Kubernetes securityContext
Ne: Pod seviyesinde `runAsNonRoot`, `runAsUser: 1001`, `seccompProfile`.
Konteyner seviyesinde `allowPrivilegeEscalation: false`,
`capabilities: drop: ALL`, `readOnlyRootFilesystem`, kaynak sınırları.
Neden: Dockerfile'daki ayarları Kubernetes tarafında da zorlamak. Kaynak
sınırları ayrıca hizmet reddi koruması sağlıyor — bir konteyner node'u
çökertemiyor.
Dikkat: `runAsNonRoot: true` bir kapı. Dockerfile'dan `USER` satırı
silinirse pod başlamıyor, smoke test patlıyor, imaj yayınlanmıyor. Güvenlik
ayarı niyet olarak kalmıyor, CI tarafından zorlanıyor.
---
5. RBAC denetimi
Ne: Secret'lara kimin eriştiği sorgulandı. Traefik'in erişimi meşru çıktı
(TLS sertifikaları secret olarak saklanıyor), dar kapsamda bağlıydı.
Bulunan sorun: Varsayılan servis hesabı her şeye erişebiliyordu. Sebep:
MicroK8s'te RBAC eklentisi kapalı geliyordu. Açıldı ve doğrulandı.
Yöntem: Kim yetkili → yetki kime bağlı → `kubectl auth can-i` ile test et.
---
6. Ağ erişimi (Tailscale)
Ne: Uygulama hiçbir port yayınlamadan çalışıyor. Erişim zero trust tüneli
üzerinden, yalnızca kimliği doğrulanmış cihazlardan.
Neden: Açık port yoksa port tarayan botlar hedefi bulamaz.
Ayrıntı: tailscale.md
---
7. Host denetimi (Docker Bench)
Ne: CIS Docker Benchmark'a göre yaklaşık 86 kontrol çalıştırıldı.
Düzeltilenler: HEALTHCHECK eksikti, eklendi. Kullanılmayan Swarm modu
kapatıldı.
Kabul edilenler: Denetim kayıtları (auditd) ve user namespace. İkisi de
kurumsal gereklilik; geliştirme ortamında uygulanmadı.
Dikkat: Puan sıfır veya negatif çıkabilir, normal. CIS benchmark kurumsal
üretim için yazılmış. Amaç puan yükseltmek değil, her maddeyi gözden geçirmek.
---
8. Yapılandırma taraması (Trivy misconfig)
Ne: Dockerfile ve Kubernetes manifesti yapılandırma hatalarına karşı
tarandı. Dockerfile temiz çıktı, manifestte 10 bulgu vardı.
Düzeltilenler: Kaynak sınırları ve seccomp profili eklendi. 10 bulgu 4'e
indi.
Kabul edilenler: UID'nin 10000 üstü olması önerisi, ayrı namespace
önerisi, ve bir yanlış pozitif — tarayıcı `${TESTING\_IMAGE}` değişkenini
çözemediği için etiket eksik sanıyor.
---
9. İmaj imzalama (Cosign)
Ne: İmajlar CI'da imzalanıyor, Kubernetes'e dağıtılmadan önce doğrulanıyor.
Neden: Trivy "açık var mı" diye bakıyor, "bu gerçekten bizim imajımız mı"
sorusunu cevaplamıyor. Registry'ye sızan biri imajı değiştirebilir.
İmza digest'e bağlı — digest değişirse doğrulama başarısız olur, dağıtım durur.
Keyless mod kullanıldı, saklanacak anahtar yok.
---
10. Çalışma zamanı izleme (Falco)
Ne: Test ortamında denendi, kalıcı kurulum yapılmadı.
Neden: Diğer araçlar imajı dağıtımdan önce denetliyor. Falco çalışırken ne
olduğunu izliyor — konteynere kabuk açılması, hassas dosya okunması gibi.
Engellemiyor, kaydediyor. Değeri bir olay yaşandığında geriye dönüp izleri
takip edebilmekte.
---
Bilinen sınırlar
Python bağımlılıkları engelleyici taramada yok. `vuln-type: 'os'` ayarı
nedeniyle. Bulunan Python açıklarının tamamı `pip`, `setuptools` gibi paket
kurma araçlarından geliyordu — `requirements.txt` değiştirilerek düzeltilemiyor
ve uygulama çalışırken kullanılmıyorlar.
Bu boşluk Dependabot ile kapatıldı; `requirements.txt` ayrıca izleniyor.
Dal koruması yok. `main` dalına doğrudan push yapılabiliyor. Ekip
çalışmasına geçildiğinde tanımlanmalı.
---
Çıkarımlar
Varsayılanlar güvenli olmak zorunda değil. MicroK8s kolaylık için RBAC'ı
kapalı getiriyordu.
Her bulgu eyleme dönüştürülebilir değil. Filtreler olmadan 166 uyarı
arasında gerçek sorunlar kaybolurdu.
İstisnalar gerekçelendirilmeli. `.trivyignore` dosyasında her satırın
yanında neden görmezden gelindiği yazıyor.
Araçlar beklendiği gibi davranmayabilir. SARIF'in severity filtresini yok
sayması belgelerde öne çıkan bir bilgi değildi; günlükler okunarak teşhis
edildi.
