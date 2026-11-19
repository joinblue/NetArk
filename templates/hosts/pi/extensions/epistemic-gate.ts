// NetArk Epistemic Gate & Progressive Context Disclosure Extension
// ================================================================
// 1. Active-Only Progressive Disclosure: Injects the Turn-1 Frozen Codebook Map
//    (`memory/index/CONTEXT_INDEX.json`) into the system prompt on turn start.
// 2. Tiered Modularity Gate (`GATE-02`): 401~550 lines soft warning buffer,
//    > 550 lines (`newLines > oldLines`, `delta > 0`) hard block (`MODULARITY-GATE`).
// 3. Write-Time Schema & Index Enforcement + Code-to-Spec Drift Alert.

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
	findAffectedMemoryNodes, queryCodeIntelligenceMap, queryLibraryNodes,
	registerEpistemicLibraryTools, runSessionShutdownConsolidation,
} from "./epistemic-library-tools.ts";

export {
	findAffectedMemoryNodes, queryCodeIntelligenceMap, queryLibraryNodes,
	registerEpistemicLibraryTools, runSessionShutdownConsolidation,
};

export const CATALOG_STAGE2_THRESHOLD = 25;
export const CODE_SOFT_LINE_LIMIT = 400;
export const CODE_HARD_LINE_LIMIT = 550;

export function readHandoverBodySnapshot(cwd: string): string | null {
	const handoverPath = path.join(cwd, "memory", "episodic", "HANDOVER.md");
	if (!fs.existsSync(handoverPath)) return null;
	try {
		const raw = fs.readFileSync(handoverPath, "utf-8");
		const stripped = raw.replace(/^---\n[\s\S]*?\n---\n/, "").trim();
		if (!stripped) return null;
		return [
			"",
			"### 🔄 [Session Boot Handover Snapshot (Frozen at Turn 1 for KV Cache — Source: memory/episodic/HANDOVER.md)]",
			...stripped.split(/\r?\n/).slice(0, 45),
		].join("\n");
	} catch {
		return null;
	}
}

export function buildProgressiveContextSummary(cwd: string): string | null {
	const indexPath = path.join(cwd, "memory", "index", "CONTEXT_INDEX.json");
	const privateIndexPath = path.join(cwd, "memory", "index", "PRIVATE_INDEX.json");
	if (!fs.existsSync(indexPath) && !fs.existsSync(privateIndexPath)) return null;

	try {
		const raw = fs.existsSync(indexPath) ? JSON.parse(fs.readFileSync(indexPath, "utf-8")) : {};
		const privateRaw = fs.existsSync(privateIndexPath) ? JSON.parse(fs.readFileSync(privateIndexPath, "utf-8")) : null;
		const registry = raw.domain_registry ?? {};
		const itemLines: string[] = [];
		const pinnedLines: string[] = [];
		let activeCount = 0;
		let isolatedCount = 0;

		const collectRegistry = (reg: Record<string, any>, isPrivate = false) => {
			for (const [code, section] of Object.entries<any>(reg)) {
				const items = section?.items ?? [];
				if (!Array.isArray(items) || items.length === 0) continue;
				for (const item of items) {
					if (item.status === "archived" || item.status === "deprecated") {
						isolatedCount++;
						continue;
					}
					activeCount++;
					const tag = isPrivate ? "🔒PRIVATE | " : "";
					const line = `- [${tag}${code} | ${item.node_key} | ${item.node_id} (${item.artifact_type}/${item.status})] ${item.summary_1line} -> \`${item.path}\``;
					itemLines.push(line);
					if (
						code === "000" || code === "100" || item.always_pin ||
						item.node_key === "300.LEDGER.v1" || item.status === "draft" ||
						item.status === "reviewing" || item.status === "stub_ready"
					) {
						pinnedLines.push(line);
					}
				}
			}
		};

		collectRegistry(registry, false);
		if (privateRaw?.domain_registry) collectRegistry(privateRaw.domain_registry, true);

		const handoverBlock = readHandoverBodySnapshot(cwd);
		const hasReverseLookup = Boolean(raw?.codebook_map?.reverse_lookup);
		const codebookCompact =
			typeof raw?.codebook_map?.compact_text === "string" && (hasReverseLookup || raw.codebook_map.compact_text)
				? raw.codebook_map.compact_text.trim()
				: "";

		if (codebookCompact) {
			const parts = ["", codebookCompact];
			if (handoverBlock) parts.push(handoverBlock);
			return parts.join("\n");
		}

		if (activeCount > CATALOG_STAGE2_THRESHOLD) {
			const stats = raw.domain_stats ?? {};
			const statsSummary = Object.entries(stats).filter(([_, c]) => (c as number) > 0).map(([d, c]) => `${d}: ${c}`).join(" | ");
			const summaryLines: string[] = [
				"",
				`## 🧩 [NetArk Progressive Context Index] 專案圖書館分類摘要 (節點數: ${activeCount} > ${CATALOG_STAGE2_THRESHOLD})`,
				`館藏統計：${statsSummary}`,
				"提示：館藏條目已超過緊湊閾值，使用 `query_library(domain=..., query=...)` 可精準檢索條目與雙向圖譜。",
				"### 核心憲法、活躍工單與施工中分片 (Pinned):",
				...pinnedLines,
			];
			const compactCatalog = summaryLines.slice(0, 22).join("\n");
			return handoverBlock ? `${compactCatalog}\n${handoverBlock}` : compactCatalog;
		}

		const lines: string[] = [
			"",
			"## 🧩 [NetArk Progressive Context Index] 專案記憶節點單行索引 (CONTEXT_INDEX — Active-Only)",
			`專案: ${raw.project ?? path.basename(cwd)} | 活躍節點數: ${activeCount} (已隔離歷史/淘汰節點: ${isolatedCount})`,
			"提示：此索引僅供需要查閱架構規範時按需使用 `read` 調閱；一般對話請直接回應使用者需求，無須主動詢問是否執行驗證。",
			...itemLines,
		];

		const pendingAlignments = [
			...(Array.isArray(raw.pending_topology_alignments) ? raw.pending_topology_alignments : []),
			...(Array.isArray(privateRaw?.pending_topology_alignments) ? privateRaw.pending_topology_alignments : []),
		];
		if (pendingAlignments.length > 0) {
			lines.push("", "⚠️ [Pending Topology Alignment | 跨文件潛在規格衝突與待收斂提醒 (supersedes/conflicts_with 留空監測)]:");
			for (const item of pendingAlignments) {
				const targets = Array.isArray(item.unlinked_targets) ? item.unlinked_targets.join(", ") : "";
				lines.push(
					`- 節點 ${item.source_node_id} (${item.source_node_key} @ \`${item.source_path}\`) 內文提及活躍節點 [${targets}]，但標頭 \`supersedes\`/\`conflicts_with\` 尚未掛載收斂！調閱相關規格時請以最新節點或真實程式碼為準，並在驗證完成後歸檔舊節點。`,
				);
			}
		}

		if (handoverBlock) lines.push(handoverBlock);
		return lines.join("\n");
	} catch {
		return null;
	}
}

const sessionPinnedSummaries = new Map<string, string>();

export function getSessionPinnedContextSummary(sessionKey: string, cwd: string, forceRefresh = false): string | null {
	if (!forceRefresh && sessionPinnedSummaries.has(sessionKey)) return sessionPinnedSummaries.get(sessionKey) ?? null;
	const built = buildProgressiveContextSummary(cwd);
	if (built) sessionPinnedSummaries.set(sessionKey, built);
	return built;
}

export function clearSessionPinnedContextSummaries(): void {
	sessionPinnedSummaries.clear();
}

export interface NetArkEpistemicBridge {
	getVerifiedIndexSnapshot(cwd: string): any;
	getCatalogSummary(cwd: string): string | null;
	queryLibrary(cwd: string, params: { domain?: string; query?: string; node_key?: string; include_neighbors?: boolean; limit?: number }): any[];
	getSessionPinnedContextSummary(sessionKey: string, cwd: string, forceRefresh?: boolean): string | null;
	clearSessionPinnedContextSummaries(): void;
}

export const netarkEpistemicBridge: NetArkEpistemicBridge = {
	getVerifiedIndexSnapshot: (cwd: string) => {
		const p = path.join(cwd, "memory", "index", "CONTEXT_INDEX.json");
		return fs.existsSync(p) ? JSON.parse(fs.readFileSync(p, "utf-8")) : null;
	},
	getCatalogSummary: (cwd: string) => buildProgressiveContextSummary(cwd),
	queryLibrary: (cwd: string, params) => queryLibraryNodes(cwd, params),
	getSessionPinnedContextSummary,
	clearSessionPinnedContextSummaries,
};
export const fridayEpistemicBridge = netarkEpistemicBridge;

(globalThis as any).__netarkEpistemicBridge = netarkEpistemicBridge;
(globalThis as any).__fridayEpistemicBridge = fridayEpistemicBridge;

export default function (pi: ExtensionAPI) {
	(globalThis as any).__netarkEpistemicBridge = netarkEpistemicBridge;
	(globalThis as any).__fridayEpistemicBridge = fridayEpistemicBridge;

	registerEpistemicLibraryTools(pi, (cwd, params) => fridayEpistemicBridge.queryLibrary(cwd, params));

	pi.on("session_shutdown", async (_event: any, ctx: any) => {
		const cwd = ctx?.cwd || process.cwd();
		try {
			runSessionShutdownConsolidation(cwd, sessionPinnedSummaries.size);
		} finally {
			clearSessionPinnedContextSummaries();
		}
	});

	pi.on("session_start", async (_event, ctx) => {
		const sessionKey = `${ctx.sessionManager?.getSessionId?.() ?? "default"}::${ctx.cwd}`;
		getSessionPinnedContextSummary(sessionKey, ctx.cwd, true);
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const sessionKey = `${ctx.sessionManager?.getSessionId?.() ?? "default"}::${ctx.cwd}`;
		const summary = getSessionPinnedContextSummary(sessionKey, ctx.cwd, false);
		return summary ? { systemPrompt: `${event.systemPrompt}\n${summary}` } : undefined;
	});

	// GATE-02: Pre-Tool Anti-God-Script Hard Gate (`CODE_HARD_LINE_LIMIT = 550` & `newLines > oldLines`)
	pi.on("tool_call", async (event, ctx) => {
		if (event.toolName !== "write" && event.toolName !== "edit") return undefined;
		const input = (event.input ?? {}) as Record<string, unknown>;
		const rawPath = String(input.path ?? input.file_path ?? "").trim();
		if (!rawPath) return undefined;

		const absPath = path.isAbsolute(rawPath) ? path.resolve(rawPath) : path.resolve(ctx.cwd, rawPath);
		const relToCwd = path.relative(ctx.cwd, absPath).replace(/\\/g, "/");
		if (relToCwd.startsWith("memory/") || relToCwd.startsWith("scratch/")) return undefined;

		const baseName = path.basename(relToCwd);
		const isCodeFile = (relToCwd.endsWith(".ts") || relToCwd.endsWith(".py")) && !baseName.startsWith("test_");
		if (!isCodeFile) return undefined;

		const oldText = fs.existsSync(absPath) ? fs.readFileSync(absPath, "utf-8") : "";
		const oldLines = oldText ? oldText.split(/\r?\n/).length : 0;
		let effText = oldText;
		if (event.toolName === "write" && typeof input.content === "string") {
			effText = input.content;
		} else if (event.toolName === "edit") {
			const edits = Array.isArray(input.edits)
				? (input.edits as Array<{ oldText?: string; newText?: string }>)
				: typeof input.oldText === "string" && typeof input.newText === "string"
					? [{ oldText: input.oldText, newText: input.newText }]
					: [];
			for (const ed of edits) {
				if (ed?.oldText && typeof ed?.newText === "string" && effText.includes(ed.oldText)) {
					effText = effText.replace(ed.oldText, ed.newText);
				}
			}
		}
		const newLines = effText ? effText.split(/\r?\n/).length : 0;

		if (newLines > CODE_HARD_LINE_LIMIT && newLines > oldLines) {
			return {
				block: true,
				reason:
					`🛡️ [NetArk Modularity Gate | MODULARITY-GATE | ANTI-GOD-SCRIPT BLOCK]\n` +
					`目標代碼檔 \`${relToCwd}\` 修改後將達 ${newLines} 行（超過硬性阻斷紅線 ${CODE_HARD_LINE_LIMIT} 行，且本次淨增 +${newLines - oldLines} 行 > 0）！\n` +
					`👉 [處方籤 Remediation]: 嚴禁繼續往 > 550 行之巨型腳本堆疊新功能（已廢除 delta > 15 漏洞）！只允許刪減瘦身，或將新增邏輯拆分為獨立子模組 / \`.netark/extensions/<feature>.ts\` 插件。`,
			};
		}
		const hygScript = path.join(ctx.cwd, "schemas", "code_hygiene_ast.py");
		if (relToCwd.endsWith(".py") && fs.existsSync(hygScript)) {
			try {
				const out = execFileSync(
					"python3",
					["-c", "import json,sys; from schemas.code_hygiene_ast import check_python_ast_hygiene; print(json.dumps(check_python_ast_hygiene(sys.stdin.read(), sys.argv[1])))", relToCwd],
					{ cwd: ctx.cwd, input: effText, encoding: "utf-8", timeout: 5_000 },
				).trim();
				const res = out && out !== "null" ? JSON.parse(out) : null;
				if (res && res.allowed === false) return { block: true, reason: `🛡️ [NetArk AST Code Hygiene Gate | ${res.code}]\n${res.reason}` };
			} catch {}
		}
		return undefined;
	});

	// Write-Time Schema & Index Enforcement + GATE-02 401~550 Soft Warning Buffer + Code-to-Spec Drift Alert
	pi.on("tool_result", async (event, ctx) => {
		if (event.toolName !== "write" && event.toolName !== "edit") return undefined;
		if (event.isError) return undefined;

		const input = (event.input ?? {}) as Record<string, unknown>;
		const rawPath = String(input.path ?? input.file_path ?? "").trim();
		if (!rawPath) return undefined;

		const absPath = path.isAbsolute(rawPath) ? path.resolve(rawPath) : path.resolve(ctx.cwd, rawPath);
		const relToCwd = path.relative(ctx.cwd, absPath).replace(/\\/g, "/");

		if (relToCwd.startsWith("memory/") && relToCwd.toLowerCase().endsWith(".md")) {
			if (relToCwd === "memory/codex/CONTEXT_MAP.md") return undefined;

			const syncScriptPath = path.join(ctx.cwd, "scripts", "sync_doc_metadata.py");
			const validatorPath = path.join(ctx.cwd, "schemas", "schema_validator.py");
			const mapScriptPath = path.join(ctx.cwd, "scripts", "auto_update_map.py");
			if (!fs.existsSync(validatorPath) || !fs.existsSync(absPath)) return undefined;

			let syncOut = "";
			if (fs.existsSync(syncScriptPath)) {
				try {
					syncOut = execFileSync("python3", [syncScriptPath, "--file", absPath, "--project-root", ctx.cwd], {
						cwd: ctx.cwd, encoding: "utf-8", timeout: 15_000,
					}).trim();
				} catch {}
			}

			try {
				const valOut = execFileSync("python3", [validatorPath, "--file", absPath], { cwd: ctx.cwd, encoding: "utf-8", timeout: 15_000 }).trim();
				const mapOut = fs.existsSync(mapScriptPath)
					? execFileSync("python3", [mapScriptPath], { cwd: ctx.cwd, encoding: "utf-8", timeout: 15_000 }).trim()
					: "";
				const existingContent = Array.isArray(event.content) ? event.content : [];
				const syncPrefix = syncOut ? `${syncOut}\n` : "";
				return {
					content: [...existingContent, { type: "text", text: `\n${syncPrefix}✅ [Epistemic Write-Time Gate] ${valOut}${mapOut ? `\n${mapOut}` : ""}` }],
				};
			} catch (err: any) {
				const stdout = err?.stdout ? String(err.stdout).trim() : "";
				const stderr = err?.stderr ? String(err.stderr).trim() : String(err);
				const existingContent = Array.isArray(event.content) ? event.content : [];
				const syncPrefix = syncOut ? `${syncOut}\n` : "";
				return {
					content: [
						...existingContent,
						{ type: "text", text: `\n${syncPrefix}❌ [Epistemic Write-Time Gate — YAML Schema Violation in ${relToCwd}]\n${stdout}\n${stderr}\n👉 請立即根據上方處方籤修復範本 (Prescription Skeleton) 修正該記憶節點！` },
					],
					isError: true,
				};
			}
		}

		const extraAlerts: string[] = [];
		const baseName = path.basename(relToCwd);
		const isCodeFile = (relToCwd.endsWith(".ts") || relToCwd.endsWith(".py")) && !baseName.startsWith("test_");
		if (isCodeFile && fs.existsSync(absPath)) {
			try {
				const lineCount = fs.readFileSync(absPath, "utf-8").split(/\r?\n/).length;
				if (lineCount > CODE_HARD_LINE_LIMIT) {
					extraAlerts.push(
						`\n🚨 [Modularity Gate | 防上帝腳本硬性警報 (${lineCount} > ${CODE_HARD_LINE_LIMIT} 行)]\n` +
							`檔案 \`${relToCwd}\` 已達 ${lineCount} 行（超過硬上限 ${CODE_HARD_LINE_LIMIT} 行）！請立即拆分子模組。`,
					);
				} else if (lineCount > CODE_SOFT_LINE_LIMIT) {
					extraAlerts.push(
						`\n⚠️ [Modularity Buffer] 檔案已達 ${lineCount} 行 (> ${CODE_SOFT_LINE_LIMIT} 行標準預算)，完成本次修復後請規劃拆分子模組。`,
					);
				}
			} catch {}
		}

		const affectedNodes = findAffectedMemoryNodes(ctx.cwd, relToCwd);
		if (affectedNodes.length > 0) {
			const nodeBullets = affectedNodes.map((n) => `  - [${n.node_key} | ${n.node_id}] \`${n.path}\` (${n.summary_1line})`).join("\n");
			extraAlerts.push(
				`\n⚠️ [Code-to-Spec Drift Alert | 源碼變更連動警報]\n` +
					`您剛修改了受保護源碼 \`${relToCwd}\`，以下活躍記憶節點將此路徑列為 \`affected_paths\`：\n${nodeBullets}\n` +
					`💡 若本次變更涉及架構介面、路由行為或安全規則調整，請同步檢視並更新對應之記憶節點與 \`epistemic_profile\` 計數。`,
			);
		}

		if (extraAlerts.length > 0) {
			const existingContent = Array.isArray(event.content) ? event.content : [];
			return { content: [...existingContent, { type: "text", text: extraAlerts.join("\n") }] };
		}
		return undefined;
	});
}
