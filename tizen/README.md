# Remote Subtitle (TR) — Samsung TV uygulaması

TV, PS5'in bağlı olduğu HDMI girişini tam ekran gösterir ve üstüne bilgisayardaki çeviri katmanını koyar.
Çeviri kutusunu bilgisayar çizer (konum ve görünüm masaüstü uygulamasındaki oyun profilinden); TV yalnız yerleştirir.
Uygulama mantığı bilgisayarda olduğu için PC tarafı güncellendiğinde TV uygulamasını yeniden kurmak gerekmez.

## Kurulum (masaüstü uygulamasından, Tizen Studio gerekmez)

Masaüstü uygulamasında **Kurulum** sekmesi → **Samsung TV uygulaması**:

1. **TV'de Geliştirici Modu**: TV'de *Uygulamalar* ekranında kumandayla **1 2 3 4 5** → *Developer mode* **On**,
   *Host PC IP* = sekmede yazan bilgisayar adresi → TV'yi kapatıp açın (güç tuşuna basılı tutun).
2. **TV'leri ara**: geliştirici modundaki TV'ler (sdb portu 26101) bulunur; model ve TV kimliği (DUID) okunur.
3. **Samsung ile giriş yap ve sertifika oluştur**: tarayıcıda kendi Samsung hesabınızla giriş yapın. Uygulama
   yazar ve dağıtıcı sertifikasını Samsung'un sertifika sunucusundan alır; bulunan TV'lerin kimlikleri sertifikaya
   eklenir. Yeni TV eklendiğinde aynı düğmeyle sertifika yenilenir (yazar sertifikası aynı kalır).
   Özel anahtarlar `%APPDATA%\remote-subtitle\tv-cert` içinde Windows DPAPI ile şifreli saklanır.
4. **Kur**: uygulama imzalanır (bilgisayarın adresi pakete yazılır), TV'ye kurulum izni verilir, kurulur ve açılır.

Yedek yol: Tizen Studio Certificate Manager ile oluşturulmuş bir Samsung sertifika profili
**Tizen Studio sertifikasını içe aktar** ile alınabilir (`%USERPROFILE%\SamsungCertificate\<profil>`).

## Kullanım

- TV'de *Uygulamalar* → **Remote Subtitle (TR)**. PC'de **Çeviriyi başlat** basılı olmalı.
- **Geri** tuşu uygulamadan çıkar (arka planda çalışmaz). **Kırmızı tuş**: PC adresi ve HDMI numarası ayarı.

## Teknik notlar

- Samsung sertifika arayüzü belgelenmemiştir; Tizen Studio'nun Samsung Certificate Extension'ının yaptığı istekler
  taklit edilir (`rsub/tizen_cert.py`). İmza biçimi: W3C widget dijital imzası (`rsub/tizen_sign.py`).
- TV komutları (`rsub/tizen_device.py`): kurulum izni = `device-profile.xml` → `/home/developer`; kurulum =
  `0 appinstall <paket> <yol>` (eski TV: `0 vd_appinstall`); başlatma = `0 execute <uygulama>`.
- Tarayıcıda önizleme: `tizen/index.html` dosyasını açın (TV API'leri olmadığı için HDMI atlanır).
