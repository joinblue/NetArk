#!/usr/bin/env python3
"""Render NetArk 2x Retina PNGs and animated pre-write guard GIF using headless Chrome."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image
from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
ASSETS_DIR = HERE.parents[1] / "docs" / "assets"
CHROME_PATH = "/usr/bin/google-chrome"

TARGETS: Tuple[Tuple[str, str, int, int], ...] = (
    ("hero-architecture.html", "hero-architecture.png", 1200, 676),
    ("demo-prewrite-guard.html", "demo-prewrite-guard.png", 1200, 688),
    ("demo-token-compression.html", "demo-token-compression.png", 1200, 676),
    ("demo-dashboard-preview.html", "demo-dashboard-preview.png", 1200, 700),
)


def _assert_dom_qa(page: Page, name: str) -> None:
    metrics: Dict[str, object] = page.evaluate("""() => {
        const doc = document.documentElement;
        const nodes = Array.from(document.querySelectorAll('.title, .subtitle, .eyebrow, .badge, .code-box, .code-snip, .node-key, .kpi-val'));
        const empty = nodes.filter(el => el.innerText.trim().length === 0).length;
        const invisible = nodes.filter(el => {
            const st = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return parseFloat(st.opacity) <= 0 || r.width <= 0 || r.height <= 0;
        }).length;
        return {
            sw: doc.scrollWidth,
            cw: doc.clientWidth,
            sh: doc.scrollHeight,
            ch: doc.clientHeight,
            totalNodes: nodes.length,
            empty,
            invisible
        };
    }""")
    assert metrics["sw"] <= metrics["cw"], f"{name}: horizontal overflow {metrics['sw']} > {metrics['cw']}"
    assert metrics["sh"] <= metrics["ch"], f"{name}: vertical overflow {metrics['sh']} > {metrics['ch']}"
    assert metrics["totalNodes"] >= 4, f"{name}: insufficient text nodes {metrics['totalNodes']}"
    assert metrics["empty"] == 0, f"{name}: found empty text nodes"
    assert metrics["invisible"] == 0, f"{name}: found invisible text nodes"


def _render_prewrite_gif(page: Page, html_uri: str, out_gif: Path) -> None:
    frames: List[Image.Image] = []
    durations = [1000, 1300, 1500, 3800]
    page.set_viewport_size({"width": 1200, "height": 688})
    for step_idx in range(1, 5):
        page.goto(html_uri, wait_until="load")
        if step_idx < 4:
            page.evaluate(f"document.body.className = 'frame-{step_idx}'")
        png_bytes = page.screenshot(type="png")
        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        img_resized = img.resize((1200, 688), Image.Resampling.LANCZOS)
        frames.append(img_resized.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE))
    frames[0].save(
        out_gif,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


def render_all() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for old_svg in ASSETS_DIR.glob("*.svg"):
        old_svg.unlink()

    launch_kwargs = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"],
    }
    if Path(CHROME_PATH).is_file():
        launch_kwargs["executable_path"] = CHROME_PATH

    with sync_playwright() as pw:
        browser = pw.chromium.launch(**launch_kwargs)
        context = browser.new_context(viewport={"width": 1200, "height": 700}, device_scale_factor=2)
        page = context.new_page()
        for html_name, png_name, width, height in TARGETS:
            page.set_viewport_size({"width": width, "height": height})
            html_uri = (HERE / html_name).resolve().as_uri()
            page.goto(html_uri, wait_until="load")
            _assert_dom_qa(page, html_name)
            out_png = ASSETS_DIR / png_name
            page.screenshot(path=str(out_png), type="png")
            assert out_png.stat().st_size > 40_000, f"{png_name} unexpectedly small"

        gif_ctx = browser.new_context(viewport={"width": 1200, "height": 688}, device_scale_factor=1)
        gif_page = gif_ctx.new_page()
        out_gif = ASSETS_DIR / "demo-prewrite-guard.gif"
        _render_prewrite_gif(gif_page, (HERE / "demo-prewrite-guard.html").resolve().as_uri(), out_gif)
        assert out_gif.stat().st_size > 40_000, "demo-prewrite-guard.gif unexpectedly small"
        browser.close()
    print("Rendered 4 2x PNGs and animated demo-prewrite-guard.gif cleanly.")


if __name__ == "__main__":
    render_all()
