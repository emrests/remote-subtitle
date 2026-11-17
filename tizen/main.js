// remote-subtitle TV kabuğu. Eski Tizen tarayıcıları için ES5.
// İş bölümü: TV yalnız HDMI görüntüsünü gösterir ve PC'deki gösterim sayfasını saydam katman olarak açar.
// Bütün çeviri/çizim mantığı PC'de; uygulama güncellense de TV tarafını yeniden kurmak gerekmez.
(function () {
  var PORT = 8765;
  var KEY_BACK = 10009, KEY_ENTER = 13, KEY_RED = 403;
  var hasTizen = typeof tizen !== "undefined";
  var overlay = document.getElementById("overlay");
  var setup = document.getElementById("setup");
  var pcInput = document.getElementById("pc");
  var hdmiInput = document.getElementById("hdmi");

  var DEFAULT_PC = (typeof RSUB_DEFAULT_PC === "string" && RSUB_DEFAULT_PC) || "";  // kurulumda PC yazar
  function load(k, d) {
    try { return localStorage.getItem(k) || (k === "pc" ? DEFAULT_PC : "") || d; } catch (e) { return d; }
  }
  function save(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* yoksay */ } }

  function toast(text, ms) {
    var t = document.getElementById("toast");
    t.textContent = text; t.style.display = "block";
    clearTimeout(toast.timer);
    toast.timer = setTimeout(function () { t.style.display = "none"; }, ms || 4000);
  }

  // --- HDMI görüntüsü (TVWindow) ---
  function showHdmi(number) {
    if (!hasTizen || !tizen.tvwindow) { toast("TVWindow yok (tarayıcıda önizleme)"); return; }
    tizen.systeminfo.getPropertyValue("VIDEOSOURCE", function (vs) {
      var list = (vs && vs.connected) || [], pick = null, i;
      for (i = 0; i < list.length; i++) {
        if (list[i].type === "HDMI" && (!pick || String(list[i].number) === String(number))) pick = list[i];
      }
      if (!pick) { toast("Bağlı HDMI kaynağı bulunamadı. PS5 açık mı?", 8000); return; }
      tizen.tvwindow.setSource(pick, function () {
        tizen.tvwindow.show(function () { /* gösterildi */ }, function (e) { toast("HDMI gösterilemedi: " + e.message, 8000); },
          ["0px", "0px", "1920px", "1080px"], "MAIN", "BEHIND");  // BEHIND: görüntü web katmanının altında
        // (varsayılan FRONT; 2024 TV'de görüntü çeviri katmanını örtüyordu)
      }, function (e) { toast("HDMI seçilemedi: " + e.message, 8000); });
    }, function (e) { toast("Görüntü kaynakları okunamadı: " + e.message, 8000); });
  }

  // --- PC'deki çeviri katmanı ---
  function showOverlay(pc) {
    overlay.src = "http://" + pc + ":" + PORT + "/display.html?tv=1&host=" + encodeURIComponent(pc + ":" + PORT);
  }

  function openSetup() {
    pcInput.value = load("pc", ""); hdmiInput.value = load("hdmi", "1");
    setup.style.display = "flex"; pcInput.focus();
  }

  function start() {
    var pc = load("pc", "");
    if (!pc) { openSetup(); return; }
    setup.style.display = "none";
    showHdmi(load("hdmi", "1"));
    showOverlay(pc);
  }

  function saveSetup() {
    var pc = pcInput.value.replace(/^https?:\/\//, "").replace(/[:/].*$/, "").trim();
    if (!/^[\w.-]+$/.test(pc)) { toast("Geçerli bir adres girin, örneğin 192.168.1.20"); return; }
    save("pc", pc); save("hdmi", (hdmiInput.value || "1").replace(/\D/g, "") || "1");
    start();
  }

  if (hasTizen && tizen.tvinputdevice) {
    try { tizen.tvinputdevice.registerKey("ColorF0Red"); } catch (e) { /* yoksay */ }
  }
  document.addEventListener("keydown", function (e) {
    if (e.keyCode === KEY_BACK) {
      if (setup.style.display === "flex" && load("pc", "")) { start(); return; }
      if (hasTizen) tizen.application.getCurrentApplication().exit();
    } else if (e.keyCode === KEY_RED) {
      openSetup();
    } else if (e.keyCode === KEY_ENTER && setup.style.display === "flex") {
      if (document.activeElement === pcInput) hdmiInput.focus(); else saveSetup();
    }
  });

  start();
})();
