/**
 * NetArk Epistemic Library Query, Code Intelligence Map & Consolidation Tools
 * ===========================================================================
 * Helper module for `epistemic-gate.ts`:
 * 1. `findAffectedMemoryNodes`: Resolves active memory nodes whose `affected_paths` match a file.
 * 2. `queryLibraryNodes`: Queries `CONTEXT_INDEX.json` & `PRIVATE_INDEX.json`, short-code `reverse_lookup` (`000..900`, `C0..Cn`), 1-hop neighbors, and AST code intelligence.
 * 3. `queryCodeIntelligenceMap`: Queries AST `code_intelligence_map` (`symbols`, `imports`, `hooks`, `max_nesting_depth`, `unused_imports`).
 * 4. `runSessionShutdownConsolidation`: Deterministic rolling-20-entry `SESSION_DIGEST.md` consolidation on shutdown.
 * 5. `registerEpistemicLibraryTools`: Registers `query_library` and `code_intelligence_map` tools on `ExtensionAPI`.
 *
 * NOTE: Exports a no-op default factory function so Pi's top-level `.netark/extensions/*.ts`
 * auto-loader succeeds while `epistemic-gate.ts` registers the tools once.
 */

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

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
	const indexPaths = [
		path.join(cwd, "memory", "index", "CONTEXT_INDEX.json"),
		path.join(cwd, "memory", "index", "PRIVATE_INDEX.json"),
	].filter((p) => fs.existsSync(p));
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
		} catch {}
	}

	const rawLookupKey = (params.query ?? params.node_key ?? "").trim();
	const upperLookupKey = rawLookupKey.toUpperCase();
	const directCodebookEntry = reverseLookup[rawLookupKey] ?? reverseLookup[upperLookupKey];
	if (directCodebookEntry && directCodebookEntry.kind === "script") {
		const scriptInfo = codeIntelMap[directCodebookEntry.path] ?? directCodebookEntry;
		return [{ ...directCodebookEntry, code_intelligence: [scriptInfo] }];
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
			enriched.neighbor_summaries = Array.from(neighborKeys).map((k) => {
				const target = allNodesByKey.get(k);
				return target
					? { node_key: target.node_key, node_id: target.node_id, summary_1line: target.summary_1line, path: target.path }
					: { node_key: k, unresolved: true };
			});
		}

		const affPaths: string[] = Array.isArray(it.affected_paths) ? it.affected_paths : [];
		const matchedCodeIntel: any[] = [];
		for (const [codePath, info] of Object.entries(codeIntelMap)) {
			const byAffected = affPaths.some(
				(ap) => codePath === ap || codePath.startsWith(ap.replace(/\/$/, "") + "/") || ap.endsWith(path.basename(codePath)),
			);
			const byQuery =
				params.query &&
				(codePath.toLowerCase().includes(params.query.toLowerCase()) ||
					(Array.isArray(info.symbols) &&
						info.symbols.some((s: any) => String(s.name).toLowerCase().includes(params.query!.toLowerCase()))));
			if (byAffected || byQuery) matchedCodeIntel.push(info);
		}
		if (matchedCodeIntel.length > 0) enriched.code_intelligence = matchedCodeIntel;
		results.push(enriched);
	}

	return params.limit && params.limit > 0 ? results.slice(0, params.limit) : results;
}

export function queryCodeIntelligenceMap(
	cwd: string,
	params: { file_path?: string; symbol?: string; kind?: string; unused_only?: boolean; limit?: number },
): any[] {
	const indexPath = path.join(cwd, "memory", "index", "CONTEXT_INDEX.json");
	if (!fs.existsSync(indexPath)) return [];
	try {
		const raw = JSON.parse(fs.readFileSync(indexPath, "utf-8"));
		const codeIntelMap: Record<string, any> = raw.code_intelligence_map ?? {};
		let entries = Object.values(codeIntelMap);
		if (params.file_path) {
			const fp = params.file_path.toLowerCase();
			entries = entries.filter((e: any) => String(e.path ?? "").toLowerCase().includes(fp));
		}
		if (params.symbol) {
			const sym = params.symbol.toLowerCase();
			entries = entries.filter(
				(e: any) => Array.isArray(e.symbols) && e.symbols.some((s: any) => String(s.name ?? "").toLowerCase().includes(sym)),
			);
		}
		if (params.kind) {
			const k = params.kind.toLowerCase();
			entries = entries.filter(
				(e: any) => Array.isArray(e.symbols) && e.symbols.some((s: any) => String(s.kind ?? "").toLowerCase() === k),
			);
		}
		if (params.unused_only) {
			entries = entries.filter((e: any) => Array.isArray(e.unused_imports) && e.unused_imports.length > 0);
		}
		return params.limit && params.limit > 0 ? entries.slice(0, params.limit) : entries;
	} catch {
		return [];
	}
}

export function runSessionShutdownConsolidation(cwd: string, pinnedCount: number): void {
	try {
		const episodicDir = path.join(cwd, "memory", "episodic");
		fs.mkdirSync(episodicDir, { recursive: true });
		const digestRelPath = "memory/episodic/SESSION_DIGEST.md";
		const digestAbsPath = path.join(cwd, digestRelPath);
		const syncScript = path.join(cwd, "scripts", "sync_doc_metadata.py");

		if (!fs.existsSync(digestAbsPath) && fs.existsSync(syncScript)) {
			execFileSync(
				"python3",
				[syncScript, "--init", "--type", "digest", "--domain", "900", "--title", "Episodic Session Digest Log", "--file", digestRelPath],
				{ cwd, stdio: "pipe", timeout: 8000 },
			);
		}

		const ts = new Date().toISOString();
		let dirtyFilesInfo = "clean";
		try {
			const gitStatusOut = execFileSync("git", ["status", "--short"], { cwd, encoding: "utf-8", stdio: "pipe", timeout: 4000 }).trim();
			if (gitStatusOut) {
				const dirtyList = gitStatusOut.split(/\r?\n/).map((l) => l.trim().split(/\s+/).pop() ?? "").filter(Boolean).slice(0, 8);
				if (dirtyList.length > 0) dirtyFilesInfo = `modified=[${dirtyList.join(", ")}]`;
			}
		} catch {}

		const entryLine = `- \`${ts}\` | Session shutdown auto-consolidated (pinned=${pinnedCount}, ${dirtyFilesInfo}).`;
		if (fs.existsSync(digestAbsPath)) {
			const existingDigest = fs.readFileSync(digestAbsPath, "utf-8");
			const digestLines = existingDigest.split(/\r?\n/);
			const bulletIndices = digestLines.map((l, idx) => (l.startsWith("- `20") ? idx : -1)).filter((idx) => idx >= 0);
			let updatedDigest = existingDigest.trimEnd();
			if (bulletIndices.length >= 20) {
				const removeSet = new Set(bulletIndices.slice(0, bulletIndices.length - 19));
				updatedDigest = digestLines.filter((_, idx) => !removeSet.has(idx)).join("\n").trimEnd();
			}
			fs.writeFileSync(digestAbsPath, `${updatedDigest}\n${entryLine}\n`, "utf-8");
			if (fs.existsSync(syncScript)) {
				execFileSync("python3", [syncScript, "--file", digestRelPath], { cwd, stdio: "pipe", timeout: 8000 });
			}
		}

		const mapScript = path.join(cwd, "scripts", "auto_update_map.py");
		if (fs.existsSync(mapScript)) {
			execFileSync("python3", [mapScript], { cwd, stdio: "pipe", timeout: 10000 });
		}
	} catch {}
}

function resolveToolExecArgs(a0: any, a1?: any, a2?: any, _a3?: any, a4?: any): { isPiRuntime: boolean; cwd: string; params: any } {
	if (typeof a0 === "string") {
		const ctxObj = a4 ?? a2;
		return { isPiRuntime: true, cwd: String(ctxObj?.cwd || process.cwd()), params: a1 && typeof a1 === "object" ? a1 : {} };
	}
	return { isPiRuntime: false, cwd: String(a1?.cwd || process.cwd()), params: a0 && typeof a0 === "object" ? a0 : {} };
}

export function registerEpistemicLibraryTools(
	pi: ExtensionAPI,
	queryFn: (cwd: string, params: any) => any[] = queryLibraryNodes,
): void {
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
		execute: async (a0: any, a1?: any, a2?: any, a3?: any, a4?: any) => {
			const { isPiRuntime, cwd, params } = resolveToolExecArgs(a0, a1, a2, a3, a4);
			const res = queryFn(cwd, params);
			return isPiRuntime ? { content: [{ type: "text", text: JSON.stringify(res, null, 2) }], details: { count: res.length } } : res;
		},
	});

	pi.registerTool({
		name: "code_intelligence_map",
		description: "Query NetArk Single-Pass AST Code Intelligence Map (symbols, line ranges, imports, hooks, max_nesting_depth, unused_imports).",
		parameters: {
			type: "object",
			properties: {
				file_path: { type: "string", description: "Substring filter on relative file path" },
				symbol: { type: "string", description: "Substring filter on function/class/const symbol name" },
				kind: { type: "string", description: "Exact symbol kind (function, async_function, class, interface, const)" },
				unused_only: { type: "boolean", description: "Only return modules with detected unused imports (P4)" },
				limit: { type: "number", description: "Max module entries to return" },
			},
		},
		execute: async (a0: any, a1?: any, a2?: any, a3?: any, a4?: any) => {
			const { isPiRuntime, cwd, params } = resolveToolExecArgs(a0, a1, a2, a3, a4);
			const res = queryCodeIntelligenceMap(cwd, params);
			return isPiRuntime ? { content: [{ type: "text", text: JSON.stringify(res, null, 2) }], details: { count: res.length } } : res;
		},
	});
}

export default function (_pi: any): void {}

