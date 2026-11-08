// NetArk Epistemic Gate & Progressive Context Disclosure Extension
// ================================================================
// 1. Active-Only Progressive Disclosure: Injects the project's 1-line Context Index
//    (`memory/index/CONTEXT_INDEX.json`) into the system prompt on turn start,
//    automatically isolating `archived` and `deprecated` nodes.
// 2. Write-Time Schema & Index Enforcement: Automatically validates `memory/**/*.md`
//    writes/edits via `schema_validator.py` (with YAML Prescription Skeleton on error)
//    and recompiles `CONTEXT_INDEX.json` + `CONTEXT_MAP.md` (`auto_update_map.py`).
// 3. Code-to-Spec Drift Alert: When `write`/`edit` modifies a governed source file
//    listed in any active node's `affected_paths`, appends a reminder to check/update
//    the corresponding architecture spec node.
// 4. Provides `/validate` command to run the independent Oracle (`schema_validator.py`).

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

export const CATALOG_STAGE2_THRESHOLD = 25;
export const CODE_SOFT_LINE_LIMIT = 400;
export const CODE_HARD_LINE_LIMIT = 600;

export function readHandoverBodySnapshot(cwd: string): string | null {
	const handoverPath = path.join(cwd, "memory", "episodic", "HANDOVER.md");
	if (!fs.existsSync(handoverPath)) return null;
	try {
		const raw = fs.readFileSync(handoverPath, "utf-8");
		const stripped = raw.replace(/^---\n[\s\S]*?\n---\n/, "").trim();
		if (!stripped) return null;
		const bodyLines = stripped.split(/\r?\n/).slice(0, 45);
		return [
			"",
			"### 🔄 [Session Boot Handover Snapshot (Frozen at Turn 1 for KV Cache — Source: memory/episodic/HANDOVER.md)]",
			...bodyLines,
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
					// Stage 5: Active-Only Injection (automatically isolate archived & deprecated nodes)
					if (item.status === "archived" || item.status === "deprecated") {
						isolatedCount++;
						continue;
					}
					activeCount++;
					const tag = isPrivate ? "🔒PRIVATE | " : "";
					const line = `- [${tag}${code} | ${item.node_key} | ${item.node_id} (${item.artifact_type}/${item.status})] ${item.summary_1line} -> \`${item.path}\``;
					itemLines.push(line);
					if (
						code === "000" ||
						code === "100" ||
						item.always_pin ||
						item.node_key === "300.LEDGER.v1" ||
						item.status === "draft" ||
						item.status === "reviewing" ||
						item.status === "stub_ready"
					) {
						pinnedLines.push(line);
					}
				}
			}
		};

		collectRegistry(registry, false);
		if (privateRaw?.domain_registry) {
			collectRegistry(privateRaw.domain_registry, true);
		}

		const handoverBlock = readHandoverBodySnapshot(cwd);
		const codebookCompact = typeof raw?.codebook_map?.compact_text === "string" ? raw.codebook_map.compact_text.trim() : "";

		if (codebookCompact) {
			const parts = ["", codebookCompact];
			if (handoverBlock) parts.push(handoverBlock);
			return parts.join("\n");
		}

		if (activeCount > CATALOG_STAGE2_THRESHOLD) {
			// Stage 1 Compact Summary: <= 20 lines + Handover Snapshot
			const stats = raw.domain_stats ?? {};
			const statsSummary = Object.entries(stats)
				.filter(([_, c]) => (c as number) > 0)
				.map(([d, c]) => `${d}: ${c}`)
				.join(" | ");
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
			lines.push("");
			lines.push("⚠️ [Pending Topology Alignment | 跨文件潛在規格衝突與待收斂提醒 (supersedes/conflicts_with 留空監測)]:");
			for (const item of pendingAlignments) {
				const targets = Array.isArray(item.unlinked_targets) ? item.unlinked_targets.join(", ") : "";
				lines.push(
					`- 節點 ${item.source_node_id} (${item.source_node_key} @ \`${item.source_path}\`) 內文提及活躍節點 [${targets}]，但標頭 \`supersedes\`/\`conflicts_with\` 尚未掛載收斂！調閱相關規格時請以最新節點或真實程式碼為準，並在驗證完成後歸檔舊節點。`,
				);
			}
		}

		if (handoverBlock) {
			lines.push(handoverBlock);
		}

		return lines.join("\n");
	} catch {
		return null;
	}
}

export function findAffectedMemoryNodes(
	cwd: string,
	relFilePath: string,
): Array<{ node_id: string; node_key: string; path: string; summary_1line: string }> {
	const indexPaths = [
		path.join(cwd, "memory", "index", "CONTEXT_INDEX.json"),
		path.join(cwd, "memory", "index", "PRIVATE_INDEX.json"),
	].filter((p) => fs.existsSync(p));
	if (indexPaths.length === 0) return [];
	try {
		const matches: Array<{ node_id: string; node_key: string; path: string; summary_1line: string }> = [];
		const normalizedTarget = relFilePath.replace(/\\/g, "/").replace(/^\.\//, "");

		for (const indexPath of indexPaths) {
			const raw = JSON.parse(fs.readFileSync(indexPath, "utf-8"));
			const registry = raw.domain_registry ?? {};
			for (const section of Object.values<any>(registry)) {
				const items = section?.items ?? [];
				if (!Array.isArray(items)) continue;
				for (const item of items) {
					if (item.status === "archived" || item.status === "deprecated") continue;
					const affected: string[] = Array.isArray(item.affected_paths) ? item.affected_paths : [];
					const isAffected = affected.some((ap) => {
						const normAp = String(ap).replace(/\\/g, "/").replace(/^\.\//, "").replace(/\/$/, "");
						return normalizedTarget === normAp || normalizedTarget.startsWith(`${normAp}/`);
					});
					if (isAffected) {
						matches.push({
							node_id: String(item.node_id ?? ""),
							node_key: String(item.node_key ?? ""),
							path: String(item.path ?? ""),
							summary_1line: String(item.summary_1line ?? ""),
						});
					}
				}
			}
		}
		return matches;
	} catch {
		return [];
	}
}

const sessionPinnedSummaries = new Map<string, string>();

export function getSessionPinnedContextSummary(sessionKey: string, cwd: string, forceRefresh = false): string | null {
	if (!forceRefresh && sessionPinnedSummaries.has(sessionKey)) {
		return sessionPinnedSummaries.get(sessionKey) ?? null;
	}
	const built = buildProgressiveContextSummary(cwd);
	if (built) {
		sessionPinnedSummaries.set(sessionKey, built);
	}
	return built;
}

export function clearSessionPinnedContextSummaries(): void {
	sessionPinnedSummaries.clear();
}

export interface NetArkEpistemicBridge {
	getVerifiedIndexSnapshot(cwd: string): any;
	getCatalogSummary(cwd: string): string | null;
	queryLibrary(
		cwd: string,
		params: {
			domain?: string;
			query?: string;
			node_key?: string;
			include_neighbors?: boolean;
			limit?: number;
		},
	): any[];
	getSessionPinnedContextSummary(sessionKey: string, cwd: string, forceRefresh?: boolean): string | null;
	clearSessionPinnedContextSummaries(): void;
}

export function queryLibraryNodes(
	cwd: string,
	params: {
		domain?: string;
		query?: string;
		node_key?: string;
		artifact_type?: string;
		tag?: string;
		include_neighbors?: boolean;
		limit?: number;
	},
): any[] {
	const indexPath = path.join(cwd, "memory", "index", "CONTEXT_INDEX.json");
	const privatePath = path.join(cwd, "memory", "index", "PRIVATE_INDEX.json");
	const indexPaths = [indexPath, privatePath].filter((p) => fs.existsSync(p));
	if (indexPaths.length === 0) return [];

	const allNodesByKey = new Map<string, any>();
	const codeIntelMap: Record<string, any> = {};
	const reverseLookup: Record<string, any> = {};
	const candidateItems: any[] = [];

	for (const p of indexPaths) {
		try {
			const index = JSON.parse(fs.readFileSync(p, "utf-8"));
			if (index.code_intelligence_map && typeof index.code_intelligence_map === "object") {
				Object.assign(codeIntelMap, index.code_intelligence_map);
			}
			if (index.codebook_map?.reverse_lookup && typeof index.codebook_map.reverse_lookup === "object") {
				Object.assign(reverseLookup, index.codebook_map.reverse_lookup);
			}
			for (const sec of Object.values<any>(index.domain_registry ?? {})) {
				for (const it of sec.items ?? []) {
					if (it.node_key) allNodesByKey.set(it.node_key, it);
					if (it.node_id) allNodesByKey.set(it.node_id, it);
					candidateItems.push(it);
				}
			}
		} catch {
			// ignore parse errors
		}
	}

	const rawLookupKey = (params.query ?? params.node_key ?? "").trim();
	const upperLookupKey = rawLookupKey.toUpperCase();
	const directCodebookEntry = reverseLookup[rawLookupKey] ?? reverseLookup[upperLookupKey];
	if (directCodebookEntry && directCodebookEntry.kind === "script") {
		const scriptInfo = codeIntelMap[directCodebookEntry.path] ?? directCodebookEntry;
		return [
			{
				...directCodebookEntry,
				code_intelligence: [scriptInfo],
			},
		];
	}
	const resolvedQuery =
		directCodebookEntry && directCodebookEntry.kind === "node"
			? String(directCodebookEntry.node_key || directCodebookEntry.node_id || params.query || "")
			: params.query;

	let results: any[] = [];
	for (const it of candidateItems) {
		if (params.domain && it.domain_code !== params.domain && it.subdomain !== params.domain) continue;
		if (params.node_key && it.node_key !== params.node_key && it.node_id !== params.node_key) continue;
		if (params.artifact_type && it.artifact_type !== params.artifact_type) continue;
		if (params.tag) {
			const tagLower = params.tag.toLowerCase();
			const tags: string[] = [
				...(Array.isArray(it.facet_tags) ? it.facet_tags : []),
				...(Array.isArray(it.keywords) ? it.keywords : []),
			];
			if (!tags.some((t) => String(t).toLowerCase() === tagLower)) continue;
		}
		if (resolvedQuery) {
			const q = resolvedQuery.toLowerCase();
			const matched =
				(it.node_key ?? "").toLowerCase().includes(q) ||
				(it.node_id ?? "").toLowerCase().includes(q) ||
				(it.summary_1line ?? "").toLowerCase().includes(q) ||
				(it.path ?? "").toLowerCase().includes(q) ||
				(Array.isArray(it.keywords) && it.keywords.some((k: string) => String(k).toLowerCase().includes(q))) ||
				(Array.isArray(it.facet_tags) && it.facet_tags.some((t: string) => String(t).toLowerCase().includes(q))) ||
				(Array.isArray(it.affected_paths) && it.affected_paths.some((ap: string) => String(ap).toLowerCase().includes(q)));
			if (!matched) continue;
		}

		const enriched: any = { ...it };
		if (params.include_neighbors !== false) {
			const neighborKeys = new Set<string>([
				...(Array.isArray(it.outbound_links) ? it.outbound_links : []),
				...(Array.isArray(it.backlinks) ? it.backlinks : []),
				...(Array.isArray(it.depends_on) ? it.depends_on : []),
			]);
			enriched.neighbor_summaries = Array.from(neighborKeys)
				.map((k) => {
					const target = allNodesByKey.get(k);
					return target
						? {
								node_key: target.node_key,
								node_id: target.node_id,
								summary_1line: target.summary_1line,
								path: target.path,
							}
						: { node_key: k, unresolved: true };
				});
		}

		const affPaths: string[] = Array.isArray(it.affected_paths) ? it.affected_paths : [];
		const matchedCodeIntel: any[] = [];
		for (const [codePath, info] of Object.entries(codeIntelMap)) {
			const byAffected = affPaths.some(
				(ap) =>
					codePath === ap ||
					codePath.startsWith(ap.replace(/\/$/, "") + "/") ||
					ap.endsWith(path.basename(codePath)),
			);
			const byQuery =
				params.query &&
				(codePath.toLowerCase().includes(params.query.toLowerCase()) ||
					(Array.isArray(info.symbols) &&
						info.symbols.some((s: any) => String(s.name).toLowerCase().includes(params.query!.toLowerCase()))));
			if (byAffected || byQuery) {
				matchedCodeIntel.push(info);
			}
		}
		if (matchedCodeIntel.length > 0) {
			enriched.code_intelligence = matchedCodeIntel;
		}

		results.push(enriched);
	}

	if (params.limit && params.limit > 0) {
		results = results.slice(0, params.limit);
	}
	return results;
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

	pi.registerTool({
		name: "query_library",
		description: "Query NetArk Library Context Index, @D/@C/@G short codes (e.g. C1, 100), bidirectional wiki graph, and AST code intelligence map.",
		parameters: {
			type: "object",
			properties: {
				domain: { type: "string", description: "3-digit domain classification code" },
				query: { type: "string", description: "Keyword search in node_key, summary, keywords, facet_tags, and affected_paths" },
				node_key: { type: "string", description: "Exact node key lookup" },
				artifact_type: { type: "string", description: "Filter by artifact_type (spec, audit, wiki, digest, reference)" },
				tag: { type: "string", description: "Filter by exact facet_tag or keyword" },
				include_neighbors: { type: "boolean", description: "Whether to return resolved 1-hop neighbor summaries" },
				limit: { type: "number", description: "Max results to return" },
			},
		},
		execute: async (args: any, ctx: any) => {
			return fridayEpistemicBridge.queryLibrary(ctx.cwd, args ?? {});
		},
	});

	// [Stage 6 Fix] Unified /dream entry point is served exclusively via .netark/prompts/dream.md.
	// Deterministic session consolidation runs automatically on session_shutdown:
	pi.on("session_shutdown", async (_event: any, ctx: any) => {
		const cwd = ctx?.cwd || process.cwd();
		try {
			const episodicDir = path.join(cwd, "memory", "episodic");
			fs.mkdirSync(episodicDir, { recursive: true });
			const digestRelPath = "memory/episodic/SESSION_DIGEST.md";
			const digestAbsPath = path.join(cwd, digestRelPath);
			const syncScript = path.join(cwd, "scripts", "sync_doc_metadata.py");

			if (!fs.existsSync(digestAbsPath) && fs.existsSync(syncScript)) {
				execFileSync(
					"python3",
					[
						syncScript,
						"--init",
						"--type",
						"digest",
						"--domain",
						"900",
						"--title",
						"Episodic Session Digest Log",
						"--file",
						digestRelPath,
					],
					{ cwd, stdio: "pipe", timeout: 8000 },
				);
			}

			const ts = new Date().toISOString();
			let dirtyFilesInfo = "clean";
			try {
				const gitStatusOut = execFileSync("git", ["status", "--short"], {
					cwd,
					encoding: "utf-8",
					stdio: "pipe",
					timeout: 4000,
				}).trim();
				if (gitStatusOut) {
					const dirtyList = gitStatusOut
						.split(/\r?\n/)
						.map((l) => l.trim().split(/\s+/).pop() ?? "")
						.filter(Boolean)
						.slice(0, 8);
					if (dirtyList.length > 0) {
						dirtyFilesInfo = `modified=[${dirtyList.join(", ")}]`;
					}
				}
			} catch {
				// Ignore git errors on non-git directories
			}

			const entryLine = `- \`${ts}\` | Session shutdown auto-consolidated (pinned=${sessionPinnedSummaries.size}, ${dirtyFilesInfo}).`;
			if (fs.existsSync(digestAbsPath)) {
				const existingDigest = fs.readFileSync(digestAbsPath, "utf-8");
				const digestLines = existingDigest.split(/\r?\n/);
				const bulletIndices = digestLines
					.map((l, idx) => (l.startsWith("- `20") ? idx : -1))
					.filter((idx) => idx >= 0);
				// Rolling window: keep at most the latest 19 existing entries + 1 new entry = 20 entries
				let updatedDigest = existingDigest.trimEnd();
				if (bulletIndices.length >= 20) {
					const removeSet = new Set(bulletIndices.slice(0, bulletIndices.length - 19));
					updatedDigest = digestLines.filter((_, idx) => !removeSet.has(idx)).join("\n").trimEnd();
				}
				fs.writeFileSync(digestAbsPath, `${updatedDigest}\n${entryLine}\n`, "utf-8");
				if (fs.existsSync(syncScript)) {
					execFileSync("python3", [syncScript, "--file", digestRelPath], {
						cwd,
						stdio: "pipe",
						timeout: 8000,
					});
				}
			}

			const mapScript = path.join(cwd, "scripts", "auto_update_map.py");
			if (fs.existsSync(mapScript)) {
				execFileSync("python3", [mapScript], { cwd, stdio: "pipe", timeout: 10000 });
			}
		} catch {
			// Best-effort deterministic consolidation on shutdown
		} finally {
			clearSessionPinnedContextSummaries();
		}
	});
	pi.on("session_start", async (_event, ctx) => {
		const sessionKey = `${ctx.sessionManager?.getSessionId?.() ?? "default"}::${ctx.cwd}`;
		getSessionPinnedContextSummary(sessionKey, ctx.cwd, true);
	});

	pi.on("before_agent_start", async (event, ctx) => {
		// Prefix KV Cache Guard (Killer 3 Fix):
		// Pin the Progressive Context Index summary per session so mid-session `memory/**/*.md` edits
		// (which trigger `auto_update_map.py`) do NOT mutate `messages[0]` (Token 0) and invalidate the Prefix KV Cache.
		const sessionKey = `${ctx.sessionManager?.getSessionId?.() ?? "default"}::${ctx.cwd}`;
		const summary = getSessionPinnedContextSummary(sessionKey, ctx.cwd, false);
		if (!summary) return undefined;
		return {
			systemPrompt: `${event.systemPrompt}\n${summary}`,
		};
	});

	// Stage 5 + M6 + M7:
	// 0. Pre-Tool Anti-God-Script Hard Gate (`CODE_HARD_LINE_LIMIT = 600` & `deltaLines > 15`)
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

		const oldLines = fs.existsSync(absPath) ? fs.readFileSync(absPath, "utf-8").split(/\r?\n/).length : 0;
		let newLines = oldLines;
		let deltaLines = 0;

		if (event.toolName === "write" && typeof input.content === "string") {
			newLines = input.content.split(/\r?\n/).length;
			deltaLines = oldLines > 0 ? newLines - oldLines : newLines;
		} else if (event.toolName === "edit" && typeof input.oldText === "string" && typeof input.newText === "string") {
			const oldSpan = input.oldText.split(/\r?\n/).length;
			const newSpan = input.newText.split(/\r?\n/).length;
			deltaLines = newSpan - oldSpan;
			newLines = oldLines + deltaLines;
		}

		if (newLines > CODE_HARD_LINE_LIMIT && deltaLines > 15) {
			return {
				block: true,
				reason:
					`🛡️ [NetArk Modularity Gate | ANTI-GOD-SCRIPT BLOCK]\n` +
					`目標代碼檔 \`${relToCwd}\` 修改後將達 ${newLines} 行（超過硬上限 ${CODE_HARD_LINE_LIMIT} 行，且本次單筆淨增 +${deltaLines} 行 > 15 行）！\n` +
					`👉 [處方籤 Remediation]: 嚴禁繼續往巨型腳本堆疊新功能！請將本次新增邏輯拆分為獨立模組或新建 \`.netark/extensions/<feature>.ts\` 插件（僅允許對既有大檔進行 deltaLines <= 15 之局部修補或減行重構）。`,
			};
		}
		return undefined;
	});

	// 1. Write-Time Schema & Index Enforcement whenever `write` or `edit` modifies `memory/**/*.md`
	// 2. Code-to-Spec Drift Alert whenever `write` or `edit` modifies a file in `affected_paths`
	pi.on("tool_result", async (event, ctx) => {
		if (event.toolName !== "write" && event.toolName !== "edit") return undefined;
		if (event.isError) return undefined;

		const input = (event.input ?? {}) as Record<string, unknown>;
		const rawPath = String(input.path ?? input.file_path ?? "").trim();
		if (!rawPath) return undefined;

		const absPath = path.isAbsolute(rawPath) ? path.resolve(rawPath) : path.resolve(ctx.cwd, rawPath);
		const relToCwd = path.relative(ctx.cwd, absPath).replace(/\\/g, "/");

		// Case A: Modified a governed memory node in `memory/**/*.md`
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
						cwd: ctx.cwd,
						encoding: "utf-8",
						timeout: 15_000,
					}).trim();
				} catch {
					// If raw frontmatter is malformed, let schema_validator.py report the Prescription Skeleton below
				}
			}

			try {
				const valOut = execFileSync("python3", [validatorPath, "--file", absPath], {
					cwd: ctx.cwd,
					encoding: "utf-8",
					timeout: 15_000,
				}).trim();
				let mapOut = "";
				if (fs.existsSync(mapScriptPath)) {
					mapOut = execFileSync("python3", [mapScriptPath], {
						cwd: ctx.cwd,
						encoding: "utf-8",
						timeout: 15_000,
					}).trim();
				}
				const existingContent = Array.isArray(event.content) ? event.content : [];
				const syncPrefix = syncOut ? `${syncOut}\n` : "";
				return {
					content: [
						...existingContent,
						{
							type: "text",
							text: `\n${syncPrefix}✅ [Epistemic Write-Time Gate] ${valOut}${mapOut ? `\n${mapOut}` : ""}`,
						},
					],
				};
			} catch (err: any) {
				const stdout = err?.stdout ? String(err.stdout).trim() : "";
				const stderr = err?.stderr ? String(err.stderr).trim() : String(err);
				const existingContent = Array.isArray(event.content) ? event.content : [];
				const syncPrefix = syncOut ? `${syncOut}\n` : "";
				return {
					content: [
						...existingContent,
						{
							type: "text",
							text: `\n${syncPrefix}❌ [Epistemic Write-Time Gate — YAML Schema Violation in ${relToCwd}]\n${stdout}\n${stderr}\n👉 請立即根據上方處方籤修復範本 (Prescription Skeleton) 修正該記憶節點！`,
						},
					],
					isError: true,
				};
			}
		}

		// Case B: Modified a source/config file outside `memory/` -> check Modularity Gate (M6) & Code-to-Spec Drift Alert
		const extraAlerts: string[] = [];
		const baseName = path.basename(relToCwd);
		const isCodeFile = (relToCwd.endsWith(".ts") || relToCwd.endsWith(".py")) && !baseName.startsWith("test_");
		if (isCodeFile && fs.existsSync(absPath)) {
			try {
				const lineCount = fs.readFileSync(absPath, "utf-8").split(/\r?\n/).length;
				if (lineCount > CODE_HARD_LINE_LIMIT) {
					extraAlerts.push(
						`\n🚨 [Modularity Gate | 防上帝腳本硬性警報 (${lineCount} > ${CODE_HARD_LINE_LIMIT} 行)]\n` +
							`檔案 \`${relToCwd}\` 已達 ${lineCount} 行（超過模組化上限 ${CODE_HARD_LINE_LIMIT} 行）！嚴禁繼續往單一巨型腳本堆疊新功能，請將新增職責抽離為獨立子模組或 \`.netark/extensions/<plugin>.ts\` 插件。`,
					);
				} else if (lineCount >= CODE_SOFT_LINE_LIMIT) {
					extraAlerts.push(
						`\n💡 [Modularity Hint | 模組化軟性提醒 (${lineCount} >= ${CODE_SOFT_LINE_LIMIT} 行)]\n` +
							`檔案 \`${relToCwd}\` 目前為 ${lineCount} 行，建議檢視是否可將獨立邏輯拆分為 helper 模組或插件，避免演變為上帝腳本。`,
					);
				}
			} catch {
				// Ignore read error
			}
		}

		const affectedNodes = findAffectedMemoryNodes(ctx.cwd, relToCwd);
		if (affectedNodes.length > 0) {
			const nodeBullets = affectedNodes
				.map((n) => `  - [${n.node_key} | ${n.node_id}] \`${n.path}\` (${n.summary_1line})`)
				.join("\n");
			extraAlerts.push(
				`\n⚠️ [Code-to-Spec Drift Alert | 源碼變更連動警報]\n` +
					`您剛修改了受保護源碼 \`${relToCwd}\`，以下活躍記憶節點將此路徑列為 \`affected_paths\`：\n` +
					`${nodeBullets}\n` +
					`💡 若本次變更涉及架構介面、路由行為或安全規則調整，請同步檢視並更新對應之記憶節點與 \`epistemic_profile\` 計數。`,
			);
		}

		if (extraAlerts.length > 0) {
			const existingContent = Array.isArray(event.content) ? event.content : [];
			return {
				content: [
					...existingContent,
					{
						type: "text",
						text: extraAlerts.join("\n"),
					},
				],
			};
		}

		return undefined;
	});
}
