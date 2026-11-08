/* Shard 2 Frontend Controller (`910.SHARD-WEB-WARROOM.v1` — < 385 lines) */
const state = {
  projectId: "NetArk",
  overview: null,
  filter: "all",
  ledgerFilter: "all",
  search: "",
  selectedKey: null,
  hoveredNode: null,
  showCodeInGraph: false,
  graphNodes: [],
  graphEdges: [],
  swimlanes: {},
  camera: { x: 0, y: 0, zoom: 1 },
  draggingNode: null,
  panning: false,
  lastMouse: { x: 0, y: 0 },
};

const COLORS = {
  verified: "#56ad96",
  blueprint: "#4d8f8b",
  stub_ready: "#e8b45a",
  draft: "#d67c49",
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
  if (!entry) return `<code>${escapeHtml(displayOverride || token)}</code>`;
  const icon = entry.kind === "code" ? "⚙️" : "📘";
  const shortName = displayOverride || (entry.file_path ? entry.file_path.split("/").pop() : token);
  const titleAttr = `${entry.label} (${entry.file_path || entry.key}) — 點擊於右側開啟`;
  return `<span class="chip chip-jump" title="${escapeHtml(titleAttr)}" onclick="event.stopPropagation();inspectNode('${escapeHtml(entry.key)}', true)">${icon} ${escapeHtml(shortName)} <small>${escapeHtml(entry.label)}</small></span>`;
}

function renderSmartRichText(rawText) {
  if (!rawText) return "";
  let s = escapeHtml(rawText);
  s = s.replace(/`?\[(FACT|INFERRED|HYPOTHESIS|UNVERIFIED)\]`?/g, (_, tag) => {
    const cls = tag === "FACT" ? "badge-verified" : "badge-stub_ready";
    return `<span class="badge ${cls}" style="margin-right:4px">${tag}</span>`;
  });
  s = s.replace(/\[\[([^\]]+)\]\]/g, (_, key) => renderJumpChip(key, key));
  s = s.replace(/`([^`]+)`/g, (_, tok) => {
    const entry = resolveAlias(tok);
    return entry ? renderJumpChip(tok, tok.length > 34 ? tok.split("/").pop() : tok) : `<code class="inline-code">${tok}</code>`;
  });
  s = s.replace(/\b(MEM-\d{4}-\d{4})\b/g, (m, id, offset, full) => {
    const before = full.slice(Math.max(0, offset - 28), offset);
    return (before.includes("inspectNode") || before.includes("chip-jump") || before.includes(">")) ? m : renderJumpChip(id, id);
  });
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

async function init() {
  const res = await fetch("/api/projects");
  const data = await res.json();
  const sel = document.getElementById("projectSelect");
  sel.innerHTML = data.projects.map((p) => `<option value="${p.id}">${escapeHtml(p.name)} (${p.public_node_count + p.private_node_count} 節點)</option>`).join("");
  sel.addEventListener("change", (e) => loadProject(e.target.value));

  document.getElementById("searchInput").addEventListener("input", (e) => {
    state.search = e.target.value.trim().toLowerCase();
    renderAllViews();
  });

  document.getElementById("rescanBtn").addEventListener("click", async () => {
    const btn = document.getElementById("rescanBtn");
    btn.textContent = "⏳ 掃描中...";
    const r = await fetch(`/api/project/${state.projectId}/rescan`, { method: "POST" });
    state.overview = await r.json();
    btn.textContent = "🔄 重掃架構";
    setupGraphSimulation();
    renderAllViews();
  });

  document.getElementById("showCodeNodesToggle").addEventListener("change", (e) => {
    state.showCodeInGraph = e.target.checked;
    fitCameraToCanvas();
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
        const bp = state.overview.nodes.find((n) => getNodeVisualCat(n) === "blueprint");
        if (bp) state.selectedKey = bp.node_key || bp.node_id;
      }
      fitCameraToCanvas();
      renderAllViews();
    });
  });

  document.getElementById("resetViewBtn").addEventListener("click", () => { fitCameraToCanvas(); drawGraph(); });
  initCanvasInteractions();
  await loadProject(data.projects[0]?.id || "NetArk");
}

async function loadProject(pid) {
  state.projectId = pid;
  closeInspectorMobile();
  const res = await fetch(`/api/project/${pid}/overview`);
  state.overview = await res.json();
  setupGraphSimulation();
  renderAllViews();
  const defaultNode = state.overview.nodes.find((n) => n.node_key === "910.PM-CONTROL-NOTEBOOK.v1" || n.node_key === "500.HANDOVER-SHARDING-STUB.v1" || n.node_key === "900.HANDOVER.v1");
  if (defaultNode) inspectNode(defaultNode.node_key || defaultNode.node_id, false);
}

function setLedgerFilter(mode) { state.ledgerFilter = mode; renderPMView(); }

function matchesFilter(n) {
  const cat = getNodeVisualCat(n);
  if (state.filter !== "all") {
    if (state.filter === "code" && n.node_kind !== "code") return false;
    if (state.filter !== "code" && cat !== state.filter) return false;
  }
  if (state.search) {
    const hay = `${n.title_zh || ""} ${n.node_key || ""} ${n.node_id || ""} ${n.file_path || ""} ${n.summary_1line || ""} ${(n.keywords || []).join(" ")}`.toLowerCase();
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
  return `<div class="node-card ${isSel}" onclick="inspectNode('${escapeHtml(key)}', true)">
    <div class="node-card-header"><div class="node-title-zh">${escapeHtml(n.title_zh || key)}</div><span class="badge badge-${cat}">${escapeHtml(cat.toUpperCase())}</span></div>
    <div class="node-key-sub">${escapeHtml(key)} · <code>${escapeHtml(n.file_path)}</code></div>
    <div class="node-summary">${escapeHtml(n.summary_1line)}</div>
    <div class="node-meta-footer"><span>⬆️ 依賴: ${upCount}</span><span>⬇️ 下游/被引用: ${downCount}</span><span>⚙️ 控制源碼: ${codeCount} 支</span></div>
  </div>`;
}

function renderBlueprintShardProgress(children) {
  if (!children.length) return "";
  const total = children.length;
  const vCount = children.filter((c) => c.status === "verified").length;
  const sCount = children.filter((c) => c.status === "stub_ready").length;
  const dCount = total - vCount - sCount;
  const pct = Math.round(((vCount + sCount * 0.5) / total) * 100);
  return `<div class="bp-progress-bar">
    <div style="display:flex;justify-content:space-between;font-size:11.5px;margin-bottom:4px">
      <span>🧩 <strong>子切片落地進度 (${total} 支)</strong>：🟢 已驗證 ${vCount} · 🟡 Stub就緒 ${sCount} · 🟠 草案 ${dCount}</span>
      <strong style="color:var(--gold-bright)">${pct}%</strong>
    </div>
    <div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:linear-gradient(90deg, var(--c-verified), var(--gold-warm))"></div></div>
  </div>`;
}

function renderAllViews() {
  if (!state.overview) return;
  const s = state.overview.stats;
  document.getElementById("statsBar").innerHTML = `
    <div class="stat-card"><span class="stat-label">📚 記憶節點</span><span class="stat-val">${s.total_memory_nodes}</span></div>
    <div class="stat-card"><span class="stat-label">🟢 已驗證</span><span class="stat-val" style="color:var(--c-verified)">${s.verified_count}</span></div>
    <div class="stat-card"><span class="stat-label">🟣 藍圖/Stub</span><span class="stat-val" style="color:var(--c-blueprint)">${s.blueprint_count}/${s.stub_ready_count}</span></div>
    <div class="stat-card"><span class="stat-label">🟠 草案</span><span class="stat-val" style="color:var(--c-draft)">${s.draft_count}</span></div>
    <div class="stat-card"><span class="stat-label">📋 工單進度</span><span class="stat-val">${s.ledger_done}/${s.ledger_total}</span></div>
    <div class="stat-card"><span class="stat-label">🛡️ 上帝腳本</span><span class="stat-val" style="color:${s.god_script_count > 0 ? "var(--c-god)" : "var(--c-verified)"}">${s.god_script_count} 支</span></div>
  `;
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

  document.getElementById("matrixContent").innerHTML = `
    ${blueprints.length ? `<div class="section-card">
      <h3>🏛️ 藍圖分片與子模組樹 (Blueprint ➔ Shards ➔ 綁定程式碼)</h3>
      <p class="layer-desc">呈現總藍圖母體如何拆解為獨立子切片，並追蹤各子切片之驗證進度與控制源碼。</p>
      ${blueprints.map((bp) => {
        const children = (bp.shard_modules || []).map((k) => byKey[k]).filter(Boolean);
        return `<div class="blueprint-tree-box">${renderNodeCardHtml(bp)}${renderBlueprintShardProgress(children)}${children.length ? `<div class="shard-children">${children.map(renderNodeCardHtml).join("")}</div>` : ""}</div>`;
      }).join("")}
    </div>` : ""}
    <div class="section-card"><h3>🏛️ 第 1 層：核心憲法與安全護欄 (${layer1.length})</h3><p class="layer-desc">全專案最高指導原則（000 憲法、100 邊界與安全規則），所有下層規格皆依賴此層。</p><div class="node-grid">${layer1.map(renderNodeCardHtml).join("")}</div></div>
    <div class="section-card"><h3>⚙️ 第 2 層：核心架構與領域規格 (${layer2.length})</h3><p class="layer-desc">定義路由器、快取、交接、雙軌圖書館與領域法則之正式規格書。</p><div class="node-grid">${layer2.map(renderNodeCardHtml).join("")}</div></div>
    <div class="section-card"><h3>📚 第 3 層：Wiki 知識庫、審計報告與交接台帳 (${layer3.length})</h3><p class="layer-desc">操作指南、歷史壓力測試審計、微對話交接快照與活躍工單台帳。</p><div class="node-grid">${layer3.map(renderNodeCardHtml).join("")}</div></div>
  `;
}

function renderPMView() {
  const { handover, ledger, stats } = state.overview;
  const pct = stats.ledger_total ? Math.round((stats.ledger_done / stats.ledger_total) * 100) : 0;
  const secEntries = Object.entries(handover.sections || {});
  const activeCount = ledger.filter((x) => !x.is_done).length;
  const doneCount = ledger.filter((x) => x.is_done).length;
  const sortedLedger = [...ledger].sort((a, b) => Number(a.is_done) - Number(b.is_done));
  const filteredLedger = sortedLedger.filter((item) => state.ledgerFilter === "active" ? !item.is_done : state.ledgerFilter === "done" ? item.is_done : true);

  document.getElementById("pmContent").innerHTML = `
    <div class="section-card">
      <h3><span>🔄 當前對話交接快照 (<code>HANDOVER.md</code> — 點擊任意膠囊直接於右側預覽檔案)</span><button class="chip chip-jump" onclick="inspectNode('900.HANDOVER.v1', true)">📖 檢視完整 HANDOVER.md</button></h3>
      <div class="handover-grid">${secEntries.map(([title, content]) => {
        const displayTitle = HANDOVER_TITLE_MAP[title.trim().charAt(0)] || title;
        return `<div class="handover-box"><h4>${escapeHtml(displayTitle)}</h4>${renderHandoverSectionContent(title, content)}</div>`;
      }).join("")}</div>
    </div>
    <div class="section-card">
      <h3>
        <span>📋 專案唯一活躍工單台帳 (<code>LEDGER.md</code> — 完成率 ${pct}%)</span>
        <div class="filter-pills">
          <button class="pill ${state.ledgerFilter === "all" ? "active" : ""}" onclick="setLedgerFilter('all')">📋 全部 (${ledger.length})</button>
          <button class="pill ${state.ledgerFilter === "active" ? "active" : ""}" onclick="setLedgerFilter('active')">🔥 進行中 / 草案 (${activeCount})</button>
          <button class="pill ${state.ledgerFilter === "done" ? "active" : ""}" onclick="setLedgerFilter('done')">✅ 已完成 (${doneCount})</button>
          <button class="chip chip-jump" onclick="inspectNode('300.LEDGER.v1', true)">📖 原始台帳</button>
        </div>
      </h3>
      <div class="progress-track" style="margin-bottom:12px"><div class="progress-fill" style="width:${pct}%;background:var(--c-verified)"></div></div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th style="width:115px">工單 ID</th><th>任務主旨與技術細項 (點擊膠囊開啟藍圖/規格)</th><th style="width:170px">狀態 / 藍圖</th><th style="width:120px">負責角色</th><th style="width:240px">驗收基準 (點擊開啟腳本/規格)</th></tr></thead>
          <tbody>${filteredLedger.map((item) => `<tr class="${item.is_done ? "" : "wo-active-row"}">
            <td><strong>${escapeHtml(item.wo_id)}</strong></td>
            <td><div class="wo-title-main">${escapeHtml(item.title_main || item.title)}</div>${item.title_sub ? `<div class="wo-title-sub">${renderSmartRichText(item.title_sub)}</div>` : ""}</td>
            <td><span class="badge ${item.is_done ? "badge-verified" : "badge-draft"}" style="margin-bottom:4px">${escapeHtml(item.status.split("(")[0].trim())}</span>${item.status.includes("(") ? `<div style="margin-top:3px">${renderSmartRichText(item.status.slice(item.status.indexOf("(")))}</div>` : ""}</td>
            <td><code class="inline-code">${escapeHtml(item.role)}</code></td>
            <td><div class="oracle-cell">${renderSmartRichText(item.oracle)}</div></td>
          </tr>`).join("")}</tbody>
        </table>
      </div>
    </div>
  `;
}

function renderCodeView() {
  const codes = state.overview.code_health.filter((c) => matchesFilter(c));
  document.getElementById("codeContent").innerHTML = `
    <div class="section-card">
      <h3>🛡️ 程式碼模組行數水位與防上帝腳本監控 (軟性預警 400 行 / 剛性凍結 600 行)</h3>
      <div class="table-wrap"><table class="data-table">
        <thead><tr><th>模組路徑</th><th>行數水位 (上限 600)</th><th>健康狀態</th><th>AST 符號</th><th>統御規格</th></tr></thead>
        <tbody>${codes.map((c) => {
          const pct = Math.min(100, Math.round((c.line_count / 600) * 100));
          const color = COLORS[c.status] || COLORS.code;
          return `<tr style="cursor:pointer" onclick="inspectNode('${escapeHtml(c.node_key)}', true)">
            <td><strong><code>${escapeHtml(c.file_path)}</code></strong></td>
            <td style="width:180px"><div>${c.line_count} 行</div><div class="progress-track"><div class="progress-fill" style="width:${pct}%;background:${color}"></div></div></td>
            <td><span class="badge badge-${c.status}">${escapeHtml(c.health_label)}</span></td>
            <td>${c.symbol_count} 個</td>
            <td>${(c.governing_specs || []).map((g) => `<span class="chip chip-jump" onclick="event.stopPropagation();inspectNode('${escapeHtml(g)}', true)">📘 ${escapeHtml(g)}</span>`).join(" ")}</td>
          </tr>`;
        }).join("")}</tbody>
      </table></div>
    </div>
  `;
}

function renderFormattedMarkdownBody(md) {
  if (!md) return "";
  let inCode = false;
  const out = [];
  for (const line of md.split("\n")) {
    if (line.trim().startsWith("```")) { inCode = !inCode; out.push(inCode ? `<pre class="md-code-block">` : `</pre>`); continue; }
    if (inCode) { out.push(escapeHtml(line) + "\n"); continue; }
    if (line.startsWith("### ")) out.push(`<h5 class="md-h3">${renderSmartRichText(line.slice(4))}</h5>`);
    else if (line.startsWith("## ")) out.push(`<h4 class="md-h2">${renderSmartRichText(line.slice(3))}</h4>`);
    else if (line.startsWith("# ")) out.push(`<h3 class="md-h1">${renderSmartRichText(line.slice(2))}</h3>`);
    else if (line.trim().startsWith("- ")) out.push(`<div class="md-bullet">• ${renderSmartRichText(line.trim().slice(2))}</div>`);
    else out.push(`<div class="md-line">${renderSmartRichText(line)}</div>`);
  }
  if (inCode) out.push(`</pre>`);
  return out.join("");
}

async function inspectNode(nodeKey, openSheetOnMobile = true) {
  const entry = resolveAlias(nodeKey);
  const resolvedKey = entry ? entry.key : nodeKey;
  state.selectedKey = resolvedKey;
  renderMatrixView();
  drawGraph();
  if (openSheetOnMobile) openInspectorMobile();

  const panel = document.getElementById("inspectorPanel");
  const res = await fetch(`/api/project/${state.projectId}/node/${encodeURIComponent(resolvedKey)}`);
  if (!res.ok) return;
  const d = await res.json();
  const byKey = Object.fromEntries(state.overview.nodes.map((n) => [n.node_key || n.node_id, n]));
  const labelOf = (k) => (byKey[k] && byKey[k].title_zh ? `${byKey[k].title_zh} (${k})` : k);
  const cat = getNodeVisualCat(d);
  const upstreams = [...new Set([...(d.depends_on || []), ...(d.parent_blueprint ? [d.parent_blueprint] : []), ...(d.governing_specs || [])])];
  const downstreams = [...new Set([...(d.shard_modules || []), ...(d.backlinks || []), ...(d.outbound_links || [])])];

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
    <div class="inspector-section"><h4>⚙️ 控制哪些程式碼與函式行號 (${(d.code_bindings || []).length})</h4>${(d.code_bindings || []).map((cb) => `<div style="background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:9px;margin-bottom:8px"><div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px;font-size:12px;margin-bottom:6px"><strong style="cursor:pointer;color:var(--c-code)" onclick="inspectNode('code:${escapeHtml(cb.file_path)}', true)">📄 ${escapeHtml(cb.file_path)}</strong><span>${escapeHtml(cb.health_label || "")}</span></div><div class="chip-list">${(cb.symbols || []).slice(0, 18).map((sym) => `<span class="chip" style="font-size:11px">ƒ ${escapeHtml(sym.name)} (L${sym.line_start}-L${sym.line_end})</span>`).join("")}</div></div>`).join("") || `<span style="font-size:12px;color:var(--text-muted)">無直接綁定源碼</span>`}</div>
    <div class="inspector-section"><h4>📖 完整規格筆記內容 (點擊內文膠囊可連續跳轉)</h4><div class="md-body">${renderFormattedMarkdownBody(d.body_markdown || "")}</div></div>
  `;
}

window.addEventListener("DOMContentLoaded", init);
