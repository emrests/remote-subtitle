// Kontrol paneli: sunucuyla WebSocket üzerinden komut/yanıt.
const $ = (id) => document.getElementById(id);
const FONTS = ["Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Calibri", "Georgia", "Cambria"];
const SAMPLE = [{ speaker: "Arthur", color: null, en: "Hello my friend!", tr: "Merhaba dostum!" }];

let ws = null, nextId = 1;
const pending = new Map();
const S = { settings: null, profile: null, profiles: [], models: [], vram: null, ip: "", port: 8765, status: {}, shot: null, history: [] };

// ---------- iletişim ----------
function send(cmd, args = {}) {
  return new Promise((resolve, reject) => {
    if (!ws || ws.readyState !== 1) return reject(new Error("Sunucuya bağlı değil"));
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, cmd, ...args }));
  });
}

function onMessage(msg) {
  if (msg.type === "reply") {
    const p = pending.get(msg.id);
    if (!p) return;
    pending.delete(msg.id);
    msg.ok ? p.resolve(msg.data) : p.reject(new Error(msg.error || "Hata"));
  } else if (msg.type === "lines" && msg.lines.length) {
    if (msg.feed === "skip") return;  // sunucu tekrar saydı
    const entry = { t: msg.t || Date.now() / 1000, lines: msg.lines };
    S.history = [...(msg.feed === "replace" ? S.history.slice(0, -1) : S.history), entry].slice(-20);
    renderFeed(true);
  } else if (msg.type === "status") {
    S.status = msg.status;
    renderStatus();
  } else if (msg.type === "style" && S.profile && !saveTimer) {
    // Ayar başka yerden değişti (başka panel, sunucu): formu güncelle ki eski değerler geri kaydedilmesin
    if (JSON.stringify(msg.style) !== JSON.stringify(S.profile.style)) {
      S.profile.style = msg.style;
      renderStyleForm(); renderPreview(); renderChars();
    }
  } else if (msg.type === "profile" && S.profile && msg.profile.name === S.profile.name) {
    // Pipeline yeni karakter ekledi: sadece karakter listesini al, formdaki düzenlemeleri ezme
    for (const [name, v] of Object.entries(msg.profile.speakers)) if (!(name in S.profile.speakers)) S.profile.speakers[name] = v;
    renderChars();
  }
}

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 2600);
}

async function act(fn) {
  try { return await fn(); } catch (e) { toast(e.message); }
}

// ---------- profil kaydı ----------
let saveTimer = null;
function saveProfileSoon() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => { saveTimer = null; act(() => send("save_profile", { profile: S.profile })); }, 300);
}

async function loadState() {
  const d = await send("get_state");
  Object.assign(S, { settings: d.settings, profile: d.profile, profiles: d.profiles, models: d.models, vram: d.vramMb, ip: d.ip, port: d.port, status: d.status, history: d.history || [] });
  renderAll();
  loadSources();
}

function renderAll() {
  renderProfiles(); renderStyleForm(); renderPreview(); refreshRegions(); renderGlossary(); renderChars(); renderModels(); renderConn(); renderStatus(); renderFeed(false);
}

// ---------- üst çubuk ----------
function renderProfiles() {
  const names = S.profiles.includes(S.profile.name) ? S.profiles : [S.profile.name, ...S.profiles];
  $("profile").replaceChildren(...names.map((n) => new Option(n, n, false, n === S.profile.name)));
}

// Liste açılırken güncelle: profil başka yerden (başka panel, sunucu) eklenmiş olabilir
$("profile").onfocus = () => send("get_state").then((d) => { S.profiles = d.profiles; renderProfiles(); }).catch(() => {});
$("profile").onchange = (e) => act(async () => {
  S.profile = await send("select_profile", { name: e.target.value });
  S.shot = null;
  renderAll();
  loadSources();
});

let nameMode = null; // "new" | "copy"
function askName(mode) {
  nameMode = mode;
  $("profile-actions").hidden = true;
  $("profile-name-form").hidden = false;
  $("profile-name").value = mode === "copy" ? S.profile.name + " (kopya)" : "";
  $("profile-name").focus();
  $("profile-name").select();
}
function closeName() { $("profile-actions").hidden = false; $("profile-name-form").hidden = true; }
$("btn-new").onclick = () => askName("new");
$("btn-copy").onclick = () => askName("copy");
$("btn-name-cancel").onclick = closeName;
$("profile-name").onkeydown = (e) => { if (e.key === "Enter") $("btn-name-ok").click(); if (e.key === "Escape") closeName(); };
$("btn-name-ok").onclick = () => act(async () => {
  const name = $("profile-name").value.trim();
  if (!name) return toast("Bir ad yazın");
  if (S.profiles.includes(name)) return toast("Bu adla bir profil zaten var");
  if (nameMode === "copy") await send("copy_profile", { name: S.profile.name, newName: name });
  else await send("save_profile", { profile: { name } });
  closeName();
  S.profiles = [...S.profiles, name].sort();
  S.profile = await send("select_profile", { name });
  S.shot = null;
  renderAll();
  toast(nameMode === "copy" ? "Profil kopyalandı" : "Profil oluşturuldu");
});

// Silme: tarayıcı onay penceresi yerine iki adımlı düğme
$("btn-del").onclick = (e) => act(async () => {
  const b = e.currentTarget;
  if (!b.classList.contains("armed")) {
    b.classList.add("armed"); b.textContent = "Silmeyi onayla";
    setTimeout(() => { b.classList.remove("armed"); b.textContent = "Sil"; }, 3000);
    return;
  }
  b.classList.remove("armed"); b.textContent = "Sil";
  const gone = S.profile.name;
  S.profiles = await send("delete_profile", { name: gone });
  await loadState();
  toast(`"${gone}" silindi`);
});

function chip(label, on, title) {
  const c = document.createElement("span");
  c.className = "chip" + (on ? " on" : "");
  c.title = title;
  c.append(document.createElement("i"), label);
  return c;
}

function renderStatus() {
  const st = S.status || {};
  const chips = [
    chip("Ollama", st.ollama, st.ollama ? "Ollama çalışıyor" : "Ollama çalışmıyor. Ollama uygulamasını başlatın."),
    chip("Model", st.modelReady, st.modelReady ? `${st.model} hazır` : `${st.model || "Model"} kurulu değil. Çeviri modeli bölümünden indirin.`),
    chip("OCR", !!st.ocrLang, st.ocrLang ? `Metin tanıma hazır (Windows OCR, dil: ${st.ocrLang})` : "Windows'ta Latin alfabeli bir OCR dili yok. Ayarlar > Dil'den İngilizce ya da Türkçe ekleyin."),
    S.profile && S.profile.source === "ps5"
      ? chip("PS5", st.window, st.window ? "PS5'ten görüntü geliyor" : (st.ps5Error || "PS5'e bağlanılıyor ya da çeviri durdurulmuş."))
      : chip("Pencere", st.window, st.window ? "Kaynak bulundu" : "Kaynak pencere bulunamadı ya da küçültülmüş."),
    chip(`Ekran ${st.clients || 0}`, (st.clients || 0) > 0, "Bağlı gösterim ekranı (TV ya da tarayıcıdaki gösterim sayfası) sayısı"),
  ];
  $("chips").replaceChildren(...chips);
  renderTargets();

  const running = !!st.running;
  const run = $("btn-run");
  run.setAttribute("aria-pressed", String(running));
  run.textContent = running ? "Çeviri açık, durdur" : "Çeviriyi başlat";

  const ll = st.lastLine;
  const line = $("last-line");
  if (!running) {
    line.replaceChildren(Object.assign(document.createElement("span"), {
      className: "muted", textContent: "Çeviri durduruldu. Kaynağı ve bölgeyi seçip üstteki \"Çeviriyi başlat\" düğmesine basın." }));
  } else if (ll && ll.lines && ll.lines.length) {
    line.replaceChildren();
    ll.lines.forEach((l, i) => {
      if (i) line.append("  ");
      if (l.speaker) { const b = document.createElement("b"); b.textContent = l.speaker + ": "; line.append(b); }
      line.append(l.tr);
    });
    line.title = ll.en;
  }
  const t = $("times");
  t.replaceChildren();
  const pullInfo = st.pull && !st.pull.error;
  if (pullInfo) {
    const p = document.createElement("span"); p.className = "info";
    p.textContent = `Çeviri modeli indiriliyor %${st.pull.pct}. Bitince çeviri kendiliğinden başlar.`; t.append(p);
  } else if (st.error) { const e = document.createElement("span"); e.className = "err"; e.textContent = st.error; t.append(e); }
  if (st.last) {
    for (const [k, label] of [["capture", "Yakalama"], ["ocr", "OCR"], ["translate", "Çeviri"]]) {
      const s = document.createElement("span"); const v = document.createElement("strong");
      v.textContent = st.last[k] + " ms"; s.append(label + " ", v); t.append(s);
    }
    if (st.slow) { const a = document.createElement("span"); a.className = "alert"; a.textContent = `Ortalama ${st.avgMs} ms. Daha küçük bir model deneyin.`; t.append(a); }
  }
  if (st.pull) renderModels();
  const n = st.clients || 0;
  $("clients-info").textContent = n ? `${n} gösterim ekranı bağlı.` : "Şu an bağlı gösterim ekranı yok.";
}

$("btn-run").onclick = () => act(async () => {
  const want = $("btn-run").getAttribute("aria-pressed") !== "true";
  await send("set_running", { running: want });
  S.status = { ...S.status, running: want };
  renderStatus();
  toast(want ? "Çeviri başladı" : "Çeviri durduruldu");
});

// ---------- çeviri akışı ----------
function renderFeed(fresh) {
  // en yeni satır en üstte
  const box = $("feed-rows");
  $("feed-empty").hidden = S.history.length > 0;
  const rows = [...S.history].reverse();
  box.replaceChildren(...rows.map((h, i) => {
    const row = document.createElement("div");
    row.className = "feed-row" + (fresh && i === 0 ? " fresh" : "");
    const time = document.createElement("time");
    time.textContent = new Date(h.t * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    // Konuşmacı ayrı sütunda: OCR'ın konuşanı doğru ayırıp ayırmadığı buradan görülür
    const who = document.createElement("div"); who.className = "who-col";
    const en = document.createElement("div"); en.className = "en";
    const tr = document.createElement("div"); tr.className = "tr";
    h.lines.forEach((l, j) => {
      if (j) for (const el of [who, en, tr]) el.append(document.createElement("br"));
      const name = document.createElement("span");
      if (l.speaker) {
        name.textContent = l.speaker;
        name.style.color = l.color || S.profile?.style?.nameColor || "";
      } else {
        name.textContent = "—"; name.className = "none"; name.title = "Konuşmacı algılanmadı";
      }
      who.append(name);
      en.append(l.en); tr.append(l.tr);
    });
    row.append(time, who, en, tr);
    return row;
  }));
}

// ---------- sekmeler ----------
document.querySelectorAll("nav button[data-tab]").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("nav button[data-tab]").forEach((x) => x.removeAttribute("aria-current"));
    b.setAttribute("aria-current", "page");
    document.querySelectorAll("main > section").forEach((s) => (s.hidden = s.id !== "tab-" + b.dataset.tab));
    if (b.dataset.tab === "style") fitPreview();
  };
});

// ---------- kaynak ve bölge ----------
async function loadSources() {
  const list = await act(() => send("list_sources")) || [];
  const cur = S.profile.source;
  const opts = [];
  if (!list.some((s) => s.id === cur)) opts.push(new Option(`${cur} (şu an açık değil)`, cur, false, true));
  for (const name of ["PS5", "Ekranlar", "Uygulama pencereleri"]) {
    const items = list.filter((s) => (s.group || "Uygulama pencereleri") === name);
    if (!items.length) continue;
    const g = document.createElement("optgroup");
    g.label = name;
    g.append(...items.map((s) => new Option(s.label, s.id, false, s.id === cur)));
    opts.push(g);
  }
  $("source").replaceChildren(...opts);
}
$("btn-sources").onclick = loadSources;
$("source").onchange = (e) => { S.profile.source = e.target.value; S.shot = null; renderRegion(); renderTargets(); saveProfileSoon(); };

async function snap() {
  const d = await send("snapshot", { source: S.profile.source });
  S.shot = d.image;
  renderRegion(); renderPreview();
}
$("btn-snap").onclick = () => act(snap);

// Canlı: kaynak sekmesi açıkken ve bölge çizilmiyorken saniyede bir yenile
let liveBusy = false, drawing = false;
setInterval(async () => {
  if (!$("live").checked || liveBusy || drawing || $("tab-source").hidden || !ws) return;
  liveBusy = true;
  try { await snap(); } catch (e) { /* kaynak geçici yoksa sessizce bekle */ }
  liveBusy = false;
}, 1000);

// ---------- çeviriyi göster: bilgisayar / TV ----------
function renderTargets() {
  if (!S.profile) return;
  const ps5Src = S.profile.source === "ps5";
  $("show-pc").checked = S.profile.showPc !== false && !ps5Src;
  $("show-pc").disabled = ps5Src;
  $("show-pc-info").textContent = ps5Src
    ? "PS5 kaynağında kullanılamaz: bilgisayarda oyun penceresi yok."
    : "Kaynağın üstünde, orijinal İngilizce altyazıyı kapatarak.";
  $("show-tv").checked = S.profile.showTv !== false;
  const [cls, text, tip] = tvLink((S.status && S.status.displays) || []);
  const info = $("show-tv-info");
  info.replaceChildren();
  const dot = document.createElement("span"); dot.className = "dot " + cls;
  info.append(dot, text);
  info.title = tip;
}

// TV iletişimi: bağlantı tek başına yetmez (uygulama arka plandayken de açık kalır); TV'deki sayfa 2 sn'de bir
// "buradayım" der ve ekranda görünüp görünmediğini bildirir
function tvLink(displays) {
  if (!displays.length) return ["", "TV uygulaması açık değil", "TV'de Remote Subtitle uygulamasını açın"];
  const d = displays.find((x) => x.tv) || displays[0];
  const extra = displays.length > 1 ? ` (${displays.length} ekran)` : "";
  if (d.age === null) return ["warn", "TV bağlı, yanıt bekleniyor" + extra,
    "Bağlantı açık ama TV henüz bildirim göndermedi. Sürmesi halinde TV uygulamasını kapatıp açın."];
  if (d.age > 6) return ["", `TV yanıt vermiyor (${Math.round(d.age)} sn)` + extra,
    "Bağlantı açık görünüyor ama TV'deki sayfa bildirim göndermiyor: uygulama donmuş ya da kapanmış olabilir."];
  if (!d.visible) return ["warn", "TV uygulaması arka planda: çeviri görünmez" + extra,
    "TV'de kaynak HDMI'ye geçmiş ya da başka uygulama açılmış olabilir. Oyunu Remote Subtitle içinden izleyin."];
  return ["on", `TV ile iletişim var · ekranda · ${d.covers} çeviri kutusu alındı` + extra,
    "TV'deki sayfa 2 sn'de bir yanıt veriyor ve ekranda görünüyor."];
}
$("show-pc").onchange = (e) => { S.profile.showPc = e.target.checked; saveProfileSoon(); renderTargets(); };
$("show-tv").onchange = (e) => { S.profile.showTv = e.target.checked; saveProfileSoon(); renderTargets(); };

// Çizimle değişen bölge: -1 = altyazı, 0.. = ek bölge (extraRegions sırası = öncelik)
let selRegion = -1;
const extras = () => (S.profile.extraRegions = S.profile.extraRegions || []);
const selRect = () => (selRegion < 0 ? S.profile.region : extras()[selRegion].region);
function setSelRect(r) { if (selRegion < 0) S.profile.region = r; else extras()[selRegion].region = r; }
const place = (el, [x, y, w, h]) => Object.assign(el.style, { left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%" });

function renderRegion() {
  if (selRegion >= extras().length) selRegion = -1;
  const has = !!S.shot;
  $("shot-empty").hidden = has;
  $("shot-img").hidden = !has;
  if (has) $("shot-img").src = S.shot;
  const r = $("region");
  r.hidden = !has;
  r.classList.toggle("sel", selRegion < 0);
  place(r, S.profile.region);
  $("shot").querySelectorAll(".region.extra").forEach((el) => el.remove());
  if (has) extras().forEach((x, i) => {
    const el = document.createElement("div");
    el.className = "region extra" + (i === selRegion ? " sel" : "");
    el.innerHTML = "<span></span>";
    el.firstChild.textContent = `${i + 2}. ${x.name}`;
    place(el, x.region);
    $("shot").append(el);
  });
  const [x, y, w, h] = selRect();
  $("region-info").textContent = `${selRegion < 0 ? "Altyazı" : extras()[selRegion].name} bölgesi: soldan %${Math.round(x * 100)}, üstten %${Math.round(y * 100)}, genişlik %${Math.round(w * 100)}, yükseklik %${Math.round(h * 100)}.`;
}
// Liste yalnız değişince çizilir (canlı görüntü her saniye renderRegion çağırır; yazılan ad kaybolmasın)
const refreshRegions = () => { renderRegion(); renderRegionList(); };

function renderRegionList() {
  const row = (i, label) => {
    const li = document.createElement("li");
    li.className = i === selRegion ? "sel" : "";
    const pick = document.createElement("input");
    pick.type = "radio"; pick.name = "region-sel"; pick.checked = i === selRegion; pick.title = "Bu bölgeyi çiz";
    pick.onchange = () => { selRegion = i; refreshRegions(); };
    li.append(pick);
    if (i < 0) { li.append("1. Altyazı"); return li; }
    const name = document.createElement("input");
    name.type = "text"; name.value = label;
    name.onfocus = () => {  // listeyi yeniden çizmeden seç (yazılan ad odaktan düşmesin)
      selRegion = i; renderRegion();
      $("region-list").querySelectorAll("li").forEach((x, k) => { x.classList.toggle("sel", k - 1 === i); x.firstChild.checked = k - 1 === i; });
    };
    name.onchange = () => { extras()[i].name = name.value.trim() || `Bölge ${i + 2}`; saveProfileSoon(); renderRegion(); };
    const btn = (text, title, fn, disabled) => {
      const b = document.createElement("button");
      b.className = "btn ghost"; b.textContent = text; b.title = title; b.disabled = disabled;
      b.onclick = () => { fn(); saveProfileSoon(); refreshRegions(); };
      return b;
    };
    const move = (d) => { const a = extras(); [a[i], a[i + d]] = [a[i + d], a[i]]; selRegion = i + d; };
    li.append(`${i + 2}.`, name,
      btn("↑", "Önceliği artır", () => move(-1), i === 0),
      btn("↓", "Önceliği azalt", () => move(1), i === extras().length - 1),
      btn("Sil", "Bölgeyi sil", () => { extras().splice(i, 1); selRegion = -1; }, false));
    return li;
  };
  $("region-list").replaceChildren(row(-1), ...extras().map((x, i) => row(i, x.name)));
}

$("btn-add-region").onclick = () => {
  const names = ["Sağ alt", "Sağ üst", "Sol üst", "Sol alt"];
  const n = extras().length;
  extras().push({ name: names[n] || `Bölge ${n + 2}`, region: [[0.7, 0.75, 0.28, 0.2], [0.7, 0.03, 0.28, 0.2], [0.02, 0.03, 0.28, 0.2], [0.02, 0.75, 0.28, 0.2]][n % 4] });
  selRegion = n;
  saveProfileSoon(); refreshRegions();
  toast("Bölge eklendi: görüntünün üstüne çizerek yerini ayarlayın");
};

(() => {
  const wrap = $("shot");
  let start = null;
  const pt = (e) => {
    const b = $("shot-img").getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))];
  };
  wrap.addEventListener("pointerdown", (e) => {
    if (!S.shot) return;
    drawing = true;
    start = pt(e);
    wrap.setPointerCapture(e.pointerId);
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!start) return;
    const [px, py] = pt(e);
    setSelRect([Math.min(start[0], px), Math.min(start[1], py), Math.abs(px - start[0]), Math.abs(py - start[1])]);
    renderRegion();
  });
  wrap.addEventListener("pointerup", () => {
    if (!start) return;
    start = null;
    drawing = false;
    const [, , w, h] = selRect();
    if (w < 0.02 || h < 0.02) return toast("Bölge çok küçük, daha geniş bir alan çizin");
    saveProfileSoon();
    toast("Bölge kaydedildi");
  });
})();

// ---------- görünüm ----------
function renderStyleForm() {
  const st = S.profile.style;
  const fonts = FONTS.includes(st.font) ? FONTS : [st.font, ...FONTS];
  $("st-font").replaceChildren(...fonts.map((f) => { const o = new Option(f, f, false, f === st.font); o.style.fontFamily = f; return o; }));
  $("st-size").value = st.size; $("o-size").value = st.size + " px";
  $("st-color").value = st.color; $("st-name").value = st.nameColor; $("st-bg").value = st.bg;
  $("st-op").value = st.bgOpacity; $("o-op").value = "%" + Math.round(st.bgOpacity * 100);
  $("st-blur").value = st.blur ?? 16; $("o-blur").value = (st.blur ?? 16) + " px";
  $("st-blurmode").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === (st.blurMode || "live"))));
  $("st-cover").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === (st.cover || "early"))));
  $("st-place").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === (st.place || "over"))));
}

function setStyle(key, value) {
  S.profile.style[key] = value;
  renderStyleForm(); renderPreview(); renderChars();
  saveProfileSoon();
}
$("st-font").onchange = (e) => setStyle("font", e.target.value);
$("st-size").oninput = (e) => setStyle("size", +e.target.value);
$("st-color").oninput = (e) => setStyle("color", e.target.value);
$("st-name").oninput = (e) => setStyle("nameColor", e.target.value);
$("st-bg").oninput = (e) => setStyle("bg", e.target.value);
$("st-op").oninput = (e) => setStyle("bgOpacity", +e.target.value);
$("st-blur").oninput = (e) => setStyle("blur", +e.target.value);
$("st-blurmode").querySelectorAll("button").forEach((b) => (b.onclick = () => setStyle("blurMode", b.dataset.v)));
$("st-cover").querySelectorAll("button").forEach((b) => (b.onclick = () => setStyle("cover", b.dataset.v)));
$("st-place").querySelectorAll("button").forEach((b) => (b.onclick = () => setStyle("place", b.dataset.v)));

function renderPreview() {
  const lines = SAMPLE.map((l) => ({ ...l, color: (S.profile.speakers[l.speaker] || {}).color || S.profile.style.nameColor }));
  renderSubtitle($("preview"), lines, S.profile.style);
  const scene = $("scene");
  scene.classList.toggle("has-shot", !!S.shot);
  scene.style.backgroundImage = S.shot ? `url("${S.shot}")` : "";
}

function fitPreview() {
  const w = $("tv-screen").clientWidth;
  if (w) $("tv-stage").style.transform = `scale(${w / 1920})`;
}
new ResizeObserver(fitPreview).observe($("tv-screen"));

// ---------- terimler ----------
$("game-context").oninput = (e) => { S.profile.context = e.target.value; saveProfileSoon(); };
$("game-tone").oninput = (e) => { S.profile.tone = e.target.value; saveProfileSoon(); };
function renderGlossary() {
  if (document.activeElement !== $("game-context")) $("game-context").value = S.profile.context || "";
  if (document.activeElement !== $("game-tone")) $("game-tone").value = S.profile.tone || "";
  renderSlang();
  const rows = Object.entries(S.profile.glossary);
  $("glossary-empty").hidden = rows.length > 0;
  $("glossary").hidden = rows.length === 0;
  $("glossary").tBodies[0].replaceChildren(...rows.map(([en, tr]) => glossaryRow(en, tr)));
}
function glossaryRow(en, tr) {
  const row = document.createElement("tr");
  const mk = (v, label) => { const i = document.createElement("input"); i.type = "text"; i.value = v; i.setAttribute("aria-label", label); return i; };
  const a = mk(en, "İngilizce terim"), b = mk(tr, "Türkçe karşılık");
  const del = document.createElement("button"); del.className = "btn ghost"; del.textContent = "Kaldır";
  const sync = () => {
    const g = {};
    $("glossary").querySelectorAll("tbody tr").forEach((r) => { const [x, y] = r.querySelectorAll("input"); if (x.value.trim()) g[x.value.trim()] = y.value.trim(); });
    S.profile.glossary = g; saveProfileSoon();
  };
  a.onchange = sync; b.onchange = sync;
  del.onclick = () => { row.remove(); sync(); renderGlossary(); };
  const cells = [a, b, del].map((el) => { const td = document.createElement("td"); td.append(el); return td; });
  cells[2].className = "actions";
  row.append(...cells);
  return row;
}
$("btn-term-add").onclick = () => {
  $("glossary-empty").hidden = true; $("glossary").hidden = false;
  const row = glossaryRow("", "");
  $("glossary").tBodies[0].append(row);
  row.querySelector("input").focus();
};

// Argo sözlüğü: satır düzenlenince bütün tablo profile yazılır (filtre gizlediği satırlar da tabloda durur)
function renderSlang() {
  const rows = S.profile.slang || [];
  $("slang-empty").hidden = rows.length > 0;
  $("slang").hidden = rows.length === 0;
  $("slang").tBodies[0].replaceChildren(...rows.map(slangRow));
  filterSlang();
}
function syncSlang() {
  S.profile.slang = [...$("slang").querySelectorAll("tbody tr")].map((r) => {
    const [en, tr, note] = [...r.querySelectorAll("input")].map((i) => i.value.trim());
    return { en, tr, note };
  }).filter((r) => r.en);
  saveProfileSoon();
}
function slangRow(r) {
  const row = document.createElement("tr");
  const mk = (v, label) => { const i = document.createElement("input"); i.type = "text"; i.value = v || ""; i.setAttribute("aria-label", label); i.onchange = syncSlang; return i; };
  const del = document.createElement("button"); del.className = "btn ghost"; del.textContent = "Kaldır";
  del.onclick = () => { row.remove(); syncSlang(); renderSlang(); };
  const cells = [mk(r.en, "İngilizce kelime"), mk(r.tr, "Türkçe karşılık"), mk(r.note, "Not"), del].map((el) => { const td = document.createElement("td"); td.append(el); return td; });
  cells[3].className = "actions";
  row.append(...cells);
  return row;
}
function filterSlang() {
  const q = $("slang-filter").value.trim().toLocaleLowerCase("tr");
  $("slang").querySelectorAll("tbody tr").forEach((r) => {
    r.hidden = !!q && ![...r.querySelectorAll("input")].some((i) => i.value.toLocaleLowerCase("tr").includes(q));
  });
}
$("slang-filter").oninput = filterSlang;
$("btn-slang-add").onclick = () => {
  $("slang-filter").value = "";
  $("slang-empty").hidden = true; $("slang").hidden = false;
  const row = slangRow({});
  $("slang").tBodies[0].prepend(row);
  filterSlang();
  row.querySelector("input").focus();
};

// ---------- karakterler ----------
$("speaker-color").onchange = (e) => { S.profile.speakerColor = e.target.checked; saveProfileSoon(); };
function renderChars() {
  $("speaker-color").checked = !!S.profile.speakerColor;
  const names = Object.keys(S.profile.speakers).sort((a, b) => a.localeCompare(b, "tr"));
  $("chars-empty").hidden = names.length > 0;
  $("chars").hidden = names.length === 0;
  $("chars").tBodies[0].replaceChildren(...names.map((name) => {
    const sp = S.profile.speakers[name];
    const row = document.createElement("tr");
    const n = document.createElement("span"); n.className = "char-name"; n.textContent = name; n.style.color = sp.color || S.profile.style.nameColor;
    const color = document.createElement("input"); color.type = "color"; color.value = sp.color || S.profile.style.nameColor; color.setAttribute("aria-label", `${name} isim rengi`);
    const reset = document.createElement("button"); reset.className = "btn ghost"; reset.textContent = "Varsayılana dön"; reset.hidden = !sp.color;
    const colorCell = document.createElement("div"); colorCell.className = "inline-form"; colorCell.append(color, reset);
    color.oninput = () => { sp.color = color.value; n.style.color = color.value; reset.hidden = false; renderPreview(); saveProfileSoon(); };
    reset.onclick = () => { sp.color = null; renderChars(); renderPreview(); saveProfileSoon(); };
    const voice = document.createElement("span"); voice.className = "tag"; voice.textContent = "Dublaj aşamasında";
    const del = document.createElement("button"); del.className = "btn ghost"; del.textContent = "Kaldır";
    del.onclick = () => { delete S.profile.speakers[name]; renderChars(); saveProfileSoon(); };
    const cells = [n, colorCell, voice, del].map((el) => { const td = document.createElement("td"); td.append(el); return td; });
    cells[3].className = "actions";
    row.append(...cells);
    return row;
  }));
}

// ---------- modeller ----------
function renderModels() {
  const pull = (S.status || {}).pull;
  const installed = new Set(S.models.filter((m) => m.installed).map((m) => m.id));
  if (S.status && S.status.modelReady) installed.add(S.settings.model);
  $("vram-info").textContent = S.vram
    ? `Ekran kartınızda ${Math.round(S.vram / 1024)} GB bellek var. Modeller iyiden hızlıya sıralıdır; önerilen model bu kart için en iyi dengedir.`
    : "Ekran kartı belleği okunamadı. Modeller iyiden hızlıya sıralıdır; emin değilseniz en küçük modeli seçin.";
  $("models").replaceChildren(...S.models.map((m, i) => {
    const row = document.createElement("div");
    const active = m.id === S.settings.model;
    row.className = "model" + (active ? " active" : "");
    const rank = document.createElement("div"); rank.className = "rank"; rank.textContent = i + 1;
    const info = document.createElement("div");
    const title = document.createElement("div"); title.className = "title";
    const strong = document.createElement("strong"); strong.textContent = m.label; title.append(strong);
    const tag = (cls, text) => { const t = document.createElement("span"); t.className = "tag " + cls; t.textContent = text; title.append(t); };
    if (m.recommended) tag("rec", "Önerilen");
    if (installed.has(m.id)) tag("ok", "Kurulu");
    if (!m.fits && S.vram) tag("warn", "Bu kart için büyük");
    const meta = document.createElement("div"); meta.className = "meta";
    meta.textContent = `${m.note}. İndirme ${m.size_gb} GB, en az ${Math.round(m.min_vram_mb / 1024)} GB ekran kartı belleği.`;
    info.append(title, meta);
    if (pull && pull.model === m.id) {
      const bar = document.createElement("div"); bar.className = "progress";
      const fill = document.createElement("div"); fill.style.width = pull.pct + "%"; bar.append(fill);
      const p = document.createElement("div"); p.className = "meta";
      p.textContent = pull.error ? `İndirme başarısız: ${pull.error}` : `İndiriliyor %${pull.pct}. Yarıda kalırsa kaldığı yerden devam eder.`;
      info.append(bar, p);
    }
    const btn = document.createElement("button");
    if (active && installed.has(m.id)) { btn.className = "btn"; btn.disabled = true; btn.textContent = "Kullanılıyor"; }
    else if (installed.has(m.id)) {
      btn.className = "btn primary"; btn.textContent = "Kullan";
      btn.onclick = () => act(async () => { S.settings = await send("save_settings", { settings: { model: m.id } }); renderModels(); toast(`${m.label} seçildi`); });
    } else {
      btn.className = active ? "btn primary" : "btn"; btn.textContent = "İndir"; btn.disabled = !!pull;
      if (active) tag("warn", "Seçili ama kurulu değil");
      btn.onclick = () => act(async () => { await send("pull_model", { model: m.id }); toast(`${m.label} indiriliyor`); });
    }
    row.append(rank, info, btn);
    return row;
  }));
}

// ---------- bağlantı ----------
function renderConn() {
  const url = `http://${S.ip}:${S.port}/display.html`;
  $("tv-url").textContent = url;
  $("btn-copy-url").onclick = () => navigator.clipboard.writeText(url).then(() => toast("Adres kopyalandı"));
  $("btn-open-display").onclick = () => window.open(`/display.html`, "_blank");
  $("chiaki-path").value = S.settings.chiakiPath || "";
}
$("chiaki-path").onchange = (e) => act(async () => { S.settings = await send("save_settings", { settings: { chiakiPath: e.target.value.trim() } }); });
$("btn-chiaki").onclick = () => act(async () => { await send("launch_chiaki"); toast("chiaki-ng başlatıldı"); });

// ---------- PS5 eşleştirme ----------
async function loadPs5(host) {
  const d = await send("ps5_state", host ? { host } : {});
  S.ps5 = d;
  const paired = !!(d.ps5 && d.ps5.paired);
  $("ps5-account").textContent = d.account ? `— ${d.account}` : "";
  $("ps5-login").closest("li").classList.toggle("done", !!d.account);
  if (d.host && !$("ps5-host").value) $("ps5-host").value = d.host;
  const tag = $("ps5-tag");
  tag.className = "tag " + (paired ? "ok" : d.host ? "warn" : "");
  tag.textContent = !d.host ? "Eşleştirilmedi" : !d.ps5 ? "PS5'e ulaşılamıyor" : paired ? `Eşleşti: ${d.ps5.name}` : "Eşleştirilmedi";
  const using = S.profile.source === "ps5";
  $("ps5-conn").textContent = !paired ? "Önce eşleştirin."
    : d.connected ? "Bağlı: görüntü geliyor."
    : d.error ? `Son deneme: ${d.error}`
    : using ? "Kaynak PS5. Çeviri başlayınca (ya da Kaynak ve bölge'de 'Görüntü al'a basınca) bağlanır."
    : "Eşleşti. Bu profilde kaynak olarak seçin.";
  $("btn-ps5-use").disabled = !paired || using;
  $("btn-ps5-use").textContent = using ? "Kaynak: PS5" : "PS5'i kaynak yap";
}
$("btn-ps5-login").onclick = () => act(() => send("ps5_open_login"));
$("btn-ps5-account").onclick = () => act(async () => {
  const name = await send("ps5_add_account", { url: $("ps5-redirect").value.trim() });
  $("ps5-redirect").value = "";
  toast(`PSN hesabı kaydedildi: ${name}`);
  await loadPs5();
});
$("btn-ps5-pair").onclick = () => act(async () => {
  const host = $("ps5-host").value.trim();
  if (!host) throw new Error("PS5'in IP adresini yazın");
  toast("Eşleştiriliyor…");
  const r = await send("ps5_pair", { host, pin: $("ps5-pin").value });
  S.settings = r.settings;
  $("ps5-pin").value = "";
  toast(`Eşleşti: ${r.name}`);
  await loadPs5();
});
$("btn-ps5-use").onclick = () => act(async () => {
  S.profile.source = "ps5"; S.shot = null; saveProfileSoon();
  await loadSources(); renderRegion();
  toast("Kaynak PS5 oldu. Kaynak ve bölge'de 'Görüntü al' ile altyazı bölgesini seçin.");
  await loadPs5();
});
$("btn-ps5-check").onclick = () => act(async () => { toast("PS5 yoklanıyor…"); await loadPs5($("ps5-host").value.trim()); });
document.querySelector('nav button[data-tab="conn"]').addEventListener("click", () => act(() => loadPs5()));

// ---------- Samsung TV kurulumu ----------
function renderTv(d) {
  S.tv = d;
  $("tv-pcip").textContent = d.pcIp;
  const cert = d.cert;
  $("tv-cert").textContent = cert ? `— ${cert.name}, ${cert.duids.length} TV, ${cert.expires} tarihine kadar geçerli` : "— yok";
  $("btn-tv-cert").textContent = cert ? "Samsung ile giriş yap ve sertifikayı yenile" : "Samsung ile giriş yap ve sertifika oluştur";
  const rows = (d.tvs || []).map((t) => {
    const tr = document.createElement("tr");
    const ok = cert && cert.duids.includes(t.duid);
    tr.innerHTML = `<td><b></b><br><span class="muted"></span></td><td><code></code></td><td><span class="tag ${ok ? "ok" : "warn"}">${ok ? "Sertifikada" : "Sertifikada yok"}</span></td><td><button class="btn primary">Kur</button></td>`;
    tr.querySelector("b").textContent = t.model || "Samsung TV";
    tr.querySelector("span.muted").textContent = t.ip;
    tr.querySelector("code").textContent = t.duid || t.error || "";
    tr.querySelector("button").disabled = !ok;
    tr.querySelector("button").onclick = () => tvInstall(t.ip);
    return tr;
  });
  $("tv-list").querySelector("tbody").replaceChildren(...rows);
  const installed = (d.tvs || []).some((t) => t.installed);
  $("tv-tag").className = "tag " + (installed ? "ok" : cert ? "warn" : "");
  $("tv-tag").textContent = installed ? "Kuruldu" : cert ? "Sertifika hazır" : "Kurulmadı";
  $("tv-busy").textContent = d.busy || "";
}
async function loadTv() { renderTv(await send("tv_state")); }
async function tvScan(ip) {
  $("tv-busy").textContent = "TV aranıyor…";
  const r = await send("tv_scan", ip ? { ip } : {});
  const errs = r.found.filter((f) => f.error);
  if (!r.found.length) toast("Geliştirici modunda TV bulunamadı. Host PC IP doğru mu, TV yeniden başlatıldı mı?");
  else if (errs.length) toast(errs[0].error);
  await loadTv();
}
async function tvInstall(ip) {
  $("tv-busy").textContent = "İmzalanıyor ve TV'ye kuruluyor…";
  try {
    await send("tv_install", { ip });
    toast("Kuruldu: uygulama TV'de açıldı");
  } finally { await loadTv(); }
}
$("btn-tv-scan").onclick = () => act(() => tvScan());
$("btn-tv-add").onclick = () => act(() => tvScan($("tv-ip").value.trim()));
$("btn-tv-cert").onclick = () => act(async () => {
  $("tv-busy").textContent = "Tarayıcıda Samsung hesabınızla giriş yapın…";
  try {
    const c = await send("tv_create_cert");
    toast(`Sertifika hazır: ${c.duids.length} TV`);
  } finally { await loadTv(); }
});
$("btn-tv-import").onclick = () => act(async () => {
  const c = await send("tv_import_tizen");
  toast(`Sertifika içe aktarıldı: ${c.name}, ${c.duids.length} TV`);
  await loadTv();
});
document.querySelector('nav button[data-tab="conn"]').addEventListener("click", () => act(loadTv));

// ---------- başlat ----------
connectSubtitles(`ws://${location.host}`, onMessage, (up, sock) => {
  if (up) { ws = sock; act(loadState); }
  else { ws = null; S.status = { ...(S.status || {}), ollama: false }; toast("Sunucuyla bağlantı koptu, yeniden deneniyor"); }
});
