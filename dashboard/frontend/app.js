/* Shard 2 Frontend Controller (`910.SHARD-WEB-WARROOM.v1` — <= 550 effective lines) */
const state = {
  projectId: "NetArk",
  overview: null,
  filter: "all",
  topic: "",
  blueprint: "",
  showWiki: true,
  includeArchived: false,
  ledgerFilter: "all",
  selectedHandover: null,
  search: "",
  selectedKey: null,
  currentNode: null,
  hoveredNode: null,
  showCodeInGraph: false,
  graphNodes: [],
  graphEdges: [],
  swimlanes: {},
  camera: { x: 0, y: 0, zoom: 1 },
  draggingNode: null,
  panning: false,
  lastMouse: { x: 0, y: 0 },
  paneMode: "split",
};

const COLORS = {
  verified: "#56ad96",
  blueprint: "#4d8f8b",
  stub_ready: "#e8b45a",
  reviewing: "#5b9bd5",
  draft: "#d67c49",
  archived: "#786e60",
  deprecated: "#786e60",
  code: "#6fa3b8",
  healthy: "#6fa3b8",
  warning: "#e8b45a",
  god_script: "#d9534f",
};

const HANDOVER_TITLE_MAP = {
  "1": "🎯 1. 當前目標與分片座標 (Active Objective)",
  "2": "📂 2. 異動、空殼與目標檔案座標 (Target Files)",
  "3": "⚖️ 3. 已拍板決策與排除死路 (Key Decisions)",
  "4": "🚀 4. 下一輪開局第一步指令 (Next Step)",
};

function getNodeVisualCat(n) {
  if (n.node_kind === "code") return n.status === "god_script" ? "god_script" : "code";
  if (n.artifact_type === "blueprint" || (n.shard_modules && n.shard_modules.length > 0)) return "blueprint";
  return n.status || "draft";
}

function escapeHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function unescapeHtml(s) {
  return String(s || "").replace(/&(amp|lt|gt|quot|#39);/g, (_, e) => ({ amp: "&", lt: "<", gt: ">", quot: '"', "#39": "'" })[e]);
}

function resolveAlias(rawToken) {
  if (!state.overview || !state.overview.alias_map) return null;
  const clean = String(rawToken || "").trim().replace(/^`|`$/g, "");
  const amap = state.overview.alias_map;
  if (amap[clean]) return amap[clean];
  const base = clean.split("/").pop();
  return (base && amap[base]) ? amap[base] : null;
}

function renderJumpChip(token, displayOverride = null) {
  const entry = resolveAlias(token);
  if (!entry) return `<code class="inline-code">${escapeHtml(displayOverride || token)}</code>`;
  const safeLabel = String(entry.label || entry.key).replace(/\*\*/g, "");
  const titleAttr = `${safeLabel} (${entry.file_path || entry.key}) — 點擊跳轉`.replace(/\*\*/g, "");
  let inner = "";
  if (entry.kind === "code") {
    const fname = entry.file_path ? String(entry.file_path).split("/").pop() : String(token || "");
    const cleanTok = String(token || "").trim();
    inner = /^C\d+$/.test(cleanTok) ? `⚙️ ${escapeHtml(cleanTok)} <small>${escapeHtml(fname)}</small>` : `⚙️ ${escapeHtml(fname)}`;
  } else {
    const memFile = entry.file_path ? String(entry.file_path).split("/").pop() : "";
    const mCode = memFile.match(/^(\d{3}(?:_\d{2})?)/);
    const shortCode = mCode ? mCode[1] : String(entry.key || token || "").split(".")[0];
    const rawLbl = String(entry.label || "").trim()
      .replace(/^\d{3}(?:_\d{2})?\s*/, "")
      .replace(/^[\p{Extended_Pictographic}\u2600-\u27BF\uFE0F\u200D\s`]+/gu, "")
      .replace(/^(?:\d{3}(?:_\d{2})?_)?[A-Z][A-Z0-9_.-]{3,}[`…_]*(?=$|[\s—–:：\-|])/, "")
      .replace(/^[\s—–:：\-|]+/, "").trim();
    const zhShort = rawLbl.length > 14 ? rawLbl.slice(0, 14) : rawLbl;
    inner = `📘 ${escapeHtml(shortCode)}${zhShort && zhShort !== shortCode ? ` <small>${escapeHtml(zhShort)}</small>` : ""}`;
  }
  return `<span class="chip chip-jump" title="${escapeHtml(titleAttr)}" onclick="event.stopPropagation();inspectNode('${escapeHtml(entry.key)}', true)">${inner}</span>`;
}

function renderSmartRichText(rawText) {
  if (!rawText) return "";
  let s = escapeHtml(rawText);
  const seenKeys = new Set();
  const chipOrDedup = (tok) => {
    const e = resolveAlias(tok);
    if (e && seenKeys.has(e.key)) return "__DUP_CHIP__";
    if (e) seenKeys.add(e.key);
    return renderJumpChip(tok);
  };
  s = s.replace(/`?\[(FACT|INFERRED|HYPOTHESIS|UNVERIFIED)\]`?/g, (_, tag) => {
    const cls = tag === "FACT" ? "badge-epistemic-fact" : "badge-epistemic-inferred";
    return `<span class="badge ${cls}">${tag}</span>`;
  });
  s = s.replace(/\[\[([^\]]+)\]\]/g, (_, key) => chipOrDedup(unescapeHtml(key)));
  s = s.replace(/`([^`]+)`/g, (_, tok) => chipOrDedup(unescapeHtml(tok)));
  s = s.replace(/(<(?:span|code)[^>]*>[\s\S]*?<\/(?:span|code)>|<[^>]+>)|\b(MEM-\d{4}-\d{4})\b/g, (m, skip, id) => skip || chipOrDedup(id));
  if (s.includes("__DUP_CHIP__")) {
    s = s.replace(/\s*(?:\(\s*__DUP_CHIP__\s*\)|（\s*__DUP_CHIP__\s*）)/g, "").replace(/__DUP_CHIP__/g, "").replace(/ {2,}/g, " ").trim();
  }
  s = s.replace(/\*\*\s*(.+?)\s*\*\*/g, "<strong>$1</strong>");
  return s;
}

function renderHandoverSectionContent(secTitle, content) {
  if ((secTitle.startsWith("2.") || secTitle.includes("Files")) && content.includes("、")) {
    const colonIdx = content.indexOf("：");
    const prefix = colonIdx !== -1 ? content.slice(0, colonIdx + 1) : "";
    const rest = colonIdx !== -1 ? content.slice(colonIdx + 1) : content;
    const parts = rest.split(/、|\s+及\s+/).map((x) => x.trim()).filter(Boolean);
    return `<div style="margin-bottom:6px;color:var(--text-muted);font-size:12px">${renderSmartRichText(prefix)}</div>
      <div class="handover-file-list">${parts.map((p) => `<div class="handover-file-item">${renderSmartRichText(p)}</div>`).join("")}</div>`;
  }
  return `<div class="handover-prose">${content.split("\n").map((line) => `<div style="margin-bottom:4px">${renderSmartRichText(line.replace(/^-\s*/, ""))}</div>`).join("")}</div>`;
}

function openInspectorMobile() {
  document.getElementById("inspectorPanel").classList.add("open");
  document.getElementById("inspectorBackdrop").classList.add("open");
}

function closeInspectorMobile() {
  document.getElementById("inspectorPanel").classList.remove("open");
  document.getElementById("inspectorBackdrop").classList.remove("open");
}

const PANE_MODES = ["left-collapsed", "split", "right-collapsed"];
const PANE_LABELS = { "left-collapsed": "全寬閱讀", split: "雙欄", "right-collapsed": "全寬畫布" };

function setWorkspacePaneMode(mode) {
  const next = PANE_MODES.includes(mode) ? mode : "split";
  state.paneMode = next;
  const ws = document.getElementById("workspaceLayout");
  if (ws) {
    ws.classList.toggle("pane-left-collapsed", next === "left-collapsed");
    ws.classList.toggle("pane-right-collapsed", next === "right-collapsed");
  }
  const lb = document.getElementById("paneCollapseLeftBtn");
  const rb = document.getElementById("paneCollapseRightBtn");
  const mid = document.getElementById("paneResetBtn");
  if (lb) lb.disabled = next === "left-collapsed";
  if (rb) rb.disabled = next === "right-collapsed";
  if (mid) mid.textContent = PANE_LABELS[next];
  try { localStorage.setItem("netark_dashboard_pane_mode", next); } catch (_) {}
  if (next !== "left-collapsed" && document.getElementById("tab-graph")?.classList.contains("active")) requestAnimationFrame(() => resizeCanvas(true));
}

function stepWorkspacePane(delta) {
  const idx = Math.max(0, PANE_MODES.indexOf(state.paneMode));
  setWorkspacePaneMode(PANE_MODES[Math.max(0, Math.min(2, idx + delta))]);
}

async function init() {
  const res = await fetch("/api/projects");
  const data = await res.json();
  const sel = document.getElementById("projectSelect");
  sel.innerHTML = data.projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${p.public_node_count + p.private_node_count} 節點)</option>`).join("");
  sel.addEventListener("change", (e) => loadProject(e.target.value));

  document.getElementById("topicSelect").addEventListener("change", (e) => {
    state.topic = e.target.value;
    state.selectedKey = null;
    setupGraphSimulation();
    renderAllViews();
  });

  document.getElementById("blueprintSelect").addEventListener("change", (e) => {
    state.blueprint = e.target.value;
    state.selectedKey = null;
    setupGraphSimulation();
    renderAllViews();
  });

  document.getElementById("showWikiToggle").addEventListener("change", (e) => {
    state.showWiki = e.target.checked;
    setupGraphSimulation();
    renderAllViews();
  });

  document.getElementById("showArchivedToggle").addEventListener("change", async (e) => {
    state.includeArchived = e.target.checked;
    await loadProject(state.projectId);
  });

  document.getElementById("searchInput").addEventListener("input", (e) => {
    state.search = e.target.value.trim().toLowerCase();
    setupGraphSimulation();
    renderAllViews();
  });

  document.getElementById("rescanBtn").addEventListener("click", async () => {
    const btn = document.getElementById("rescanBtn");
    btn.textContent = "⏳ 掃描中...";
    const r = await fetch(`/api/project/${state.projectId}/rescan`, { method: "POST" });
    state.overview = await r.json();
    btn.textContent = "🔄 重掃架構";
    populateSelectors();
    setupGraphSimulation();
    renderAllViews();
  });

  document.getElementById("showCodeNodesToggle").addEventListener("change", (e) => {
    state.showCodeInGraph = e.target.checked;
    setupGraphSimulation();
    drawGraph();
  });

  document.getElementById("clearSelBtn").addEventListener("click", () => { state.selectedKey = null; drawGraph(); });

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "graph") resizeCanvas(true);
    });
  });

  document.querySelectorAll("#filterPills .pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      document.querySelectorAll("#filterPills .pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      state.filter = pill.dataset.filter;
      state.selectedKey = null;
      if (state.filter === "code") {
        state.showCodeInGraph = true;
        document.getElementById("showCodeNodesToggle").checked = true;
      } else if (state.filter === "blueprint") {
        const bp = state.overview.nodes.find((n) => getNodeVisualCat(n) === "blueprint" && matchesFilter(n));
        if (bp) state.selectedKey = bp.node_key || bp.node_id;
      }
      setupGraphSimulation();
      renderAllViews();
    });
  });

  document.getElementById("resetViewBtn").addEventListener("click", () => { fitCameraToCanvas(); drawGraph(); });
  document.getElementById("paneCollapseLeftBtn")?.addEventListener("click", () => stepWorkspacePane(-1));
  document.getElementById("paneCollapseRightBtn")?.addEventListener("click", () => stepWorkspacePane(1));
  document.getElementById("paneResetBtn")?.addEventListener("click", () => setWorkspacePaneMode("split"));
  try { setWorkspacePaneMode(localStorage.getItem("netark_dashboard_pane_mode") || "split"); } catch (_) {}
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDocFocusModal(); });
  initCanvasInteractions();
  await loadProject(data.projects[0]?.id || "NetArk");
}

function populateSelectors() {
  const topicSel = document.getElementById("topicSelect");
  const bpSel = document.getElementById("blueprintSelect");
  const topics = state.overview?.available_topics || [];
  const bps = state.overview?.available_blueprints || [];
  if (topicSel) {
    if (state.topic && !topics.includes(state.topic)) state.topic = "";
    topicSel.innerHTML = `<option value="">🏷️ 全部主題 (${topics.length})</option>` +
      topics.map((t) => `<option value="${escapeHtml(t)}" ${t === state.topic ? "selected" : ""}>🏷️ ${escapeHtml(t)}</option>`).join("");
  }
  if (bpSel) {
    if (state.blueprint && !bps.some((b) => b.node_key === state.blueprint)) state.blueprint = "";
    bpSel.innerHTML = `<option value="">🏛️ 全部藍圖 (${bps.length})</option>` +
      bps.map((b) => `<option value="${escapeHtml(b.node_key)}" ${b.node_key === state.blueprint ? "selected" : ""}>🏛️ ${escapeHtml(b.title_zh || b.node_key)} (${b.shard_count} shards)</option>`).join("");
  }
}

async function loadProject(pid) {
  state.projectId = pid;
  state.selectedHandover = null;
  state.currentNode = null;
  closeDocFocusModal();
  closeInspectorMobile();
  const res = await fetch(`/api/project/${pid}/overview?include_archived=${state.includeArchived ? 1 : 0}`);
  state.overview = await res.json();
  populateSelectors();
  setupGraphSimulation();
  renderAllViews();
  const defaultNode = state.overview.nodes.find((n) => n.node_key === "910.PM-CONTROL-NOTEBOOK.v1" || n.node_key === "500.HANDOVER-SHARDING-STUB.v1" || n.node_key === "900.HANDOVER.v1");
  if (defaultNode) inspectNode(defaultNode.node_key || defaultNode.node_id, false);
}

function setLedgerFilter(mode) { state.ledgerFilter = mode; renderPMView(); }

function setHandoverTrack(filename) { state.selectedHandover = filename; renderPMView(); }

function getNodeTopic(n) {
  if (n.topic && String(n.topic).trim()) return String(n.topic).trim();
  const tags = Array.isArray(n.facet_tags) ? n.facet_tags : [];
  for (const t of tags) {
    const parts = String(t).split(":");
    if (parts.length >= 2 && parts[1].trim()) return parts[1].trim();
  }
  return "";
}

function getSubgraphSets() {
  const nodes = state.overview?.nodes || [];
  let bpMemKeys = null, bpCodePaths = null, topicCodePaths = null;
  if (state.blueprint) {
    const bp = nodes.find((n) => n.node_kind === "memory" && (n.node_key === state.blueprint || n.node_id === state.blueprint));
    bpMemKeys = new Set();
    bpCodePaths = new Set();
    if (bp) {
      const bpKey = bp.node_key || bp.node_id;
      const coreKeys = new Set([bpKey, bp.node_id, ...(bp.shard_modules || [])].filter(Boolean));
      for (const m of nodes) {
        if (m.node_kind === "memory" && (m.parent_blueprint === bpKey || m.parent_blueprint === bp.node_id)) {
          if (m.node_key) coreKeys.add(m.node_key);
          if (m.node_id) coreKeys.add(m.node_id);
        }
      }
      bpMemKeys = new Set([...coreKeys, ...(bp.depends_on || [])]);
      for (const m of nodes) {
        if (m.node_kind === "memory" && (coreKeys.has(m.node_key) || coreKeys.has(m.node_id))) {
          for (const p of [...(m.affected_paths || []), ...(m.stub_paths || [])]) bpCodePaths.add(p);
        }
      }
    }
  }
  if (state.topic) {
    const tLow = state.topic.toLowerCase();
    topicCodePaths = new Set();
    for (const m of nodes) {
      if (m.node_kind === "memory" && getNodeTopic(m).toLowerCase() === tLow) {
        for (const p of [...(m.affected_paths || []), ...(m.stub_paths || [])]) topicCodePaths.add(p);
      }
    }
  }
  return { bpMemKeys, bpCodePaths, topicCodePaths };
}

function matchesFilter(n) {
  if (!state.includeArchived && (n.status === "archived" || n.status === "deprecated")) return false;
  if (!state.showWiki && n.node_kind === "memory" && (n.domain_code === "310" || n.artifact_type === "note" || n.artifact_type === "wiki")) return false;
  if (state.topic || state.blueprint) {
    const { bpMemKeys, bpCodePaths, topicCodePaths } = getSubgraphSets();
    if (topicCodePaths) {
      if (n.node_kind === "code" && !topicCodePaths.has(n.file_path)) return false;
      if (n.node_kind !== "code" && getNodeTopic(n).toLowerCase() !== state.topic.toLowerCase()) return false;
    }
    if (bpMemKeys) {
      if (n.node_kind === "code" && !bpCodePaths.has(n.file_path)) return false;
      if (n.node_kind !== "code" && !bpMemKeys.has(n.node_key) && !bpMemKeys.has(n.node_id)) return false;
    }
  }
  const cat = getNodeVisualCat(n);
  if (state.filter !== "all") {
    if (state.filter === "code" && n.node_kind !== "code") return false;
    if (state.filter !== "code" && cat !== state.filter) return false;
  }
  if (state.search) {
    const hay = `${n.title_zh || ""} ${n.node_key || ""} ${n.node_id || ""} ${n.file_path || ""} ${n.summary_1line || ""} ${getNodeTopic(n)} ${(n.keywords || []).join(" ")}`.toLowerCase();
    if (!hay.includes(state.search)) return false;
  }
  return true;
}

function renderNodeCardHtml(n) {
  const cat = getNodeVisualCat(n);
  const key = n.node_key || n.node_id;
  const isSel = state.selectedKey === key ? "selected" : "";
  const upCount = (n.depends_on || []).length + (n.parent_blueprint ? 1 : 0);
  const downCount = (n.shard_modules || []).length + (n.backlinks || []).length;
  const codeCount = (n.affected_paths || []).length + (n.stub_paths || []).length;
  return `<div class="node-card ${isSel}" onclick="inspectNode('${escapeHtml(key)}', true)"><div class="node-card-header"><div class="node-title-zh">${escapeHtml(n.title_zh || key)}</div><span class="badge badge-${cat}">${escapeHtml(cat.toUpperCase())}</span></div><div class="node-key-sub">${escapeHtml(key)} · <code>${escapeHtml(n.file_path)}</code></div><div class="node-summary">${escapeHtml(n.summary_1line)}</div><div class="node-meta-footer"><span>⬆️ 依賴: ${upCount}</span><span>⬇️ 下游/被引用: ${downCount}</span><span>⚙️ 控制源碼: ${codeCount} 支</span></div></div>`;
}

function renderBlueprintShardProgress(children) {
  if (!children.length) return "";
  const total = children.length;
  const vCount = children.filter((c) => c.status === "verified").length;
  const sCount = children.filter((c) => c.status === "stub_ready").length;
  const dCount = total - vCount - sCount;
  const pct = Math.round(((vCount + sCount * 0.5) / total) * 100);
  return `<div class="bp-progress-bar"><div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:4px"><span>🧩 <strong>子切片落地進度 (${total} 支)</strong>：🟢 已驗證 ${vCount} · 🟡 Stub就緒 ${sCount} · 🟠 草案 ${dCount}</span><strong style="color:var(--gold-bright)">${pct}%</strong></div><div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:linear-gradient(90deg, var(--c-verified), var(--gold-warm))"></div></div></div>`;
}

function renderAllViews() {
  if (!state.overview) return;
  const s = state.overview.stats;
  document.getElementById("statsBar").innerHTML =
    `<div class="stat-card"><span class="stat-label">📚 記憶節點</span><span class="stat-val">${s.total_memory_nodes}</span></div>` +
    `<div class="stat-card"><span class="stat-label">🟢 已驗證</span><span class="stat-val" style="color:var(--c-verified)">${s.verified_count}</span></div>` +
    `<div class="stat-card"><span class="stat-label">🏛️ 藍圖/Stub</span><span class="stat-val" style="color:var(--c-blueprint)">${s.blueprint_count}/${s.stub_ready_count}</span></div>` +
    `<div class="stat-card"><span class="stat-label">🔵 待施工 / 🟠 草案</span><span class="stat-val" style="color:var(--c-reviewing)">${s.reviewing_count ?? 0} <small style="color:var(--c-draft)">/ ${s.draft_count}</small></span></div>` +
    `<div class="stat-card"><span class="stat-label">📋 工單進度</span><span class="stat-val">${s.ledger_done}/${s.ledger_total}</span></div>` +
    `<div class="stat-card"><span class="stat-label">🛡️ 上帝腳本</span><span class="stat-val" style="color:${s.god_script_count > 0 ? "var(--c-god)" : "var(--c-verified)"}">${s.god_script_count} 支</span></div>`;
  renderMatrixView();
  renderPMView();
  renderCodeView();
  drawGraph();
}

function renderMatrixView() {
  const memNodes = state.overview.nodes.filter((n) => n.node_kind === "memory" && matchesFilter(n));
  const byKey = Object.fromEntries(state.overview.nodes.map((n) => [n.node_key || n.node_id, n]));
  const blueprints = memNodes.filter((n) => n.artifact_type === "blueprint" || (n.shard_modules && n.shard_modules.length > 0));
  const shardKeySet = new Set(blueprints.flatMap((bp) => bp.shard_modules || []));
  const layer1 = memNodes.filter((n) => n.layer_rank === 1 && !shardKeySet.has(n.node_key));
  const layer2 = memNodes.filter((n) => n.layer_rank === 2 && !shardKeySet.has(n.node_key) && !blueprints.includes(n));
  const layer3 = memNodes.filter((n) => n.layer_rank === 3 && !shardKeySet.has(n.node_key));

  const l3Reviewing = layer3.filter((n) => n.domain_code === "310" && n.status === "reviewing");
  const l3Draft = layer3.filter((n) => n.domain_code === "310" && n.status === "draft");
  const l3Verified = layer3.filter((n) => n.domain_code === "310" && n.status !== "reviewing" && n.status !== "draft");
  const l3AuditHandover = layer3.filter((n) => n.domain_code !== "310");
  const renderSubCard = (title, desc, list) => `<div class="sub-compartment"><h4>${title} (${list.length})</h4><p class="sub-compartment-desc">${desc}</p><div class="node-grid">${list.length ? list.map(renderNodeCardHtml).join("") : `<span style="font-size:12px;color:var(--text-muted)">（無符合節點）</span>`}</div></div>`;
  const bpHtml = blueprints.length ? `<div class="section-card"><h3>🏛️ 藍圖分片與子模組樹 (Blueprint ➔ Shards ➔ 綁定程式碼)</h3><p class="layer-desc">呈現總藍圖母體如何拆解為獨立子切片，並追蹤各子切片之驗證進度與控制源碼。</p>${blueprints.map((bp) => {
    const children = (bp.shard_modules || []).map((k) => byKey[k]).filter((c) => c && matchesFilter(c));
    return `<div class="blueprint-tree-box">${renderNodeCardHtml(bp)}${renderBlueprintShardProgress(children)}${children.length ? `<div class="shard-children">${children.map(renderNodeCardHtml).join("")}</div>` : ""}</div>`;
  }).join("")}</div>` : "";
  document.getElementById("matrixContent").innerHTML = `${bpHtml}<div class="section-card"><h3>🏛️ 第 1 層：核心憲法與安全護欄 (${layer1.length})</h3><p class="layer-desc">全專案最高指導原則（000 憲法、100 邊界與安全規則），所有下層規格皆依賴此層。</p><div class="node-grid">${layer1.map(renderNodeCardHtml).join("")}</div></div><div class="section-card"><h3>⚙️ 第 2 層：核心架構與領域規格 (${layer2.length})</h3><p class="layer-desc">定義路由器、快取、交接、雙軌圖書館與領域法則之正式規格書。</p><div class="node-grid">${layer2.map(renderNodeCardHtml).join("")}</div></div><div class="section-card"><h3>📚 第 3 層：310 開架知識庫、稽核與交接四分艙 (${layer3.length})</h3><p class="layer-desc">依生命週期自動分艙：待立項筆記、討論中草案、常駐百科指南，以及 700 稽核與 900 交接快照。</p><div class="layer3-subcards">${renderSubCard("🎯 待立項施工筆記 (310 reviewing)", "已完成設計拍板、排隊轉正為正式藍圖或規格之筆記。", l3Reviewing)}${renderSubCard("💭 討論中草案 (310 draft)", "尚在發散討論或未定案之技術備忘與待決清單。", l3Draft)}${renderSubCard("📚 常駐百科與指南 (310 verified)", "常駐生效之架構目錄、操作指南與已驗證百科。", l3Verified)}${renderSubCard("🔍 稽核與交接 (700/900)", "700 工程審計紀錄與 900 跨對話交接快照。", l3AuditHandover)}</div></div>`;
}

function renderHandoverCard(handover, handovers) {
  const hasList = Array.isArray(handovers) && handovers.length > 0;
  const active = hasList ? (handovers.find((h) => h.filename === state.selectedHandover) || handovers[0]) : null;
  const sections = active ? (active.sections || {}) : (handover?.sections || {});
  const secEntries = Object.entries(sections);
  const trackSelect = hasList ? `<select id="handoverTrackSelect" onchange="setHandoverTrack(this.value)" style="background:var(--bg-card);color:var(--text-main);border:1px solid var(--border);border-radius:6px;padding:3px 8px;font-size:12px">${handovers.map((h) => `<option value="${escapeHtml(h.filename)}" ${h.filename === active.filename ? "selected" : ""}>${escapeHtml(h.track_id || h.filename)} (${escapeHtml(h.status || "active")}) — ${escapeHtml(h.filename)}</option>`).join("")}</select>` : "";
  const metaLine = active ? `<div style="font-size:12px;color:var(--text-muted);margin-bottom:10px;display:flex;flex-wrap:wrap;gap:8px;align-items:center"><span class="badge badge-${active.status === "archived" || active.status === "completed" ? "verified" : "stub_ready"}">${escapeHtml(active.status || "active")}</span><span>軌道: <code>${escapeHtml(active.track_id || "")}</code></span>${active.updated_at ? `<span>更新: ${escapeHtml(active.updated_at)}</span>` : ""}${active.summary ? `<span>· ${escapeHtml(active.summary)}</span>` : ""}</div>` : "";
  const bodyHtml = secEntries.length
    ? `<div class="handover-grid">${secEntries.map(([title, content]) => `<div class="handover-box"><h4>${escapeHtml(HANDOVER_TITLE_MAP[title.trim().charAt(0)] || title)}</h4>${renderHandoverSectionContent(title, content)}</div>`).join("")}</div>`
    : `<div class="handover-prose">${active?.content ? renderFormattedMarkdownBody(active.content) : `<span style="color:var(--text-muted)">（此交接檔無可顯示內容）</span>`}</div>`;
  const activeName = escapeHtml(active ? active.filename : "HANDOVER.md");
  return `<div class="section-card">
    <h3><span>🔄 當前對話交接快照 (<code>${activeName}</code> — 點擊任意膠囊直接於右側預覽檔案)</span><div style="display:flex;align-items:center;gap:8px">${trackSelect}<button class="chip chip-jump" onclick="inspectNode('900.HANDOVER.v1', true)">📖 檢視完整 HANDOVER.md</button></div></h3>
    ${metaLine}${bodyHtml}
  </div>`;
}

function renderPMView() {
  const { handover, handovers, ledger, stats } = state.overview;
  const pct = stats.ledger_total ? Math.round((stats.ledger_done / stats.ledger_total) * 100) : 0;
  const activeCount = ledger.filter((x) => !x.is_done).length;
  const doneCount = ledger.filter((x) => x.is_done).length;
  const sortedLedger = [...ledger].sort((a, b) => Number(a.is_done) - Number(b.is_done));
  const filteredLedger = sortedLedger.filter((item) => state.ledgerFilter === "active" ? !item.is_done : state.ledgerFilter === "done" ? item.is_done : true);

  const ledgerRows = filteredLedger.map((item) => `<tr class="${item.is_done ? "" : "wo-active-row"}"><td><strong>${escapeHtml(item.wo_id)}</strong></td><td><div class="wo-title-main">${escapeHtml(item.title_main || item.title)}</div>${item.title_sub ? `<div class="wo-title-sub">${renderSmartRichText(item.title_sub)}</div>` : ""}</td><td><span class="badge ${item.is_done ? "badge-verified" : "badge-draft"}" style="margin-bottom:4px">${escapeHtml(item.status.split("(")[0].trim())}</span>${item.status.includes("(") ? `<div style="margin-top:3px">${renderSmartRichText(item.status.slice(item.status.indexOf("(")))}</div>` : ""}</td><td><code class="inline-code">${escapeHtml(item.role)}</code></td><td><div class="oracle-cell">${renderSmartRichText(item.oracle)}</div></td></tr>`).join("");
  document.getElementById("pmContent").innerHTML = `${renderHandoverCard(handover, handovers)}<div class="section-card"><h3><span>📋 專案唯一活躍工單台帳 (<code>LEDGER.md</code> — 完成率 ${pct}%)</span><div class="filter-pills"><button class="pill ${state.ledgerFilter === "all" ? "active" : ""}" onclick="setLedgerFilter('all')">📋 全部 (${ledger.length})</button><button class="pill ${state.ledgerFilter === "active" ? "active" : ""}" onclick="setLedgerFilter('active')">🔥 進行中 / 草案 (${activeCount})</button><button class="pill ${state.ledgerFilter === "done" ? "active" : ""}" onclick="setLedgerFilter('done')">✅ 已完成 (${doneCount})</button><button class="chip chip-jump" onclick="inspectNode('300.LEDGER.v1', true)">📖 原始台帳</button></div></h3><div class="progress-track" style="margin-bottom:12px"><div class="progress-fill" style="width:${pct}%;background:var(--c-verified)"></div></div><div class="table-wrap"><table class="data-table"><thead><tr><th style="width:115px">工單 ID</th><th>任務主旨與技術細項 (點擊膠囊開啟藍圖/規格)</th><th style="width:170px">狀態 / 藍圖</th><th style="width:120px">負責角色</th><th style="width:240px">驗收基準 (點擊開啟腳本/規格)</th></tr></thead><tbody>${ledgerRows}</tbody></table></div></div>`;
}

function renderCodeView() {
  const codes = state.overview.code_health.filter((c) => matchesFilter(c));
  const codeRows = codes.map((c) => {
    const pct = Math.min(100, Math.round((c.line_count / 600) * 100));
    const color = COLORS[c.status] || COLORS.code;
    return `<tr style="cursor:pointer" onclick="inspectNode('${escapeHtml(c.node_key)}', true)"><td><strong><code>${escapeHtml(c.file_path)}</code></strong></td><td style="width:180px"><div>${c.line_count} 行</div><div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:${color}"></div></div></td><td><span class="badge badge-${c.status}">${escapeHtml(c.health_label)}</span></td><td>${c.symbol_count} 個</td><td>${(c.governing_specs || []).map((g) => `<span class="chip chip-jump" onclick="event.stopPropagation();inspectNode('${escapeHtml(g)}', true)">📘 ${escapeHtml(g)}</span>`).join(" ")}</td></tr>`;
  }).join("");
  document.getElementById("codeContent").innerHTML = `<div class="section-card"><h3>🛡️ 程式碼模組行數水位與防上帝腳本監控 (軟性預警 400 行 / 剛性凍結 600 行)</h3><div class="table-wrap"><table class="data-table"><thead><tr><th>模組路徑</th><th>行數水位 (上限 600)</th><th>健康狀態</th><th>AST 符號</th><th>統御規格</th></tr></thead><tbody>${codeRows}</tbody></table></div></div>`;
}

function renderFormattedMarkdownBody(md) {
  if (!md) return "";
  let inCode = false, inList = false, inTable = false;
  const out = [];
  const closeBlocks = () => {
    if (inList) { out.push("</ul>"); inList = false; }
    if (inTable) { out.push("</tbody></table></div>"); inTable = false; }
  };
  for (const line of String(md).split("\n")) {
    const t = line.trim();
    if (t.startsWith("```")) { closeBlocks(); inCode = !inCode; out.push(inCode ? `<pre class="md-code-block">` : `</pre>`); continue; }
    if (inCode) { out.push(escapeHtml(line) + "\n"); continue; }
    if (t.startsWith("|") && t.endsWith("|") && t.length > 2) {
      if (inList) { out.push("</ul>"); inList = false; }
      if (/^\|[\s:|-]+\|$/.test(t)) continue;
      const cells = t.slice(1, -1).split("|").map((c) => renderSmartRichText(c.trim()).replace(/&lt;br\s*\/?&gt;/gi, "<br>"));
      if (!inTable) { out.push(`<div class="md-table-wrap"><table class="data-table md-table"><thead><tr>${cells.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>`); inTable = true; }
      else out.push(`<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`);
      continue;
    }
    if (t.startsWith("- ") || t.startsWith("* ")) {
      if (inTable) { out.push("</tbody></table></div>"); inTable = false; }
      if (!inList) { out.push(`<ul class="md-list">`); inList = true; }
      out.push(`<li>${renderSmartRichText(t.slice(2))}</li>`);
      continue;
    }
    closeBlocks();
    if (line.startsWith("### ")) out.push(`<h5 class="md-h3">${renderSmartRichText(line.slice(4))}</h5>`);
    else if (line.startsWith("## ")) out.push(`<h4 class="md-h2">${renderSmartRichText(line.slice(3))}</h4>`);
    else if (line.startsWith("# ")) out.push(`<h3 class="md-h1">${renderSmartRichText(line.slice(2))}</h3>`);
    else out.push(`<div class="md-line">${renderSmartRichText(line)}</div>`);
  }
  closeBlocks();
  if (inCode) out.push(`</pre>`);
  return out.join("");
}

function syncDocFocusModal(d) {
  if (!d) return;
  const cat = getNodeVisualCat(d);
  const badge = document.getElementById("focusModalBadge");
  const title = document.getElementById("focusModalTitle");
  const meta = document.getElementById("focusModalMeta");
  const body = document.getElementById("focusModalBody");
  if (badge) { badge.className = `badge badge-${cat}`; badge.textContent = cat.toUpperCase(); }
  if (title) title.textContent = d.title_zh || d.node_key || d.label || "";
  if (meta) meta.textContent = `${d.node_id ? `${d.node_id} · ` : ""}${d.node_key || ""}${d.file_path ? ` · 📂 ${d.file_path}` : ""}`;
  if (body) { body.innerHTML = renderFormattedMarkdownBody(d.body_markdown || ""); body.scrollTop = 0; }
}

function openDocFocusModal() {
  if (!state.currentNode) return;
  syncDocFocusModal(state.currentNode);
  document.getElementById("docFocusModal")?.classList.add("open");
}

function closeDocFocusModal() {
  document.getElementById("docFocusModal")?.classList.remove("open");
}

function renderCodeBindingsHtml(bindings) {
  return bindings.map((cb) => {
    const syms = cb.symbols || [];
    const fname = cb.file_path ? String(cb.file_path).split("/").pop() : "";
    const symChips = syms.slice(0, 18).map((sym) => `<span class="chip" style="font-size:11px">ƒ ${escapeHtml(sym.name)} (L${sym.line_start}-L${sym.line_end})</span>`).join("");
    return `<details class="code-binding-group"><summary class="code-binding-summary" title="${escapeHtml(cb.file_path || "")}"><span>📄 <strong>${escapeHtml(fname)}</strong> <small>(${syms.length} 函式)</small></span><span>${escapeHtml(cb.health_label || "")} <button type="button" class="btn-jump-code" onclick="event.preventDefault();event.stopPropagation();inspectNode('code:${escapeHtml(cb.file_path || "")}', true)">檔案節點 ↗</button></span></summary><div class="chip-list" style="margin-top:8px">${symChips || `<span style="font-size:11px;color:var(--text-muted)">無 AST 符號</span>`}</div></details>`;
  }).join("") || `<span style="font-size:12px;color:var(--text-muted)">無直接綁定源碼</span>`;
}

function toggleCodeBindingsExpand(btn, totalCount, maxVisible) {
  const section = btn.closest('.inspector-section');
  if (!state.currentNode) return;
  const codeBindings = state.currentNode.code_bindings || [];
  const isExpanded = btn.dataset.expanded === 'true';
  const listEl = section.querySelector('.code-bindings-list');
  if (isExpanded) {
    const visibleBindings = codeBindings.slice(0, maxVisible);
    const hiddenCount = totalCount - maxVisible;
    listEl.innerHTML = renderCodeBindingsHtml(visibleBindings);
    btn.textContent = `+${hiddenCount} 支檔案`;
    btn.dataset.expanded = 'false';
  } else {
    listEl.innerHTML = renderCodeBindingsHtml(codeBindings);
    btn.textContent = `收合 (${totalCount} 支檔案)`;
    btn.dataset.expanded = 'true';
  }
}

async function inspectNode(nodeKey, openSheetOnMobile = true) {
  const entry = resolveAlias(nodeKey);
  const resolvedKey = entry ? entry.key : nodeKey;
  state.selectedKey = resolvedKey;
  renderMatrixView();
  drawGraph();
  if (openSheetOnMobile && window.innerWidth > 860 && state.paneMode === "right-collapsed") setWorkspacePaneMode("split");
  if (openSheetOnMobile) openInspectorMobile();

  const panel = document.getElementById("inspectorPanel");
  const res = await fetch(`/api/project/${state.projectId}/node/${encodeURIComponent(resolvedKey)}`);
  if (!res.ok) return;
  const d = await res.json();
  state.currentNode = d;
  const byKey = Object.fromEntries(state.overview.nodes.map((n) => [n.node_key || n.node_id, n]));
  const labelOf = (k) => (byKey[k] && byKey[k].title_zh ? `${byKey[k].title_zh} (${k})` : k);
  const cat = getNodeVisualCat(d);
  const upstreams = [...new Set([...(d.depends_on || []), ...(d.parent_blueprint ? [d.parent_blueprint] : []), ...(d.governing_specs || [])])];
  const downstreams = [...new Set([...(d.shard_modules || []), ...(d.backlinks || []), ...(d.outbound_links || [])])];
  const codeBindings = d.code_bindings || [];
  const MAX_VISIBLE_BINDINGS = 4;
  const showAllBindings = codeBindings.length <= MAX_VISIBLE_BINDINGS;
  const visibleBindings = showAllBindings ? codeBindings : codeBindings.slice(0, MAX_VISIBLE_BINDINGS);
  const hiddenCount = codeBindings.length - MAX_VISIBLE_BINDINGS;
  const bindingsHtml = `<div class="code-bindings-list">${renderCodeBindingsHtml(visibleBindings)}</div>`;
  const expandBtnHtml = !showAllBindings ? `<button type="button" class="btn-focus-expand" style="margin-top:8px" data-expanded="false" onclick="event.stopPropagation();toggleCodeBindingsExpand(this, ${codeBindings.length}, ${MAX_VISIBLE_BINDINGS})">+${hiddenCount} 支檔案</button>` : "";

  panel.innerHTML = `
    <div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px">
        <div><span class="badge badge-${cat}">${escapeHtml(cat.toUpperCase())}</span><span style="font-size:12px;color:var(--text-muted);margin-left:6px">${escapeHtml(d.node_id || "")}</span></div>
        <button class="mobile-close-btn" onclick="closeInspectorMobile()">✕ 關閉</button>
      </div>
      <h2 style="font-size:16px;margin-bottom:4px;color:var(--gold-bright)">${escapeHtml(d.title_zh || d.node_key || d.label)}</h2>
      <p style="font-size:11.5px;color:var(--text-muted);margin-bottom:8px;font-family:monospace">${escapeHtml(d.node_key || "")} · 📂 ${escapeHtml(d.file_path || "")}</p>
      <p style="font-size:13px;line-height:1.5">${renderSmartRichText(d.summary_1line || "")}</p>
    </div>
    <div class="inspector-section"><h4>⬆️ 依賴哪個上游 / 隸屬哪張母體藍圖 (${upstreams.length})</h4><div class="chip-list">${upstreams.length ? upstreams.map((k) => `<span class="chip chip-jump" onclick="inspectNode('${escapeHtml(k)}', true)">🔗 ${escapeHtml(labelOf(k))}</span>`).join("") : `<span style="font-size:12px;color:var(--text-muted)">無上游依賴（頂層節點）</span>`}</div></div>
    <div class="inspector-section"><h4>⬇️ 拆出哪些子切片 / 被哪些節點引用 (${downstreams.length})</h4><div class="chip-list">${downstreams.length ? downstreams.map((k) => `<span class="chip chip-jump" onclick="inspectNode('${escapeHtml(k)}', true)">🧩 ${escapeHtml(labelOf(k))}</span>`).join("") : `<span style="font-size:12px;color:var(--text-muted)">無下游引用</span>`}</div></div>
    <div class="inspector-section"><h4>⚙️ 控制哪些程式碼與函式行號 (${codeBindings.length})</h4>${bindingsHtml}${expandBtnHtml}</div>
    <div class="inspector-section"><div class="spec-header-row"><h4>📖 完整規格筆記內容</h4><button type="button" class="btn-focus-expand" onclick="openDocFocusModal()">⛶ 展開</button></div><div class="md-body spec-content">${renderFormattedMarkdownBody(d.body_markdown || "")}</div></div>
  `;
  const focusModal = document.getElementById("docFocusModal");
  if (focusModal && focusModal.classList.contains("open")) syncDocFocusModal(d);
}

window.addEventListener("DOMContentLoaded", init);
