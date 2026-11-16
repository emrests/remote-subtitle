// Altyazı çizimi: panel önizlemesi ve TV/ikinci ekran gösterimi aynı kodu kullanır.
// Eski TV tarayıcıları için sade JS (modül/optional chaining yok).

function hexToRgba(hex, alpha) {
  var h = (hex || "#000000").replace("#", "");
  if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
  var n = parseInt(h, 16);
  return "rgba(" + ((n >> 16) & 255) + "," + ((n >> 8) & 255) + "," + (n & 255) + "," + alpha + ")";
}

function applySubtitleStyle(container, style) {
  var s = container.style;
  s.setProperty("--sub-font", '"' + style.font + '", "Segoe UI", sans-serif');
  s.setProperty("--sub-size", style.size + "px");
  s.setProperty("--sub-color", style.color);
  s.setProperty("--sub-bg", hexToRgba(style.bg, style.bgOpacity));
  s.setProperty("--sub-name", style.nameColor);
  container.classList.toggle("sub-top", style.position === "top");
  container.classList.toggle("sub-bottom", style.position !== "top");
  s.setProperty("--sub-offset", style.offset + "px");
}

function renderSubtitle(container, lines, style) {
  if (style) applySubtitleStyle(container, style);
  container.textContent = "";
  (lines || []).forEach(function (line) {
    if (!line.tr) return;
    var div = document.createElement("div");
    div.className = "sub-line";
    if (line.speaker) {
      var name = document.createElement("span");
      name.className = "sub-name";
      name.textContent = line.speaker + ": ";
      if (line.color) name.style.color = line.color;
      div.appendChild(name);
    }
    div.appendChild(document.createTextNode(line.tr)); // textContent: OCR metni HTML olarak yorumlanmaz
    container.appendChild(div);
  });
}

function connectSubtitles(url, onMsg, onState) {
  function open() {
    var ws = new WebSocket(url);
    ws.onopen = function () { if (onState) onState(true, ws); };
    ws.onmessage = function (e) { onMsg(JSON.parse(e.data), ws); };
    ws.onclose = function () {
      if (onState) onState(false, ws);
      setTimeout(open, 2000);
    };
  }
  open();
}
