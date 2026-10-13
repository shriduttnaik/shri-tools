"use strict";
/* Shri Tools studio - plain JS, no internet needed. */

// ---------- tiny helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const _replace = Element.prototype.replaceChildren;  // skip empty slots (null/false) instead of printing "null"
Element.prototype.replaceChildren = function (...kids) {
  return _replace.apply(this, kids.flat(Infinity).filter((k) => k !== null && k !== undefined && k !== false));
};
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
function icon(name, cls = "i") {
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("class", cls);
  const u = document.createElementNS(ns, "use");
  u.setAttribute("href", "#i-" + name);
  s.append(u);
  return s;
}
async function api(path, method = "GET", data) {
  const opt = { method, headers: {} };
  if (data instanceof FormData) opt.body = data;
  else if (data !== undefined) { opt.body = JSON.stringify(data); opt.headers["Content-Type"] = "application/json"; }
  const r = await fetch("/api" + path, opt);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function toast(msg, err) {
  const t = h("div", { class: "toast" + (err ? " err" : "") }, msg);
  $("#toasts").append(t);
  setTimeout(() => t.remove(), err ? 6000 : 3200);
}
async function safe(fn, okMsg) {
  try { const r = await fn(); if (okMsg) toast(okMsg); return r; } catch (e) { toast(e.message, true); }
}
function go(hash) { if (location.hash === hash) route(); else location.hash = hash; }
const lib = (p) => (p ? "/lib/" + p : null);
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const words = (t) => (t || "").trim().split(/\s+/).filter(Boolean).length;
function fmtSec(s) { s = Math.round(s || 0); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }
function copy(text, what = "Copied") { navigator.clipboard.writeText(text).then(() => toast(what)); }
function field(label, input, hint) { return h("label", { class: "f" }, h("span", {}, label), input, hint ? h("div", { class: "hint" }, hint) : null); }
function toggle(label, checked, onchange) {
  const inp = h("input", { type: "checkbox", checked, onchange: (e) => onchange(e.target.checked) });
  return h("label", { class: "toggle" }, inp, h("span", { class: "sw" }), h("span", {}, label));
}
function modal(title, content, wide) {
  const close = () => bg.remove();
  const bg = h("div", { class: "modal-bg", onmousedown: (e) => { if (e.target === bg) close(); } },
    h("div", { class: "modal" + (wide ? " wide" : "") },
      h("div", { class: "mh" }, h("h2", {}, title), h("button", { class: "ghost icon", onclick: close }, icon("x"))),
      content));
  document.body.append(bg);
  const esc = (e) => { if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); } };
  document.addEventListener("keydown", esc);
  return close;
}
function openVideo(url, title) {
  modal(title || "Video", h("video", { src: url, controls: true, autoplay: true }), true);
}
const STATE = {
  draft: ["Draft", ""], waiting: ["Waiting", "amber"], running: ["Working", "run"], approve: ["Check pictures", "amber"],
  done: ["Ready", "g"], failed: ["Failed", "red"], cancelled: ["Stopped", ""],
};
function statePill(st, final) {
  if ((st === "done" || !st || st === "draft" || st === "cancelled") && final) return h("span", { class: "pill g" }, "Video ready");
  const [t, c] = STATE[st] || STATE.draft;
  return h("span", { class: "pill " + c }, t);
}

const STYLE_DESC = {
  cinematic: "Real people, film look", pixar: "3D cartoon, big eyes, warm colors", anime: "Hand-drawn 2D animation",
  storybook: "Soft watercolor picture book", clay: "Stop-motion plasticine",
};
const IDEAS = [
  { t: "The Paper Boat", s: "pixar", i: "A rainy day in the forest. Pip, the tiny orange fox cub, floats his paper boat down the stream and it races away. Slow old Toby the turtle knows the shortcut along the stream. Lesson: patience. Sounds: rain, splashes, frogs, thunder." },
  { t: "Storm Night", s: "pixar", i: "A monsoon night: the river floods the school road. Shri and little Chotu save the school books on a small raft, while Vikram's men run away from the thunder. Lesson: nobody is too small to be brave." },
  { t: "The Kite Battle", s: "pixar", i: "Makar Sankranti kite festival on the village rooftops. Vikram's huge black kite cuts every kite in the sky, until Chotu and old Kaka fly a tiny red kite with a secret strong string." },
  { t: "Diwali for Everyone", s: "pixar", i: "Vikram cuts the village electricity on Diwali night. Meera's students light a thousand clay lamps instead, and even Vikram's men end up smiling." },
  { t: "Golu Goes to School", s: "pixar", i: "Golu, a playful baby elephant, follows Chotu to the village school and causes cheerful chaos in the classroom. Teacher Meera turns it into a lesson in kindness to animals." },
  { t: "Toby's Birthday", s: "pixar", i: "Pip and the forest friends secretly prepare a birthday party for old Toby the turtle, who keeps almost finding out. Lesson: friendship. Sounds: giggles, crackling leaves, a drum." },
];

// spoken languages (same list as store.LANGUAGES on the server)
const LANGS = [["en", "English"], ["hi", "Hindi - हिन्दी"], ["kn", "Kannada - ಕನ್ನಡ"], ["kok", "Konkani - कोंकणी"],
  ["mr", "Marathi - मराठी"], ["ta", "Tamil - தமிழ்"], ["te", "Telugu - తెలుగు"], ["ml", "Malayalam - മലയാളം"],
  ["bn", "Bengali - বাংলা"], ["gu", "Gujarati - ગુજરાતી"], ["pa", "Punjabi - ਪੰਜਾਬੀ"], ["ur", "Urdu - اردو"]];
const langName = (code) => (LANGS.find(([k]) => k === (code || "en")) || LANGS[0])[1];
function langSelect(value, onchange, withDefault) {
  return h("select", { onchange: (e) => onchange(e.target.value) },
    withDefault ? h("option", { value: "", selected: !value }, "Same as the video") : null,
    LANGS.map(([k, n]) => h("option", { value: k, selected: k === value }, n)));
}

// ---------- app state ----------
const S = { health: {}, projects: [], view: null, poll: null };

// ---------- sidebar ----------
function renderNav(active) {
  const items = [["", "home", "Home"], ["create", "spark", "Create"], ["seasons", "tv", "Seasons"], ["music", "music", "Music videos"],
    ["characters", "users", "Characters"], ["queue", "list", "Queue"], ["connect", "link", "Connect"], ["settings", "gear", "Settings"]];
  $("#nav").replaceChildren(...items.map(([r, ic, t]) => h("a", { href: "#/" + r, class: active === r ? "on" : "" }, icon(ic), t,
    r === "queue" && (S.health.waiting || S.health.busy) ? h("span", { class: "count" }, (S.health.waiting || 0) + (S.health.busy ? 1 : 0)) : null)));
}
function renderRecent(currentId) {
  $("#recent").replaceChildren(...S.projects.slice(0, 12).map((p) =>
    h("a", { href: `#/p/${p.id}/storyboard`, class: p.id === currentId ? "on" : "" },
      h("div", { class: "t" }, p.title),
      h("div", { class: "s" }, p.state === "running" ? h("span", { class: "dot busy" }) : null,
        p.final ? "Video ready" : (STATE[p.state] || STATE.draft)[0], p.episode ? ` · Ep ${p.episode}` : ""))));
}
function renderHealth() {
  const H = S.health;
  $("#health").replaceChildren(
    h("div", { class: "row" }, h("span", { class: "dot " + (H.busy ? "busy" : "ok") }),
      h("span", { class: "job" }, H.busy ? H.job || "Working" : "Idle - ready")),
    h("div", { class: "row" }, h("span", { class: "dot " + (H.comfy ? "ok" : "warn") }), "Video engine ", H.comfy ? "on" : "starts when needed"),
    h("div", { class: "row" }, h("span", { class: "dot " + (H.ollama ? "ok" : "bad") }), "Story AI ", H.ollama ? "on" : "off"),
    S.sys ? h("div", { class: "row dim" }, S.sys.gpu ? `GPU ${S.sys.gpu.load ?? "-"}% · ${S.sys.gpu.temp ?? "-"}°C · ` : "", `RAM ${S.sys.ram_used}/${S.sys.ram_total} GB`) : null,
    h("div", { class: "row dim" }, `${H.disk_free_gb ?? "?"} GB free on D:`));
}
async function refreshSide() {
  try {
    const [hh, pp, sys] = await Promise.all([api("/health"), api("/projects"), api("/system").catch(() => null)]);
    S.health = hh; S.projects = pp.projects; S.sys = sys;
    // a newer Shri Tools was installed: load it (but never while you are typing - then just tell you)
    if (hh.build && S.build && hh.build !== S.build) {
      const typing = document.activeElement && ["INPUT", "TEXTAREA"].includes(document.activeElement.tagName);
      if (!typing && !document.querySelector(".modal-bg")) return location.reload();
      if (!S.toldNew) { S.toldNew = true; toast("Shri Tools was updated - press F5 when you are done typing"); }
    }
    S.build = S.build || hh.build;
  } catch (e) { S.health = {}; }
  const r = (location.hash.slice(2) || "").split("/");
  renderNav(r[0] === "p" ? null : r[0].split("?")[0]);
  renderRecent(r[0] === "p" ? r[1] : null);
  renderHealth();
}

// ---------- router ----------
async function route() {
  clearInterval(S.poll);
  S.view = null;
  const raw = location.hash.slice(2);
  const [path, qs] = raw.split("?");
  const parts = path.split("/");
  const q = Object.fromEntries(new URLSearchParams(qs || ""));
  renderNav(parts[0] === "p" ? null : parts[0]);
  renderRecent(parts[0] === "p" ? parts[1] : null);
  const main = $("#main");
  main.scrollTop = 0;
  try {
    let page;
    if (!parts[0]) page = await viewHome();
    else if (parts[0] === "create") page = await viewCreate(q);
    else if (parts[0] === "characters") page = await viewCharacters();
    else if (parts[0] === "seasons") page = await viewSeasons();
    else if (parts[0] === "music") page = await viewMusic();
    else if (parts[0] === "season") page = await viewSeason(parts[1]);
    else if (parts[0] === "p") page = await viewProject(parts[1], parts[2] || "storyboard");
    else if (parts[0] === "queue") page = await viewQueue();
    else if (parts[0] === "settings") page = await viewSettings();
    else if (parts[0] === "connect") page = await viewConnect();
    else page = h("div", { class: "page" }, h("h1", {}, "Not found"));
    main.replaceChildren(page);
  } catch (e) {
    main.replaceChildren(h("div", { class: "page" }, h("div", { class: "empty" }, h("h3", {}, "Something went wrong"), e.message)));
  }
}
window.addEventListener("hashchange", route);

// ---------- HOME ----------
async function viewHome() {
  const [{ projects }, health] = await Promise.all([api("/projects"), api("/health").catch(() => ({}))]);
  S.projects = projects;
  S.health = health;
  const H = health;
  const running = projects.find((p) => p.state === "running");
  return h("div", { class: "page" },
    h("div", { class: "hero" },
      h("div", { class: "grow" },
        h("h1", {}, "What are we making today?"),
        h("p", {}, "Write a story, meet your characters, and Shri Tools draws every scene, makes the characters act and speak with MiniMax H3's own voices, checks every clip and hands you the final video with Shorts, titles, description, tags and thumbnails. Everything runs on this laptop, offline.")),
      h("div", { class: "btns" },
        h("button", { class: "primary big", onclick: () => go("#/create") }, icon("plus"), "New video"),
        h("button", { class: "big", onclick: () => go("#/seasons") }, icon("tv"), "Seasons"))),
    h("div", { class: "statusbar" },
      h("div", { class: "card" }, h("span", { class: "dot " + (running ? "busy" : "ok") }),
        h("div", {}, h("div", { class: "k" }, "Now"), h("div", { class: "v" }, running ? running.title : "Nothing running"))),
      h("div", { class: "card" }, h("span", { class: "dot " + (H.ollama ? "ok" : "bad") }),
        h("div", {}, h("div", { class: "k" }, "Story AI (Ollama)"), h("div", { class: "v" }, H.ollama ? "Ready" : "Not running"))),
      h("div", { class: "card" }, h("span", { class: "dot " + (H.comfy ? "ok" : "warn") }),
        h("div", {}, h("div", { class: "k" }, "Video engine (ComfyUI)"), h("div", { class: "v" }, H.comfy ? "Running" : "Starts by itself"))),
      h("div", { class: "card" }, h("span", { class: "dot ok" }),
        h("div", {}, h("div", { class: "k" }, "Videos"), h("div", { class: "v" }, `${projects.filter((p) => p.final).length} ready of ${projects.length}`)))),
    h("h2", {}, "Your videos"),
    h("div", { class: "grid projects" },
      h("div", { class: "pcard new", onclick: () => go("#/create") }, h("div", { style: { display: "grid", placeItems: "center", gap: "8px" } }, icon("plus"), "New video")),
      projects.map(projectCard)));
}
function projectCard(p) {
  return h("div", { class: "pcard", onclick: () => go(`#/p/${p.id}/${p.final ? "video" : "storyboard"}`) },
    h("div", { class: "cover", style: p.cover ? { backgroundImage: `url("${lib(p.cover)}")` } : {} },
      p.cover ? null : icon("video"), h("div", { class: "state" }, statePill(p.state, p.final))),
    h("div", { class: "body" }, h("div", { class: "t" }, p.title),
      h("div", { class: "m" }, [p.episode ? `Episode ${p.episode}` : p.kind, plural(p.scenes, "scene"), plural(p.lines, "line")].join(" · "))));
}

// ---------- CREATE ----------
async function viewCreate(q) {
  const [{ characters }, { seasons }] = await Promise.all([api("/characters"), api("/seasons")]);
  const season = seasons.find((s) => s.id === q.season);
  const f = {
    title: q.title || "", kind: season ? "episode" : "video", season_id: season ? season.id : "", style: season ? season.style : "pixar",
    cast: season ? [...season.cast] : [], idea: "", scenes_wanted: 18, approve: true, music: false, music_prompt: "",
    language: "en",
  };
  const castBox = h("div", { class: "mini" });
  const drawCast = () => castBox.replaceChildren(...(characters.length ? characters.map((c) =>
    h("div", { class: "c" + (f.cast.includes(c.id) ? " on" : ""), onclick: () => {
      f.cast = f.cast.includes(c.id) ? f.cast.filter((x) => x !== c.id) : [...f.cast, c.id]; drawCast(); } },
      h("div", { class: "av", style: c.pictures.face ? { backgroundImage: `url("${lib(c.pictures.face)}")` } : {} }), c.name))
    : [h("span", { class: "muted" }, "No characters yet - ", h("a", { href: "#/characters" }, "make your first character"), ". You can also write without a cast.")]));
  drawCast();
  const styleBox = h("div", { class: "styles" });
  const drawStyles = () => styleBox.replaceChildren(...Object.entries(STYLE_DESC).map(([k, d]) =>
    h("div", { class: "s" + (f.style === k ? " on" : ""), onclick: () => { f.style = k; drawStyles(); } },
      { cinematic: "Realistic cinematic", pixar: "3D Pixar cartoon", anime: "Anime", storybook: "Storybook", clay: "Claymation" }[k],
      h("div", { class: "d" }, d))));
  drawStyles();
  if (q.idea) f.idea = q.idea;
  const title = h("input", { value: f.title, placeholder: "e.g. The Paper Boat", oninput: (e) => (f.title = e.target.value) });
  const idea = h("textarea", { rows: 6, value: f.idea, placeholder: "What happens? Who wants what, what goes wrong, how does it end? A few sentences are enough - the story AI writes the scenes, and you can change every scene afterwards.", oninput: (e) => (f.idea = e.target.value) });
  const est = h("span", { class: "muted" });
  const setEst = () => (est.textContent = `${f.scenes_wanted} scenes ≈ ${fmtSec(f.scenes_wanted * 4.87)} video · about ${Math.round(f.scenes_wanted * 13 / 60 * 10) / 10} h to make`);
  setEst();
  const seasonSel = h("select", { onchange: (e) => {
    f.season_id = e.target.value; const s = seasons.find((x) => x.id === f.season_id);
    if (s) { f.kind = "episode"; f.style = s.style; f.cast = [...s.cast]; drawStyles(); drawCast(); kindSel.value = "episode"; } } },
  h("option", { value: "" }, "No season (single video)"), seasons.map((s) => h("option", { value: s.id, selected: s.id === f.season_id }, `${s.title} (${s.episodes.length} episodes)`)));
  const kindSel = h("select", { onchange: (e) => { f.kind = e.target.value; if (f.kind === "short" && f.scenes_wanted > 11) { f.scenes_wanted = 10; range.value = 10; setEst(); } } },
    h("option", { value: "episode", selected: f.kind === "episode" }, "Episode (16:9, about 1-2 min)"),
    h("option", { value: "video", selected: f.kind === "video" }, "Single video (16:9)"),
    h("option", { value: "short", selected: f.kind === "short" }, "Short story (under 1 min, also as 9:16)"));
  const range = h("input", { type: "range", min: 4, max: 30, value: f.scenes_wanted, oninput: (e) => { f.scenes_wanted = +e.target.value; setEst(); } });
  async function create(write) {
    if (write && !f.idea.trim()) return toast("Write the idea first (a few sentences)", true);
    const r = await safe(() => api("/projects", "POST", { ...f, title: f.title || (write ? "" : "Untitled video"), write,
      options: { approve_pictures: f.approve, music: f.music, music_prompt: f.music_prompt } }));
    if (r) { toast(write ? "Writing the story - it takes a few minutes" : "Video created"); go(`#/p/${r.project.id}/${write ? "story" : "storyboard"}`); }
  }
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, season ? `New episode of ${season.title}` : "New video"),
      h("div", { class: "sub" }, "Idea → story → pictures → acting videos with voices → checked final video, Short and YouTube kit."))),
    h("div", { class: "split" },
      h("div", {},
        h("div", { class: "card" },
          field("Title", title, "Leave empty and the story AI suggests one."),
          h("div", { class: "row2" }, field("Season", seasonSel), field("Type", kindSel)),
          field("Spoken language", langSelect(f.language, (v) => (f.language = v)),
            "The characters speak this language (lines in its own script, English meaning in the subtitles)."),
          field("Story idea", idea),
          h("div", { class: "ideas" }, h("span", { class: "dim", style: { alignSelf: "center", fontSize: "12px" } }, "Ready ideas:"),
            IDEAS.map((x) => h("button", { class: "small", onclick: () => { idea.value = f.idea = x.i; if (!f.title) title.value = f.title = x.t; } }, x.t)))),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Style"), styleBox),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Cast"),
          h("div", { class: "hint", style: { marginTop: 0, marginBottom: "10px" } }, "Characters with pictures stay the same in every scene. Give recurring side characters a character card too."),
          castBox)),
      h("div", {},
        h("div", { class: "card hl" },
          h("h3", {}, "Length"), range, h("div", { style: { marginTop: "6px" } }, est),
          h("div", { class: "sep" }),
          toggle("Let me check the pictures before the videos are made", f.approve, (v) => (f.approve = v)),
          toggle("Background music under the whole video", f.music, (v) => (f.music = v)),
          h("input", { placeholder: "Music style, e.g. gentle playful piano and strings", style: { marginTop: "6px" }, oninput: (e) => (f.music_prompt = e.target.value) }),
          h("div", { class: "sep" }),
          h("div", { class: "btns", style: { flexDirection: "column", alignItems: "stretch" } },
            h("button", { class: "primary big", style: { justifyContent: "center" }, onclick: () => create(true) }, icon("spark"), "Write story with AI"),
            h("button", { class: "big", style: { justifyContent: "center" }, onclick: () => create(false) }, icon("edit"), "I'll write the scenes myself"))),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "How Shri Tools keeps it right"),
          h("div", { class: "muted", style: { fontSize: "13px", lineHeight: 1.6 } },
            "• Each speaking scene is a close-up of one character with one short line - H3 lip-syncs best that way.", h("br"),
            "• Action scenes name loud sounds whose source is in the picture (no floating fans).", h("br"),
            "• Every clip is checked: right words, right language, no invented talking, not silent. Bad clips are made again and the best try is kept.", h("br"),
            "• The final video joins the clips themselves, so lips stay in sync.")))));
}

// ---------- MUSIC VIDEOS ----------
let MUSIC = {};
async function viewMusic() {
  const [{ characters }, opts] = await Promise.all([api("/characters"), api("/music/options")]);
  MUSIC = opts;
  const f = { title: "", language: "hi", genre: "bollywood_romantic", vocal: "female", mood: "", style: "pixar", setting: "",
    seconds: 60, idea: "", lyrics: "", singers: [], approve_pictures: true, new_singer: { name: "", look: "", pronoun: "she" } };
  const sel = (key, options) => h("select", { onchange: (e) => (f[key] = e.target.value) },
    Object.entries(options).map(([k, n]) => h("option", { value: k, selected: f[key] === k }, n)));
  const castBox = h("div", { class: "mini" });
  const drawCast = () => castBox.replaceChildren(...characters.map((c) =>
    h("div", { class: "c" + (f.singers.includes(c.id) ? " on" : ""), onclick: () => {
      f.singers = f.singers.includes(c.id) ? f.singers.filter((x) => x !== c.id) : [...f.singers, c.id]; drawCast(); } },
      h("div", { class: "av", style: c.pictures.face ? { backgroundImage: `url("${lib(c.pictures.face)}")` } : {} }), c.name)));
  drawCast();
  const est = h("span", { class: "muted" });
  const lenLabel = h("b", {}, fmtSec(f.seconds));
  const setEst = () => {
    const n = Math.ceil(f.seconds / 5.17);
    lenLabel.textContent = fmtSec(f.seconds);
    est.textContent = `${n} shots - about ${Math.round(n * 11 / 6) / 10} h of video making after the song`;
  };
  setEst();
  const list = S.projects.filter((p) => p.kind === "music");
  async function create() {
    if (!f.idea.trim() && !f.lyrics.trim()) return toast("Write what the song is about, or the lyrics", true);
    if (!f.singers.length && !f.new_singer.name.trim() && f.vocal !== "none") return toast("Pick a singer, or describe a new one", true);
    const r = await safe(() => api("/music", "POST", f));
    if (r) { toast("Making the song - then the shot pictures"); go(`#/p/${r.project.id}/song`); }
  }
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Music videos"),
      h("div", { class: "sub" }, "A song in any language (MiniMax Music 3), then your characters sing it with lip sync (MiniMax H3)."))),
    list.length ? h("div", { class: "grid projects", style: { marginBottom: "22px" } }, list.map(projectCard)) : null,
    h("div", { class: "split" },
      h("div", {},
        h("div", { class: "card" }, h("h3", {}, "New music video"),
          field("Title", h("input", { placeholder: "e.g. Tuntun ka Gaana (leave empty: the AI suggests one)", oninput: (e) => (f.title = e.target.value) })),
          field("What is the song about?", h("textarea", { rows: 3, placeholder: "e.g. Tuntun sings about his day in the colony and thanks everyone who helps", oninput: (e) => (f.idea = e.target.value) })),
          h("div", { class: "row2" }, field("Language", langSelect(f.language, (v) => (f.language = v))), field("Music style", sel("genre", opts.genres))),
          h("div", { class: "row2" }, field("Voice", sel("vocal", opts.vocals)),
            field("Mood", h("input", { placeholder: "happy, romantic, devotional, energetic...", oninput: (e) => (f.mood = e.target.value) }))),
          h("div", { class: "row2" }, field("Video style", sel("style", opts.styles)),
            field("Where it happens", h("input", { placeholder: "e.g. a colorful Indian colony street at sunset", oninput: (e) => (f.setting = e.target.value) }))),
          field("Lyrics (optional)", h("textarea", { rows: 6, placeholder: "Leave empty: the story AI writes them in the chosen language.\n[Verse]\n...\n[Chorus]\n...", oninput: (e) => (f.lyrics = e.target.value) }),
            "Write them in the language's own script. Tags like [Verse] [Chorus] [Instrumental] shape the song.")),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Singer"),
          h("div", { class: "hint", style: { marginTop: 0, marginBottom: "10px" } }, "Pick one (or two for a duet). Their picture keeps the face the same in every close-up."),
          castBox,
          h("div", { class: "sep" }),
          h("div", { class: "row2" },
            field("...or a new singer: name", h("input", { placeholder: "e.g. Meera", oninput: (e) => (f.new_singer.name = e.target.value) })),
            field("Looks like", h("input", { placeholder: "e.g. a young Indian woman, long braid, yellow saree", oninput: (e) => (f.new_singer.look = e.target.value) }))))),
      h("div", {},
        h("div", { class: "card hl" },
          h("h3", {}, "Length"),
          h("input", { type: "range", min: 30, max: 180, step: 10, value: f.seconds, oninput: (e) => { f.seconds = +e.target.value; setEst(); } }),
          h("div", { style: { marginTop: "6px" } }, lenLabel, " - ", est),
          h("div", { class: "sep" }),
          toggle("Let me check the pictures before the videos are made", f.approve_pictures, (v) => (f.approve_pictures = v)),
          h("div", { class: "sep" }),
          h("button", { class: "primary big", style: { justifyContent: "center", width: "100%" }, onclick: create }, icon("music"), "Make the song")),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Tips"),
          h("div", { class: "muted", style: { fontSize: "13px", lineHeight: 1.6 } },
            "- 60 seconds is a good first test (12 shots, about 2.5 hours).", h("br"),
            "- Indian languages: write lyrics in their own script; the song model sings them, H3 lip-syncs.", h("br"),
            "- Listen to the song first (Song tab). Not right? New take of the song, or edit the lyrics.", h("br"),
            "- Characters from your seasons (Tuntun, Shri Mama...) can be the singers.")))));
}

// ---------- CHARACTERS ----------
async function viewCharacters() {
  const { characters } = await api("/characters");
  const page = h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", { class: "grow" }, h("h1", {}, "Characters"),
      h("div", { class: "sub" }, "Each character gets a full-body and a face picture. Every scene uses them, so faces and clothes stay the same.")),
      h("button", { class: "primary", onclick: () => characterForm(null, () => route()) }, icon("plus"), "New character")),
    characters.length ? h("div", { class: "grid chars" }, characters.map((c) => characterCard(c, () => route())))
      : h("div", { class: "empty" }, h("h3", {}, "No characters yet"), "Create one from a description - or from photos of a real person (like you)."));
  if (characters.some((c) => ["waiting", "running"].includes(c.job.state))) S.poll = setInterval(async () => {
    const r = await api("/characters").catch(() => null);
    if (r && !r.characters.some((c) => ["waiting", "running"].includes(c.job.state))) route();
    else if (r) $(".grid.chars", page)?.replaceChildren(...r.characters.map((c) => characterCard(c, () => route())));
  }, 5000);
  return page;
}
function characterCard(c, after, opts = {}) {
  const busy = ["waiting", "running"].includes(c.job.state);
  const pic = (v, label) => h("div", { style: c.pictures[v] ? { backgroundImage: `url("${lib(c.pictures[v])}")` } : {} },
    c.pictures[v] ? null : busy ? h("span", { class: "spin" }) : label);
  return h("div", { class: "ccard" + (opts.pick ? " pick" : "") + (opts.on ? " on" : ""), onclick: opts.onclick },
    h("div", { class: "pics" }, pic("front", "No full-body picture"), pic("face", "No face picture")),
    h("div", { class: "body" },
      h("div", { class: "nm" }, c.name, h("span", { class: "chip" }, c.tag),
        busy ? h("span", { class: "pill run" }, c.job.state === "running" ? "Drawing" : "Waiting") : null,
        c.job.state === "failed" ? h("span", { class: "pill red", title: c.job.error || "" }, "Failed") : null),
      h("div", { class: "lk" }, c.look || h("span", { class: "dim" }, "No description")),
      c.voice ? h("div", { class: "lk", style: { marginTop: "6px" } }, "🎙 ", c.voice) : null),
    opts.pick ? null : h("div", { class: "acts" },
      h("button", { class: "small" + (c.pictures.front ? "" : " outline"), disabled: busy, onclick: async () => {
        if (c.pictures.front && !confirm(`Draw new pictures for ${c.name}? Scenes made later use the new look.`)) return;
        await safe(() => api(`/characters/${c.id}/make`, "POST", { force: !!c.pictures.front }), "Drawing - about 2 minutes"); after(); } },
      icon("redo"), c.pictures.front ? "Draw again" : "Draw pictures"),
      h("button", { class: "small", onclick: () => characterForm(c, after) }, icon("edit"), "Edit"),
      opts.remove ? h("button", { class: "small danger", onclick: opts.remove }, icon("x"), "Remove") : null));
}
function characterForm(c, after, extra = {}) {
  const f = { name: c?.name || "", look: c?.look || "", voice: c?.voice || "", pronoun: c?.pronoun || "he", style: c?.style || extra.style || "" };
  const photos = h("input", { type: "file", accept: "image/*", multiple: true });
  const own = { front: h("input", { type: "file", accept: "image/*" }), face: h("input", { type: "file", accept: "image/*" }) };
  let makeNow = true;
  const close = modal(c ? `Edit ${c.name}` : "New character", h("div", {},
    h("div", { class: "row2" },
      field("Name", h("input", { value: f.name, placeholder: "e.g. Pip", oninput: (e) => (f.name = e.target.value) }), "In scenes you write @" + "Name."),
      field("He / she / they", h("select", { onchange: (e) => (f.pronoun = e.target.value) },
        ["he", "she", "they"].map((p) => h("option", { value: p, selected: f.pronoun === p }, p))))),
    field("Look", h("textarea", { rows: 3, value: f.look, placeholder: "a tiny orange fox cub with huge sparkling blue eyes, fluffy white-tipped tail, small green scarf", oninput: (e) => (f.look = e.target.value) }),
      "Age, body, hair, face, clothes, colors - the same words are used for every picture."),
    field("Voice", h("input", { value: f.voice, placeholder: "a small, high-pitched, cheerful young boy's voice", oninput: (e) => (f.voice = e.target.value) }),
      "H3 makes the voice from these words. Keep them the same for the whole season."),
    field("Style", h("select", { onchange: (e) => (f.style = e.target.value) },
      h("option", { value: "" }, "Same as the video"), Object.entries(STYLE_DESC).map(([k]) => h("option", { value: k, selected: f.style === k }, k)))),
    field("Photos of a real person (optional)", photos, "For a character based on a real person (like you): 1-3 clear photos of the face. Only these photos are used."),
    h("div", { class: "row2" }, field("Or use my own full-body picture", own.front), field("Or my own face picture", own.face)),
    toggle(c ? "Draw new pictures after saving" : "Draw the pictures now (about 2 minutes)", c ? (makeNow = false) : true, (v) => (makeNow = v)),
    h("div", { class: "btns", style: { marginTop: "14px" } },
      h("button", { class: "primary", onclick: save }, icon("check"), "Save"),
      c ? h("button", { class: "danger", onclick: async () => {
        if (!confirm(`Delete ${c.name}? (moved to the library trash)`)) return;
        await safe(() => api(`/characters/${c.id}`, "DELETE")); close(); after(); } }, icon("trash"), "Delete") : null)));
  async function save() {
    if (!f.name.trim()) return toast("Give the character a name", true);
    const r = await safe(() => c ? api(`/characters/${c.id}`, "PATCH", f) : api("/characters", "POST", { ...f, season_id: extra.season_id }));
    if (!r) return;
    const id = r.character.id;
    if (photos.files.length) {
      const fd = new FormData(); for (const x of photos.files) fd.append("file", x, x.name);
      await safe(() => api(`/characters/${id}/photos`, "POST", fd));
    }
    for (const v of ["front", "face"]) if (own[v].files.length) {
      const fd = new FormData(); fd.append("file", own[v].files[0], own[v].files[0].name);
      await safe(() => api(`/characters/${id}/picture?view=${v}`, "POST", fd));
    }
    if (makeNow) await safe(() => api(`/characters/${id}/make`, "POST", { force: !!c }));
    toast(makeNow ? "Saved - drawing the pictures" : "Saved");
    close();
    after(r.character);
  }
}

// ---------- SEASONS ----------
async function viewSeasons() {
  const { seasons } = await api("/seasons");
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", { class: "grow" }, h("h1", {}, "Seasons"),
      h("div", { class: "sub" }, "A season keeps one style and one cast, and the story AI remembers the earlier episodes.")),
      h("button", { class: "primary", onclick: () => seasonForm(null) }, icon("plus"), "New season")),
    seasons.length ? h("div", { class: "grid projects" }, seasons.map((s) => {
      const cover = s.episode_list.find((e) => e.cover)?.cover;
      return h("div", { class: "pcard", onclick: () => go(`#/season/${s.id}`) },
        h("div", { class: "cover", style: cover ? { backgroundImage: `url("${lib(cover)}")` } : {} }, cover ? null : icon("tv"),
          h("div", { class: "state" }, h("span", { class: "pill g" }, STYLE_DESC[s.style] ? s.style : ""))),
        h("div", { class: "body" }, h("div", { class: "t" }, s.title),
          h("div", { class: "m" }, `${plural(s.episodes.length, "episode")} · ${plural(s.cast.length, "character")}`)));
    })) : h("div", { class: "empty" }, h("h3", {}, "No seasons yet"), "Start one - e.g. “Pip and Toby” in 3D Pixar style."));
}
async function seasonForm(s) {
  const { characters } = await api("/characters");
  const f = { title: s?.title || "", style: s?.style || "pixar", about: s?.about || "", cast: s ? [...s.cast] : [] };
  const box = h("div", { class: "mini" });
  const draw = () => box.replaceChildren(...characters.map((c) => h("div", { class: "c" + (f.cast.includes(c.id) ? " on" : ""),
    onclick: () => { f.cast = f.cast.includes(c.id) ? f.cast.filter((x) => x !== c.id) : [...f.cast, c.id]; draw(); } },
  h("div", { class: "av", style: c.pictures.face ? { backgroundImage: `url("${lib(c.pictures.face)}")` } : {} }), c.name)));
  draw();
  const close = modal(s ? "Edit season" : "New season", h("div", {},
    field("Title", h("input", { value: f.title, placeholder: "Pip and Toby", oninput: (e) => (f.title = e.target.value) })),
    field("Style", h("select", { onchange: (e) => (f.style = e.target.value) }, Object.entries(STYLE_DESC).map(([k, d]) => h("option", { value: k, selected: f.style === k }, `${k} - ${d}`)))),
    field("About the season", h("textarea", { rows: 3, value: f.about, placeholder: "Where it happens, the main characters, the kind of stories", oninput: (e) => (f.about = e.target.value) })),
    h("h3", {}, "Cast"), characters.length ? box : h("div", { class: "muted" }, "Make characters first (Characters page)."),
    h("div", { class: "btns", style: { marginTop: "16px" } }, h("button", { class: "primary", onclick: async () => {
      if (!f.title.trim()) return toast("Give the season a title", true);
      const r = await safe(() => s ? api(`/seasons/${s.id}`, "PATCH", f) : api("/seasons", "POST", f));
      if (r) { close(); go(`#/season/${r.season.id}`); route(); } } }, icon("check"), "Save"))));
}
async function viewSeason(id) {
  const { season, episodes, cast } = await api(`/seasons/${id}`);
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", { class: "grow" },
      h("div", { class: "chips" }, h("span", { class: "chip g" }, "Season"), h("span", { class: "chip" }, STYLE_DESC[season.style] || season.style)),
      h("h1", { style: { marginTop: "8px" } }, season.title), season.about ? h("div", { class: "sub" }, season.about) : null),
      h("button", { onclick: () => seasonForm(season) }, icon("edit"), "Edit"),
      h("button", { class: "primary", onclick: () => go(`#/create?season=${season.id}`) }, icon("plus"), "New episode")),
    h("h2", {}, "Episodes"),
    h("div", { class: "grid projects" }, episodes.map(projectCard),
      h("div", { class: "pcard new", onclick: () => go(`#/create?season=${season.id}`) }, h("div", { style: { display: "grid", placeItems: "center", gap: "8px" } }, icon("plus"), `Episode ${episodes.length + 1}`))),
    h("div", { class: "page-h", style: { marginTop: "26px" } }, h("h2", { class: "grow", style: { margin: 0 } }, "Ideas for the next episodes"),
      h("button", { onclick: async () => {
        const r = await safe(() => api(`/seasons/${season.id}/ideas`, "POST"));
        if (r) toast("The story AI writes 10 ideas as soon as the graphics card is free (between jobs) - they appear here");
      } }, icon("spark"), (season.ideas || []).length ? "10 new ideas" : "Give me 10 ideas")),
    (season.ideas || []).length ? h("div", { class: "grid projects" }, season.ideas.map((x) =>
      h("div", { class: "card", style: { display: "flex", flexDirection: "column", gap: "8px" } },
        h("b", {}, x.title), h("div", { class: "muted", style: { fontSize: "13px", flex: 1 } }, x.idea),
        x.hook ? h("div", { class: "dim", style: { fontSize: "12.5px" } }, "Hook: " + x.hook) : null,
        h("button", { class: "small primary", onclick: () => go(`#/create?season=${season.id}&title=${encodeURIComponent(x.title)}&idea=${encodeURIComponent(x.idea + (x.hook ? " Hook: " + x.hook : ""))}`) },
          icon("plus"), "Make this episode"))))
      : h("div", { class: "muted" }, "No ideas yet."),
    h("h2", {}, "Cast"),
    cast.length ? h("div", { class: "grid chars" }, cast.map((c) => characterCard(c, () => route()))) : h("div", { class: "muted" }, "No cast yet - Edit the season to add characters."));
}

// ---------- PROJECT ----------
const TABS = [["story", "book", "Story"], ["cast", "users", "Cast"], ["storyboard", "grid", "Storyboard"], ["build", "hammer", "Build"],
  ["video", "play", "Video"], ["shorts", "phone", "Shorts"], ["publish", "yt", "Publish"]];

async function viewProject(id, tab) {
  const P = { id, tab, data: await api(`/projects/${id}`), keys: {} };
  if (P.data.project.kind === "music" && tab === "story") P.tab = tab = "song";
  if (P.data.project.kind !== "music" && tab === "song") P.tab = tab = "story";
  if (P.data.project.kind === "music" && !MUSIC.genres) MUSIC = await api("/music/options").catch(() => ({}));
  S.view = P;
  const head = h("div");
  const tabs = h("div", { class: "tabs" });
  const body = h("div");
  P.head = head; P.body = body;
  const draw = (force) => {
    drawHead(P);
    const d = P.data, n = d.project.scenes.length;
    const pics = Object.values(d.files).filter((f) => f.picture).length, clips = Object.values(d.files).filter((f) => f.clip).length;
    const tabList = d.project.kind === "music" ? [["song", "music", "Song"], ...TABS.filter(([k]) => k !== "story")] : TABS;
    tabs.replaceChildren(...tabList.map(([k, ic, t]) => h("a", { href: `#/p/${id}/${k}`, class: tab === k ? "on" : "" }, icon(ic), t,
      k === "storyboard" && n ? h("span", { class: "n" }, n) : null, k === "build" && n && clips < n ? h("span", { class: "n" }, `${clips}/${n}`) : null)));
    const key = tabKey(P);
    if (force || key !== P.keys[tab]) {
      if (!force && (tab === "story" || tab === "song" || tab === "publish") && document.activeElement && body.contains(document.activeElement)) return;
      P.keys[tab] = key;
      const st = body.scrollTop;
      body.replaceChildren(TAB_VIEWS[tab](P));
    }
  };
  P.draw = draw;
  P.reload = async () => { P.data = await api(`/projects/${id}`); draw(); refreshSide(); };
  draw(true);
  S.poll = setInterval(async () => {
    const d = await api(`/projects/${id}`).catch(() => null);
    if (!d || S.view !== P) return;
    P.data = d; draw();
  }, 3000);
  return h("div", { class: "page" }, head, tabs, body);
}
function tabKey(P) {
  const d = P.data;
  const live = { st: d.status.state, f: d.files, r: d.results, o: d.outputs, q: d.queue.length, sc: d.project.scenes, c: d.cast.map((c) => [c.pictures, c.job]) };
  switch (P.tab) {
    case "build": return JSON.stringify([live, d.status.label, d.status.log, d.project.options]);
    case "story": return JSON.stringify([d.project.scenes, d.project.idea, d.project.title, d.status.state]);
    case "song": return JSON.stringify([d.project.music, d.outputs["song.wav"], d.status.state, d.status.label, d.project.scenes.length]);
    case "video": case "shorts": return JSON.stringify([d.outputs, d.results, d.status.state, d.publish.short, d.project.scenes.length]);
    case "publish": return JSON.stringify([d.outputs, d.publish.made, d.publish.thumbnails, d.status.state]);
    default: return JSON.stringify(live);
  }
}
function drawHead(P) {
  const d = P.data, p = d.project, st = d.status, busy = ["running", "waiting"].includes(st.state) || d.queue.length;
  const n = p.scenes.length, lines = p.scenes.filter((s) => s.kind === "talk").length;
  const clips = Object.values(d.files).filter((f) => f.clip).length;
  const passed = Object.values(d.results).filter((r) => r.qc && r.qc.ok).length;
  const title = h("div", { class: "title", contenteditable: "true", spellcheck: "false",
    onblur: async (e) => { const t = e.target.textContent.trim(); if (t && t !== p.title) { await safe(() => api(`/projects/${p.id}`, "PATCH", { title: t }), "Renamed"); P.reload(); } },
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); e.target.blur(); } } }, p.title);
  if (P.head.contains(document.activeElement)) return;
  let actions;
  if (busy) actions = [h("button", { class: "danger", onclick: async () => { if (confirm("Stop the work on this video? Finished pictures and videos are kept.")) { await safe(() => api(`/projects/${p.id}/cancel`, "POST"), "Stopped"); P.reload(); } } }, icon("stop"), "Stop")];
  else if (!n) actions = [h("button", { class: "primary", onclick: () => go(`#/p/${p.id}/story`) }, icon("spark"), "Write the story")];
  else if (st.state === "approve") actions = [h("button", { class: "", onclick: () => go(`#/p/${p.id}/storyboard`) }, icon("grid"), "Check pictures"),
    h("button", { class: "primary", onclick: () => run(P, "approve", null, "Making the videos - about 13 min per scene") }, icon("video"), "Pictures OK - make videos")];
  else actions = [d.outputs["final.mp4"] ? h("button", { onclick: () => go(`#/p/${p.id}/video`) }, icon("play"), "Watch") : null,
    h("button", { class: "primary", onclick: () => {
      const missing = n - clips;
      if (!missing && !confirm("All scenes have videos. Run the check, final video and publish kit again?")) return;
      run(P, missing ? "build" : "finish", null, missing ? "Building" : "Making the final video and kit"); } },
    icon("play"), clips < n ? (clips ? "Continue building" : "Build everything") : "Finish again")];
  const pct = st.total ? Math.round((100 * (st.done || 0)) / st.total) : null;
  P.head.replaceChildren(h("div", { class: "ph" },
    h("div", { class: "grow" },
      h("div", { class: "chips" },
        d.season ? h("a", { class: "chip g", href: `#/season/${d.season.id}` }, `${d.season.title}${p.episode ? " · Episode " + p.episode : ""}`) : h("span", { class: "chip" }, p.kind),
        h("span", { class: "chip" }, d.styles[p.style] || p.style), h("span", { class: "chip" }, "MiniMax H3 voices"),
        p.imported ? h("span", { class: "chip amber" }, "imported") : null),
      title,
      h("div", { class: "chips" }, h("span", { class: "stat" }, plural(n, "scene")), h("span", { class: "stat" }, plural(lines, "line")),
        h("span", { class: "stat" }, `≈ ${fmtSec(n * 4.87)}`), h("span", { class: "stat" }, `${clips}/${n} videos`),
        clips ? h("span", { class: "stat" }, `${passed}/${clips} checked OK`) : null)),
    h("div", { class: "btns" }, actions)),
  busy || ["failed", "approve"].includes(st.state) ? h("div", {},
    busy ? h("div", { class: "progress" + (pct === null ? " indet" : "") }, h("div", { style: { width: (pct || 0) + "%" } })) : h("div", { style: { height: "14px" } }),
    h("div", { class: "statusline" },
      busy ? h("span", { class: "spin" }) : null, statePill(st.state),
      h("b", {}, st.state === "waiting" || (!st.state && d.queue.length) ? "Waiting for the current job to finish" : st.label || ""),
      st.eta_min ? h("span", {}, `· about ${st.eta_min >= 60 ? Math.floor(st.eta_min / 60) + " h " : ""}${st.eta_min % 60} min left`) : null,
      st.state === "failed" ? h("span", { style: { color: "var(--red)" } }, st.error || "") : null)) : null);
}
async function run(P, action, scenes, msg) {
  const r = await safe(() => api(`/projects/${P.id}/run`, "POST", { action, scenes }));
  if (r) { toast(msg || "Started"); P.reload(); }
}
async function saveScenes(P, scenes, msg) {
  const r = await safe(() => api(`/projects/${P.id}/scenes`, "PUT", { scenes }), msg);
  if (r) await P.reload();
  return r;
}

// "@ShriMama" -> "Shri Mama" (the cast's real names) for reading
function untag(P, t) {
  const names = Object.fromEntries((P.data.cast || []).map((c) => [c.tag.toLowerCase(), c.name]));
  return (t || "").replace(/@(\w+)/g, (m, w) => names["@" + w.toLowerCase()] || w);
}

// ----- Song tab (music videos) -----
function tabSong(P) {
  const d = P.data, p = d.project, m = { ...(p.music || {}) }, busy = ["running", "waiting"].includes(d.status.state);
  const has = d.outputs["song.wav"];
  const lyr = h("textarea", { rows: 14, value: m.lyrics || "", placeholder: "Leave empty and the story AI writes them in the song's language.\n[Verse]\n...\n[Chorus]\n...", oninput: (e) => (m.lyrics = e.target.value) });
  const cap = h("textarea", { rows: 7, value: m.caption || "", placeholder: "Global Metadata: ...\n\nVocal Details: ...\n\nArrangement: ...", oninput: (e) => (m.caption = e.target.value) });
  const save = () => safe(() => api(`/projects/${p.id}`, "PATCH", { music: m }), "Saved");
  return h("div", { class: "split" },
    h("div", {},
      h("div", { class: "card" },
        field("Lyrics (with [Verse] [Chorus] tags)", lyr, `Sung in ${langName(p.language)}. The tags shape the song; [Instrumental] makes a music-only part.`),
        field("Music description (English)", cap, "Three parts: Global Metadata (style, BPM, mood), Vocal Details (voice, language), Arrangement (instruments per section)."),
        h("div", { class: "btns" },
          h("button", { onclick: async () => { await save(); P.reload(); } }, icon("check"), "Save"),
          h("button", { class: "primary", disabled: busy, onclick: async () => { await save(); run(P, has ? "song" : "build", null, has ? "New take of the song" : "Making the song"); } },
            icon("music"), has ? "New take of the song" : "Make the song"),
          has ? h("button", { disabled: busy, onclick: () => { if (confirm("Plan the shots again? New pictures and videos are made for every shot.")) run(P, "plan", null, "Planning the shots"); } }, icon("grid"), "Plan shots again") : null))),
    h("div", {},
      h("div", { class: "card hl" }, h("h3", {}, "The song"),
        has ? h("audio", { controls: true, src: lib(`projects/${p.id}/output/song.wav?v=${has}`), style: { width: "100%" } })
          : h("div", { class: "muted" }, busy ? "Being made..." : "Not made yet."),
        h("div", { class: "kv", style: { marginTop: "12px" } },
          h("div", { class: "k" }, "Style"), h("div", {}, (MUSIC.genres || {})[m.genre] || m.genre || "-"),
          h("div", { class: "k" }, "Voice"), h("div", {}, (MUSIC.vocals || {})[m.vocal] || m.vocal || "-"),
          h("div", { class: "k" }, "Language"), h("div", {}, langName(p.language)),
          h("div", { class: "k" }, "Length"), h("div", {}, m.song_seconds ? `${fmtSec(m.song_seconds)} (asked ${fmtSec(m.seconds)})` : `about ${fmtSec(m.seconds || 60)}`),
          h("div", { class: "k" }, "Shots"), h("div", {}, p.scenes.length ? `${p.scenes.length} (${p.scenes.filter((s) => s.kind === "sing").length} singing)` : "after the song"))),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "How it is made"),
        h("div", { class: "muted", style: { fontSize: "13px", lineHeight: 1.6 } },
          "1. MiniMax Music 3 makes the song from the lyrics and the description.", h("br"),
          "2. Whisper finds where words are sung; the song is cut into 5.2-second shots.", h("br"),
          "3. Sung parts: the singer in close-up. Music parts: story and dance shots.", h("br"),
          "4. Each shot is an H3 clip guided by its own piece of the song, so lips and moves follow the music.", h("br"),
          "5. The shots are joined under the original song."))));
}

// ----- dubbing: the same episode in another language -----
function dubDialog(P) {
  const p = P.data.project, talk = p.scenes.filter((s) => s.kind === "talk").length;
  let lang = (LANGS.find(([k]) => k !== (p.language || "en")) || LANGS[1])[0];
  const close = modal("Make it in another language", h("div", {},
    h("div", { class: "muted", style: { marginBottom: "14px", lineHeight: 1.6 } },
      `A copy of “${p.title}” in another language. All ${p.scenes.length} pictures and the ${p.scenes.length - talk} action scenes are reused; `,
      `the story AI translates the ${talk} spoken lines and only those ${talk} talking scenes are made again (about ${Math.round(talk * 11 / 6) / 10} h).`),
    field("Language", langSelect(lang, (v) => (lang = v))),
    h("div", { class: "btns", style: { marginTop: "16px" } },
      h("button", { class: "primary", onclick: async () => {
        const r = await safe(() => api(`/projects/${p.id}/dub`, "POST", { language: lang }));
        if (r) { close(); toast(`Making the ${langName(lang).split(" - ")[0]} version`); go(`#/p/${r.project.id}/storyboard`); } } },
        icon("redo"), "Make this language version"))));
}

// ----- Story tab -----
function tabStory(P) {
  const p = P.data.project, busy = ["running", "waiting"].includes(P.data.status.state);
  const f = { idea: p.idea, logline: p.logline || "", hook_text: p.hook_text || "", style: p.style, scenes_wanted: p.scenes_wanted, language: p.language || "en" };
  const writing = busy && (P.data.status.stage === "write" || (P.data.queue[0] || {}).steps?.includes("write"));
  const script = p.scenes.map((s, i) => h("div", { style: { padding: "10px 0", borderBottom: "1px solid var(--line)" } },
    h("div", { class: "dim", style: { fontSize: "11.5px", fontWeight: 700, letterSpacing: "1px" } }, `SCENE ${i + 1} · ${s.kind === "talk" ? "TALK" : "ACTION"}${i === 0 ? " · HOOK" : ""}`),
    s.kind === "talk" ? h("div", { style: { margin: "4px 0" } }, h("b", { class: "green" }, s.speaker), h("span", { class: "muted" }, ` (${s.tone || "says"}) `), h("b", {}, `“${s.line}”`),
      s.line_en ? h("span", { class: "muted" }, ` - ${s.line_en}`) : null) : null,
    h("div", { class: "muted", style: { fontSize: "13px" } }, untag(P, s.action || s.picture))));
  return h("div", { class: "split" },
    h("div", {},
      h("div", { class: "card" },
        field("Story idea", h("textarea", { rows: 7, value: f.idea, oninput: (e) => (f.idea = e.target.value) })),
        field("One-line story (logline)", h("input", { value: f.logline, oninput: (e) => (f.logline = e.target.value) })),
        field("Hook words", h("input", { value: f.hook_text, placeholder: "e.g. WHAT DID TUNTUN SAY?", oninput: (e) => (f.hook_text = e.target.value) }),
          "Scene 1 is the hook shot. These words go on the Short and the first thumbnail."),
        h("div", { class: "row2" },
          field("Style", h("select", { onchange: (e) => (f.style = e.target.value) }, Object.entries(P.data.styles).map(([k, n]) => h("option", { value: k, selected: f.style === k }, n))),
            "Changing it affects new pictures only."),
          field("Scenes to write", h("input", { type: "number", min: 4, max: 30, value: f.scenes_wanted, oninput: (e) => (f.scenes_wanted = +e.target.value) }))),
        field("Spoken language", langSelect(f.language, (v) => (f.language = v)),
          "For the story AI and for every scene that has no language of its own. Changing it affects new videos only."),
        h("div", { class: "btns" },
          h("button", { onclick: async () => { await safe(() => api(`/projects/${p.id}`, "PATCH", f), "Saved"); P.reload(); } }, icon("check"), "Save"),
          h("button", { class: "primary", disabled: busy, onclick: async () => {
            if (!f.idea.trim()) return toast("Write the idea first", true);
            if (p.scenes.length && !confirm("Write the whole story again? All scenes are replaced (pictures and videos already made stay in the folder).")) return;
            await api(`/projects/${p.id}`, "PATCH", f);
            run(P, "write", null, "Writing the story - a few minutes"); } }, icon("spark"), p.scenes.length ? "Write again with AI" : "Write story with AI"),
          p.scenes.length ? h("button", { onclick: () => dubDialog(P) }, icon("redo"), "Make it in another language") : null)),
      writing ? h("div", { class: "card hl", style: { marginTop: "16px", display: "flex", gap: "12px", alignItems: "center" } }, h("span", { class: "spin" }),
        h("div", {}, h("b", {}, "The story AI is writing your scenes…"), h("div", { class: "muted" }, "On this laptop it takes about 5-15 minutes. You can leave this page."))) : null),
    h("div", { class: "card" }, h("h3", {}, "Script"), p.scenes.length ? script : h("div", { class: "muted" }, "No scenes yet.")));
}

// ----- Cast tab -----
function tabCast(P) {
  const p = P.data.project;
  const wrap = h("div", {}, h("div", { class: "muted" }, "Loading…"));
  api("/characters").then(({ characters }) => {
    const inCast = P.data.cast;
    const others = characters.filter((c) => !p.cast.includes(c.id));
    const setCast = async (ids) => { await safe(() => api(`/projects/${p.id}`, "PATCH", { cast: ids })); P.reload(); };
    const missing = inCast.filter((c) => !c.pictures.front || !c.pictures.face).length;
    wrap.replaceChildren(
      h("div", { class: "page-h" }, h("div", { class: "grow" }, h("div", { class: "sub" }, "Write @Name in a scene to put that character in it. Their pictures are the reference for every scene.")),
        missing ? h("button", { class: "outline", onclick: () => run(P, "sheets", null, "Drawing character pictures") }, icon("redo"), `Draw ${plural(missing, "missing character")}`) : null,
        h("button", { class: "primary", onclick: () => characterForm(null, async (c) => { if (c) await setCast([...p.cast, c.id]); }, { style: "" }) }, icon("plus"), "New character")),
      inCast.length ? h("div", { class: "grid chars" }, inCast.map((c) => characterCard(c, () => P.reload(), { remove: () => setCast(p.cast.filter((x) => x !== c.id)) })))
        : h("div", { class: "empty" }, h("h3", {}, "No cast yet"), "Add characters from your library or make a new one."),
      others.length ? h("h2", {}, "Add from your library") : null,
      others.length ? h("div", { class: "mini" }, others.map((c) => h("div", { class: "c", onclick: () => setCast([...p.cast, c.id]) },
        h("div", { class: "av", style: c.pictures.face ? { backgroundImage: `url("${lib(c.pictures.face)}")` } : {} }), "+ " + c.name))) : null);
  });
  return wrap;
}

// ----- Storyboard tab -----
function tabStoryboard(P) {
  const d = P.data, p = d.project, busy = ["running", "waiting"].includes(d.status.state);
  if (!p.scenes.length) return h("div", { class: "empty" }, h("h3", {}, "No scenes yet"),
    h("div", { style: { marginBottom: "14px" } }, "Let the story AI write them, or add scenes yourself."),
    h("div", { class: "btns", style: { justifyContent: "center" } },
      h("button", { class: "primary", onclick: () => go(`#/p/${p.id}/story`) }, icon("spark"), "Write with AI"),
      h("button", { onclick: () => sceneForm(P, null) }, icon("plus"), "Add a scene")));
  const working = d.status.state === "running" ? d.status.stage : null;
  return h("div", {},
    d.status.state === "approve" ? h("div", { class: "card hl", style: { marginBottom: "16px", display: "flex", gap: "14px", alignItems: "center", flexWrap: "wrap" } },
      h("div", { style: { flex: 1, minWidth: "260px" } }, h("b", {}, "Pictures are ready - check them."),
        h("div", { class: "muted" }, "Wrong face, extra person, odd object? Press “New picture” on that scene (or edit its text first). When all look right, make the videos.")),
      h("button", { class: "primary", onclick: () => run(P, "approve", null, "Making the videos") }, icon("video"), "Pictures OK - make videos")) : null,
    h("div", { class: "grid scenes" }, p.scenes.map((s, i) => sceneCard(P, s, i, busy, working)),
      h("div", { class: "addscene", onclick: () => sceneForm(P, null) }, h("div", { style: { display: "grid", placeItems: "center", gap: "6px" } }, icon("plus"), "Add scene"))));
}
function sceneCard(P, s, i, busy, working) {
  const d = P.data, p = d.project, f = d.files[s.id] || {}, r = d.results[s.id] || {}, qc = r.qc;
  const base = `projects/${P.id}`;
  const img = f.picture ? `url("${lib(`${base}/pictures/${s.id}.png?v=${f.picture}`)}")` : null;
  const warn = [];
  if (s.kind === "talk" && words(s.line) > 12) warn.push("long line");
  if (s.kind === "action" && !s.sounds) warn.push("no sounds named");
  return h("div", { class: "scene" },
    h("div", { class: "img", style: img ? { backgroundImage: img } : {} },
      f.picture ? null : (working === "pictures" ? h("span", { class: "spin" }) : "No picture yet"),
      h("div", { class: "tl" }, h("span", { class: "pill" }, `${i + 1}`), h("span", { class: "pill " + (s.kind !== "action" ? "g" : "") }, { talk: "Talk", sing: "Sing" }[s.kind] || "Action"),
        s.start != null && s.start !== "" ? h("span", { class: "pill" }, fmtSec(s.start)) : null,
        i === 0 ? h("span", { class: "pill amber" }, "Hook") : null),
      h("div", { class: "tr" },
        f.clip ? h("span", { class: "pill g" }, "Video") : null,
        r.clip_outdated ? h("span", { class: "pill amber", title: "The picture changed after this video was made" }, "Old video") : null),
      f.clip ? h("div", { class: "play", onclick: () => openVideo(lib(`${base}/clips/${s.id}.mp4?v=${f.clip}`), `Scene ${i + 1}`) }, h("span", {}, icon("play", "i"))) : null),
    h("div", { class: "txt" },
      s.kind !== "action" && s.line ? h("div", { class: "line" }, h("span", { class: "who" }, s.speaker || "?"), ` “${s.line}”`,
        (s.language || p.language || "en") !== "en" ? h("span", { class: "dim" }, ` · ${langName(s.language || p.language).split(" - ")[0]}`) : null) : null,
      s.line_en ? h("div", { class: "act" }, s.line_en) : null,
      h("div", { class: "act" }, untag(P, s.action || s.picture))),
    qc || warn.length ? h("div", { class: "qc" },
      qc ? (qc.ok ? h("span", { class: "chip g" }, icon("check"), "Checked") : h("span", { class: "chip red", title: `heard: ${qc.heard || ""}` }, icon("x"), qc.problems.join(", "))) : null,
      warn.map((w) => h("span", { class: "chip amber", style: { marginLeft: "4px" } }, w))) : null,
    h("div", { class: "acts" },
      h("button", { class: "small ghost", title: "Edit the scene", onclick: () => sceneForm(P, s) }, icon("edit"), "Edit"),
      h("button", { class: "small ghost", title: "Draw a new picture", disabled: busy, onclick: () => {
        if (f.clip && !confirm("A new picture also makes a new video for this scene (about 13 min). Go?")) return;
        run(P, "pictures", [s.id], "New picture" + (f.clip ? " and video" : "")); } }, icon("image"), "Picture"),
      h("button", { class: "small ghost", title: "Make the video again (new take)", disabled: busy || !f.picture, onclick: () => run(P, "videos", [s.id], "New video - about 13 min") }, icon("video"), "Video")));
}
function sceneForm(P, s) {
  const p = P.data.project, isNew = !s;
  const f = s ? { camera: "", ...s } : { id: "", kind: "action", picture: "", action: "", speaker: "", line: "", tone: "says", sounds: "", camera: "" };
  const names = P.data.cast.map((c) => c.name);
  const tags = P.data.cast.map((c) => c.tag);
  const pic = h("textarea", { rows: 4, value: f.picture, oninput: (e) => { f.picture = e.target.value; check(); } });
  const lineIn = h("input", { value: f.line, placeholder: "one short line, at most 10 words (in the scene's language and script)", oninput: (e) => { f.line = e.target.value; check(); } });
  const sounds = h("input", { value: f.sounds, placeholder: "rain drums on the tin roof, his boots splash in the puddle", oninput: (e) => { f.sounds = e.target.value; check(); } });
  const warnBox = h("div");
  const talkBox = h("div", {},
    h("div", { class: "row3" },
      field("Who speaks", h("select", { onchange: (e) => (f.speaker = e.target.value) }, h("option", { value: "" }, "-"), names.map((n) => h("option", { value: n, selected: f.speaker === n }, n)))),
      field("How", h("input", { value: f.tone, placeholder: "says warmly / whispers / shouts", oninput: (e) => (f.tone = e.target.value) })),
      field("Language", langSelect(f.language || "", (v) => (f.language = v), true))),
    field("Line", lineIn),
    field("English meaning (subtitles)", h("input", { value: f.line_en || "", placeholder: "only for Indian-language lines", oninput: (e) => (f.line_en = e.target.value) })));
  const kindBtns = h("div", { class: "btns" });
  const drawKind = () => {
    const kinds = p.kind === "music" ? ["sing", "action"] : ["talk", "action"];
    kindBtns.replaceChildren(...kinds.map((k) => h("button", { class: f.kind === k ? "outline" : "", onclick: () => { f.kind = k; drawKind(); check(); } },
      { talk: "Talk - one character speaks", sing: "Sing - the singer in close-up", action: p.kind === "music" ? "Story / dance - no singing" : "Action - no words" }[k])));
    talkBox.style.display = f.kind !== "action" ? "" : "none";
  };
  function check() {
    const w = [];
    if (f.kind === "talk") {
      if (words(f.line) > 10) w.push(`The line has ${words(f.line)} words - at most 10 keeps the lip sync clean.`);
      if (!/close-up/i.test(f.picture)) w.push("Talk pictures work best as “tight head-and-shoulders close-up of @Name, face filling the frame”.");
      if (!f.speaker) w.push("Choose who speaks.");
    } else if (!f.sounds.trim()) w.push("Name 2-3 loud sounds whose source is in the picture, or the clip may come out silent.");
    if (/\b(silence|silent|quiet|tense|standoff)\b/i.test(f.sounds + " " + f.action + " " + f.picture)) w.push("Avoid silence / quiet / tense / standoff - H3 then makes a soundless clip.");
    const untagged = names.filter((n) => new RegExp(`\\b${n}\\b`).test(f.picture) && !f.picture.includes("@" + n.replace(/\W+/g, "")));
    if (untagged.length) w.push(`Write ${untagged.map((n) => "@" + n.replace(/\W+/g, "")).join(", ")} so the character picture is used.`);
    warnBox.replaceChildren(...w.map((x) => h("div", { class: "warn-text" }, "⚠ " + x)));
  }
  drawKind(); check();
  const idx = p.scenes.findIndex((x) => x.id === f.id);
  const close = modal(isNew ? "New scene" : `Scene ${idx + 1}`, h("div", {},
    kindBtns, h("div", { style: { height: "14px" } }),
    field("Picture (first frame)", pic, null),
    h("div", { class: "chips", style: { marginTop: "-8px", marginBottom: "14px" } }, tags.map((t) => h("button", { class: "small", onclick: () => {
      const a = pic.selectionStart ?? pic.value.length; pic.value = pic.value.slice(0, a) + t + " " + pic.value.slice(a); f.picture = pic.value; pic.focus(); check(); } }, t)),
      f.kind === "talk" || true ? h("button", { class: "small ghost", onclick: () => {
        const who = tags[names.indexOf(f.speaker)] || tags[0] || "@Name";
        pic.value = f.picture = `tight head-and-shoulders close-up of ${who}, face filling the frame, ` + pic.value; check(); } }, "+ close-up") : null),
    field("What happens (movement, acting)", h("textarea", { rows: 2, value: f.action, oninput: (e) => { f.action = e.target.value; check(); } })),
    talkBox,
    field("Sounds", sounds, "Loud, concrete sounds from things in the picture. Never sounds of things that are not there."),
    field("Camera", h("input", { value: f.camera, placeholder: "slow push-in on his face / low angle tracking her run / static close-up", oninput: (e) => (f.camera = e.target.value) })),
    warnBox,
    h("div", { class: "btns", style: { marginTop: "16px" } },
      h("button", { class: "primary", onclick: () => save(false) }, icon("check"), "Save"),
      !isNew ? h("button", { onclick: () => save(true) }, icon("image"), "Save + new picture") : null,
      !isNew ? h("button", { class: "ghost", disabled: idx <= 0, onclick: () => move(-1) }, icon("up"), "Earlier") : null,
      !isNew ? h("button", { class: "ghost", disabled: idx >= p.scenes.length - 1, onclick: () => move(1) }, h("span", { style: { transform: "rotate(180deg)", display: "inline-flex" } }, icon("up")), "Later") : null,
      h("div", { style: { flex: 1 } }),
      !isNew ? h("button", { class: "danger", onclick: async () => {
        if (!confirm("Delete this scene?")) return;
        await saveScenes(P, p.scenes.filter((x) => x.id !== f.id), "Scene deleted"); close(); } }, icon("trash"), "Delete") : null)));
  async function save(newPic) {
    if (!f.picture.trim()) return toast("Describe the picture", true);
    const scenes = isNew ? [...p.scenes, f] : p.scenes.map((x) => (x.id === f.id ? f : x));
    const r = await saveScenes(P, scenes, "Scene saved");
    if (!r) return;
    close();
    if (newPic) run(P, "pictures", [f.id], "New picture");
  }
  async function move(dir) {
    const sc = [...p.scenes]; const [x] = sc.splice(idx, 1); sc.splice(idx + dir, 0, { ...x, ...f });
    await saveScenes(P, sc, "Moved"); close();
  }
}

// ----- Build tab -----
function tabBuild(P) {
  const d = P.data, p = d.project, st = d.status, n = p.scenes.length;
  const F = Object.values(d.files);
  const pics = F.filter((f) => f.picture).length, clips = F.filter((f) => f.clip).length;
  const checked = Object.values(d.results).filter((r) => r.qc).length, passed = Object.values(d.results).filter((r) => r.qc && r.qc.ok).length;
  const castOk = d.cast.filter((c) => c.pictures.front && c.pictures.face).length;
  const running = st.state === "running" ? st.stage : null;
  const steps = [
    ["write", "Story", n ? `${plural(n, "scene")}, ${plural(p.scenes.filter((s) => s.kind === "talk").length, "spoken line")}` : "Not written yet", !!n],
    ["sheets", "Character pictures", d.cast.length ? `${castOk} of ${d.cast.length} characters ready` : "No cast", d.cast.length > 0 && castOk === d.cast.length],
    ["pictures", "Scene pictures (FLUX.2 Klein)", `${pics} of ${n}`, n > 0 && pics === n],
    ["clips", "Acting videos with voices (MiniMax H3)", `${clips} of ${n} · about 13 min each`, n > 0 && clips === n],
    ["check", "Quality check", checked ? `${passed} of ${checked} passed (line heard, English only, not silent)` : "Runs after the videos", checked > 0 && passed === checked && checked === clips],
    ["final", "Final video", d.outputs["final.mp4"] ? `ready · ${st.final_seconds ? fmtSec(st.final_seconds) : ""}` : "Clips joined, each with its own sound", !!d.outputs["final.mp4"]],
    ["publish", "Shorts + YouTube kit", d.outputs["short1.mp4"] ? "Short, titles, description, tags, thumbnails, subtitles" : "Made after the final video", !!d.outputs["short1.mp4"]],
  ];
  const opts = p.options || {};
  const setOpt = async (k, v) => { await safe(() => api(`/projects/${p.id}`, "PATCH", { options: { [k]: v } })); };
  const log = h("div", { class: "log" }, (st.log || []).map((l) => h("div", { class: /FAILED|error|BAD/i.test(l) ? "e" : /done|ready|OK/.test(l) ? "g" : "" }, l)));
  setTimeout(() => (log.scrollTop = log.scrollHeight), 0);
  return h("div", { class: "split" },
    h("div", {},
      h("div", { class: "steps" }, steps.map(([k, t, desc, done], i) =>
        h("div", { class: "step" + (running === k ? " now" : done ? " done" : "") },
          h("div", { class: "ic" }, running === k ? h("span", { class: "spin", style: { borderTopColor: "var(--green-ink)", borderColor: "rgba(0,0,0,.2)" } }) : done ? icon("check") : i + 1),
          h("div", {}, h("div", { class: "n" }, t), h("div", { class: "d" }, running === k && st.label ? st.label : desc)),
          h("div", {}, stepButton(P, k, done))))),
      h("h2", {}, "Log"), log),
    h("div", {},
      h("div", { class: "card" }, h("h3", {}, "Options"),
        toggle("Stop after the pictures so I can check them", opts.approve_pictures !== false, (v) => setOpt("approve_pictures", v)),
        toggle("Background music", !!opts.music, (v) => setOpt("music", v)),
        h("input", { value: opts.music_prompt || "", placeholder: "music style (MusicGen, offline)", style: { marginTop: "6px" }, onchange: (e) => setOpt("music_prompt", e.target.value) }),
        h("div", { class: "hint" }, "Music is mixed under H3's own sound and ducks under the voices.")),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Time"),
        h("div", { class: "kv" },
          h("div", { class: "k" }, "Pictures"), h("div", {}, `${n - pics} to make · ~${Math.ceil((n - pics) * 0.8)} min`),
          h("div", { class: "k" }, "Videos"), h("div", {}, `${n - clips} to make · ~${Math.round((n - clips) * 13 / 6) / 10} h`),
          h("div", { class: "k" }, "Check + final"), h("div", {}, "~15-30 min"))),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Keep in mind"),
        h("div", { class: "muted", style: { fontSize: "13px", lineHeight: 1.6 } },
          "Keep the laptop on the charger. If it shuts down, open Shri Tools again: the job continues where it stopped. Starting a second job while one runs just puts it in the queue."))));
}
function stepButton(P, k, done) {
  const d = P.data, busy = ["running", "waiting"].includes(d.status.state);
  if (busy) return null;
  const n = d.project.scenes.length;
  const map = {
    write: () => go(`#/p/${P.id}/story`),
    sheets: () => run(P, "sheets", null, "Drawing character pictures"),
    pictures: () => run(P, "build", null, "Making pictures"),
    clips: () => run(P, "approve", null, "Making videos"),
    check: () => run(P, "check", null, "Checking all videos"),
    final: () => run(P, "final", null, "Joining the final video"),
    publish: () => run(P, "publish", null, "Making the Short and YouTube kit"),
  };
  if (!n && k !== "write") return null;
  const label = { write: done ? "Edit" : "Write", sheets: "Draw", pictures: done ? null : "Make", clips: done ? null : "Make", check: "Check", final: done ? "Join again" : "Join", publish: done ? "Make again" : "Make" }[k];
  return label ? h("button", { class: "small" + (done ? " ghost" : " outline"), onclick: map[k] }, label) : null;
}

// ----- Video tab -----
function tabVideo(P) {
  const d = P.data, p = d.project, base = `projects/${P.id}`;
  if (!d.outputs["final.mp4"]) return h("div", { class: "empty" }, h("h3", {}, "No final video yet"),
    "It is made when all scene videos are done and checked.", h("div", { style: { marginTop: "14px" } }, h("button", { class: "primary", onclick: () => go(`#/p/${P.id}/build`) }, icon("hammer"), "Go to Build")));
  const url = lib(`${base}/output/final.mp4?v=${d.outputs["final.mp4"]}`);
  const rows = p.scenes.map((s, i) => { const q = (d.results[s.id] || {}).qc; return h("tr", {},
    h("td", {}, i + 1), h("td", {}, s.kind === "talk" ? h("span", {}, h("b", { class: "green" }, s.speaker), ` “${s.line}”`) : h("span", { class: "muted" }, "action")),
    h("td", { class: "muted" }, q ? (q.heard || "").slice(0, 90) : "-"),
    h("td", {}, q ? (q.ok ? h("span", { class: "chip g" }, "OK") : h("span", { class: "chip red" }, q.problems.join(", "))) : h("span", { class: "dim" }, "not checked"))); });
  return h("div", {},
    h("div", { class: "split" },
      h("div", { class: "player" }, h("video", { src: url, controls: true, preload: "metadata" })),
      h("div", { class: "card" }, h("h3", {}, "Final video"),
        h("div", { class: "kv" },
          h("div", { class: "k" }, "Length"), h("div", {}, d.status.final_seconds ? fmtSec(d.status.final_seconds) : "-"),
          h("div", { class: "k" }, "Scenes"), h("div", {}, p.scenes.length),
          h("div", { class: "k" }, "Made"), h("div", {}, d.status.final_made || "-"),
          h("div", { class: "k" }, "Sound"), h("div", {}, "every clip keeps its own H3 voices and sounds, levelled")),
        h("div", { class: "sep" }),
        h("div", { class: "btns" },
          h("a", { class: "btn primary", href: `/download/${base}/output/final.mp4?name=${encodeURIComponent(p.title)}.mp4` }, icon("down"), "Download"),
          h("button", { onclick: () => api("/open", "POST", { path: `${base}/output/final.mp4` }) }, icon("folder"), "Show in folder"),
          h("button", { onclick: () => run(P, "final", null, "Joining again") }, icon("redo"), "Join again")),
        h("div", { class: "hint", style: { marginTop: "12px" } }, "Also saved in the Shri Tools output folder. To fix one scene: Storyboard → that scene → Video (new take), then Join again."))),
    h("h2", {}, "Check report"),
    h("div", { class: "card", style: { padding: "6px 8px" } }, h("table", { class: "t" }, h("tr", {}, h("th", {}, "#"), h("th", {}, "Line"), h("th", {}, "Heard by the checker"), h("th", {}, "Result")), rows)));
}

// ----- Shorts tab -----
function tabShorts(P) {
  const d = P.data, p = d.project, base = `projects/${P.id}`, pub = d.publish;
  const withClip = p.scenes.filter((s) => (d.files[s.id] || {}).clip);
  if (!withClip.length) return h("div", { class: "empty" }, h("h3", {}, "No videos yet"), "Shorts are cut from the scene videos.");
  let sel = new Set((pub.short && pub.short.scenes) || p.short_scenes || []);
  const total = h("b");
  const list = h("div");
  const drawList = () => {
    const secs = withClip.filter((s) => sel.has(s.id)).length * 4.87;
    total.textContent = `${sel.size} scenes · ≈ ${fmtSec(secs)}`;
    total.style.color = secs > 59 ? "var(--red)" : "var(--green)";
    list.replaceChildren(...withClip.map((s) => h("div", { class: "check" + (sel.has(s.id) ? " on" : ""), onclick: () => { sel.has(s.id) ? sel.delete(s.id) : sel.add(s.id); drawList(); } },
      h("span", { class: "box" }), h("div", {}, h("b", {}, `Scene ${p.scenes.indexOf(s) + 1} `),
        s.kind === "talk" ? h("span", {}, h("span", { class: "green" }, s.speaker), ` “${s.line}”`) : h("span", { class: "muted" }, (s.action || s.picture).slice(0, 80))))));
  };
  drawList();
  const has = d.outputs["short1.mp4"];
  return h("div", { class: "split" },
    h("div", { style: { display: "flex", gap: "20px", flexWrap: "wrap", alignItems: "flex-start" } },
      has ? h("div", { class: "player v" }, h("video", { src: lib(`${base}/output/short1.mp4?v=${has}`), controls: true, preload: "metadata" }))
        : h("div", { class: "empty", style: { width: "300px" } }, h("h3", {}, "No Short yet"), "Pick scenes and press Make Short - or it is made with the YouTube kit."),
      h("div", { style: { flex: 1, minWidth: "240px" } },
        h("div", { class: "card" }, h("h3", {}, "Short (9:16, under 60 s)"),
          field("Title on the Short", h("input", { value: pub.short_title || "", onchange: async (e) => { await safe(() => api(`/projects/${P.id}/publish`, "PATCH", { short_title: e.target.value }), "Saved - press Make Short to use it"); } })),
          field("Short description", h("textarea", { rows: 3, value: pub.short_description || "", onchange: async (e) => { await safe(() => api(`/projects/${P.id}/publish`, "PATCH", { short_description: e.target.value }), "Saved"); } })),
          h("div", { class: "btns" },
            has ? h("a", { class: "btn primary", href: `/download/${base}/output/short1.mp4?name=${encodeURIComponent(p.title)} - Short.mp4` }, icon("down"), "Download") : null,
            h("button", { onclick: () => copy(`${pub.short_title || p.title}\n\n${pub.short_description || ""}\n\n${(pub.hashtags || []).join(" ")} #shorts`, "Short text copied") }, icon("copy"), "Copy text"))))),
    h("div", { class: "card" }, h("h3", {}, "Scenes in the Short"), h("div", { class: "hint", style: { marginTop: 0, marginBottom: "8px" } }, "Lines get big captions. Under 60 s."), total, list,
      h("div", { class: "btns", style: { marginTop: "14px" } },
        h("button", { class: "primary", disabled: !sel.size || !d.outputs["final.mp4"] || ["running", "waiting"].includes(d.status.state), onclick: () =>
          run(P, "short", p.scenes.filter((s) => sel.has(s.id)).map((s) => s.id), "Making the Short") }, icon("phone"), "Make Short"),
        !d.outputs["final.mp4"] ? h("span", { class: "dim" }, "after the final video") : null)));
}

// ----- Publish tab -----
function tabPublish(P) {
  const d = P.data, p = d.project, base = `projects/${P.id}`;
  const pub = { titles: [], tags: [], hashtags: [], thumbnails: [], checklist: {}, ...d.publish };
  if (!pub.titles.length) return h("div", { class: "empty" }, h("h3", {}, "No YouTube kit yet"),
    "Titles, description, tags, thumbnails, subtitles and the Short are made after the final video.",
    h("div", { style: { marginTop: "14px" } }, h("button", { class: "primary", disabled: !d.outputs["final.mp4"] || ["running", "waiting"].includes(d.status.state),
      onclick: () => run(P, "publish", null, "Making the YouTube kit") }, icon("yt"), "Make the YouTube kit")));
  const save = (k, v) => api(`/projects/${P.id}/publish`, "PATCH", { [k]: v }).catch((e) => toast(e.message, true));
  let choice = pub.title_choice || 0;
  const titlesBox = h("div", { class: "titles" });
  const drawTitles = () => titlesBox.replaceChildren(...pub.titles.map((t, i) => h("div", { class: "opt" + (i === choice ? " on" : ""), onclick: () => { choice = i; save("title_choice", i); drawTitles(); } },
    h("span", { class: "radio" }), h("input", { value: t, onclick: (e) => e.stopPropagation(), onchange: (e) => { pub.titles[i] = e.target.value; save("titles", pub.titles); } }),
    h("span", { class: "dim", style: { fontSize: "11px" } }, `${t.length}/100`),
    h("button", { class: "small ghost icon", title: "Copy", onclick: (e) => { e.stopPropagation(); copy(pub.titles[i], "Title copied"); } }, icon("copy")))));
  drawTitles();
  const desc = h("textarea", { rows: 9, value: pub.description || "", onchange: (e) => { pub.description = e.target.value; save("description", pub.description); } });
  const tagBox = h("div", { class: "tags" });
  const drawTags = () => tagBox.replaceChildren(...pub.tags.map((t, i) => h("span", { class: "chip" }, t, h("button", { onclick: () => { pub.tags.splice(i, 1); save("tags", pub.tags); drawTags(); } }, "×"))),
    h("input", { placeholder: "+ tag", style: { width: "120px", padding: "4px 10px", borderRadius: "99px" }, onkeydown: (e) => {
      if (e.key === "Enter" && e.target.value.trim()) { pub.tags.push(e.target.value.trim()); save("tags", pub.tags); drawTags(); } } }));
  drawTags();
  let th = pub.thumbnail_choice || 0;
  const thumbBox = h("div", { class: "thumbs" });
  const drawThumbs = () => thumbBox.replaceChildren(...pub.thumbnails.map((t, i) => h("div", { class: "th" + (i === th ? " on" : ""),
    style: { backgroundImage: `url("${lib(`${base}/${t}?v=${d.outputs[t.split("/").pop()] || 0}`)}")` }, onclick: () => { th = i; save("thumbnail_choice", i); drawThumbs(); } },
  i === th ? h("span", { class: "pill run" }, "Chosen") : null)));
  drawThumbs();
  const CHECK = [["title", "Title and thumbnail chosen"], ["ai", "YouTube Studio: “Altered or synthetic content” = Yes (AI-generated)"],
    ["subs", "Subtitles uploaded (subtitles.srt, English)"], ["playlist", "Added to the season playlist"], ["end", "End screen: next episode + subscribe"], ["short", "Short uploaded with a link to the full video"]];
  const checkBox = h("div");
  const drawCheck = () => checkBox.replaceChildren(...CHECK.map(([k, t]) => h("div", { class: "check" + (pub.checklist[k] ? " on" : ""), onclick: () => { pub.checklist[k] = !pub.checklist[k]; save("checklist", pub.checklist); drawCheck(); } }, h("span", { class: "box" }), t)));
  drawCheck();
  const busy = ["running", "waiting"].includes(d.status.state);
  return h("div", { class: "split" },
    h("div", {},
      h("div", { class: "card" }, h("div", { style: { display: "flex", alignItems: "center", marginBottom: "10px" } }, h("h3", { style: { margin: 0, flex: 1 } }, "Title"),
        h("button", { class: "small ghost", disabled: busy, onclick: () => run(P, "publish", null, "Writing new texts") && api(`/projects/${P.id}/run`, "POST", { action: "publish", texts: true }) }, icon("redo"), "Write new texts")), titlesBox),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("div", { style: { display: "flex", alignItems: "center", marginBottom: "10px" } }, h("h3", { style: { margin: 0, flex: 1 } }, "Description"),
        h("button", { class: "small", onclick: () => copy(`${desc.value}\n\n${pub.hashtags.join(" ")}`, "Description copied") }, icon("copy"), "Copy")), desc,
        h("div", { class: "chips", style: { marginTop: "8px" } }, pub.hashtags.map((x) => h("span", { class: "chip g" }, x)))),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("div", { style: { display: "flex", alignItems: "center", marginBottom: "10px" } }, h("h3", { style: { margin: 0, flex: 1 } }, "Tags"),
        h("button", { class: "small", onclick: () => copy(pub.tags.join(", "), "Tags copied") }, icon("copy"), "Copy all")), tagBox)),
    h("div", {},
      h("div", { class: "card" }, h("div", { style: { display: "flex", alignItems: "center", marginBottom: "10px" } }, h("h3", { style: { margin: 0, flex: 1 } }, "Thumbnail"),
        h("button", { class: "small ghost", disabled: busy, onclick: async () => { const r = await safe(() => api(`/projects/${P.id}/run`, "POST", { action: "publish", thumbs: true })); if (r) { toast("Drawing new thumbnails"); P.reload(); } } }, icon("redo"), "New")),
        thumbBox,
        pub.thumbnails[th] ? h("div", { class: "btns", style: { marginTop: "10px" } }, h("a", { class: "btn", href: `/download/${base}/${pub.thumbnails[th]}?name=${encodeURIComponent(p.title)} - thumbnail.jpg` }, icon("down"), "Download chosen")) : null),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Files"),
        h("div", { class: "btns" },
          d.outputs["final.mp4"] ? h("a", { class: "btn primary", href: `/download/${base}/output/final.mp4?name=${encodeURIComponent(p.title)}.mp4` }, icon("down"), "Video") : null,
          d.outputs["subtitles.srt"] ? h("a", { class: "btn", href: `/download/${base}/output/subtitles.srt?name=${encodeURIComponent(p.title)}.srt` }, icon("down"), "Subtitles .srt") : null,
          d.outputs["short1.mp4"] ? h("button", { onclick: () => go(`#/p/${P.id}/shorts`) }, icon("phone"), "Short") : null,
          h("button", { onclick: () => api("/open", "POST", { path: `${base}/output` }) }, icon("folder"), "Folder"))),
      h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Upload checklist"), checkBox)));
}

const TAB_VIEWS = { song: tabSong, story: tabStory, cast: tabCast, storyboard: tabStoryboard, build: tabBuild, video: tabVideo, shorts: tabShorts, publish: tabPublish };

// ---------- this laptop: GPU, temperature, memory (Queue page + sidebar) ----------
function meter(label, value, max, text, warn, bad) {
  const pct = max ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const cls = bad != null && pct >= bad ? "bad" : warn != null && pct >= warn ? "warn" : "";
  return h("div", { class: "meter " + cls },
    h("div", { class: "mh" }, h("span", {}, label), h("b", {}, text)),
    h("div", { class: "mbar" }, h("div", { style: { width: pct.toFixed(0) + "%" } })));
}
function systemCard() {
  const box = h("div", { class: "card sys" }, h("div", { class: "muted" }, "Reading the laptop..."));
  const draw = (x) => {
    const g = x.gpu || {};
    const gb = (mb) => (mb / 1024).toFixed(1);
    box.replaceChildren(
      h("div", { class: "sys-h" }, h("h3", {}, "This laptop right now"), h("span", { class: "dim" }, g.name || "no NVIDIA GPU found")),
      h("div", { class: "meters" },
        meter("GPU load", g.load || 0, 100, g.load != null ? `${g.load.toFixed(0)}%` : "-"),
        meter("GPU temperature", g.temp || 0, 100, g.temp != null ? `${g.temp.toFixed(0)} °C` : "-", 80, 88),
        meter("GPU memory (VRAM)", g.vram_used || 0, g.vram_total || 1, g.vram_total ? `${gb(g.vram_used)} / ${gb(g.vram_total)} GB` : "-", 90, 98),
        meter("RAM", x.ram_used, x.ram_total, `${x.ram_used} / ${x.ram_total} GB`, 90),
        meter("Memory commit (RAM + page file)", x.commit_used, x.commit_total, `${x.commit_used} / ${x.commit_total} GB`, 85, 95),
        meter("CPU", x.cpu, 100, `${x.cpu.toFixed(0)}% of ${x.cores} threads`),
        meter("Disk used", x.disk_total - x.disk_free, x.disk_total, `${x.disk_free} GB free`, 85, 95)),
      h("div", { class: "sys-f dim" },
        g.power != null ? `GPU power ${g.power.toFixed(0)} W` : "", g.clock != null ? ` · clock ${g.clock.toFixed(0)} MHz` : "",
        x.battery ? ` · battery ${x.battery.percent}%${x.battery.plugged ? " (charging)" : " - ON BATTERY: plug in for full speed"}` : "",
        ` · updated ${x.time.slice(11)}`),
      h("div", { class: "sys-f dim" }, "Full RAM while a video clip is made is normal. The limit that matters is Memory commit: near 100% ComfyUI can crash (Shri Tools then restarts it and tries again)."));
  };
  const tick = async () => { const x = await api("/system").catch(() => null); if (x) draw(x); };
  tick();
  const id = setInterval(() => { if (!document.body.contains(box)) clearInterval(id); else tick(); }, 3000);
  return box;
}

// ---------- automations (Queue page) ----------
const DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
function automationsCard() {
  const box = h("div", { class: "card", style: { marginBottom: "16px" } }, h("div", { class: "muted" }, "Loading automations..."));
  const load = async () => {
    const [{ schedules }, { seasons }] = await Promise.all([api("/schedules"), api("/seasons")]);
    const what = { next_episode: "Next episode of", dub_latest: "Latest episode again, in another language, of" };
    box.replaceChildren(
      h("div", { class: "sys-h" }, h("h3", {}, "Automations"),
        h("button", { class: "small primary", onclick: () => automationForm(null, seasons, load) }, icon("plus"), "New automation")),
      schedules.length ? h("table", { class: "t" },
        h("tr", {}, h("th", {}, "What"), h("th", {}, "When"), h("th", {}, "Next start"), h("th", {}, "")),
        schedules.map((x) => h("tr", {},
          h("td", {}, h("b", {}, x.name || "Automation"), h("div", { class: "muted", style: { fontSize: "12.5px" } },
            `${what[x.kind]} ${x.season_title}`, x.language ? ` · ${langName(x.language).split(" - ")[0]}` : "",
            x.kind === "next_episode" ? ` · ${x.auto ? "fully automatic" : "stops at the pictures for you"} · ${x.ideas_left} ideas left` : "")),
          h("td", { class: "muted" }, x.days.map((d) => DAY_NAMES[d]).join(" "), " at ", x.time),
          h("td", {}, x.enabled === false ? h("span", { class: "pill" }, "Off") : h("span", { class: "muted" }, x.next_run || "-")),
          h("td", { style: { whiteSpace: "nowrap" } },
            h("button", { class: "small ghost", onclick: () => automationForm(x, seasons, load) }, icon("edit"), "Edit"),
            h("button", { class: "small ghost", onclick: async () => { if (await safe(() => api(`/schedules/${x.id}/run`, "POST"), "Started now - see the queue")) route(); } }, icon("play"), "Run now"),
            h("button", { class: "small ghost", onclick: async () => { if (!confirm("Delete this automation?")) return; await api(`/schedules/${x.id}`, "DELETE"); load(); } }, icon("trash"))))))
        : h("div", { class: "muted" }, "Nothing automatic yet. Example: every Monday, Wednesday and Friday at 22:00, the next episode of Shri Mama and Tuntun - ready when you wake up."));
  };
  load();
  return box;
}
function automationForm(x, seasons, after) {
  const f = x ? { ...x } : { name: "", kind: "next_episode", season_id: (seasons[0] || {}).id, language: "", days: [0, 2, 4], time: "22:00", auto: false, enabled: true };
  const days = h("div", { class: "chips" });
  const drawDays = () => days.replaceChildren(...DAY_NAMES.map((d, i) => h("button", { class: "small" + (f.days.includes(i) ? " outline" : ""), onclick: () => {
    f.days = f.days.includes(i) ? f.days.filter((x) => x !== i) : [...f.days, i]; drawDays(); } }, d)));
  drawDays();
  const close = modal(x ? "Edit automation" : "New automation", h("div", {},
    field("Name", h("input", { value: f.name, placeholder: "e.g. Tuntun every other night", oninput: (e) => (f.name = e.target.value) })),
    h("div", { class: "row2" },
      field("What", h("select", { onchange: (e) => (f.kind = e.target.value) },
        h("option", { value: "next_episode", selected: f.kind === "next_episode" }, "Make the next episode"),
        h("option", { value: "dub_latest", selected: f.kind === "dub_latest" }, "Make the latest episode in another language"))),
      field("Season", h("select", { onchange: (e) => (f.season_id = e.target.value) }, seasons.map((s) => h("option", { value: s.id, selected: s.id === f.season_id }, s.title))))),
    h("div", { class: "row2" },
      field("Language", langSelect(f.language || "", (v) => (f.language = v), true), "Same as the video = the season's usual language. For another-language copies pick one."),
      field("Time", h("input", { type: "time", value: f.time, oninput: (e) => (f.time = e.target.value) }))),
    field("Days", days),
    toggle("Fully automatic (no picture check - straight to the finished video)", !!f.auto, (v) => (f.auto = v)),
    toggle("On", f.enabled !== false, (v) => (f.enabled = v)),
    h("div", { class: "hint" }, "New episodes use the season's idea list first (Seasons → Give me 10 ideas), then the story AI invents a fresh idea in the series' theme. With your Telegram bot set up you get a message when it starts and when it is ready."),
    h("div", { class: "btns", style: { marginTop: "14px" } },
      h("button", { class: "primary", onclick: async () => { if (await safe(() => api("/schedules", "POST", f), "Saved")) { close(); after(); } } }, icon("check"), "Save"))));
}
function startAtDialog(t) {
  let at = t.start_at ? t.start_at.replace(" ", "T") : new Date(Date.now() + 3600e3 - new Date().getTimezoneOffset() * 60e3).toISOString().slice(0, 16);
  const close = modal("Start this job at", h("div", {},
    h("div", { class: "muted", style: { marginBottom: "10px" } }, t.title),
    field("Date and time", h("input", { type: "datetime-local", value: at, oninput: (e) => (at = e.target.value) })),
    h("div", { class: "btns" },
      h("button", { class: "primary", onclick: async () => { if (await safe(() => api(`/queue/${t.id}/start_at`, "POST", { start_at: at }), "Scheduled")) { close(); route(); } } }, icon("check"), "Schedule"),
      t.start_at ? h("button", { onclick: async () => { if (await safe(() => api(`/queue/${t.id}/start_at`, "POST", { start_at: "" }), "It starts as soon as the GPU is free")) { close(); route(); } } }, icon("play"), "As soon as possible") : null)));
}

// ---------- QUEUE ----------
async function viewQueue() {
  const { queue } = await api("/queue");
  if (S.sysCard && !document.body.contains(S.sysCard)) S.sysCard = null;
  if (S.autoCard && !document.body.contains(S.autoCard)) S.autoCard = null;
  const tbl = h("table", { class: "t" }, h("tr", {}, h("th", {}, "Job"), h("th", {}, "Steps"), h("th", {}, "State"), h("th", {}, "Added"), h("th", {}, "")),
    queue.map((t) => h("tr", {},
      h("td", {}, t.project ? h("a", { href: `#/p/${t.project}/build` }, t.title) : t.title),
      h("td", { class: "muted" }, (t.steps || [t.kind === "ideas" ? "episode ideas" : "character pictures"]).join(" → ") + (t.scenes ? ` (${t.scenes.join(", ")})` : "")),
      h("td", {}, t.state === "running" ? h("span", { class: "pill run" }, "Running") : t.state === "waiting" ? h("span", { class: "pill amber" }, t.start_at ? `At ${t.start_at.slice(5)}` : "Waiting")
        : t.state === "done" ? h("span", { class: "pill g" }, "Done") : t.state === "failed" ? h("span", { class: "pill red" }, "Failed") : h("span", { class: "pill" }, t.state)),
      h("td", { class: "muted" }, t.added),
      h("td", { style: { whiteSpace: "nowrap" } }, t.state === "waiting" ? h("button", { class: "small ghost", onclick: () => startAtDialog(t) }, icon("list"), "Start at") : null,
        ["running", "waiting"].includes(t.state) ? h("button", { class: "small danger", onclick: async () => {
        if (!confirm("Stop this job?")) return; await safe(() => api(`/queue/${t.id}/cancel`, "POST"), "Stopped"); route(); } }, icon("stop"), "Stop") : null))));
  S.poll = setInterval(async () => { const r = await api("/queue").catch(() => null); if (r && JSON.stringify(r.queue) !== JSON.stringify(queue)) route(); }, 5000);
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Queue"), h("div", { class: "sub" }, "One job at a time on the GPU. Jobs continue after a restart."))),
    S.sysCard || (S.sysCard = systemCard()),
    S.autoCard || (S.autoCard = automationsCard()),
    queue.length ? h("div", { class: "card", style: { padding: "6px 8px" } }, tbl) : h("div", { class: "empty" }, h("h3", {}, "Nothing in the queue")));
}

// ---------- SETTINGS ----------
async function viewSettings() {
  const [{ settings }, { models }] = await Promise.all([api("/settings"), api("/ollama/models")]);
  const f = { ...settings };
  const H = S.health;
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Settings"), h("div", { class: "sub" }, "Everything runs on this laptop unless you choose a cloud story AI below."))),
    h("div", { class: "split" },
      h("div", { class: "card" },
        h("div", { class: "row2" },
          field("Video size", h("select", { onchange: (e) => (f.clip_sizes = JSON.parse(e.target.value)) },
            h("option", { value: "[[864,480],[736,416]]", selected: f.clip_sizes[0][0] === 864 }, "864×480 (best, ~13 min/scene)"),
            h("option", { value: "[[736,416],[608,352]]", selected: f.clip_sizes[0][0] === 736 }, "736×416 (faster)"))),
          field("Check rounds", h("select", { onchange: (e) => (f.qc_rounds = +e.target.value) }, [0, 1, 2, 3].map((n) => h("option", { value: n, selected: n === f.qc_rounds }, n === 0 ? "check only" : `remake up to ${n}×`))))),
        h("div", { class: "row2" },
          field("Loudness of each clip (rms)", h("input", { type: "number", step: "0.01", value: f.level, oninput: (e) => (f.level = +e.target.value) })),
          field("Short: longest (seconds)", h("input", { type: "number", value: f.short_max_seconds, oninput: (e) => (f.short_max_seconds = +e.target.value) }))),
        field("AI note at the end of every description", h("input", { value: f.ai_disclosure, oninput: (e) => (f.ai_disclosure = e.target.value) })),
        h("button", { class: "primary", onclick: () => safe(() => api("/settings", "PATCH", f), "Settings saved") }, icon("check"), "Save")),
      h("div", {},
        h("div", { class: "card" }, h("h3", {}, "Engines"),
          h("div", { class: "kv" },
            h("div", { class: "k" }, "Video engine"), h("div", {}, h("span", { class: "dot " + (H.comfy ? "ok" : "warn"), style: { display: "inline-block", marginRight: "8px" } }), H.comfy ? "ComfyUI running (memory-safe)" : "starts by itself when needed"),
            h("div", { class: "k" }, "Story AI"), h("div", {}, h("span", { class: "dot " + (H.ollama ? "ok" : "bad"), style: { display: "inline-block", marginRight: "8px" } }), H.ollama ? "Ollama running" : "Ollama is not running - start it from the Start menu"),
            h("div", { class: "k" }, "Pictures"), h("div", {}, "FLUX.2 Klein 4B"),
            h("div", { class: "k" }, "Acting + voices"), h("div", {}, "MiniMax H3 (native audio, 4-step)"),
            h("div", { class: "k" }, "Checker"), h("div", {}, "Whisper base (English) + Whisper small (Indian languages)"),
            h("div", { class: "k" }, "Disk"), h("div", {}, `${H.disk_free_gb} GB free on D:`)),
          h("div", { class: "btns", style: { marginTop: "14px" } },
            h("button", { disabled: H.comfy, onclick: () => safe(() => api("/comfy/start", "POST"), "Starting the video engine") }, icon("play"), "Start video engine"),
            h("button", { onclick: () => api("/open", "POST", { path: "output" }) }, icon("folder"), "Output folder"))),
        storyAICard(f, models),
        phoneCard(f),
        brandCard(f))));
}

const PROVIDERS = {
  ollama: { name: "Ollama - on this laptop (free, offline)", model: "", key: null },
  claude: { name: "Claude (Anthropic)", model: "claude-opus-5-5", key: "anthropic_api_key", hint: "Key from console.anthropic.com" },
  openai: { name: "ChatGPT (OpenAI)", model: "gpt-5-mini", key: "openai_api_key", hint: "Key from platform.openai.com" },
  gemini: { name: "Gemini (Google)", model: "gemini-2.5-flash", key: "gemini_api_key", hint: "Key from aistudio.google.com" },
  compat: { name: "Other (OpenAI-compatible: OpenRouter, Groq, DeepSeek, LM Studio...)", model: "", key: "compat_api_key", hint: "Key from that service (LM Studio needs none)" },
};
function storyAICard(f, models) {
  const box = h("div");
  const msg = h("span", { class: "muted" });
  const draw = () => {
    const P = PROVIDERS[f.llm_provider || "ollama"];
    box.replaceChildren(
      field("Who writes the stories, lyrics and YouTube texts", h("select", { onchange: (e) => { f.llm_provider = e.target.value; f.llm_model = ""; draw(); } },
        Object.entries(PROVIDERS).map(([k, v]) => h("option", { value: k, selected: (f.llm_provider || "ollama") === k }, v.name)))),
      (f.llm_provider || "ollama") === "ollama"
        ? field("Ollama model", h("select", { onchange: (e) => (f.story_model = e.target.value) },
            (models.length ? models : [f.story_model]).map((m) => h("option", { value: m, selected: m === f.story_model }, m))), "gpt-oss:20b writes the best stories; qwen3.5:9b is faster. Install Ollama from ollama.com.")
        : h("div", {},
            f.llm_provider === "compat" ? field("Base URL", h("input", { value: f.compat_base_url || "", placeholder: "https://openrouter.ai/api/v1", oninput: (e) => (f.compat_base_url = e.target.value.trim()) })) : null,
            field("Model", h("input", { value: f.llm_model || "", placeholder: P.model || "model name from that service", oninput: (e) => (f.llm_model = e.target.value.trim()) }),
              P.model ? `Empty = ${P.model}` : "The model name exactly as the service lists it."),
            field("API key", h("input", { type: "password", value: f[P.key] || "", placeholder: "paste your key", oninput: (e) => (f[P.key] = e.target.value.trim()) }), P.hint),
            h("div", { class: "hint", style: { marginTop: "-6px", marginBottom: "10px" } }, "Cloud story AIs cost a little per story and receive your idea, characters and lines. The key stays on this laptop.")),
      h("div", { class: "btns" },
        h("button", { onclick: () => safe(() => api("/settings", "PATCH", pick(f)), "Saved") }, icon("check"), "Save"),
        h("button", { onclick: async () => {
          msg.textContent = "Testing...";
          const r = await api("/settings/llm-test", "POST", pick(f)).catch((e) => ({ error: e.message }));
          msg.textContent = r.ok ? `Works (${r.seconds} s): ${r.answer.hello || "ok"}` : (r.error || "failed");
        } }, icon("spark"), "Test"),
        msg));
  };
  const pick = (x) => Object.fromEntries(["llm_provider", "llm_model", "story_model", "anthropic_api_key", "openai_api_key", "gemini_api_key", "compat_base_url", "compat_api_key"].map((k) => [k, x[k] ?? ""]));
  draw();
  return h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Story AI"), box);
}

function phoneCard(f) {
  const tok = h("input", { type: "password", value: f.telegram_token || "", placeholder: "123456789:ABC...", oninput: (e) => (f.telegram_token = e.target.value.trim()) });
  const chat = h("input", { value: f.telegram_chat_id || "", placeholder: "found with the button below", oninput: (e) => (f.telegram_chat_id = e.target.value.trim()) });
  const msg = h("span", { class: "muted" });
  return h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Phone (Telegram)"),
    h("div", { class: "muted", style: { fontSize: "13px", lineHeight: 1.6, marginBottom: "10px" } },
      "1. In Telegram open @BotFather, send /newbot, copy the token. 2. Paste it here and Save. ",
      "3. Send any message to your new bot. 4. Press Find my chat id, Save, Send test. ",
      "No tunnel needed: Shri Tools asks Telegram for messages itself, and only answers your chat."),
    field("Bot token", tok), field("Your chat id", chat),
    h("div", { class: "btns" },
      h("button", { onclick: () => safe(() => api("/settings", "PATCH", { telegram_token: f.telegram_token, telegram_chat_id: f.telegram_chat_id }), "Saved") }, icon("check"), "Save"),
      h("button", { onclick: async () => {
        const r = await safe(() => api("/settings/telegram-chat", "POST", { token: f.telegram_token }));
        if (r && r.chats.length) { chat.value = f.telegram_chat_id = String(r.chats[r.chats.length - 1].id); msg.textContent = `found: ${r.chats.map((c) => c.name || c.id).join(", ")} - press Save`; } } }, icon("users"), "Find my chat id"),
      h("button", { onclick: () => safe(() => api("/settings/telegram-test", "POST", { token: f.telegram_token, chat_id: f.telegram_chat_id }), "Sent - look at your phone") }, icon("phone"), "Send test"),
      msg),
    h("div", { class: "hint" }, "The bot tells you when a video is ready, failed, or its pictures wait for you (with the pictures). Commands: /status, /videos, /approve N, /pictures N, /short N, /make idea, /stop N."));
}

function brandCard(f) {
  return h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Logo in videos (optional)"),
    h("div", { class: "muted", style: { fontSize: "13px", marginBottom: "10px" } }, "Off by default. Applies to videos finished after you switch it on."),
    toggle("2-second logo intro (waving flag)", !!f.brand_intro, (v) => (f.brand_intro = v)),
    toggle("Small logo in the corner", !!f.brand_watermark, (v) => (f.brand_watermark = v)),
    toggle("3-second end card", !!f.brand_end, (v) => (f.brand_end = v)),
    field("End card text", h("input", { value: f.brand_end_text || "", oninput: (e) => (f.brand_end_text = e.target.value) })),
    h("button", { class: "primary", onclick: () => safe(() => api("/settings", "PATCH", { brand_intro: f.brand_intro, brand_watermark: f.brand_watermark, brand_end: f.brand_end, brand_end_text: f.brand_end_text }), "Saved") }, icon("check"), "Save"));
}

// ---------- CONNECT (n8n and other tools) ----------
async function viewConnect() {
  const { settings, version } = await api("/settings");
  const base = location.origin;
  let key = settings.api_key || "";
  const keyBox = h("code", { style: { wordBreak: "break-all" } });
  const drawKey = () => (keyBox.textContent = key || "(none - only tools on this laptop can call Shri Tools)");
  drawKey();
  const ex = (method, path, bodyText) => {
    const hdr = key ? ` -H "X-Api-Key: ${key}"` : "";
    return `curl${method === "GET" ? "" : " -X " + method}${hdr}${bodyText ? ' -H "Content-Type: application/json" -d ' + "'" + bodyText + "'" : ""} ${base}${path}`;
  };
  const sample = JSON.stringify({ title: "Say Thank You, Tuntun!", idea: "Tuntun meets the vegetable seller and learns to say thank you.", season: "Shri Mama and Tuntun", language: "hi" });
  const rows = [
    ["GET", "/api/connect/health", "Is Shri Tools up, is it busy"],
    ["GET", "/api/connect/options", "Seasons, characters, styles and languages (names and ids)"],
    ["POST", "/api/connect/videos", "Make a video: {title, idea | scenes, season | season_id, language, style, cast, scenes_wanted, approve_pictures, music, hook_text, callback_url}"],
    ["GET", "/api/connect/videos", "The latest videos"],
    ["GET", "/api/connect/videos/{id}", "State (waiting, running, approve, done, failed), progress, file links, YouTube texts"],
    ["POST", "/api/connect/videos/{id}/approve", "Pictures OK - make the videos (when approve_pictures was true)"],
    ["POST", "/api/connect/videos/{id}/retry", "Run the unfinished steps again"],
    ["POST", "/api/connect/videos/{id}/cancel", "Stop it"],
    ["GET", "/api/connect/videos/{id}/files/final", "Download: final | short | subtitles | thumb1 | thumb2 | thumb3"],
  ];
  const test = h("span", { class: "muted" });
  return h("div", { class: "page" },
    h("div", { class: "page-h" }, h("div", {}, h("h1", {}, "Connect"),
      h("div", { class: "sub" }, `Shri Tools Connect ${version || ""} - let n8n (or any tool) make videos: send an idea, get the finished video, Short, thumbnails and YouTube texts back.`))),
    h("div", { class: "split" },
      h("div", {},
        h("div", { class: "card hl" }, h("h3", {}, "1. Get the n8n workflow"),
          h("div", { class: "muted", style: { marginBottom: "12px" } }, "Download it and import it in n8n (Workflows > Import from file). It already contains this address and your key."),
          h("div", { class: "btns" },
            h("a", { class: "btn primary", href: "/api/connect/n8n-workflow" + (key ? "?key=" + encodeURIComponent(key) : ""), download: "" }, icon("down"), "Download n8n workflow"),
            h("button", { onclick: async () => { const r = await api("/connect/health").catch((e) => ({ error: e.message })); test.textContent = r.ok ? `OK - Shri Tools ${r.version}, ${r.busy ? "busy: " + r.job : "idle"}, ${r.waiting} waiting` : "Not reachable: " + (r.error || ""); } }, icon("check"), "Test the connection"), test)),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "2. Calls"),
          h("div", { class: "kv", style: { gridTemplateColumns: "60px 1fr" } }, rows.flatMap(([m, p, d]) => [
            h("div", { class: "k" }, h("b", { class: m === "POST" ? "green" : "" }, m)),
            h("div", {}, h("code", {}, p), h("div", { class: "muted", style: { fontSize: "12px" } }, d))])),
          h("div", { class: "hint", style: { marginTop: "12px" } }, "Give callback_url (an n8n Webhook URL) and Shri Tools POSTs {event, video} when the video is done, failed or waits for picture approval - no polling needed.")),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "Try it (copy into a terminal)"),
          h("div", { class: "log" }, ex("POST", "/api/connect/videos", sample)),
          h("div", { class: "btns", style: { marginTop: "10px" } }, h("button", { class: "small", onclick: () => copy(ex("POST", "/api/connect/videos", sample)) }, icon("copy"), "Copy")))),
      h("div", {},
        h("div", { class: "card" }, h("h3", {}, "Address"),
          h("div", { class: "kv" },
            h("div", { class: "k" }, "From this laptop"), h("div", {}, h("code", {}, base)),
            h("div", { class: "k" }, "From Docker n8n"), h("div", {}, h("code", {}, "http://host.docker.internal:7880"), h("div", { class: "muted", style: { fontSize: "12px" } }, "needs an API key + “Allow other computers” below")))),
        h("div", { class: "card", style: { marginTop: "16px" } }, h("h3", {}, "API key"),
          h("div", { style: { marginBottom: "10px" } }, keyBox),
          h("div", { class: "btns" },
            h("button", { onclick: async () => { const r = await safe(() => api("/settings/api-key", "POST", {}), "New key made - update it in n8n"); if (r) { key = r.api_key; drawKey(); } } }, icon("redo"), key ? "New key" : "Make a key"),
            key ? h("button", { class: "ghost", onclick: async () => { const r = await safe(() => api("/settings/api-key", "POST", { clear: true }), "Key removed"); if (r) { key = ""; drawKey(); } } }, icon("x"), "Remove key") : null,
            key ? h("button", { class: "ghost", onclick: () => copy(key, "Key copied") }, icon("copy"), "Copy") : null),
          h("div", { class: "sep" }),
          toggle("Allow other computers (n8n in Docker / on another PC)", !!settings.api_network, async (v) => {
            if (v && !key) { toast("Make an API key first", true); return route(); }
            await safe(() => api("/settings", "PATCH", { api_network: v }), "Saved - restart Shri Tools (close the window, open SHRI TOOLS again) to apply");
          }),
          h("div", { class: "hint" }, "Off: only this laptop can call Shri Tools. On: other computers can call /api/connect/ with the key; the app itself still only opens here.")))));
}

// ---------- start ----------
refreshSide();
setInterval(refreshSide, 5000);
route();
