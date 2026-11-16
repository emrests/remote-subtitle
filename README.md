# remote-subtitle
PS5 altyazılarını yerelde Türkçeye çevirip TV'de gösterir. Görüntü PC'ye Remote Play (chiaki-ng) penceresinden gelir.

```
pip install -r requirements.txt
ollama pull translategemma:12b
python server.py --region x,y,genişlik,yükseklik   # altyazı bölgesi
```
Gösterim: `display/index.html?host=PC_IP` (işte Chrome'da, evde TV'de). Arkaya video için `&bg=video.mp4`.
