// Kontrol paneli: sunucuyla WebSocket üzerinden komut/yanıt.
const $ = (id) => document.getElementById(id);
const FONTS = ["Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Calibri", "Georgia", "Cambria"];
const SAMPLE = [{ speaker: "Arthur", color: null, en: "Hello my friend!", tr: "Merhaba dostum!" }];

let ws = null, nextId = 1;
const pending = new Map();
const S = { settings: null, profile: null, profiles: [], models: [], vram: null, ip: "", port: 8765, status: {}, shot: null };

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
  } else if (msg.type === "status") {
    S.status = msg.status;
    renderStatus();
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
  saveTimer = setTimeout(() => act(() => send("save_profile", { profile: S.profile })), 300);
}

async function loadState() {
  const d = await send("get_state");
  Object.assign(S, { settings: d.settings, profile: d.profile, profiles: d.profiles, models: d.models, vram: d.vramMb, ip: d.ip, port: d.port, status: d.status });
  renderAll();
  loadSources();
}

function renderAll() {
  renderProfiles(); renderStyleForm(); renderPreview(); renderRegion(); renderGlossary(); renderChars(); renderModels(); renderConn(); renderStatus();
}

// ---------- üst çubuk ----------
function renderProfiles() {
  const names = S.profiles.includes(S.profile.name) ? S.profiles : [S.profile.name, ...S.profiles];
  $("profile").replaceChildren(...names.map((n) => new Option(n, n, false, n === S.profile.name)));
}

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
    chip("OCR", st.ocrEnglish, st.ocrEnglish ? "İngilizce OCR paketi kurulu" : "İngilizce OCR paketi yok, okuma doğruluğu düşük olabilir."),
    chip("Pencere", st.window, st.window ? "Kaynak bulundu" : "Kaynak pencere bulunamadı ya da küçültülmüş."),
    chip(`Ekran ${Math.max(0, (st.clients || 1) - 1)}`, (st.clients || 0) > 1, "Bağlı gösterim ekranı sayısı (bu panel hariç)"),
  ];
  $("chips").replaceChildren(...chips);

  const ll = st.lastLine;
  const line = $("last-line");
  if (ll && ll.lines && ll.lines.length) {
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
  if (st.error) { const e = document.createElement("span"); e.className = "err"; e.textContent = st.error; t.append(e); }
  if (st.last) {
    for (const [k, label] of [["capture", "Yakalama"], ["ocr", "OCR"], ["translate", "Çeviri"]]) {
      const s = document.createElement("span"); const v = document.createElement("strong");
      v.textContent = st.last[k] + " ms"; s.append(label + " ", v); t.append(s);
    }
    if (st.slow) { const a = document.createElement("span"); a.className = "alert"; a.textContent = `Ortalama ${st.avgMs} ms. Daha küçük bir model deneyin.`; t.append(a); }
  }
  if (st.pull) renderModels();
  const n = Math.max(0, (st.clients || 1) - 1);
  $("clients-info").textContent = n ? `${n} gösterim ekranı bağlı.` : "Şu an bağlı gösterim ekranı yok.";
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
  const opts = list.map((s) => new Option(s.label, s.id, false, s.id === cur));
  if (!list.some((s) => s.id === cur)) opts.unshift(new Option(`${cur} (şu an açık değil)`, cur, false, true));
  $("source").replaceChildren(...opts);
}
$("btn-sources").onclick = loadSources;
$("source").onchange = (e) => { S.profile.source = e.target.value; S.shot = null; renderRegion(); saveProfileSoon(); };

$("btn-snap").onclick = () => act(async () => {
  const d = await send("snapshot", { source: S.profile.source });
  S.shot = d.image;
  renderRegion(); renderPreview();
});

function renderRegion() {
  const has = !!S.shot;
  $("shot-empty").hidden = has;
  $("shot-img").hidden = !has;
  if (has) $("shot-img").src = S.shot;
  const [x, y, w, h] = S.profile.region;
  const r = $("region");
  r.hidden = !has;
  Object.assign(r.style, { left: x * 100 + "%", top: y * 100 + "%", width: w * 100 + "%", height: h * 100 + "%" });
  $("region-info").textContent = `Bölge: soldan %${Math.round(x * 100)}, üstten %${Math.round(y * 100)}, genişlik %${Math.round(w * 100)}, yükseklik %${Math.round(h * 100)}.`;
}

(() => {
  const wrap = $("shot");
  let start = null;
  const pt = (e) => {
    const b = $("shot-img").getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - b.left) / b.width)), Math.min(1, Math.max(0, (e.clientY - b.top) / b.height))];
  };
  wrap.addEventListener("pointerdown", (e) => {
    if (!S.shot) return;
    start = pt(e);
    wrap.setPointerCapture(e.pointerId);
  });
  wrap.addEventListener("pointermove", (e) => {
    if (!start) return;
    const [px, py] = pt(e);
    S.profile.region = [Math.min(start[0], px), Math.min(start[1], py), Math.abs(px - start[0]), Math.abs(py - start[1])];
    renderRegion();
  });
  wrap.addEventListener("pointerup", () => {
    if (!start) return;
    start = null;
    const [, , w, h] = S.profile.region;
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
  $("st-offset").value = st.offset; $("o-offset").value = st.offset + " px";
  $("st-color").value = st.color; $("st-name").value = st.nameColor; $("st-bg").value = st.bg;
  $("st-op").value = st.bgOpacity; $("o-op").value = "%" + Math.round(st.bgOpacity * 100);
  $("st-pos").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === st.position)));
}

function setStyle(key, value) {
  S.profile.style[key] = value;
  renderStyleForm(); renderPreview(); renderChars();
  saveProfileSoon();
}
$("st-font").onchange = (e) => setStyle("font", e.target.value);
$("st-size").oninput = (e) => setStyle("size", +e.target.value);
$("st-offset").oninput = (e) => setStyle("offset", +e.target.value);
$("st-color").oninput = (e) => setStyle("color", e.target.value);
$("st-name").oninput = (e) => setStyle("nameColor", e.target.value);
$("st-bg").oninput = (e) => setStyle("bg", e.target.value);
$("st-op").oninput = (e) => setStyle("bgOpacity", +e.target.value);
$("st-pos").querySelectorAll("button").forEach((b) => (b.onclick = () => setStyle("position", b.dataset.v)));

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
function renderGlossary() {
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

// ---------- karakterler ----------
function renderChars() {
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

// ---------- başlat ----------
connectSubtitles(`ws://${location.host}`, onMessage, (up, sock) => {
  if (up) { ws = sock; act(loadState); }
  else { ws = null; S.status = { ...(S.status || {}), ollama: false }; toast("Sunucuyla bağlantı koptu, yeniden deneniyor"); }
});
