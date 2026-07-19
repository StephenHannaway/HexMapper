const HEX_SIZE = 20;
const SQRT3 = Math.sqrt(3);

const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");

const state = {
  hexes: new Map(), // "q,r" -> {q, r, terrain, icon}
  version: 0,
  terrains: {},
  icons: [],
  iconImages: new Map(),
  tool: "paint", // paint | icon | remove
  terrain: "GRASSLAND",
  icon: null,
  offsetX: 0,
  offsetY: 0,
  scale: 1.5,
  ws: null,
  role: "dm",
};

const key = (q, r) => `${q},${r}`;

function hexToPixel(q, r) {
  return [HEX_SIZE * 1.5 * q, HEX_SIZE * SQRT3 * (r + q / 2)];
}

function pixelToHex(x, y) {
  const q = (2 / 3) * x / HEX_SIZE;
  const r = (-1 / 3 * x + (SQRT3 / 3) * y) / HEX_SIZE;
  return roundHex(q, r);
}

function roundHex(q, r) {
  const s = -q - r;
  let qr = Math.round(q), rr = Math.round(r), sr = Math.round(s);
  const dq = Math.abs(qr - q), dr = Math.abs(rr - r), ds = Math.abs(sr - s);
  if (dq > dr && dq > ds) qr = -rr - sr;
  else if (dr > ds) rr = -qr - sr;
  return [qr, rr];
}

function screenToWorld(sx, sy) {
  return [(sx - state.offsetX) / state.scale, (sy - state.offsetY) / state.scale];
}

function draw() {
  const w = canvas.width, h = canvas.height;
  ctx.fillStyle = "#1e1e1e";
  ctx.fillRect(0, 0, w, h);
  const size = HEX_SIZE * state.scale;
  for (const cell of state.hexes.values()) {
    const [wx, wy] = hexToPixel(cell.q, cell.r);
    const sx = wx * state.scale + state.offsetX;
    const sy = wy * state.scale + state.offsetY;
    if (sx < -size * 2 || sy < -size * 2 || sx > w + size * 2 || sy > h + size * 2) continue;
    ctx.beginPath();
    for (let i = 0; i < 6; i++) {
      const a = (Math.PI / 3) * i;
      const px = sx + size * Math.cos(a), py = sy + size * Math.sin(a);
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
    }
    ctx.closePath();
    ctx.fillStyle = state.terrains[cell.terrain] || "#ff00ff";
    ctx.fill();
    ctx.strokeStyle = "#323232";
    ctx.lineWidth = 1;
    ctx.stroke();
    if (cell.icon) {
      const img = state.iconImages.get(cell.icon);
      if (img && img.complete) {
        const s = size * 1.3;
        ctx.drawImage(img, sx - s / 2, sy - s / 2, s, s);
      }
    }
  }
}

function resize() {
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  draw();
}

// --- sync ---

function applyHex(h) {
  state.hexes.set(key(h.q, h.r), { icon: null, ...h });
}

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  state.ws = ws;
  ws.onopen = () => {
    setStatus("connected");
    ws.send(JSON.stringify({ op: "hello", name: playerName }));
  };
  ws.onclose = () => {
    setStatus("disconnected — retrying…");
    setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "snapshot") {
      const firstLoad = !state.hexes.size;
      state.hexes.clear();
      msg.hexes.forEach(applyHex);
      state.version = msg.version;
      if (firstLoad) fitView();
    } else if (msg.type === "op") {
      if (msg.op === "set_hex") {
        const existing = state.hexes.get(key(msg.q, msg.r));
        state.hexes.set(key(msg.q, msg.r), {
          q: msg.q, r: msg.r, terrain: msg.terrain,
          icon: existing ? existing.icon : null,
        });
      } else if (msg.op === "set_icon") {
        const cell = state.hexes.get(key(msg.q, msg.r));
        if (cell) cell.icon = msg.icon;
      } else if (msg.op === "remove_hex") {
        state.hexes.delete(key(msg.q, msg.r));
      } else if (msg.op === "apply_hexes") {
        msg.hexes.forEach(applyHex);
      }
      state.version = msg.version;
    } else if (msg.type === "presence") {
      document.getElementById("presence").innerHTML = msg.users
        .map((u) => `<div><span class="dot">●</span>${u}</div>`)
        .join("") || "nobody";
    } else if (msg.type === "error") {
      toast(msg.detail);
    }
    draw();
  };
}

function send(op) {
  if (state.ws && state.ws.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify(op));
  }
}

// --- editing ---

function editAt(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const [wx, wy] = screenToWorld(
    (clientX - rect.left) * devicePixelRatio,
    (clientY - rect.top) * devicePixelRatio
  );
  const [q, r] = pixelToHex(wx, wy);
  const k = key(q, r);
  const cell = state.hexes.get(k);

  if (state.tool === "remove") {
    if (cell) {
      state.hexes.delete(k);
      send({ op: "remove_hex", q, r });
    }
  } else if (state.tool === "icon") {
    if (!cell || !state.icon) return;
    const icon = cell.icon === state.icon ? null : state.icon;
    cell.icon = icon;
    send({ op: "set_icon", q, r, icon });
  } else {
    if (cell && cell.terrain === state.terrain) return;
    state.hexes.set(k, { q, r, terrain: state.terrain, icon: cell ? cell.icon : null });
    send({ op: "set_hex", q, r, terrain: state.terrain });
  }
  draw();
}

// --- input ---

let dragging = false, painting = false, lastX = 0, lastY = 0, moved = 0;
let spaceHeld = false;
const heldKeys = new Set();

canvas.addEventListener("pointerdown", (e) => {
  canvas.setPointerCapture(e.pointerId);
  lastX = e.clientX; lastY = e.clientY; moved = 0;
  const panning =
    state.tool === "pan" || spaceHeld || e.button === 1 || e.button === 2 || e.shiftKey;
  if (panning) {
    dragging = true;
    canvas.style.cursor = "grabbing";
  } else if (e.button === 0) painting = true;
});

canvas.addEventListener("pointermove", (e) => {
  const dx = e.clientX - lastX, dy = e.clientY - lastY;
  moved += Math.abs(dx) + Math.abs(dy);
  lastX = e.clientX; lastY = e.clientY;
  if (dragging) {
    state.offsetX += dx * devicePixelRatio;
    state.offsetY += dy * devicePixelRatio;
    draw();
  } else if (painting && state.tool === "paint") {
    editAt(e.clientX, e.clientY);
  }
});

canvas.addEventListener("pointerup", (e) => {
  if (painting && (state.tool !== "paint" || moved < 6)) editAt(e.clientX, e.clientY);
  dragging = painting = false;
  canvas.style.cursor = state.tool === "pan" ? "grab" : "crosshair";
});

function isTyping() {
  const el = document.activeElement;
  return el && (el.tagName === "INPUT" || el.tagName === "SELECT");
}

const PAN_KEYS = {
  ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, 1], ArrowDown: [0, -1],
  a: [1, 0], d: [-1, 0], w: [0, 1], s: [0, -1],
};

function panLoop() {
  if (!heldKeys.size) return;
  let dx = 0, dy = 0;
  for (const k of heldKeys) {
    const v = PAN_KEYS[k];
    if (v) { dx += v[0]; dy += v[1]; }
  }
  state.offsetX += dx * 14;
  state.offsetY += dy * 14;
  draw();
  requestAnimationFrame(panLoop);
}

function zoomAtCenter(factor) {
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const newScale = Math.min(6, Math.max(0.2, state.scale * factor));
  state.offsetX = cx - (cx - state.offsetX) * (newScale / state.scale);
  state.offsetY = cy - (cy - state.offsetY) * (newScale / state.scale);
  state.scale = newScale;
  draw();
}

window.addEventListener("keydown", (e) => {
  if (isTyping()) return;
  if (e.key === " ") {
    spaceHeld = true;
    e.preventDefault();
    return;
  }
  if (e.key === "+" || e.key === "=") { zoomAtCenter(1.15); return; }
  if (e.key === "-" || e.key === "_") { zoomAtCenter(1 / 1.15); return; }
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (PAN_KEYS[k]) {
    e.preventDefault();
    if (!heldKeys.size) requestAnimationFrame(panLoop);
    heldKeys.add(k);
  }
});

window.addEventListener("keyup", (e) => {
  if (e.key === " ") spaceHeld = false;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  heldKeys.delete(k);
});

window.addEventListener("blur", () => {
  spaceHeld = false;
  heldKeys.clear();
});

function fitView() {
  if (!state.hexes.size) return;
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const cell of state.hexes.values()) {
    const [x, y] = hexToPixel(cell.q, cell.r);
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  const pad = HEX_SIZE * 3;
  const w = maxX - minX + pad * 2, h = maxY - minY + pad * 2;
  state.scale = Math.min(6, Math.max(0.2, Math.min(canvas.width / w, canvas.height / h)));
  state.offsetX = canvas.width / 2 - ((minX + maxX) / 2) * state.scale;
  state.offsetY = canvas.height / 2 - ((minY + maxY) / 2) * state.scale;
  draw();
}

canvas.addEventListener("contextmenu", (e) => e.preventDefault());

canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  const rect = canvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) * devicePixelRatio;
  const my = (e.clientY - rect.top) * devicePixelRatio;
  const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
  const newScale = Math.min(6, Math.max(0.2, state.scale * factor));
  state.offsetX = mx - (mx - state.offsetX) * (newScale / state.scale);
  state.offsetY = my - (my - state.offsetY) * (newScale / state.scale);
  state.scale = newScale;
  draw();
}, { passive: false });

// --- ui ---

function setTool(tool) {
  state.tool = tool;
  for (const [id, t] of [["panBtn", "pan"], ["paintBtn", "paint"], ["iconBtn", "icon"], ["removeBtn", "remove"]]) {
    document.getElementById(id).classList.toggle("active", t === tool);
  }
  canvas.style.cursor = tool === "pan" ? "grab" : "crosshair";
}

function setStatus(text) {
  document.getElementById("status").textContent = text;
}

let toastTimer;
function toast(text) {
  const el = document.getElementById("toast");
  el.textContent = text;
  el.style.opacity = 1;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.style.opacity = 0), 2500);
}

document.getElementById("panBtn").onclick = () => setTool("pan");
document.getElementById("centerBtn").onclick = fitView;
document.getElementById("paintBtn").onclick = () => setTool("paint");
document.getElementById("iconBtn").onclick = () => setTool("icon");
document.getElementById("removeBtn").onclick = () => setTool("remove");
document.getElementById("layerBtn").onclick = () =>
  send({ op: "add_layer", terrain: state.terrain });
let clearArmed = false;
const clearBtn = document.getElementById("clearBtn");
clearBtn.onclick = () => {
  if (!clearArmed) {
    clearArmed = true;
    clearBtn.textContent = "Really clear? (click again)";
    clearBtn.classList.add("active");
    setTimeout(() => {
      clearArmed = false;
      clearBtn.textContent = "Clear all";
      clearBtn.classList.remove("active");
    }, 3000);
    return;
  }
  clearArmed = false;
  clearBtn.textContent = "Clear all";
  clearBtn.classList.remove("active");
  send({ op: "clear_all" });
};
document.getElementById("exportBtn").onclick = () => {
  const a = document.createElement("a");
  a.href = "/api/map/export";
  a.download = "world.hexmap";
  a.click();
};
const importInput = document.getElementById("importInput");
document.getElementById("importBtn").onclick = () => importInput.click();
importInput.onchange = async () => {
  const file = importInput.files[0];
  importInput.value = "";
  if (!file) return;
  let data;
  try {
    data = JSON.parse(await file.text());
  } catch {
    toast("Not a valid .hexmap file");
    return;
  }
  const res = await fetch("/api/map/import", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(data),
  });
  const out = await res.json().catch(() => ({}));
  toast(res.ok ? `Imported ${out.hexes} hexes` : out.detail || "Import failed");
};

// --- init ---

let playerName =
  localStorage.getItem("playerName") ||
  `adventurer-${Math.floor(Math.random() * 900) + 100}`;
localStorage.setItem("playerName", playerName);

const nameInput = document.getElementById("nameInput");
nameInput.value = playerName;
nameInput.onchange = () => {
  playerName = nameInput.value.trim() || playerName;
  localStorage.setItem("playerName", playerName);
  send({ op: "hello", name: playerName });
};

async function init() {
  const cfg = await (await fetch("/api/config")).json();
  state.terrains = cfg.terrains;
  state.icons = cfg.icons;
  state.role = cfg.role || "dm";
  document.querySelectorAll(".dm-only").forEach((el) => {
    el.style.display = state.role === "dm" ? "" : "none";
  });

  const grid = document.getElementById("terrainGrid");
  for (const [name, color] of Object.entries(cfg.terrains)) {
    const btn = document.createElement("button");
    btn.style.background = color;
    btn.title = name;
    if (name === state.terrain) btn.classList.add("selected");
    btn.onclick = () => {
      state.terrain = name;
      grid.querySelectorAll("button").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      if (state.tool === "icon") setTool("paint");
      toast(name);
    };
    grid.appendChild(btn);
  }

  const iconGrid = document.getElementById("iconGrid");
  for (const icon of cfg.icons) {
    const img = new Image();
    img.src = icon.url;
    img.onload = draw;
    state.iconImages.set(icon.name, img);

    const btn = document.createElement("button");
    btn.title = icon.name;
    const thumb = document.createElement("img");
    thumb.src = icon.url;
    thumb.alt = icon.name;
    btn.appendChild(thumb);
    btn.onclick = () => {
      if (state.icon === icon.name) {
        state.icon = null;
        btn.classList.remove("selected");
        setTool("paint");
        return;
      }
      state.icon = icon.name;
      iconGrid.querySelectorAll("button").forEach((b) => b.classList.remove("selected"));
      btn.classList.add("selected");
      setTool("icon");
      toast(icon.name);
    };
    iconGrid.appendChild(btn);
  }

  state.offsetX = canvas.clientWidth * devicePixelRatio / 2;
  state.offsetY = canvas.clientHeight * devicePixelRatio / 2;
  resize();
  connect();
}

window.addEventListener("resize", resize);
init();
