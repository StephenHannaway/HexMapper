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
  party: null, // {q, r} shared party position
  hadSnapshot: false,
  fog: false,
  features: new Map(), // id -> {id, kind, path, created_by}
  featureCosts: null,
  draft: null, // {kind, waypoints: [[q,r],...], preview: [[q,r],...]}
};

const key = (q, r) => `${q},${r}`;

function featureIdsAt(q, r) {
  const ids = [];
  for (const f of state.features.values()) {
    if (f.path.some(([pq, pr]) => pq === q && pr === r)) ids.push(f.id);
  }
  return ids;
}

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

function traceHex(sx, sy, size) {
  ctx.beginPath();
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i;
    const px = sx + size * Math.cos(a), py = sy + size * Math.sin(a);
    i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
  }
  ctx.closePath();
}

const FEATURE_STYLE = {
  river: { stroke: "#4a90d9", width: 0.3, casing: null },
  road: { stroke: "#8b6b3d", width: 0.18, casing: "#00000055" },
};

function pathToPoints(path) {
  return path.map(([q, r]) => {
    const [wx, wy] = hexToPixel(q, r);
    return [wx * state.scale + state.offsetX, wy * state.scale + state.offsetY];
  });
}

function tracePolyline(pts) {
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length - 1; i++) {
    const mx = (pts[i][0] + pts[i + 1][0]) / 2;
    const my = (pts[i][1] + pts[i + 1][1]) / 2;
    ctx.quadraticCurveTo(pts[i][0], pts[i][1], mx, my);
  }
  ctx.lineTo(pts[pts.length - 1][0], pts[pts.length - 1][1]);
}

function strokeFeature(path, kind, dashed) {
  const pts = pathToPoints(path);
  if (pts.length < 2) return;
  const size = HEX_SIZE * state.scale;
  const style = FEATURE_STYLE[kind];
  ctx.lineCap = ctx.lineJoin = "round";
  if (dashed) ctx.setLineDash([6, 6]);
  if (style.casing && !dashed) {
    tracePolyline(pts);
    ctx.strokeStyle = style.casing;
    ctx.lineWidth = size * (style.width + 0.1);
    ctx.stroke();
  }
  tracePolyline(pts);
  ctx.strokeStyle = style.stroke;
  ctx.lineWidth = Math.max(1.5, size * style.width);
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawFeaturePaths(kind) {
  const hideFog = state.fog && state.role !== "dm";
  for (const f of state.features.values()) {
    if (f.kind !== kind) continue;
    let runs = [f.path];
    if (hideFog) {
      // players see roads/rivers break at unexplored territory
      runs = [];
      let cur = [];
      for (const [q, r] of f.path) {
        const cell = state.hexes.get(key(q, r));
        if (cell && cell.explored) cur.push([q, r]);
        else if (cur.length) {
          runs.push(cur);
          cur = [];
        }
      }
      if (cur.length) runs.push(cur);
    }
    for (const run of runs) strokeFeature(run, kind, false);
  }
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
    const fogged = state.fog && !cell.explored;
    traceHex(sx, sy, size);
    if (fogged && state.role !== "dm") {
      ctx.fillStyle = "#26262c";
      ctx.fill();
      ctx.strokeStyle = "#323232";
      ctx.lineWidth = 1;
      ctx.stroke();
      continue;
    }
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
    if (cell.note) {
      ctx.beginPath();
      ctx.arc(sx + size * 0.5, sy - size * 0.55, Math.max(2.5, size * 0.16), 0, Math.PI * 2);
      ctx.fillStyle = "#ffd54a";
      ctx.fill();
      ctx.strokeStyle = "#00000088";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
    if (fogged) {
      // DM view of a hidden hex: rendered but dimmed
      traceHex(sx, sy, size);
      ctx.fillStyle = "#00000073";
      ctx.fill();
    }
  }
  drawFeaturePaths("river");
  drawFeaturePaths("road");
  if (state.draft && state.draft.waypoints.length) {
    const committed = state.draft.committed;
    const preview = state.draft.preview || [];
    const full = committed.concat(
      committed.length && preview.length ? preview.slice(1) : preview
    );
    ctx.globalAlpha = 0.5;
    strokeFeature(full.length > 1 ? full : state.draft.waypoints, state.draft.kind, true);
    ctx.globalAlpha = 1;
  }
  const cutoff = Date.now() - 6000;
  for (const c of cursors.values()) {
    if (c.ts < cutoff) continue;
    const [wx, wy] = hexToPixel(c.q, c.r);
    const sx = wx * state.scale + state.offsetX;
    const sy = wy * state.scale + state.offsetY;
    if (sx < -size * 2 || sy < -size * 2 || sx > w + size * 2 || sy > h + size * 2) continue;
    traceHex(sx, sy, size);
    ctx.fillStyle = "#ffffff14";
    ctx.fill();
    ctx.strokeStyle = nameColor(c.name);
    ctx.lineWidth = Math.max(1.5, size * 0.08);
    ctx.stroke();
    const fontPx = Math.max(10, Math.min(14, size * 0.5));
    ctx.font = `${fontPx}px system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.fillStyle = nameColor(c.name);
    ctx.fillText(c.name, sx, sy + size * 1.35);
  }
  const now = performance.now();
  for (let i = pings.length - 1; i >= 0; i--) {
    const t = (now - pings[i].start) / 1500;
    if (t > 1) {
      pings.splice(i, 1);
      continue;
    }
    const [wx, wy] = hexToPixel(pings[i].q, pings[i].r);
    const sx = wx * state.scale + state.offsetX;
    const sy = wy * state.scale + state.offsetY;
    const phase = (t * 3) % 1; // three expanding pulses
    ctx.globalAlpha = 1 - phase;
    ctx.beginPath();
    ctx.arc(sx, sy, size * (0.4 + phase * 1.2), 0, Math.PI * 2);
    ctx.strokeStyle = "#7ec8ff";
    ctx.lineWidth = Math.max(2, size * 0.1);
    ctx.stroke();
    ctx.globalAlpha = 1;
  }
  if (state.party) {
    const [wx, wy] = hexToPixel(state.party.q, state.party.r);
    const sx = wx * state.scale + state.offsetX;
    const sy = wy * state.scale + state.offsetY;
    ctx.beginPath();
    ctx.arc(sx, sy, size * 0.6, 0, Math.PI * 2);
    ctx.strokeStyle = "#000000aa";
    ctx.lineWidth = Math.max(4, size * 0.22);
    ctx.stroke();
    ctx.beginPath();
    ctx.arc(sx, sy, size * 0.6, 0, Math.PI * 2);
    ctx.strokeStyle = "#ffd54a";
    ctx.lineWidth = Math.max(2, size * 0.12);
    ctx.stroke();
  }
}

function resize() {
  canvas.width = canvas.clientWidth * devicePixelRatio;
  canvas.height = canvas.clientHeight * devicePixelRatio;
  draw();
}

// --- live cursors ---

const cursors = new Map(); // cid -> {q, r, name, ts}
let lastCursorSent = 0, lastCursorKey = "";

function nameColor(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h}, 65%, 60%)`;
}

// --- road & river drafting ---

function hexDist(aq, ar, bq, br) {
  const dq = aq - bq, dr = ar - br;
  return (Math.abs(dq) + Math.abs(dr) + Math.abs(dq + dr)) / 2;
}

function featureCost(kind, q, r) {
  const cfg = state.featureCosts[kind];
  const cell = state.hexes.get(key(q, r));
  let base = cell ? (cfg.terrains[cell.terrain] ?? cfg.default) : cfg.default;
  for (const f of state.features.values()) {
    if (f.kind === kind && f.path.some(([pq, pr]) => pq === q && pr === r)) {
      base *= state.featureCosts.reuse;
      break;
    }
  }
  return base;
}

const AXIAL_DIRS = [[1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1], [1, -1]];

function jsAStar(start, goal, kind, maxNodes = 3000) {
  if (!state.featureCosts) return null;
  if (start[0] === goal[0] && start[1] === goal[1]) return [start];
  const g = new Map([[key(...start), 0]]);
  const came = new Map();
  const open = [[hexDist(...start, ...goal), start]];
  let explored = 0;
  while (open.length) {
    open.sort((a, b) => a[0] - b[0]);
    const [, cur] = open.shift();
    if (cur[0] === goal[0] && cur[1] === goal[1]) {
      const path = [cur];
      let k = key(...cur);
      while (came.has(k)) {
        path.unshift(came.get(k));
        k = key(...came.get(k));
      }
      return path;
    }
    if (++explored > maxNodes) break;
    const gCur = g.get(key(...cur));
    for (const [dq, dr] of AXIAL_DIRS) {
      const nxt = [cur[0] + dq, cur[1] + dr];
      const t = gCur + featureCost(kind, nxt[0], nxt[1]);
      const nk = key(...nxt);
      if (t < (g.get(nk) ?? Infinity)) {
        g.set(nk, t);
        came.set(nk, cur);
        open.push([t + hexDist(...nxt, ...goal), nxt]);
      }
    }
  }
  return null; // no preview — the server stays authoritative on submit
}

function finishDraft() {
  if (!state.draft || state.draft.waypoints.length < 2) return false;
  send({ op: "add_feature", kind: state.draft.kind, waypoints: state.draft.waypoints });
  state.draft = null;
  draw();
  return true;
}

function cancelDraft() {
  if (!state.draft) return false;
  state.draft = null;
  draw();
  return true;
}

function sendCursor(q, r) {
  const now = Date.now();
  const ck = key(q, r);
  if (ck === lastCursorKey || now - lastCursorSent < 120) return;
  lastCursorKey = ck;
  lastCursorSent = now;
  send({ op: "cursor", q, r });
}

setInterval(() => {
  let changed = false;
  const cutoff = Date.now() - 6000;
  for (const [cid, c] of cursors) {
    if (c.ts < cutoff) {
      cursors.delete(cid);
      changed = true;
    }
  }
  if (changed) draw();
}, 2000);

// --- pings ---

const pings = []; // {q, r, start} ephemeral flashes

function animatePings() {
  if (!pings.length) return;
  draw();
  requestAnimationFrame(animatePings);
}

function addPing(q, r) {
  pings.push({ q, r, start: performance.now() });
  if (pings.length === 1) requestAnimationFrame(animatePings);
}

// --- sync ---

function applyHex(h) {
  state.hexes.set(key(h.q, h.r), {
    icon: null, note: null, note_author: null, explored: 1, ...h,
  });
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
      const firstLoad = !state.hadSnapshot;
      state.hadSnapshot = true;
      state.hexes.clear();
      msg.hexes.forEach(applyHex);
      state.party = msg.party || null;
      state.fog = !!msg.fog;
      state.features.clear();
      (msg.features || []).forEach((f) => state.features.set(f.id, f));
      updateFogBtn();
      state.version = msg.version;
      if (firstLoad) fitView();
      if (msg.action) {
        addHistory({
          ts: Date.now() / 1000, player: msg.by || "someone", op: msg.action, detail: {},
        });
      }
    } else if (msg.type === "op") {
      if (msg.version > state.version + 1) resync(); // missed a broadcast
      if (msg.op === "set_hex") {
        const existing = state.hexes.get(key(msg.q, msg.r));
        state.hexes.set(key(msg.q, msg.r), {
          q: msg.q, r: msg.r, terrain: msg.terrain,
          icon: existing ? existing.icon : null,
          note: existing ? existing.note : null,
          note_author: existing ? existing.note_author : null,
          explored: 1,
        });
      } else if (msg.op === "set_note") {
        const cell = state.hexes.get(key(msg.q, msg.r));
        if (cell) {
          cell.note = msg.note;
          cell.note_author = msg.note_author;
          refreshNotePanel(msg.q, msg.r);
        }
      } else if (msg.op === "add_feature") {
        state.features.set(msg.feature.id, msg.feature);
      } else if (msg.op === "remove_feature") {
        state.features.delete(msg.id);
      } else if (msg.op === "set_explored") {
        const cell = state.hexes.get(key(msg.q, msg.r));
        if (cell) cell.explored = msg.explored ? 1 : 0;
      } else if (msg.op === "set_fog") {
        state.fog = msg.enabled;
        updateFogBtn();
        toast(`Fog of war ${state.fog ? "enabled" : "disabled"}`);
      } else if (msg.op === "set_party") {
        state.party = { q: msg.q, r: msg.r };
      } else if (msg.op === "set_icon") {
        const cell = state.hexes.get(key(msg.q, msg.r));
        if (cell) cell.icon = msg.icon;
      } else if (msg.op === "remove_hex") {
        state.hexes.delete(key(msg.q, msg.r));
      } else if (msg.op === "apply_hexes") {
        msg.hexes.forEach(applyHex);
      }
      state.version = msg.version;
      addHistory({
        ts: Date.now() / 1000,
        player: msg.by || "someone",
        op: msg.op,
        detail: {
          q: msg.q, r: msg.r, terrain: msg.terrain, icon: msg.icon,
          explored: msg.explored, enabled: msg.enabled,
          kind: msg.feature ? msg.feature.kind : undefined,
        },
      });
    } else if (msg.type === "ping") {
      addPing(msg.q, msg.r);
    } else if (msg.type === "cursor") {
      cursors.set(msg.cid, { q: msg.q, r: msg.r, name: msg.by, ts: Date.now() });
    } else if (msg.type === "presence") {
      renderPresence(msg.users);
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

let resyncing = false;
async function resync() {
  if (resyncing) return;
  resyncing = true;
  try {
    const snap = await (await fetch("/api/map")).json();
    state.hexes.clear();
    snap.hexes.forEach(applyHex);
    state.party = snap.party || null;
    state.fog = !!snap.fog;
    state.features.clear();
    (snap.features || []).forEach((f) => state.features.set(f.id, f));
    updateFogBtn();
    state.version = snap.version;
    draw();
  } finally {
    resyncing = false;
  }
}

// --- editing ---

function editAt(clientX, clientY, ev) {
  const rect = canvas.getBoundingClientRect();
  const [wx, wy] = screenToWorld(
    (clientX - rect.left) * devicePixelRatio,
    (clientY - rect.top) * devicePixelRatio
  );
  const [q, r] = pixelToHex(wx, wy);
  const k = key(q, r);
  const cell = state.hexes.get(k);

  if (state.tool === "road" || state.tool === "river") {
    if (ev && ev.shiftKey) {
      const ids = featureIdsAt(q, r);
      if (ids.length) send({ op: "remove_feature", id: ids[ids.length - 1] });
      else toast("No road or river there");
      return;
    }
    if (!state.draft || state.draft.kind !== state.tool) {
      state.draft = { kind: state.tool, waypoints: [], committed: [], preview: [] };
    }
    const d = state.draft;
    if (d.waypoints.length) {
      const leg = jsAStar(d.waypoints[d.waypoints.length - 1], [q, r], d.kind) || [];
      d.committed.push(...(d.committed.length ? leg.slice(1) : leg));
    }
    d.waypoints.push([q, r]);
    d.preview = [];
    toast(
      d.waypoints.length < 2
        ? "Click more waypoints — Enter or double-click builds, Esc cancels"
        : `${d.waypoints.length} waypoints — Enter builds, Esc cancels`
    );
    draw();
  } else if (state.tool === "note") {
    if (state.fog && state.role !== "dm" && cell && !cell.explored) {
      toast("Unexplored territory");
    } else {
      openNotePanel(q, r);
    }
  } else if (state.tool === "reveal") {
    if (!cell) return;
    cell.explored = cell.explored ? 0 : 1;
    send({ op: "set_explored", q, r, explored: !!cell.explored });
  } else if (state.tool === "party") {
    state.party = { q, r };
    send({ op: "set_party", q, r });
    toast(`Party moved to ${q},${r}`);
  } else if (state.tool === "remove") {
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
    state.hexes.set(k, {
      q, r, terrain: state.terrain,
      icon: cell ? cell.icon : null,
      note: cell ? cell.note : null,
      note_author: cell ? cell.note_author : null,
      explored: 1,
    });
    send({ op: "set_hex", q, r, terrain: state.terrain });
  }
  draw();
}

// --- input ---

let dragging = false, painting = false, lastX = 0, lastY = 0, moved = 0;
let spaceHeld = false, didPinch = false, pinchDist = 0;
const pointers = new Map(); // pointerId -> {x, y}
const heldKeys = new Set();

canvas.addEventListener("pointerdown", (e) => {
  canvas.setPointerCapture(e.pointerId);
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pointers.size === 2) {
    // second finger: switch to pinch-zoom, cancel any paint/drag in progress
    dragging = painting = false;
    didPinch = true;
    const [a, b] = [...pointers.values()];
    pinchDist = Math.hypot(a.x - b.x, a.y - b.y);
    return;
  }
  if (pointers.size > 2) return;
  lastX = e.clientX; lastY = e.clientY; moved = 0;
  const featureTool = state.tool === "road" || state.tool === "river";
  const panning =
    state.tool === "pan" || spaceHeld || e.button === 1 || e.button === 2 ||
    (e.shiftKey && !featureTool); // shift+click on feature tools = remove, not pan
  if (panning) {
    dragging = true;
    canvas.style.cursor = "grabbing";
  } else if (e.button === 0) painting = true;
});

canvas.addEventListener("pointermove", (e) => {
  const p = pointers.get(e.pointerId);
  if (p && pointers.size === 2) {
    const other = [...pointers.entries()].find(([id]) => id !== e.pointerId)[1];
    const oldMidX = (p.x + other.x) / 2, oldMidY = (p.y + other.y) / 2;
    p.x = e.clientX; p.y = e.clientY;
    const newMidX = (p.x + other.x) / 2, newMidY = (p.y + other.y) / 2;
    const newDist = Math.hypot(p.x - other.x, p.y - other.y);
    state.offsetX += (newMidX - oldMidX) * devicePixelRatio;
    state.offsetY += (newMidY - oldMidY) * devicePixelRatio;
    if (pinchDist > 0) zoomAt(newMidX, newMidY, newDist / pinchDist);
    pinchDist = newDist;
    draw();
    return;
  }
  if (p) { p.x = e.clientX; p.y = e.clientY; }
  if (didPinch) return;
  const dx = e.clientX - lastX, dy = e.clientY - lastY;
  moved += Math.abs(dx) + Math.abs(dy);
  lastX = e.clientX; lastY = e.clientY;
  if (dragging) {
    state.offsetX += dx * devicePixelRatio;
    state.offsetY += dy * devicePixelRatio;
    draw();
  } else if (painting && state.tool === "paint") {
    editAt(e.clientX, e.clientY, e);
  }
  const rect = canvas.getBoundingClientRect();
  const [hwx, hwy] = screenToWorld(
    (e.clientX - rect.left) * devicePixelRatio,
    (e.clientY - rect.top) * devicePixelRatio
  );
  const [hq, hr] = pixelToHex(hwx, hwy);
  if (state.draft && state.draft.waypoints.length) {
    const last = state.draft.waypoints[state.draft.waypoints.length - 1];
    state.draft.preview = jsAStar(last, [hq, hr], state.draft.kind) || [];
    draw();
  }
  sendCursor(hq, hr);
});

function endPointer(e) {
  pointers.delete(e.pointerId);
  if (!pointers.size) didPinch = false;
  dragging = painting = false;
  canvas.style.cursor = state.tool === "pan" ? "grab" : "crosshair";
}

canvas.addEventListener("pointerup", (e) => {
  const wasPainting = painting && !didPinch;
  const doEdit = wasPainting && (state.tool !== "paint" || moved < 6);
  endPointer(e);
  if (doEdit) editAt(e.clientX, e.clientY, e);
});

canvas.addEventListener("pointercancel", endPointer);

function isTyping() {
  const el = document.activeElement;
  return el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA");
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

function zoomAt(clientX, clientY, factor) {
  const rect = canvas.getBoundingClientRect();
  const mx = (clientX - rect.left) * devicePixelRatio;
  const my = (clientY - rect.top) * devicePixelRatio;
  const newScale = Math.min(6, Math.max(0.2, state.scale * factor));
  state.offsetX = mx - (mx - state.offsetX) * (newScale / state.scale);
  state.offsetY = my - (my - state.offsetY) * (newScale / state.scale);
  state.scale = newScale;
  draw();
}

function zoomAtCenter(factor) {
  const cx = canvas.width / 2, cy = canvas.height / 2;
  const newScale = Math.min(6, Math.max(0.2, state.scale * factor));
  state.offsetX = cx - (cx - state.offsetX) * (newScale / state.scale);
  state.offsetY = cy - (cy - state.offsetY) * (newScale / state.scale);
  state.scale = newScale;
  draw();
}

const TOOL_KEYS = { p: "pan", b: "paint", i: "icon", n: "note", m: "party", o: "road", v: "river", r: "remove" };
const helpOverlay = document.getElementById("helpOverlay");
helpOverlay.onclick = () => { helpOverlay.hidden = true; };

window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (!helpOverlay.hidden) { helpOverlay.hidden = true; return; }
    if (cancelDraft()) return;
    if (!notePanel.hidden) { closeNotePanel(); return; }
  }
  if (isTyping()) return;
  if (e.key === "Enter" && finishDraft()) return;
  if (e.key === "?") {
    helpOverlay.hidden = !helpOverlay.hidden;
    return;
  }
  if (e.key === " ") {
    spaceHeld = true;
    e.preventDefault();
    return;
  }
  if (e.key === "+" || e.key === "=") { zoomAtCenter(1.15); return; }
  if (e.key === "-" || e.key === "_") { zoomAtCenter(1 / 1.15); return; }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (TOOL_KEYS[k]) {
    setTool(TOOL_KEYS[k]);
    return;
  }
  if (k === "c") { fitView(); return; }
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

canvas.addEventListener("dblclick", (e) => {
  if (finishDraft()) return;
  const rect = canvas.getBoundingClientRect();
  const [wx, wy] = screenToWorld(
    (e.clientX - rect.left) * devicePixelRatio,
    (e.clientY - rect.top) * devicePixelRatio
  );
  const [q, r] = pixelToHex(wx, wy);
  send({ op: "ping", q, r });
});

canvas.addEventListener("wheel", (e) => {
  e.preventDefault();
  zoomAt(e.clientX, e.clientY, e.deltaY < 0 ? 1.1 : 1 / 1.1);
}, { passive: false });

// --- ui ---

function setTool(tool) {
  state.tool = tool;
  for (const [id, t] of [["panBtn", "pan"], ["paintBtn", "paint"], ["iconBtn", "icon"], ["noteBtn", "note"], ["partyBtn", "party"], ["roadBtn", "road"], ["riverBtn", "river"], ["revealBtn", "reveal"], ["removeBtn", "remove"]]) {
    document.getElementById(id).classList.toggle("active", t === tool);
  }
  if (state.draft && state.draft.kind !== tool) cancelDraft();
  canvas.style.cursor = tool === "pan" ? "grab" : "crosshair";
}

// --- notes ---

let noteHex = null; // {q, r} of the hex open in the note panel
const notePanel = document.getElementById("notePanel");
const noteText = document.getElementById("noteText");

function openNotePanel(q, r) {
  const cell = state.hexes.get(key(q, r));
  if (!cell) {
    toast("No hex there — notes live on painted hexes");
    return;
  }
  noteHex = { q, r };
  document.getElementById("noteTitle").textContent = `Note — hex ${q},${r}`;
  noteText.value = cell.note || "";
  updateNoteMeta(cell);
  notePanel.hidden = false;
  noteText.focus();
}

function updateNoteMeta(cell) {
  document.getElementById("noteMeta").textContent = cell.note
    ? `last edited by ${cell.note_author || "unknown"}`
    : "no note yet";
}

function refreshNotePanel(q, r) {
  if (!noteHex || noteHex.q !== q || noteHex.r !== r) return;
  const cell = state.hexes.get(key(q, r));
  if (!cell) return;
  updateNoteMeta(cell);
  if (document.activeElement !== noteText) noteText.value = cell.note || "";
}

function closeNotePanel() {
  notePanel.hidden = true;
  noteHex = null;
}

document.getElementById("noteBtn").onclick = () => setTool("note");
document.getElementById("noteClose").onclick = closeNotePanel;
document.getElementById("noteSave").onclick = () => {
  if (!noteHex) return;
  const cell = state.hexes.get(key(noteHex.q, noteHex.r));
  if (!cell) return;
  const note = noteText.value.trim();
  cell.note = note || null;
  cell.note_author = note ? playerName : null;
  updateNoteMeta(cell);
  send({ op: "set_note", q: noteHex.q, r: noteHex.r, note });
  toast(note ? "Note saved" : "Note removed");
  draw();
};

// --- presence ---

let prevUsers = null;

function renderPresence(users) {
  document.title = `Hexmapper — ${users.length} online`;
  const counts = new Map();
  users.forEach((u) => counts.set(u, (counts.get(u) || 0) + 1));
  if (prevUsers) {
    const before = new Map();
    prevUsers.forEach((u) => before.set(u, (before.get(u) || 0) + 1));
    for (const [u, n] of counts) {
      if (n > (before.get(u) || 0)) toast(`${u} joined`);
    }
    for (const [u, n] of before) {
      if (n > (counts.get(u) || 0)) toast(`${u} left`);
    }
  }
  prevUsers = users;
  document.getElementById("presence").innerHTML =
    [...counts]
      .map(
        ([u, n]) =>
          `<div><span class="dot" style="color:${nameColor(u)}">●</span>` +
          `${esc(u)}${n > 1 ? ` ×${n}` : ""}</div>`
      )
      .join("") || "nobody";
}

// --- history feed ---

const historyEntries = [];

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

function opText(e) {
  const d = e.detail || {};
  const at = d.q !== undefined ? ` ${d.q},${d.r}` : "";
  switch (e.op) {
    case "set_hex":
      if (e.count > 1) return `painted ${e.count} hexes ${(d.terrain || "").toLowerCase()}`;
      return `painted${at} ${(d.terrain || "").toLowerCase()}`;
    case "set_icon": return d.icon ? `placed ${d.icon} at${at}` : `cleared the icon at${at}`;
    case "remove_hex": return `removed hex${at}`;
    case "set_note": return `wrote a note on${at}`;
    case "set_party": return `moved the party to${at}`;
    case "set_explored": return `${d.explored ? "revealed" : "hid"} hex${at}`;
    case "set_fog": return `turned fog of war ${d.enabled ? "on" : "off"}`;
    case "add_feature": return `built a ${d.kind || "path"}`;
    case "remove_feature": return "removed a road/river";
    case "add_layer": case "apply_hexes": return "added a ring of hexes";
    case "clear_all": return "cleared the map";
    case "import": return "restored a map";
    default: return e.op;
  }
}

function timeAgo(ts) {
  const s = Date.now() / 1000 - ts;
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function renderHistory() {
  document.getElementById("history").innerHTML = historyEntries.slice(0, 8)
    .map((e) => `<div><b>${esc(e.player)}</b> ${esc(opText(e))} · ${timeAgo(e.ts)}</div>`)
    .join("") || "nothing yet";
}

function addHistory(entry) {
  const top = historyEntries[0];
  if (top && entry.op === "set_hex" && top.op === "set_hex" &&
      top.player === entry.player && entry.ts - top.ts < 120) {
    top.count = (top.count || 1) + 1;
    top.ts = entry.ts;
    top.detail = entry.detail;
    renderHistory();
    return;
  }
  historyEntries.unshift(entry);
  if (historyEntries.length > 30) historyEntries.length = 30;
  renderHistory();
}

setInterval(renderHistory, 60000);

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
document.getElementById("partyBtn").onclick = () => setTool("party");
document.getElementById("roadBtn").onclick = () => setTool("road");
document.getElementById("riverBtn").onclick = () => setTool("river");
document.getElementById("revealBtn").onclick = () => setTool("reveal");
const fogBtn = document.getElementById("fogBtn");
function updateFogBtn() {
  fogBtn.textContent = `Fog of war: ${state.fog ? "on" : "off"}`;
}
fogBtn.onclick = () => send({ op: "set_fog", enabled: !state.fog });
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
  state.featureCosts = cfg.feature_costs;
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

  fetch("/api/history")
    .then((r) => r.json())
    .then((h) => {
      historyEntries.push(...h.ops);
      renderHistory();
    });
}

window.addEventListener("resize", resize);
init();
