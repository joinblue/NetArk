/* 16:9 Layered Topology Graph, Pill-Protected Labels & Hover Tooltip (`graph_canvas.js` — < 350 lines) */

const LAYER_TITLES = {
  1: "第 1 層：核心憲法與安全護欄 (000 / 100)",
  2: "第 2 層：核心架構規格與藍圖母體 (200 ~ 700 / Blueprint)",
  3: "第 3 層：藍圖子切片、Wiki 圖譜與交接台帳 (Shards / Wiki / 900)",
  4: "第 4 層：底層實作程式碼模組 (.ts / .py)",
};

const EDGE_LABELS = {
  shard_module: "🧩 子切片",
  depends_on: "⬆️ 依賴",
  wikilink: "🔗 引用",
  affects_code: "⚙️ 控制源碼",
  stub_path: "🧪 Stub骨架",
};

const WORLD_W = 1600;
let dynamicWorldH = 900;

function isNodeInCanvas(n) {
  if (!state.showCodeInGraph && n.node_kind === "code" && state.filter !== "code") return false;
  return true;
}

function setupGraphSimulation() {
  const allNodes = state.overview.nodes;
  const buckets = { 1: [], 2: [], 3: [], 4: [] };
  for (const n of allNodes) {
    const rank = n.layer_rank || (n.node_kind === "code" ? 4 : 2);
    (buckets[rank] || buckets[2]).push(n);
  }

  state.graphNodes = [];
  state.swimlanes = {};
  let currentY = 40;

  for (const rank of [1, 2, 3, 4]) {
    const list = buckets[rank];
    const cols = rank === 4 ? 8 : Math.min(7, Math.max(1, list.length));
    const rows = Math.max(1, Math.ceil(list.length / cols));
    const bandH = Math.max(158, 86 + rows * 82);
    const bandY = currentY;
    state.swimlanes[rank] = { y: bandY, h: bandH, rows };

    list.forEach((n, idx) => {
      const row = Math.floor(idx / cols);
      const col = idx % cols;
      const rowCount = Math.min(cols, list.length - row * cols);
      const spacingX = Math.min(225, (WORLD_W - 180) / Math.max(1, rowCount));
      const startX = WORLD_W / 2 - ((rowCount - 1) * spacingX) / 2;
      state.graphNodes.push({
        ...n,
        id: n.node_key || n.node_id,
        layer_rank: rank,
        x: startX + col * spacingX,
        y: bandY + 68 + row * 80,
      });
    });

    currentY += bandH + 26;
  }

  dynamicWorldH = Math.max(900, currentY + 20);
  const byId = Object.fromEntries(state.graphNodes.map((n) => [n.id, n]));
  state.graphEdges = state.overview.edges.filter((e) => byId[e.source] && byId[e.target]);
  resizeCanvas(true);
}

function fitCameraToCanvas() {
  const c = document.getElementById("graphCanvas");
  if (!c || !c.width || !c.height) return;
  const maxRank = state.showCodeInGraph || state.filter === "code" ? 4 : 3;
  const lane3 = state.swimlanes && state.swimlanes[3];
  const effectiveH = maxRank === 4 ? dynamicWorldH : (lane3 ? lane3.y + lane3.h + 35 : 690);
  const scaleX = (c.width - 40) / WORLD_W;
  const scaleY = (c.height - 40) / effectiveH;
  state.camera.zoom = Math.max(0.32, Math.min(1.35, Math.min(scaleX, scaleY)));
  state.camera.x = 0;
  state.camera.y = maxRank === 4 ? 0 : Math.round((dynamicWorldH - effectiveH) * 0.42 * state.camera.zoom);
}

function resizeCanvas(autoFit = false) {
  const c = document.getElementById("graphCanvas");
  if (!c || !c.parentElement) return;
  c.width = c.parentElement.clientWidth || 1100;
  c.height = Math.max(420, (c.parentElement.clientHeight || 640) - 42);
  if (autoFit) fitCameraToCanvas();
  drawGraph();
}

function getConnectedSet(selectedId) {
  const connected = new Set([selectedId]);
  for (const e of state.graphEdges) {
    if (e.source === selectedId) connected.add(e.target);
    if (e.target === selectedId) connected.add(e.source);
  }
  return connected;
}

function drawCurvedEdgeAndArrow(ctx, a, b, targetRadius, drawArrow) {
  const dy = b.y - a.y;
  const dx = b.x - a.x;
  let cp1x = a.x, cp1y = a.y + dy * 0.45;
  let cp2x = b.x, cp2y = b.y - dy * 0.45;
  if (Math.abs(dy) < 35) {
    const arcOffset = Math.min(65, Math.max(28, Math.abs(dx) * 0.18));
    cp1y = a.y - arcOffset;
    cp2y = b.y - arcOffset;
  }

  ctx.beginPath();
  ctx.moveTo(a.x, a.y);
  ctx.bezierCurveTo(cp1x, cp1y, cp2x, cp2y, b.x, b.y);
  ctx.stroke();

  if (drawArrow) {
    const angle = Math.atan2(b.y - cp2y, b.x - cp2x);
    const tipX = b.x - Math.cos(angle) * (targetRadius + 4);
    const tipY = b.y - Math.sin(angle) * (targetRadius + 4);
    const arrowLen = 8.5;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - arrowLen * Math.cos(angle - Math.PI / 6), tipY - arrowLen * Math.sin(angle - Math.PI / 6));
    ctx.lineTo(tipX - arrowLen * Math.cos(angle + Math.PI / 6), tipY - arrowLen * Math.sin(angle + Math.PI / 6));
    ctx.closePath();
    ctx.fill();
  }

  // Sample point t=0.38 on cubic Bezier for edge badge so it avoids midpoint clutter
  const t = 0.38, mt = 1 - t;
  return {
    mx: mt * mt * mt * a.x + 3 * mt * mt * t * cp1x + 3 * mt * t * t * cp2x + t * t * t * b.x,
    my: mt * mt * mt * a.y + 3 * mt * mt * t * cp1y + 3 * mt * t * t * cp2y + t * t * t * b.y,
  };
}

function drawGraph() {
  const c = document.getElementById("graphCanvas");
  if (!c) return;
  const ctx = c.getContext("2d");
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.save();
  ctx.translate(c.width / 2 + state.camera.x, c.height / 2 + state.camera.y);
  ctx.scale(state.camera.zoom, state.camera.zoom);
  ctx.translate(-WORLD_W / 2, -dynamicWorldH / 2);

  const maxRank = state.showCodeInGraph || state.filter === "code" ? 4 : 3;
  for (let r = 1; r <= maxRank; r++) {
    const lane = (state.swimlanes && state.swimlanes[r]) || { y: 45 + (r - 1) * 200, h: 175 };
    ctx.fillStyle = r % 2 === 1 ? "rgba(47, 43, 37, 0.52)" : "rgba(37, 34, 29, 0.52)";
    ctx.strokeStyle = "rgba(217, 159, 78, 0.18)";
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.roundRect(40, lane.y, WORLD_W - 80, lane.h, 10);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "rgba(243, 200, 120, 0.85)";
    ctx.font = "bold 13.5px sans-serif";
    ctx.textAlign = "left";
    ctx.fillText(LAYER_TITLES[r], 62, lane.y + 26);
  }

  const byId = Object.fromEntries(state.graphNodes.map((n) => [n.id, n]));
  const activeFocusKey = state.selectedKey || (state.hoveredNode ? state.hoveredNode.id : null);
  const spotlightSet = activeFocusKey ? getConnectedSet(activeFocusKey) : null;
  const edgeBadgesToDraw = [];

  // PASS 1: Draw Bezier Edges (Bottom Layer)
  for (const e of state.graphEdges) {
    const a = byId[e.source], b = byId[e.target];
    if (!a || !b || !isNodeInCanvas(a) || !isNodeInCanvas(b)) continue;
    const isDirect = activeFocusKey && (e.source === activeFocusKey || e.target === activeFocusKey);
    if (!isDirect && spotlightSet) continue;

    ctx.save();
    ctx.globalAlpha = isDirect ? 0.96 : 0.13;
    const strokeCol = isDirect
      ? (e.kind === "shard_module" ? "#68b5b0" : "#f3c878")
      : "#8c7d6b";
    ctx.strokeStyle = strokeCol;
    ctx.fillStyle = strokeCol;
    ctx.lineWidth = isDirect ? 2.4 : 1.0;

    const pt = drawCurvedEdgeAndArrow(ctx, a, b, b.node_kind === "code" ? 9 : 12, isDirect);
    if (isDirect) {
      edgeBadgesToDraw.push({ mx: pt.mx, my: pt.my, lbl: EDGE_LABELS[e.kind] || e.kind });
    }
    ctx.restore();
  }

  // PASS 1.5: Draw Edge Relationship Badges (Below Node Labels)
  for (const eb of edgeBadgesToDraw) {
    ctx.save();
    ctx.font = "bold 11px sans-serif";
    const w = Math.max(62, ctx.measureText(eb.lbl).width + 14);
    ctx.fillStyle = "rgba(27, 25, 22, 0.92)";
    ctx.beginPath();
    ctx.roundRect(eb.mx - w / 2, eb.my - 9, w, 18, 4);
    ctx.fill();
    ctx.strokeStyle = "rgba(217, 159, 78, 0.7)";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#f3c878";
    ctx.textAlign = "center";
    ctx.fillText(eb.lbl, eb.mx, eb.my + 4);
    ctx.restore();
  }

  // PASS 2: Draw Node Circles (Middle Layer)
  const visibleNodes = [];
  for (const n of state.graphNodes) {
    if (!isNodeInCanvas(n)) continue;
    const cat = getNodeVisualCat(n);
    const isSel = n.id === state.selectedKey || (state.hoveredNode && n.id === state.hoveredNode.id);
    const isMatchedByFilter = matchesFilter(n);
    const isNeighbor = spotlightSet ? spotlightSet.has(n.id) : false;

    let alpha = 0.94;
    if (spotlightSet) alpha = isNeighbor ? 1.0 : 0.15;
    else if (state.filter !== "all" || state.search) alpha = isMatchedByFilter ? 1.0 : 0.15;

    const r = n.node_kind === "code" ? 9 : cat === "blueprint" ? 14 : 11.5;
    visibleNodes.push({ n, cat, isSel, isNeighbor, isMatchedByFilter, alpha, r });

    ctx.save();
    ctx.globalAlpha = alpha;
    if (isSel) {
      ctx.shadowColor = "rgba(243, 200, 120, 0.85)";
      ctx.shadowBlur = 18;
    }
    ctx.beginPath();
    ctx.arc(n.x, n.y, isSel ? r + 3 : r, 0, Math.PI * 2);
    ctx.fillStyle = COLORS[cat] || "#b5a998";
    ctx.fill();
    ctx.shadowBlur = 0;

    if (isSel || isNeighbor || (state.filter !== "all" && isMatchedByFilter)) {
      ctx.lineWidth = isSel ? 3.0 : 1.8;
      ctx.strokeStyle = isSel ? "#f3c878" : "#e5d7c4";
      ctx.stroke();
    }
    ctx.restore();
  }

  // PASS 3: Draw Pill-Protected Node Text Labels (Topmost Layer — Never Occluded by Lines!)
  for (const item of visibleNodes) {
    const { n, isSel, isNeighbor, alpha, r } = item;
    ctx.save();
    ctx.globalAlpha = alpha;
    const titleText = n.title_zh || (n.label || n.id).replace(/^code:/, "");
    ctx.font = `${isSel ? "bold " : ""}12.5px sans-serif`;
    ctx.textAlign = "center";

    const textW = ctx.measureText(titleText).width;
    const pillW = textW + 14;
    const pillH = 20;
    const pillX = n.x - pillW / 2;
    const pillY = n.y + r + 5;

    ctx.fillStyle = isSel ? "rgba(42, 36, 28, 0.96)" : "rgba(24, 22, 19, 0.88)";
    ctx.beginPath();
    ctx.roundRect(pillX, pillY, pillW, pillH, 5);
    ctx.fill();

    if (isSel || isNeighbor) {
      ctx.strokeStyle = isSel ? "#f3c878" : "rgba(217, 159, 78, 0.45)";
      ctx.lineWidth = isSel ? 1.4 : 1.0;
      ctx.stroke();
    }

    ctx.fillStyle = isSel ? "#f3c878" : "#f2eadf";
    ctx.fillText(titleText, n.x, pillY + 14.5);
    ctx.restore();
  }

  ctx.restore();
  drawHoverTooltipOverlay(ctx, c);
}

function drawHoverTooltipOverlay(ctx, c) {
  const n = state.hoveredNode;
  if (!n) return;
  const cat = getNodeVisualCat(n);
  const title = `${n.title_zh || n.label || n.id} (${n.id})`;
  const pathLine = `📂 ${n.file_path || "內建節點"}  |  狀態: ${cat.toUpperCase()}`;
  const summary = n.summary_1line || "";

  ctx.save();
  ctx.font = "bold 12.5px sans-serif";
  const boxW = Math.min(440, c.width - 28);
  const boxH = 74;
  const boxX = c.width - boxW - 14;
  const boxY = 12;

  ctx.fillStyle = "rgba(27, 25, 22, 0.95)";
  ctx.beginPath();
  ctx.roundRect(boxX, boxY, boxW, boxH, 8);
  ctx.fill();
  ctx.strokeStyle = "#f3c878";
  ctx.lineWidth = 1.4;
  ctx.stroke();

  ctx.fillStyle = "#f3c878";
  ctx.textAlign = "left";
  ctx.fillText(title.slice(0, 46), boxX + 12, boxY + 22);

  ctx.font = "11px monospace";
  ctx.fillStyle = "#68b5b0";
  ctx.fillText(pathLine.slice(0, 58), boxX + 12, boxY + 41);

  ctx.font = "11.5px sans-serif";
  ctx.fillStyle = "#f2eadf";
  const shortSum = summary.length > 42 ? summary.slice(0, 42) + "…" : summary;
  ctx.fillText(shortSum, boxX + 12, boxY + 61);
  ctx.restore();
}

function screenToWorld(mx, my, c) {
  return {
    x: (mx - c.width / 2 - state.camera.x) / state.camera.zoom + WORLD_W / 2,
    y: (my - c.height / 2 - state.camera.y) / state.camera.zoom + dynamicWorldH / 2,
  };
}

function initCanvasInteractions() {
  const c = document.getElementById("graphCanvas");
  window.addEventListener("resize", () => resizeCanvas(false));
  c.addEventListener("wheel", (e) => {
    e.preventDefault();
    state.camera.zoom = Math.max(0.32, Math.min(2.6, state.camera.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
    drawGraph();
  });

  const handlePointerDown = (clientX, clientY) => {
    const rect = c.getBoundingClientRect();
    const w = screenToWorld(clientX - rect.left, clientY - rect.top, c);
    const hit = state.graphNodes.find((n) => isNodeInCanvas(n) && Math.hypot(n.x - w.x, n.y - w.y) < 26);
    if (hit) {
      state.draggingNode = hit;
      inspectNode(hit.id);
    } else {
      state.panning = true;
      state.lastMouse = { x: clientX, y: clientY };
    }
  };

  const handlePointerMove = (clientX, clientY) => {
    const rect = c.getBoundingClientRect();
    const w = screenToWorld(clientX - rect.left, clientY - rect.top, c);
    if (state.draggingNode) {
      state.draggingNode.x = w.x;
      state.draggingNode.y = w.y;
      drawGraph();
    } else if (state.panning) {
      state.camera.x += clientX - state.lastMouse.x;
      state.camera.y += clientY - state.lastMouse.y;
      state.lastMouse = { x: clientX, y: clientY };
      drawGraph();
    } else {
      const hit = state.graphNodes.find((n) => isNodeInCanvas(n) && Math.hypot(n.x - w.x, n.y - w.y) < 24) || null;
      if (state.hoveredNode !== hit) {
        state.hoveredNode = hit;
        c.style.cursor = hit ? "pointer" : "grab";
        drawGraph();
      }
    }
  };

  c.addEventListener("mousedown", (e) => handlePointerDown(e.clientX, e.clientY));
  window.addEventListener("mousemove", (e) => handlePointerMove(e.clientX, e.clientY));
  window.addEventListener("mouseup", () => { state.draggingNode = null; state.panning = false; });
  c.addEventListener("mouseleave", () => {
    if (state.hoveredNode) {
      state.hoveredNode = null;
      drawGraph();
    }
  });
}
