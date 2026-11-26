// Printyz web configurator. The server builds the REAL clicker (same engine as the print files);
// this page only collects choices and draws the returned meshes.
import * as THREE from "three";
import { OrbitControls } from "/static/vendor/three/OrbitControls.js";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const NAMES = {
  modes: { flush: "שטוח צבעוני", raised: "בולט", engraved: "חרוט" },
  keycaps: { standard: "רגיל", low_profile: "נמוך", thocky: "עבה" },
  layouts: { row: "שורה", column: "עמודה", grid: "רשת", wasd: "WASD", arrows: "חצים", custom: "חופשי" },
  textures: { smooth: "חלק", diamond: "יהלומים", ribs: "פסים", fluted: "חריצים", dots: "נקודות", chevron: "זיגזג" },
  sides: { top: "למעלה", bottom: "למטה", right: "ימין", left: "שמאל" },
  shapes: { rounded: "מעוגל", round: "עגול", square: "מרובע" },
};

let cfg = null;
const state = {
  text: "שלום", font: null, mode: "flush", size_pct: 100, keycap: "standard",
  layout: { style: "row", rows: 2, cols: 3 }, texture: "smooth",
  keychain: { enabled: false, side: "top", shape: "rounded" },
  colors: {}, extras: [],
};
let pickedSymbol = null;
let lastPreview = null;

// ------------------------------------------------------------------ helpers
function el(tag, attrs = {}, children = []) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of [].concat(children)) e.append(c);
  return e;
}

function optionGroup(container, items, current, onPick, render) {
  container.replaceChildren();
  for (const it of items) {
    const b = el("button", { class: "opt", type: "button", "aria-pressed": String(it === current) },
      render ? render(it) : String(it));
    b.addEventListener("click", () => { onPick(it); optionGroup(container, items, it, onPick, render); });
    container.append(b);
  }
}

function swatches(container, which) {
  container.replaceChildren();
  for (const c of cfg.colors) {
    const b = el("button", { class: "swatch", type: "button", "aria-pressed": String(state.colors[which] === c.hex) },
      [el("i", { style: `background:${c.hex}` }), c.name]);
    b.addEventListener("click", () => { state.colors[which] = c.hex; swatches(container, which); update(); });
    container.append(b);
  }
}

// ------------------------------------------------------------------ 3D view
const canvas = $("#view");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
scene.add(new THREE.HemisphereLight(0xffffff, 0xb8c0cc, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 1.6);
sun.position.set(80, 160, 120);
scene.add(sun);
const model = new THREE.Group();
model.rotation.x = -Math.PI / 2;            // engine is Z-up, three.js is Y-up
scene.add(model);
let framed = false;

function b64(s, Type) {
  const bin = atob(s);
  const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Type(buf.buffer);
}

function showParts(parts) {
  for (const m of model.children) { m.geometry.dispose(); m.material.dispose(); }
  model.clear();
  for (const p of parts) {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(b64(p.positions, Float32Array), 3));
    g.setIndex(new THREE.BufferAttribute(b64(p.indices, Uint32Array), 1));
    g.computeVertexNormals();
    const mat = new THREE.MeshStandardMaterial({ color: p.color, roughness: 0.55, metalness: 0.02 });
    model.add(new THREE.Mesh(g, mat));
  }
  if (!framed && parts.length) { setView("iso"); framed = true; }
}

function setView(v) {
  const box = new THREE.Box3().setFromObject(model);
  const c = box.getCenter(new THREE.Vector3());
  const r = box.getSize(new THREE.Vector3()).length() / 2;
  const d = r / Math.sin((camera.fov * Math.PI) / 360) * 1.05;
  const dir = v === "top" ? new THREE.Vector3(0, 1, 0.0001) : new THREE.Vector3(0.35, 0.75, 0.9).normalize();
  camera.position.copy(c.clone().add(dir.multiplyScalar(d)));
  controls.target.copy(c);
  camera.near = d / 50; camera.far = d * 10; camera.updateProjectionMatrix();
}

function resize() {
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (canvas.width !== Math.floor(w * renderer.getPixelRatio()) || canvas.height !== Math.floor(h * renderer.getPixelRatio())) {
    renderer.setSize(w, h, false);
    camera.aspect = w / Math.max(1, h);
    camera.updateProjectionMatrix();
  }
}
(function loop() { resize(); controls.update(); renderer.render(scene, camera); requestAnimationFrame(loop); })();
$$(".views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));

// ------------------------------------------------------------------ preview requests
let timer = null, seq = 0;
function update() {
  clearTimeout(timer);
  timer = setTimeout(requestPreview, 300);
}

async function requestPreview() {
  const my = ++seq;
  $("#busy").classList.add("on");
  try {
    const r = await fetch("/api/preview", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(design()) });
    const data = await r.json();
    if (my !== seq) return;                    // a newer request is on its way
    lastPreview = data;
    showMessages(data.errors, data.warnings);
    if (data.parts.length) showParts(data.parts);
    renderKeys(data.keys || []);
    $("#price").textContent = data.errors.length ? "—" : `₪${data.price}`;
    $("#price-lines").innerHTML = (data.price_lines || []).map(([l, a]) => `<div>${l}: ₪${a}</div>`).join("") +
      `<div><strong>סה״כ: ₪${data.price}</strong></div>`;
  } catch (e) {
    showMessages(["אין חיבור לשרת — נסו שוב."], []);
  } finally {
    if (my === seq) $("#busy").classList.remove("on");
  }
}

function design() {
  return { text: state.text, font: state.font, mode: state.mode, size_pct: state.size_pct, keycap: state.keycap,
    layout: state.layout, texture: state.texture, keychain: state.keychain, colors: state.colors, extras: state.extras };
}

function showMessages(errors, warnings) {
  const box = $("#messages");
  box.replaceChildren(...errors.map((m) => el("div", { class: "msg err" }, m)),
    ...(warnings || []).slice(0, 2).map((m) => el("div", { class: "msg warn" }, m)));
}

function renderKeys(keys) {
  const chips = $("#keychips");
  chips.replaceChildren(...keys.map((k) => el("span", { class: "chip" },
    k.kind === "char" ? k.value : k.kind === "blank" ? "□" : "★")));
  $("#keycount").textContent = `${keys.length} מקשים (מקסימום ${cfg.max_keys}) · ₪${cfg.pricing.per_key} למקש`;
  const ex = $("#extras");
  ex.replaceChildren(...state.extras.map((x, i) => el("button", { class: "chip", type: "button",
    "aria-label": "הסרת מקש נוסף", onclick: () => { state.extras.splice(i, 1); update(); } },
    `${x.kind === "blank" ? "מקש ריק" : (cfg.symbols.find((s) => s.id === x.value) || {}).name} (${NAMES.sides[x.side]}) ✕`)));
}

// ------------------------------------------------------------------ steps
const order = $$(".steps button").map((b) => b.dataset.step);
function go(step) {
  $$(".steps button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.step === step)));
  $$(".step").forEach((s) => s.classList.toggle("on", s.dataset.step === step));
  $("#next").textContent = step === "order" ? "שליחת ההזמנה" : "המשך";
  $(".cfg").classList.toggle("ordering", step === "order");
  document.querySelector(`.steps button[data-step="${step}"]`).scrollIntoView({ inline: "center", block: "nearest" });
}
$$(".steps button").forEach((b) => b.addEventListener("click", () => go(b.dataset.step)));
$("#next").addEventListener("click", () => {
  const cur = $(".steps button[aria-selected=true]").dataset.step;
  if (cur === "order") return $("#order-form").requestSubmit();
  let i = order.indexOf(cur) + 1;
  while (i < order.length && document.querySelector(`.steps button[data-step="${order[i]}"]`).hidden) i++;
  go(order[Math.min(i, order.length - 1)]);
});

// ------------------------------------------------------------------ order
$("#order-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  if (!f.reportValidity()) return;
  const btn = $("#submit");
  btn.disabled = true; btn.textContent = "שולח…";
  try {
    const r = await fetch("/api/orders", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ design: design(), customer: { name: f.name.value, email: f.email.value, phone: f.phone.value,
        notes: f.notes.value, marketing: f.marketing.checked, terms: f.terms.checked } }) });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "שגיאה");
    location.href = data.track_url;
  } catch (e) {
    showMessages([String(e.message || e)], []);
    btn.disabled = false; btn.textContent = "שליחת ההזמנה";
  }
});

// ------------------------------------------------------------------ init
async function init() {
  cfg = await (await fetch("/api/config")).json();
  state.colors = { ...cfg.defaults };
  state.mode = cfg.modes.includes("flush") ? "flush" : cfg.modes[0];
  state.keycap = cfg.keycaps[0];
  state.layout.style = cfg.layouts.includes("row") ? "row" : cfg.layouts[0];
  state.texture = cfg.textures.includes("smooth") ? "smooth" : cfg.textures[0];

  // fonts: each card is drawn in its own font
  const css = cfg.fonts.map((f) => `@font-face{font-family:"pf-${f.id.replace(/[^a-z0-9]/gi, "")}";src:url(/fonts/${encodeURIComponent(f.id)});font-display:swap}`).join("\n");
  document.head.append(el("style", { html: css }));
  state.font = (cfg.fonts.find((f) => f.id === "gf:rubik-700") || cfg.fonts[0] || {}).id;
  const renderFonts = () => optionGroup($("#fonts"), cfg.fonts.map((f) => f.id), state.font,
    (id) => { state.font = id; update(); },
    (id) => { const f = cfg.fonts.find((x) => x.id === id);
      return [el("span", { class: "sample", style: `font-family:"pf-${id.replace(/[^a-z0-9]/gi, "")}"` }, state.text || "שלום"),
        el("span", { class: "fname" }, f.family)]; });
  renderFonts();

  optionGroup($("#modes"), cfg.modes, state.mode, (m) => { state.mode = m; update(); }, (m) => NAMES.modes[m] || m);
  optionGroup($("#keycaps"), cfg.keycaps, state.keycap, (k) => { state.keycap = k; update(); },
    (k) => [el("img", { src: `/thumbs/keycap_${k}.png`, alt: "" }), NAMES.keycaps[k] || k]);
  optionGroup($("#layouts"), cfg.layouts.filter((l) => l !== "custom"), state.layout.style,
    (l) => { state.layout.style = l; $("#grid-size").hidden = l !== "grid"; update(); }, (l) => NAMES.layouts[l] || l);
  optionGroup($("#textures"), cfg.textures, state.texture, (t) => { state.texture = t; update(); },
    (t) => [el("img", { src: `/thumbs/texture_${t}.png`, alt: "" }), NAMES.textures[t] || t]);
  ["body", "cap", "legend"].forEach((w) => swatches($(`#c-${w}`), w));

  $("#keychain-box").hidden = !cfg.keychain;
  $("#kc").addEventListener("change", (e) => { state.keychain.enabled = e.target.checked; $("#kc-opts").hidden = !e.target.checked; update(); });
  optionGroup($("#kc-side"), ["top", "bottom", "right", "left"], state.keychain.side,
    (v) => { state.keychain.side = v; update(); }, (v) => NAMES.sides[v]);
  optionGroup($("#kc-shape"), ["rounded", "round", "square"], state.keychain.shape,
    (v) => { state.keychain.shape = v; update(); }, (v) => NAMES.shapes[v]);

  if (!cfg.symbols.length) { $("#tab-symbols").hidden = true; }
  const symBox = $("#symbols");
  for (const s of cfg.symbols) {
    const b = el("button", { class: "opt", type: "button", "aria-pressed": "false", title: s.name, "aria-label": s.name, html: s.svg });
    b.addEventListener("click", () => {
      pickedSymbol = s.id;
      $$("#symbols .opt").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      $("#sym-left").disabled = $("#sym-right").disabled = false;
    });
    symBox.append(b);
  }
  $("#sym-left").addEventListener("click", () => { state.extras.push({ kind: "symbol", value: pickedSymbol, side: "left" }); update(); });
  $("#sym-right").addEventListener("click", () => { state.extras.push({ kind: "symbol", value: pickedSymbol, side: "right" }); update(); });
  $("#blank-left").addEventListener("click", () => { state.extras.push({ kind: "blank", side: "left" }); update(); });
  $("#blank-right").addEventListener("click", () => { state.extras.push({ kind: "blank", side: "right" }); update(); });

  $("#text").addEventListener("input", (e) => { state.text = e.target.value; renderFonts(); update(); });
  $("#size").addEventListener("input", (e) => { state.size_pct = +e.target.value; $("#size-out").textContent = `${e.target.value}%`; update(); });
  $("#rows").addEventListener("change", (e) => { state.layout.rows = +e.target.value; update(); });
  $("#cols").addEventListener("change", (e) => { state.layout.cols = +e.target.value; update(); });
  update();
}
init();
