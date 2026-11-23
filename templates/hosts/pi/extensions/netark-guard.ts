/**
 * NetArk Unified Guard & Epistemic Bridge (netark-guard.ts)
 * Thin Pi Extension delegating hooks to `netark-mcp hook ... pi --cwd <cwd>`.
 */

import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

function resolveHookRunner(cwd: string): { cmd: string; prefixArgs: string[] } {
	const envBin = process.env.NETARK_MCP_BIN?.trim();
	if (envBin) return { cmd: envBin, prefixArgs: [] };
	for (const cfgPath of [path.join(cwd, ".pi", "mcp.json"), path.join(cwd, ".netark", "mcp.json")]) {
		if (!fs.existsSync(cfgPath)) continue;
		try {
			const cfg = JSON.parse(fs.readFileSync(cfgPath, "utf-8")) as { mcpServers?: { netark?: { command?: unknown } } };
			const cmd = cfg?.mcpServers?.netark?.command;
			if (typeof cmd === "string" && cmd.trim()) return { cmd: cmd.trim(), prefixArgs: [] };
		} catch {
			// Ignore malformed or unreadable mcp.json and try next candidate
			continue;
		}
	}
	const localScript = path.join(cwd, "scripts", "netark_mcp_server.py");
	if (fs.existsSync(localScript)) return { cmd: "python3", prefixArgs: [localScript] };
	return { cmd: "netark-mcp", prefixArgs: [] };
}

function runNetArkHook(
	cwd: string,
	modeFlag: string,
	payload: unknown,
	timeoutMs = 8000,
): { status: number; stdout: string; stderr: string } {
	const { cmd, prefixArgs } = resolveHookRunner(cwd);
	const args = ["hook", modeFlag, "pi", "--cwd", cwd];
	const opts = { cwd, input: JSON.stringify(payload), encoding: "utf-8" as const, timeout: timeoutMs };
	let res = spawnSync(cmd, [...prefixArgs, ...args], opts);
	const localScript = path.join(cwd, "scripts", "netark_mcp_server.py");
	if (res.error && !(cmd === "python3" && prefixArgs[0] === localScript) && fs.existsSync(localScript)) {
		res = spawnSync("python3", [localScript, ...args], opts);
	}
	return {
		status: typeof res.status === "number" ? res.status : res.error ? 1 : 0,
		stdout: String(res.stdout || ""),
		stderr: String(res.stderr || ""),
	};
}

const cachedTurn1ByCwd = new Map<string, string>();

function getTurn1Summary(cwd: string, forceRefresh = false): string {
	if (!forceRefresh && cachedTurn1ByCwd.has(cwd)) {
		return cachedTurn1ByCwd.get(cwd) ?? "";
	}
	const res = runNetArkHook(cwd, "--session-start-mode", { workspacePaths: [cwd] });
	if (res.status === 0) {
		const summary = res.stdout.trim();
		cachedTurn1ByCwd.set(cwd, summary);
		return summary;
	}
	return cachedTurn1ByCwd.get(cwd) ?? "";
}

const POST_HOOK_TOOLS = new Set(["write", "edit", "write_file", "edit_file", "Write", "Edit", "MultiEdit"]);

export default function (pi: ExtensionAPI): void {
	(globalThis as any).__fridayEpistemicBridge = {
		getSessionPinnedContextSummary: (_sessionKey: string, cwd: string, forceRefresh?: boolean) =>
			getTurn1Summary(cwd, Boolean(forceRefresh)) || null,
	};

	pi.on("session_start", async (_event, ctx) => {
		cachedTurn1ByCwd.delete(ctx.cwd);
	});

	pi.on("before_agent_start", async (event, ctx) => {
		const summary = getTurn1Summary(ctx.cwd);
		if (summary) return { systemPrompt: `${event.systemPrompt}\n${summary}` };
	});

	pi.on("user_bash", async (event, ctx) => {
		const res = runNetArkHook(ctx.cwd, "--hook-mode", {
			tool_name: "bash",
			tool_input: { command: event.command || "" },
		});
		if (res.status !== 0) {
			return {
				result: {
					output: (res.stderr || res.stdout || "Blocked by NetArk Enterprise Guard").trim(),
					exitCode: 126,
					cancelled: false,
					truncated: false,
				},
			};
		}
	});

	pi.on("tool_call", async (event, ctx) => {
		const res = runNetArkHook(ctx.cwd, "--hook-mode", {
			tool_name: event.toolName,
			tool_input: event.input ?? {},
		});
		if (res.status !== 0) {
			return {
				block: true,
				reason: (res.stderr || res.stdout || "Blocked by NetArk Enterprise Guard").trim(),
			};
		}
	});

	pi.on("tool_result", async (event, ctx) => {
		if (event.isError || !POST_HOOK_TOOLS.has(event.toolName)) return;
		const res = runNetArkHook(
			ctx.cwd,
			"--post-hook-mode",
			{ tool_name: event.toolName, tool_input: event.input ?? {} },
			15000,
		);
		const msg = (res.stderr || res.stdout).trim();
		if (msg) {
			return {
				content: [...(Array.isArray(event.content) ? event.content : []), { type: "text" as const, text: `\n${msg}` }],
			};
		}
	});

	pi.on("session_shutdown", async (_event, ctx) => {
		runNetArkHook(ctx.cwd, "--stop-mode", { workspacePaths: [ctx.cwd] }, 15000);
	});
}
