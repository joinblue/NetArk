/**
 * NetArk Guard Shell Parser & Boundary Helpers
 * ============================================
 * Pure helper module for `workspace-guard.ts`:
 * Quote-aware shell parser (`parseShellCommandQuoteAware`), read-only command classifier
 * (`isReadOnlyBashCommand`), path boundary helpers, and security constant tables.
 * NOTE: No default export — loaded by `workspace-guard.ts` to avoid duplicate extension hooks.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export const FILE_TOOLS = new Set(["read", "write", "edit", "grep", "find", "ls"]);

export const SECRET_FILE_PATTERNS: RegExp[] = [
	/(?:^|[\\/\s"'=])(?:\.netark[\\/])?auth\.json(?:$|[\s"';&|)])/i,
	/(?:^|[\\/])auth\.json$/i,
	/(?:^|[\\/\s"'=])[^\s"'=]*vault[^\s"'=]*\.json(?:$|[\s"';&|)])/i,
	/(?:^|[\\/]).*vault.*\.json$/i,
	/(?:^|[\\/\s"'=])\.env(?!(?:\.example|\.sample|\.template)(?:$|[\s"';&|)]))(?:(?:\.[a-zA-Z0-9._-]+)?(?:$|[\s"';&|)]))/i,
	/(?:^|[\\/])\.env(?!(?:\.example|\.sample|\.template)$)(?:\.[a-zA-Z0-9._-]+)?$/i,
	/(?:^|[\\/])id_(?:rsa|ed25519|ecdsa)$/i,
	/(?:^|[\\/])application_default_credentials\.json$/i,
];

export const PREWRITE_SECRET_PATTERNS: Array<{ type: string; re: RegExp }> = [
	{ type: "PRIVATE_KEY", re: /-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----/ },
	{ type: "AWS_ACCESS_KEY", re: /\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b/ },
	{ type: "GCP_API_KEY", re: /\bAIza[0-9A-Za-z\-_]{35}\b/ },
	{ type: "GITHUB_PAT", re: /\b(?:(?:ghp|gho|ghu|ghs|ghr)_[0-9A-Za-z]{36,255}|github_pat_[0-9A-Za-z_]{50,255})\b/ },
	{ type: "OPENAI_KEY", re: /\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_\-]{20,}\b/ },
	{ type: "ANTHROPIC_KEY", re: /\bsk-ant-api03-[A-Za-z0-9\-_]{20,}\b/ },
	{ type: "NVIDIA_NIM_KEY", re: /\bnvapi-[A-Za-z0-9\-_]{24,}\b/ },
	{ type: "SLACK_TOKEN", re: /\bxox[baprs]-[0-9A-Za-z\-]{10,48}\b/ },
	{ type: "STRIPE_OR_HF_TOKEN", re: /\b(?:(?:sk|rk)_live_[0-9a-zA-Z]{24,}|hf_[A-Za-z0-9]{34,})\b/ },
	{ type: "JWT_TOKEN", re: /\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/ },
	{ type: "DB_CONN_URI", re: /\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis):\/\/[^\s"'<>]+:[^\s"'<>@]+@[^\s"'<>]+\b/ },
	{ type: "GENERIC_SECRET_ASSIGN", re: /(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|private[_-]?key)\s*[:=]\s*["'][A-Za-z0-9/+_\-=]{16,}["']/i },
];

export const DESTRUCTIVE_BASH_PATTERNS: Array<{ id: string; pattern: RegExp; desc: string; remediation: string }> = [
	{
		id: "SEC-CMD-01",
		pattern: /\brm\s+(?:-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--recursive)\s+(?:\/(?:\s|$|[;&|*])|\.\.(?:\/|\s|$)|~(?:\/|\s|$)|\$HOME\b)/i,
		desc: "遞迴刪除根目錄、上層目錄或家目錄",
		remediation: "請僅針對專案工作區 (ctx.cwd) 內之明確子目錄或單一檔案進行清理，嚴禁對 /、.. 或 ~ 執行 rm -rf。",
	},
	{ id: "SEC-CMD-02", pattern: /\b(?:mkfs|fdisk|parted|wipefs)\b/i, desc: "磁碟格式化或分割表破壞指令", remediation: "系統磁碟管理工具屬於高風險操作，請改由使用者手動於終端機執行。" },
	{ id: "SEC-CMD-03", pattern: /\bdd\s+if=.*of=\/dev\//i, desc: "直接覆寫區塊裝置 (/dev/*)", remediation: "禁止直接寫入 /dev/* 區塊裝置；一般檔案測試請輸出至專案目錄下的相對路徑檔案。" },
	{ id: "SEC-CMD-04", pattern: /\b(?:curl|wget)\b[^|]*\|\s*(?:ba)?sh\b/i, desc: "未經驗證之遠端腳本管線直執 (curl|sh)", remediation: "請先將遠端檔案下載至專案暫存區並使用 read 檢視內容確認安全後，再明確執行。" },
	{ id: "SEC-CMD-05", pattern: /\b(?:chmod|chown)\s+-R\s+777\s+\//i, desc: "全域權限破壞 (chmod -R 777 /)", remediation: "請僅對專案內必要之單一腳本設定最小權限（例如 chmod +x scripts/foo.sh 或 chmod 600）。" },
	{ id: "SEC-CMD-06", pattern: /:\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:/, desc: "Fork Bomb 阻斷服務攻擊", remediation: "嚴禁執行任何形式的無窮遞迴程序衍生 (Fork Bomb)。" },
];

export const SAFE_SYSTEM_PREFIXES = ["/dev/null", "/dev/stdout", "/dev/stderr", "/dev/fd", "/proc/self"];

export const READ_ONLY_COMMANDS = new Set([
	"cat", "head", "tail", "less", "more", "grep", "egrep", "fgrep", "rg", "find",
	"ls", "stat", "wc", "file", "diff", "echo", "printf", "pwd", "which", "type",
	"uname", "whoami", "id", "date", "true", "false", "pytest",
]);

const ALLOWED_READONLY_PY_SCRIPTS = [
	"schema_validator.py", "auto_update_map.py", "sync_doc_metadata.py", "test_netark_harness.py",
	"netark_guard_core.py", "netark_guard_daemon.py", "netark_init.py", "test_netark_enterprise_guard.py",
	"code_hygiene_ast.py", "codebook_compiler.py", "topology_graph.py", "doc_initializer.py",
];

export function formatRemediation(code: string, message: string, pointer: string): string {
	return `🛡️ [NetArk Guard | ${code}] ${message}\n🔧 [RemediationPointer | 自癒處方籤]: ${pointer}`;
}

export function parseShellCommandQuoteAware(command: string): {
	unquotedCommand: string;
	subshells: string[];
	allExecutableSegments: string[];
} {
	const subshells: string[] = [];

	function extractFromSegment(src: string, depth: number): string {
		if (depth > 8) return src;
		let out = "";
		let i = 0;
		let mode: "none" | "single" | "double" = "none";

		while (i < src.length) {
			const ch = src[i];
			if (mode === "single") {
				if (ch === "'") { mode = "none"; out += "__SQ__"; }
				i++;
				continue;
			}
			if (ch === "\\") { i += 2; continue; }
			if (ch === "$" && src[i + 1] === "(") {
				let parenDepth = 1;
				let j = i + 2;
				let subMode: "none" | "single" | "double" = "none";
				while (j < src.length && parenDepth > 0) {
					const c = src[j];
					if (subMode === "single") {
						if (c === "'") subMode = "none";
						j++;
						continue;
					}
					if (c === "\\") { j += 2; continue; }
					if (subMode === "double") {
						if (c === '"') subMode = "none";
						else if (c === "(" && src[j - 1] === "$") parenDepth++;
						j++;
						continue;
					}
					if (c === "'") subMode = "single";
					else if (c === '"') subMode = "double";
					else if (c === "(") parenDepth++;
					else if (c === ")") parenDepth--;
					j++;
				}
				const inner = src.slice(i + 2, Math.max(i + 2, j - 1)).trim();
				if (inner) subshells.push(extractFromSegment(inner, depth + 1));
				out += " __SUBSHELL__ ";
				i = j;
				continue;
			}
			if (ch === "`") {
				let j = i + 1;
				while (j < src.length && src[j] !== "`") j += src[j] === "\\" ? 2 : 1;
				const inner = src.slice(i + 1, j).trim();
				if (inner) subshells.push(extractFromSegment(inner, depth + 1));
				out += " __SUBSHELL__ ";
				i = j + 1;
				continue;
			}
			if (mode === "double") {
				if (ch === '"') { mode = "none"; out += "__DQ__"; }
				i++;
				continue;
			}
			if (ch === "'") { mode = "single"; i++; continue; }
			if (ch === '"') { mode = "double"; i++; continue; }
			out += ch;
			i++;
		}
		return out;
	}

	const unquotedCommand = extractFromSegment(command, 0);
	return { unquotedCommand, subshells, allExecutableSegments: [unquotedCommand, ...subshells] };
}

export function isReadOnlyBashCommand(unquotedSegment: string): boolean {
	const strippedSafeRedirects = unquotedSegment.replace(/\b\d*>&\d+\b/g, "").replace(/\b\d*>+\s*\/dev\/null\b/g, "");
	if (/>/.test(strippedSafeRedirects)) return false;
	if (/\bsed\b[^;|&]*\s-[a-zA-Z]*i\b/.test(unquotedSegment)) return false;
	if (/\b(?:tee|rm|mv|cp|chmod|chown|touch|mkdir|rmdir|ln|dd|truncate|patch|install)\b/.test(unquotedSegment)) return false;
	if (/\b(?:python3?|node|perl|ruby)\s+-(?:c|e)\b/.test(unquotedSegment)) return false;

	const parts = unquotedSegment.split(/\|\||&&|[|;\n]/).map((s) => s.trim()).filter(Boolean);
	if (parts.length === 0) return true;

	for (const part of parts) {
		const tokens = part.split(/\s+/).filter((t) => !/^[A-Za-z_][A-Za-z0-9_]*=/.test(t));
		if (tokens.length === 0) continue;
		const cmd = path.basename(tokens[0]);
		if (cmd === "__SUBSHELL__" || READ_ONLY_COMMANDS.has(cmd)) continue;
		if (cmd === "git") {
			if (["status", "diff", "log", "show", "branch", "rev-parse", "ls-files", "remote"].includes(tokens[1] ?? "")) continue;
			return false;
		}
		if (cmd === "python" || cmd === "python3") {
			if (tokens.includes("--help") || tokens.includes("--version")) continue;
			let idx = 1;
			let isModuleMode = false;
			while (idx < tokens.length && tokens[idx].startsWith("-")) {
				if (tokens[idx] === "-m") { isModuleMode = true; idx++; break; }
				idx++;
			}
			const targetArg = tokens[idx] ?? "";
			if (isModuleMode && ["pytest", "unittest", "py_compile", "json.tool"].includes(targetArg)) continue;
			if (ALLOWED_READONLY_PY_SCRIPTS.some((s) => targetArg.endsWith(s))) continue;
			return false;
		}
		return false;
	}
	return true;
}

export function checkPortabilityViolation(content: string, cwd: string): { violated: boolean; matched?: string } {
	if (!content) return { violated: false };
	const homeDir = os.homedir();
	const patterns: RegExp[] = [
		new RegExp(homeDir.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
		new RegExp(cwd.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i"),
		/\bfile:\/\/\/(?:home|Users|root|var|tmp|opt)\/[^\s)"'`>]+/i,
		/(?:^|[\s"'`=(])\/(?:home|Users)\/[a-zA-Z0-9._-]+\/[^\s)"'`>]+/,
	];
	for (const pat of patterns) {
		const m = pat.exec(content);
		if (m) return { violated: true, matched: m[0].trim() };
	}
	return { violated: false };
}

export function resolveRealTarget(rawPath: string, cwd: string): string {
	const expanded = rawPath.startsWith("~/")
		? path.join(os.homedir(), rawPath.slice(2))
		: rawPath === "~" ? os.homedir() : rawPath;
	const abs = path.resolve(cwd, expanded);
	try {
		return fs.realpathSync(abs);
	} catch {
		try {
			return path.join(fs.realpathSync(path.dirname(abs)), path.basename(abs));
		} catch {
			return abs;
		}
	}
}

export function isWithinDir(target: string, baseDir: string): boolean {
	let realBase = path.resolve(baseDir);
	try { realBase = fs.realpathSync(baseDir); } catch {}
	const rel = path.relative(realBase, target);
	return rel === "" || (!rel.startsWith("..") && !path.isAbsolute(rel));
}

export function extractPathsFromBash(unquotedCommand: string): string[] {
	const candidates = new Set<string>();
	const regex =
		/(?:^|\s|[=><])((?:\/[a-zA-Z0-9._-]+){1,}|~\/[a-zA-Z0-9._/-]+|\.\.\/[a-zA-Z0-9._/-]*|\.?\/?\.netark(?:\/[a-zA-Z0-9._/-]*)?|\.?\/?schemas(?:\/[a-zA-Z0-9._/-]*)?)/g;
	let match: RegExpExecArray | null;
	while ((match = regex.exec(unquotedCommand)) !== null) {
		const token = match[1].trim();
		if (!token || SAFE_SYSTEM_PREFIXES.some((p) => token === p || token.startsWith(`${p}/`))) continue;
		if (token.startsWith("//") || token.includes("://") || /^\/(?:usr\/)?(?:local\/)?s?bin\//.test(token)) continue;
		candidates.add(token);
	}
	return Array.from(candidates);
}

export function summarizeGuardAuditLog(auditFile: string): { statsText: string; recentEventsText: string } {
	let statsText = "  (目前尚無任何攔截事件紀錄)";
	let recentEventsText = "";
	if (!fs.existsSync(auditFile)) return { statsText, recentEventsText };
	try {
		const lines = fs.readFileSync(auditFile, "utf-8").split("\n").map((l) => l.trim()).filter(Boolean);
		const stats: Record<string, number> = {};
		const parsedEntries: any[] = [];
		for (const l of lines) {
			try {
				const item = JSON.parse(l);
				const code = item.rule_code || item.rule_id || "UNKNOWN";
				stats[code] = (stats[code] || 0) + 1;
				parsedEntries.push(item);
			} catch {}
		}
		if (parsedEntries.length > 0) {
			statsText = `  • 累計攔截事件: ${parsedEntries.length} 次\n` + Object.entries(stats).map(([k, v]) => `    - ${k}: ${v} 次`).join("\n");
			recentEventsText =
				"\n• 🕒 最近 5 筆攔截事件明細:\n" +
				parsedEntries.slice(-5).reverse().map((e) => `  - [${e.timestamp?.slice(11, 19) || ""}] [${e.rule_code || e.rule_id || "RULE"}] (${e.tool_name || "tool"}): ${e.reason?.slice(0, 100) || ""}`).join("\n");
		}
	} catch {}
	return { statsText, recentEventsText };
}
