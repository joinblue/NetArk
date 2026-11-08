/**
 * NetArk Micro-Session Handover & Context Watermark Extension (session-handover.ts)
 * =================================================================================
 * Standalone modular plugin (zero intrusion into model-router.ts):
 *   1. Monitors single-session Context token usage (`50,000` soft / `80,000` hard watermark)
 *      via `before_agent_start` and injects a tail-end handover reminder without mutating
 *      `messages[0]` (preserving 100% Cloud Prefix KV Cache hit rate).
 *   2. Registers the `/handover` slash command backed by `.netark/prompts/handover.md`.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";

export const HANDOVER_SOFT_THRESHOLD = 50_000;
export const HANDOVER_HARD_THRESHOLD = 80_000;
export const HANDOVER_REMIND_STEP_TOKENS = 10_000;

export function buildHandoverMandateMessage(activeTokens: number): {
	level: "soft" | "hard" | null;
	message: string | null;
} {
	if (activeTokens >= HANDOVER_HARD_THRESHOLD) {
		const k = Math.round(activeTokens / 1000);
		return {
			level: "hard",
			message:
				`[NetArk Context Handover Gate | HARD WATERMARK: ${k}k >= 80k Tokens]\n` +
				"當前單次對話 Context 已跨越 80,000 Tokens 高水位線（長對話 KV Cache 邊際稅率已高於重開微對話）！\n" +
				"請於完成本輪當前原子動作後，**自動更新 `memory/episodic/HANDOVER.md` 之四大交接區塊（含精確檔案行號座標、已排除死路與下一步）**，並於回覆最末行輸出：\n" +
				`\`📦 [Handover Ready | Context: ${k}k] 已同步 HANDOVER.md 交接座標，建議開新對話零失憶接續。\` (繁體中文 zh-TW)`,
		};
	}
	if (activeTokens >= HANDOVER_SOFT_THRESHOLD) {
		const k = Math.round(activeTokens / 1000);
		return {
			level: "soft",
			message:
				`[NetArk Context Handover Hint | SOFT WATERMARK: ${k}k >= 50k Tokens]\n` +
				"當前對話 Context 已達 50,000 Tokens 經濟甜蜜點上限。若本輪剛好完成一個子任務或分片 (`stub_ready` / `verified`)，請順手更新 `memory/episodic/HANDOVER.md` 並在回覆末尾提示使用者可執行 `/handover` 或開啟新對話。",
		};
	}
	return { level: null, message: null };
}

export default function sessionHandoverExtension(pi: ExtensionAPI): void {
	let lastHandoverNoticeTokens = 0;
	let softNotifiedInSession = false;

	pi.on("session_start", async () => {
		lastHandoverNoticeTokens = 0;
		softNotifiedInSession = false;
	});

	pi.registerCommand("handover", {
		description: "将當前微對話進度、檔案行號座標與下一步寫入 memory/episodic/HANDOVER.md 無縫交接",
		handler: async (args, ctx) => {
			const promptPath = path.join(ctx.cwd, ".netark", "prompts", "handover.md");
			let contractText =
				"請立即將當前對話之 (1) Active Objective、(2) Modified & Stub Coordinates、(3) Key Decisions & Rejected Paths、(4) Immediate Next Step 更新至 `memory/episodic/HANDOVER.md`（總行數 <= 65 行）。";
			if (fs.existsSync(promptPath)) {
				const raw = fs.readFileSync(promptPath, "utf-8");
				contractText = raw.replace(/^---\n[\s\S]*?\n---\n/, "").trim();
			}
			const extraNote = args?.trim() ? `\n\n[使用者補充交接備註]: ${args.trim()}` : "";
			if (ctx.hasUI) {
				ctx.ui.notify("🔄 啟動 /handover 微對話無縫交接快照寫入...", "info");
			}
			pi.sendUserMessage(`${contractText}${extraNote}`);
		},
	});

	pi.on("before_agent_start", async (_event, ctx) => {
		const usage = ctx?.getContextUsage?.();
		const activeTokens = Number(usage?.tokens ?? 0);
		if (!Number.isFinite(activeTokens) || activeTokens < HANDOVER_SOFT_THRESHOLD) {
			return undefined;
		}

		if (activeTokens >= HANDOVER_HARD_THRESHOLD) {
			if (activeTokens - lastHandoverNoticeTokens < HANDOVER_REMIND_STEP_TOKENS) {
				return undefined;
			}
			lastHandoverNoticeTokens = activeTokens;
			const { message } = buildHandoverMandateMessage(activeTokens);
			if (!message) return undefined;
			return {
				message: {
					customType: "friday-handover-mandate",
					content: message,
					display: false,
				},
			};
		}

		if (!softNotifiedInSession) {
			softNotifiedInSession = true;
			lastHandoverNoticeTokens = activeTokens;
			const { message } = buildHandoverMandateMessage(activeTokens);
			if (!message) return undefined;
			return {
				message: {
					customType: "friday-handover-mandate",
					content: message,
					display: false,
				},
			};
		}

		return undefined;
	});
}
