# remote-subtitle — Samsung TV uygulaması

TV, PS5'in bağlı olduğu HDMI girişini tam ekran gösterir ve üstüne bilgisayardaki çeviri katmanını koyar.
Çeviri kutusunu bilgisayar çizer (PC'deki katmanla aynı görünüm); TV yalnız yerleştirir. Uygulama mantığı
bilgisayarda olduğu için PC tarafı güncellendiğinde TV uygulamasını yeniden kurmak gerekmez.

## Bir kerelik hazırlık (evde)

1. **Tizen Studio + TV Extension** (bilgisayara):
   <https://developer.samsung.com/smarttv/develop/getting-started/setting-up-sdk/installing-tv-sdk.html>
   - Package Manager'da: *Tizen SDK tools*, *Extension SDK → TV Extensions* ve *Samsung Certificate Extension*.
2. **Samsung sertifikası**: Tizen Studio → Tools → Certificate Manager → yeni profil, **Samsung** türü, TV.
   (Samsung hesabıyla giriş ister; sertifikaya TV'nin DUID'i eklenir — TV bağlıyken Device Manager'dan alınır.)
3. **TV'de Developer Mode**:
   - TV'de *Apps* ekranını açın, kumandada sırayla **1 2 3 4 5** tuşlayın.
   - *Developer mode* **On**, *Host PC IP* = bu bilgisayarın adresi (panelde Bağlantı bölümünde yazar).
   - TV'yi kapatıp açın.
4. **TV'yi bağlayın**: Tizen Studio → Device Manager → *Remote Device Manager* → TV'nin IP'si → bağlan.

## Paketleme ve kurulum

Tizen Studio'da: *File → Import → Tizen → Tizen Project* ile bu `tizen/` klasörünü açın, projeye sağ tık →
*Run As → Tizen Web Application*. Ya da komut satırından (Tizen Studio `tools/ide/bin` PATH'te):

```
tizen package -t wgt -s <sertifika-profil-adı> -- tizen
tizen install -n tizen/remote-subtitle.wgt -t <TV-cihaz-adı>
```

## İlk açılış

- Bilgisayarın adresini ve PS5'in bağlı olduğu HDMI numarasını girin, **OK**.
- **Kırmızı tuş**: ayar ekranı. **Geri**: çıkış.
- Bilgisayarda remote-subtitle açık ve **Çeviriyi başlat** basılı olmalı; chiaki-ng PS5 görüntüsünü göstermeli.

## Evde kontrol edilecekler

- HDMI penceresinde (TVWindow) **gecikme**: oyun modu/120 Hz/VRR korunuyor mu? Korunmuyorsa kumandayla
  oynarken tepki gecikir; o zaman HDMI'ı doğrudan izleyip altyazıyı yalnız bu uygulamada göstermek gibi
  alternatifleri konuşalım.
- Kutunun yeri: chiaki-ng tam ekranda değilse siyah şeritler hesaba katılır, ama bölge chiaki penceresinde
  çizilmelidir.
- Bilgisayar ile TV aynı ağda olmalı; Windows güvenlik duvarı 8765'e izin vermeli (kurulum sihirbazı ekler).

## Tarayıcıda önizleme

`tizen/index.html` dosyasını Chrome'da açın: TV API'leri olmadığı için HDMI atlanır; ayar ekranı ve çeviri
katmanı denenebilir.
