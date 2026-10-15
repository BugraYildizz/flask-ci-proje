Zero Trust Erişim — Tailscale
Uygulama hiçbir port yayınlamadan çalışır. Erişim yalnızca Tailscale ağı üzerinden, kimliği doğrulanmış cihazlarla mümkündür.
---
Problem
Bir servisi dışarı açmanın geleneksel yolu şudur:
```bash
docker run -p 5000:5000 flask-app
```
Bu komutla birlikte:
Host'ta 5000 portu açılır
Güvenlik duvarında delik açmak gerekir
İnternetteki herkes o porta bağlanabilir
Kimlik doğrulama tamamen uygulamanın sorumluluğuna kalır
Port tarayan botlar hedefi bulur
Uygulamada bir açık varsa, saldırgan doğrudan ona ulaşır.
---
Yaklaşım
Tünel ajanı uygulamanın yanında, aynı izole ağda çalışır. Ajan dışarıya doğru bir bağlantı kurar ve hiçbir gelen bağlantı kabul etmez.
```
İnternet ──X──  (açık port yok)

Tailscale ağı ──→ tünel ajanı ──→ flask-app:5000
                  (flask-net ağı içinde)
```
Sonuç: erişim vardır, ama internette görünür bir yüzey yoktur.
---
Kurulum
1. Auth key alın
Tailscale admin panelinde: Settings → Keys → Generate auth key
Ayar	Değer	Gerekçe
Reusable	kapalı	Tek kullanımlık yeterli
Ephemeral	açık	Konteyner silinince cihaz kaydı da silinsin
Anahtar `tskey-auth-...` biçimindedir.
2. İzole ağ ve uygulama
```bash
docker network create flask-net

docker build -t flask-app .

docker run -d --name flask-app --network flask-net flask-app
```
`-p` bayrağı yoktur. Uygulama kasıtlı olarak dışarıdan erişilemez.
3. Tünel ajanı
```bash
docker run -d --name tailscale \
  --network flask-net \
  --cap-add NET_ADMIN \
  --device /dev/net/tun \
  -e TS_AUTHKEY=<auth-key> \
  -e TS_STATE_DIR=/var/lib/tailscale \
  -v tailscale-state:/var/lib/tailscale \
  tailscale/tailscale
```
Gerekli izinler:
`--cap-add NET_ADMIN` — sanal ağ arayüzü oluşturmak için
`--device /dev/net/tun` — TUN cihazına erişim için
Volume, cihaz kimliğinin konteyner yeniden başlatıldığında korunmasını sağlar.
4. Uygulamayı tünelden yayınlayın
```bash
docker exec tailscale tailscale serve --bg http://flask-app:5000
```
`flask-app` konteyner adıdır, Docker DNS ile çözülür. Aynı ağda oldukları için ajan uygulamaya ulaşabilir.
Çıktı:
```
Available within your tailnet:
https://<makine-adi>.<tailnet>.ts.net/
|-- proxy http://flask-app:5000
```
HTTPS sertifikasını Tailscale üretir, ek yapılandırma gerekmez.
Not: `serve` özelliği hesapta varsayılan olarak kapalı gelebilir. Komut, etkinleştirme bağlantısını çıktıda verir.
5. İstemci cihazı ağa ekleyin
Erişecek her cihaz Tailscale ağında olmalıdır.
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
Masaüstü ve mobil istemciler `tailscale.com/download` adresindedir.
---
Doğrulama
```bash
# Host üzerinden — başarısız olmalı
curl localhost:5000
# curl: (7) Failed to connect to localhost port 5000

# Tailscale ağından — çalışmalı
curl https://<makine-adi>.<tailnet>.ts.net/
# {"message":"Merhaba Docker CI"}
```
Dışarıdan erişim testi
Ağa dahil olmayan bir cihazdan adresi açmayı deneyin (örneğin mobil veri üzerinden telefon).
Sayfa açılmaz. Kimlik doğrulama ekranı bile görünmez — çünkü bağlanılacak bir sunucu yoktur. Paket hiçbir yere ulaşmaz.
Bu, geleneksel yöntemden en belirgin farktır: orada en azından bir giriş ekranı görünür, yani hedef keşfedilebilir.
---
Zero trust ilkesi
"İç ağdan geliyorsa güvenilir" varsayımı reddedilir.
Erişimi belirleyen şey konum değil, kimliktir. Cihaz Tailscale'e kayıtlı ve doğrulanmış olduğu için erişir; aynı ağda bulunduğu için değil.
Pratik sonucu: şirket ağına sızan biri otomatik olarak servise erişemez. Cihazının kayıtlı olması gerekir.
---
Ne zaman uygun
Uygun: Yönetim panelleri, iç araçlar, veritabanı erişimi, geliştirme ve test ortamları — yani sınırlı sayıda kişinin eriştiği servisler.
Uygun değil: Herkese açık web siteleri ve API'ler. Her ziyaretçinin ağa katılması beklenemez. O senaryoda ters proxy, TLS ve uygulama seviyesinde kimlik doğrulama kullanılır.
---
Alternatif: Cloudflare Tunnel
Benzer mimari, farklı kullanım senaryosu.
	Tailscale	Cloudflare Tunnel
Erişim modeli	Özel ağ — sadece ağ üyeleri	Genel internet + kimlik doğrulama kapısı
Alan adı	Gerekmez	Gerekir
Kimlik doğrulama	Cihaz kaydı	SSO, MFA, cihaz uyumluluğu
Uygun olduğu yer	İç araçlar	Dış kullanıcıya açılacak servisler
Cloudflare'da ziyaretçi adrese ulaşabilir ama kimlik doğrulama ekranıyla karşılaşır. Tailscale'de adres ağ dışından hiç erişilebilir değildir.
---
Yapılmadı
ACL tanımlanmadı. Erişim şu an hesaptaki tüm cihazlara açıktır. Ekip kullanımında admin panelindeki Access Controls bölümünden daraltılmalıdır:
```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:dev"],
      "dst": ["tag:container:*"]
    }
  ]
}
```
Cihaz onayı kapalı. Admin panelinden "Device approval" açılarak, yeni cihazların ağa katılması yönetici onayına bağlanabilir.
Key expiry varsayılan. Üretimde anahtar ömürleri kısaltılmalı ve rotasyon planlanmalıdır.
