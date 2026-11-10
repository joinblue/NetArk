/**
 * NetArk Workspace Boundary Guard & SEC-CMD-V1 Extension (Pillar 2 — Stage 3)
 * ===========================================================================
 * 1. Quote-Aware Shell Parser & Read-Only Bash Exemption (via `./guard-shell-parser.ts`).
 * 2. Unconditional Credential Protection (`SEC-CRED`): Protects `auth.json`, `.env*`, SSH keys.
 * 3. Brain & Schema Lock (`SEC-BRAIN` / `SEC-SCHEMA`): Prevents unauthorized mutation of `.netark/` and `schemas/`.
 * 4. Portability & Secret Guard (`SEC-PORTABILITY` / `SEC-PREWRITE-SECRET`): Blocks absolute paths and plaintext secrets.
 */

import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { type ExtensionAPI, type ExtensionContext, getAgentDir } from "@earendil-works/pi-coding-agent";
import {
	DESTRUCTIVE_BASH_PATTERNS, FILE_TOOLS, PREWRITE_SECRET_PATTERNS, READ_ONLY_COMMANDS,
	SAFE_SYSTEM_PREFIXES, SECRET_FILE_PATTERNS, checkPortabilityViolation, extractPathsFromBash,
	formatRemediation, isReadOnlyBashCommand, isWithinDir, parseShellCommandQuoteAware,
	resolveRealTarget, summarizeGuardAuditLog,
} from "./guard-shell-parser.ts";

export {
	DESTRUCTIVE_BASH_PATTERNS, FILE_TOOLS, PREWRITE_SECRET_PATTERNS, READ_ONLY_COMMANDS,
	SAFE_SYSTEM_PREFIXES, SECRET_FILE_PATTERNS, checkPortabilityViolation, extractPathsFromBash,
	formatRemediation, isReadOnlyBashCommand, isWithinDir, parseShellCommandQuoteAware, resolveRealTarget,
};

export default function (pi: ExtensionAPI) {
	const sessionTrustedDirs = new Set<string>();

	async function verifyPathAccess(
		rawPath: string,
		toolName: string,
		operationDesc: string,
		ctx: ExtensionContext,
		isReadOnlyBash = false,
	): Promise<{ allowed: boolean; reason?: string }> {
		const target = resolveRealTarget(rawPath, ctx.cwd);
		const agentDir = getAgentDir();
		const schemasDir = path.join(ctx.cwd, "schemas");

		if (SECRET_FILE_PATTERNS.some((p) => p.test(target) || p.test(rawPath))) {
			return {
				allowed: false,
				reason: formatRemediation("SEC-CRED", `嚴格禁止存取機密憑證或金鑰檔案: ${rawPath}`, "憑證由 pi 執行期自動載入。若需引導使用者設定金鑰，請提示使用者執行 `/mode` 或 `/login`，切勿直接讀取 auth.json 或 .env。"),
			};
		}

		const isReadOnlyOperation =
			toolName === "read" || toolName === "ls" || toolName === "find" || toolName === "grep" || (toolName === "bash" && isReadOnlyBash);

		if (isWithinDir(target, schemasDir)) {
			if (isReadOnlyOperation) return { allowed: true };
			if (!ctx.hasUI) {
				return {
					allowed: false,
					reason: formatRemediation("SEC-SCHEMA", `Schema 防改鎖：禁止自動修改驗證器或契約規則目錄 -> ${target}`, "禁止透過修改 schemas/ 繞過驗證規則。請根據驗證器輸出的錯誤訊息，修正 memory/ 下的目標文件使其符合 Schema 規範。"),
				};
			}
			const optAllowSchema = "✅ 允許本次修改 schemas/ 驗證規則 (Allow once)";
			const optDenySchema = "❌ 拒絕修改 schemas/ 驗證規則 (Deny & Block)";
			const schemaChoice = await ctx.ui.select(
				["🔒 [NetArk Schema Lock | SEC-SCHEMA] 偵測到針對 schemas/ 決定性驗證器的修改請求！", `  • 觸發工具與動作: [${toolName}] ${operationDesc}`, `  • 目標解析路徑: ${target}`, "\n是否授權修改 Schema 驗證器？"].join("\n"),
				[optAllowSchema, optDenySchema],
			);
			if (schemaChoice === optAllowSchema) {
				ctx.ui.notify(`已單次授權修改 Schema 檔案: ${target}`, "info");
				return { allowed: true };
			}
			return {
				allowed: false,
				reason: formatRemediation("SEC-SCHEMA", `使用者拒絕了對 schemas/ 目錄 (${target}) 的修改請求。`, "請保持 schemas/ 驗證規則不變，改為修正目標檔案內容以通過驗證。"),
			};
		}

		if (isWithinDir(target, agentDir)) {
			if (isReadOnlyOperation) return { allowed: true };
			if (!ctx.hasUI) {
				return {
					allowed: false,
					reason: formatRemediation("SEC-BRAIN", `大腦核心保護：禁止自動修改或寫入 .netark 大腦設定與擴充檔 -> ${target}`, "子代理與非互動模式嚴禁修改 .netark/。請僅使用唯讀工具 (read/grep) 檢視設定，或由使用者透過 `/mode` 指令變更配置。"),
				};
			}
			const optAllowBrain = "✅ 允許本次修改 .netark 大腦設定 (Allow once)";
			const optDenyBrain = "❌ 拒絕修改大腦設定 (Deny & Block)";
			const brainChoice = await ctx.ui.select(
				["🧠 [NetArk Brain Core Guard | SEC-BRAIN] 偵測到針對 .netark 大腦核心目錄的修改或指令請求！", `  • 大腦核心目錄: ${agentDir}`, `  • 觸發工具與動作: [${toolName}] ${operationDesc}`, `  • 目標解析路徑: ${target}`, "\n是否授權修改 NetArk 大腦核心檔案？"].join("\n"),
				[optAllowBrain, optDenyBrain],
			);
			if (brainChoice === optAllowBrain) {
				ctx.ui.notify(`已單次授權修改大腦檔案: ${target}`, "info");
				return { allowed: true };
			}
			return {
				allowed: false,
				reason: formatRemediation("SEC-BRAIN", `使用者拒絕了對 .netark 大腦核心目錄 (${target}) 的修改請求。`, "請勿直接改寫 .netark/ 核心檔案；若需切換模型請提示使用者使用 `/mode`。"),
			};
		}

		if (isWithinDir(target, ctx.cwd)) return { allowed: true };
		for (const trusted of sessionTrustedDirs) {
			if (isWithinDir(target, trusted)) return { allowed: true };
		}

		if (!ctx.hasUI) {
			return {
				allowed: false,
				reason: formatRemediation("BOUNDARY", `越界攔截：非互動/子代理模式禁止存取專案工作區 (${ctx.cwd}) 以外之路徑 -> ${target}`, `請將所有檔案讀寫與檢索限制於專案工作區 (${ctx.cwd}) 內部之相對路徑。`),
			};
		}

		const targetDir = path.dirname(target);
		const optOnce = "✅ 允許本次操作 (Allow once)";
		const optSession = `🔓 本次 Session 信任此目錄 (${targetDir})`;
		const optDeny = "❌ 拒絕並攔截 (Deny & Block)";
		const choice = await ctx.ui.select(
			["🛡️ [NetArk Workspace Boundary Guard] 偵測到跨出專案工作區的存取請求！", `  • 目前專案鎖定範圍 (cwd): ${ctx.cwd}`, `  • 觸發工具與動作: [${toolName}] ${operationDesc}`, `  • 目標解析路徑: ${target}`, "\n是否授權 NetArk 執行此越界操作？"].join("\n"),
			[optOnce, optSession, optDeny],
		);
		if (choice === optOnce) {
			ctx.ui.notify(`已單次授權存取: ${target}`, "info");
			return { allowed: true };
		}
		if (choice === optSession) {
			sessionTrustedDirs.add(targetDir);
			ctx.ui.notify(`已將目錄加入本次 Session 信任清單: ${targetDir}`, "info");
			return { allowed: true };
		}
		return {
			allowed: false,
			reason: formatRemediation("BOUNDARY", `使用者拒絕了對專案工作區外部路徑 (${target}) 的存取請求。`, `請改用專案工作區 (${ctx.cwd}) 內的相對路徑檔案完成任務。`),
		};
	}

	pi.on("session_start", async (_event, ctx) => {
		if (ctx.hasUI) ctx.ui.setStatus("friday-guard", `🛡️ Lock:${path.basename(ctx.cwd)}`);
	});

	function recordGuardAuditEvent(cwd: string, ruleCode: string, toolName: string, reason: string): void {
		try {
			const auditDir = path.join(cwd, ".netark", "audit");
			if (!fs.existsSync(auditDir)) fs.mkdirSync(auditDir, { recursive: true });
			const auditLogPath = path.join(auditDir, "soc2_audit.jsonl");
			const entry = { timestamp: new Date().toISOString(), event: "BLOCK", rule_code: ruleCode, tool_name: toolName, reason: reason.replace(/\n+/g, " ").slice(0, 300) };
			fs.appendFileSync(auditLogPath, JSON.stringify(entry) + "\n", { encoding: "utf-8" });
		} catch {}
	}

	function blockTool(cwd: string, toolName: string, reason: string, defaultCode = "SEC-WORKSPACE-GUARD"): { block: true; reason: string } {
		const codeMatch = reason.match(/\[(SEC-[A-Z0-9_-]+|SYS-[A-Z0-9_-]+)\]/);
		recordGuardAuditEvent(cwd, codeMatch ? codeMatch[1] : defaultCode, toolName, reason);
		return { block: true, reason };
	}

	pi.on("user_bash", async (event, ctx) => {
		const command = event.command || "";
		const parsed = parseShellCommandQuoteAware(command);
		for (const seg of parsed.allExecutableSegments) {
			for (const rule of DESTRUCTIVE_BASH_PATTERNS) {
				if (rule.pattern.test(seg)) {
					const reason = formatRemediation(rule.id, `已攔截高風險指令 (${rule.desc}):\n  ${command}`, rule.remediation);
					recordGuardAuditEvent(ctx.cwd, rule.id, "bash", reason);
					return { result: { output: reason, exitCode: 126, cancelled: false, truncated: false } };
				}
			}
		}
		return undefined;
	});

	pi.on("tool_call", async (event, ctx) => {
		const toolName = event.toolName;

		if (FILE_TOOLS.has(toolName)) {
			const input = event.input as Record<string, unknown>;
			const rawPath = (input.path ?? input.file_path ?? ".") as string;
			const check = await verifyPathAccess(rawPath, toolName, `${toolName}(${rawPath})`, ctx, false);
			if (!check.allowed) return blockTool(ctx.cwd, toolName, check.reason ?? "Blocked by NetArk Workspace Guard");

			if (toolName === "write" || toolName === "edit") {
				const target = resolveRealTarget(rawPath, ctx.cwd);
				const relToCwd = path.relative(ctx.cwd, target).replace(/\\/g, "/");
				const allWrittenText = [
					typeof input.content === "string" ? input.content : "",
					typeof input.newText === "string" ? input.newText : "",
					typeof input.new_str === "string" ? input.new_str : "",
					typeof input.replacement === "string" ? input.replacement : "",
				].join("\n");

				if (process.env.NETARK_ALLOW_SECRET_FIXTURE !== "1") {
					for (const pat of PREWRITE_SECRET_PATTERNS) {
						if (pat.re.test(allWrittenText)) {
							return blockTool(
								ctx.cwd,
								toolName,
								formatRemediation(
									"SEC-PREWRITE-SECRET",
									`🛡️ [SEC-PREWRITE-SECRET] 寫檔防呆攔截：偵測到嘗試將明文金鑰或憑證 (${pat.type}) 直接寫入檔案 (${rawPath})！`,
									"嚴禁將 API Key 硬編碼寫入源碼或設定檔！請將程式碼改寫為 `os.environ.get('KEY_NAME')` 或 `process.env.KEY_NAME`，並提示人類使用者自行於 `.env` 設定（嚴禁 Agent 讀寫 `.env`）。",
								),
							);
						}
					}
				}

				const hasCodex = fs.existsSync(path.join(ctx.cwd, "memory", "codex"));
				if (hasCodex && target.toLowerCase().endsWith(".md") && !relToCwd.startsWith("..")) {
					const isUnmanagedRootMd =
						!relToCwd.includes("/") &&
						!["README.md", "README.zh-TW.md", "AGENTS.md", "COMMERCIAL-LICENSE.md", "CLA.md"].includes(relToCwd);
					if (isUnmanagedRootMd) {
						return blockTool(
							ctx.cwd,
							toolName,
							formatRemediation(
								"SEC-DOC-GOVERNANCE",
								`🛡️ [SEC-DOC-GOVERNANCE] 禁止在專案根目錄直接建立未納管的幽靈 Markdown 文件 (${rawPath}，根目錄僅允許 README.md 與 AGENTS.md)！`,
								"受治理架構規格請寫入 memory/specs/ 或 memory/private/specs/；臨時草稿請寫入 scratch/；Wiki 條目請寫入 memory/wiki/。",
							),
						);
					}
				}

				const isWiki = relToCwd.startsWith("memory/wiki/");
				const isGovernedDocOrConfig =
					!isWiki &&
					(relToCwd.startsWith("memory/") || relToCwd === "README.md" || relToCwd === "AGENTS.md" || relToCwd.startsWith(".netark/"));
				if (isGovernedDocOrConfig) {
					const portability = checkPortabilityViolation(allWrittenText, ctx.cwd);
					if (portability.violated) {
						return blockTool(
							ctx.cwd,
							toolName,
							formatRemediation(
								"SEC-PORTABILITY",
								`禁止將本機絕對路徑或個人家目錄路徑 ("${portability.matched}") 寫入受納管檔案 (${rawPath})！`,
								`為確保專案 100% 跨機可攜性 (Portable Brain)，請將路徑改寫為相對於專案根目錄的相對路徑（例如將 "${ctx.cwd}/foo/bar.md" 改為 "foo/bar.md" 或 "<WORKSPACE_ROOT>/foo/bar.md"）。`,
							),
						);
					}
				}
			}
			return undefined;
		}

		if (toolName === "bash") {
			const command = String((event.input as Record<string, unknown>).command ?? "");
			const parsed = parseShellCommandQuoteAware(command);
			for (const seg of parsed.allExecutableSegments) {
				for (const rule of DESTRUCTIVE_BASH_PATTERNS) {
					if (rule.pattern.test(seg)) {
						return blockTool(ctx.cwd, toolName, formatRemediation(rule.id, `攔截毀滅性指令 (${rule.desc}): ${command}`, rule.remediation));
					}
				}
				if (SECRET_FILE_PATTERNS.some((p) => p.test(seg))) {
					return blockTool(
						ctx.cwd,
						toolName,
						formatRemediation(
							"SEC-CRED",
							`禁止透過 bash 或子殼層存取機密金鑰與憑證檔 (auth.json / .env): ${command}`,
							"憑證由系統自動注入，請勿以 cat/grep/bash 探測 auth.json 或 .env；若需變更金鑰請引導使用者執行 `/mode`。",
						),
					);
				}
			}

			const displayCmd = command.length > 1000 ? `${command.slice(0, 1000)}...` : command;
			for (const seg of parsed.allExecutableSegments) {
				const segReadOnly = isReadOnlyBashCommand(seg);
				const extractedPaths = extractPathsFromBash(seg);
				if (!segReadOnly) {
					const quotedMatches = command.match(/(?:schemas\/|\.netark\/|memory\/LEDGER\.md)[^\s"'`)]*/g) ?? [];
					for (const qm of quotedMatches) {
						if (!extractedPaths.includes(qm)) extractedPaths.push(qm);
					}
				}
				for (const rawPath of extractedPaths) {
					const check = await verifyPathAccess(rawPath, "bash", displayCmd, ctx, segReadOnly);
					if (!check.allowed) return blockTool(ctx.cwd, toolName, check.reason ?? "Blocked by NetArk Workspace Guard");
				}
			}
		}

		const daemonPath = path.join(ctx.cwd, "scripts", "netark_guard_daemon.py");
		if (fs.existsSync(daemonPath)) {
			try {
				execFileSync("python3", [daemonPath, "--hook-mode", "pi", "--cwd", ctx.cwd], {
					input: JSON.stringify({ tool_name: toolName, tool_input: event.input }),
					env: { ...process.env, NETARK_ALLOW_CONTROL_PLANE: "1" },
					encoding: "utf-8",
					timeout: 5_000,
				});
			} catch (err: any) {
				if (err?.status === 2) {
					return blockTool(ctx.cwd, toolName, String(err?.stderr || err?.stdout || "Blocked by NetArk Enterprise Guard").trim(), "SEC-ENTERPRISE-GUARD");
				}
			}
		}
		return undefined;
	});

	pi.registerCommand("guard", {
		description: "檢視或重設 NetArk 工作區邊界防護狀態，或執行架構驗證與索引更新: /guard [reset|validate]",
		handler: async (args, ctx) => {
			const sub = args.trim().toLowerCase().split(/\s+/)[0] ?? "";
			if (sub === "reset") {
				sessionTrustedDirs.clear();
				ctx.ui.notify("🛡️ 已清空所有外部臨時授權目錄，嚴格鎖定回目前專案目錄。", "info");
				return;
			}
			if (sub === "validate") {
				const validatorPath = path.join(ctx.cwd, "schemas", "schema_validator.py");
				const mapScriptPath = path.join(ctx.cwd, "scripts", "auto_update_map.py");
				if (!fs.existsSync(validatorPath)) {
					ctx.ui.notify(`⚠️ 當前專案 (${ctx.cwd}) 尚未包含 schemas/schema_validator.py`, "warning");
					return;
				}
				try {
					const out1 = execFileSync("python3", [validatorPath, "--run-oracle"], { cwd: ctx.cwd, encoding: "utf-8", timeout: 30_000 });
					const out2 = fs.existsSync(mapScriptPath)
						? execFileSync("python3", [mapScriptPath], { cwd: ctx.cwd, encoding: "utf-8", timeout: 15_000 })
						: "";
					ctx.ui.notify(`✅ [NetArk Harness Validator 驗證通過]\n${out1.trim()}\n${out2.trim()}`, "info");
				} catch (err: any) {
					ctx.ui.notify(`❌ [NetArk Harness Validator 驗證失敗]\n${err?.stdout ?? ""}\n${err?.stderr ?? String(err)}`, "error");
				}
				return;
			}

			const auditFile = path.join(ctx.cwd, ".netark", "audit", "soc2_audit.jsonl");
			const { statsText, recentEventsText } = summarizeGuardAuditLog(auditFile);
			const trustedList =
				sessionTrustedDirs.size > 0
					? Array.from(sessionTrustedDirs).map((d) => `  - ${d}`).join("\n")
					: "  (無外部信任目錄 — 100% 鎖定於專案工作區內)";
			ctx.ui.notify(
				[
					`🛡️ NetArk Workspace Guard (Stage 3) 狀態`,
					`• 鎖定專案工作區 (ctx.cwd): ${ctx.cwd}`,
					`• NetArk 大腦目錄 (SEC-BRAIN): ${getAgentDir()}`,
					`• Schema 驗證鎖定 (SEC-SCHEMA): ${path.join(ctx.cwd, "schemas")}`,
					`• 啟用防護: 引號感知剖析 / 子殼層遞迴拆解 / 唯讀指令豁免 / SEC-PORTABILITY / 自癒處方籤`,
					`• 已臨時信任之外部目錄:\n${trustedList}`,
					`• 📊 歷史與本輪攔截統計（依規則分類計數）:\n${statsText}${recentEventsText}`,
					`• 子指令: /guard reset (重設外部目錄授權) | /guard validate (執行 schema_validator.py --run-oracle 全庫驗證)`,
				].join("\n"),
				"info",
			);
		},
	});
}
