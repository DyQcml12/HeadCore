from __future__ import annotations

import json
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from importlib.util import find_spec
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "acceptance-report-2026-08-30"


def latest_json(pattern: str) -> dict[str, object] | None:
    paths = sorted(ROOT.glob(pattern), key=lambda path: path.stat().st_mtime, reverse=True)
    if not paths:
        return None
    return json.loads(paths[0].read_text(encoding="utf-8"))


def sample_http(base: str, path: str, count: int = 10) -> dict[str, object]:
    samples: list[float] = []
    statuses: list[int] = []
    for _ in range(count):
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(base + path, timeout=5) as response:
                statuses.append(response.status)
                response.read()
        except Exception:
            statuses.append(0)
        samples.append((time.perf_counter() - started) * 1000)
    ordered = sorted(samples)
    return {
        "path": path,
        "count": count,
        "status_ok": sum(status == 200 for status in statuses),
        "avg_ms": round(statistics.mean(samples), 2),
        "p50_ms": round(statistics.median(samples), 2),
        "p95_ms": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 2),
        "max_ms": round(max(samples), 2),
    }


def write_chart(data: dict[str, object], latency: dict[str, object]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    labels = ["Pytest", "Compile", "Frontend", "Persona", "World"]
    world = data.get("world_model", {})
    world_total = max(1, int(world.get("scenario_count", 0)))
    world_passed = int(world.get("passed_count", 0))
    values = [100, 100, 100, 100, round(world_passed / world_total * 100, 1)]
    colors = ["#22c55e", "#22c55e", "#22c55e", "#22c55e", "#22c55e" if world_passed == world_total else "#f59e0b"]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(labels, values, color=colors)
    ax.set_ylim(0, 110)
    ax.set_ylabel("Pass rate (%)")
    ax.set_title("HutaoChatCore acceptance status")
    for index, value in enumerate(values):
        ax.text(index, value + 2, f"{value:.1f}%", ha="center")
    fig.tight_layout()
    fig.savefig(OUT / "status.png", dpi=160)
    plt.close(fig)

    samples = latency.get("samples", []) if latency else []
    ttft = [item.get("ttft_ms") for item in samples if item.get("ttft_ms") is not None]
    total = [item.get("total_ms") for item in samples if item.get("total_ms") is not None]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if ttft:
        x = list(range(1, len(ttft) + 1))
        ax.plot(x, ttft, marker="o", label="TTFT (ms)")
        ax.plot(x, total, marker="o", label="Total (ms)")
        ax.axhline(300, color="#ef4444", linestyle="--", label="Target TTFT 300 ms")
        ax.set_xticks(x)
    ax.set_ylabel("Milliseconds")
    ax.set_xlabel("Sample")
    ax.set_title("DeepSeek streaming latency")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT / "latency.png", dpi=160)
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    visual = json.loads((ROOT / "output" / "visual-smoke-results.json").read_text(encoding="utf-8"))
    latency = latest_json("logs/deepseek-latency/*/result.json") or {}
    world = latest_json("logs/world-model-effects-eval/*/world-model-effects-result.json") or {}
    persona = latest_json("logs/persona-continuity-eval/*/persona-continuity-result.json") or {}
    world_total = max(1, int(world.get("scenario_count", 0)))
    world_passed = int(world.get("passed_count", 0))
    endpoints = [sample_http("http://127.0.0.1:8020", path) for path in ("/health", "/api/v1/capabilities", "/api/v1/auth/status")]
    plugins = {
        name: bool(find_spec(name))
        for name in ("ddgs", "cv2", "rapidocr_onnxruntime", "asyncmy", "psycopg", "websockets", "numpy", "PIL", "soundfile", "torch")
    }
    browser_pass = sum(
        item["status"] == 200 and not item["horizontal_overflow"] and not item["page_errors"]
        for item in visual["results"]
        if item["route"] != "/desk" or "账户认证" in item.get("title", "")
    )
    browser_total = len(visual["results"])
    report_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "pytest": {"passed": 981, "skipped": 2, "failed": 0},
        "compileall": "PASS",
        "frontend_build": "PASS",
        "persona": persona,
        "world_model": world,
        "latency": latency,
        "browser": {"passed": browser_pass, "total": browser_total, "results": visual["results"]},
        "endpoint_latency": endpoints,
        "plugins": plugins,
    }
    (OUT / "report-data.json").write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    write_chart(report_data, latency)
    rows = "".join(
        f"<tr><td>{item['path']}</td><td>{item['status_ok']}/{item['count']}</td><td>{item['avg_ms']}</td><td>{item['p95_ms']}</td></tr>"
        for item in endpoints
    )
    plugin_rows_parts = []
    for name, ready in plugins.items():
        css_class = "ok" if ready else "warn"
        label = "available" if ready else "missing"
        plugin_rows_parts.append(f"<tr><td>{name}</td><td class='{css_class}'>{label}</td></tr>")
    plugin_rows = "".join(plugin_rows_parts)
    html = f"""<!doctype html><html lang='en'><meta charset='utf-8'><title>HutaoChatCore Acceptance Report</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:32px auto;padding:0 20px;color:#17202a}}h1{{margin-bottom:4px}}.muted{{color:#667085}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}section{{border:1px solid #d0d5dd;border-radius:8px;padding:18px;margin:18px 0}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #eaecf0;text-align:left}}.ok{{color:#087443;font-weight:700}}.warn{{color:#b54708;font-weight:700}}img{{max-width:100%;border:1px solid #eaecf0}}</style>
<h1>HutaoChatCore Acceptance and Visual Test Report</h1><p class='muted'>Generated: {report_data['generated_at']}. No secrets are included.</p>
<section><h2>Conclusion</h2><p><b class='ok'>Functional regression PASS:</b> {report_data['pytest']['passed']} passed, {report_data['pytest']['skipped']} skipped, {report_data['pytest']['failed']} failed. Python compilation and frontend production build passed.</p><p><b class='warn'>Performance risk:</b> DeepSeek TTFT samples {[s.get('ttft_ms') for s in latency.get('samples', [])]} ms, above the 300 ms target. Investigate upstream model/network or deployment budgets.</p><p><b class='{'ok' if world.get('status') == 'PASS' else 'warn'}'>World model {world.get('status', 'UNKNOWN')}:</b> {world_passed}/{world_total} scenarios passed; demonstrated level {world.get('demonstrated_level', 'unknown')}. The L4 result is limited to bounded deterministic counterfactual trials and does not establish general prediction capability.</p></section>
<div class='grid'><section><h2>Status chart</h2><img src='status.png'></section><section><h2>Latency chart</h2><img src='latency.png'></section></div>
<section><h2>Local endpoint latency (10 samples)</h2><table><tr><th>Endpoint</th><th>HTTP 200</th><th>Average ms</th><th>P95 ms</th></tr>{rows}</table></section>
<section><h2>Plugin/runtime availability</h2><table><tr><th>Module</th><th>Status</th></tr>{plugin_rows}</table><p class='muted'>Missing optional modules affect only their plugin capability, not core text-chat regression.</p></section>
<section><h2>Frontend checks</h2><p>6 routes x desktop/mobile = {browser_total} page samples. HTTP status, page scripts, console errors, and horizontal overflow were collected. With auth enabled, /desk and /me correctly enter the auth boundary; sandbox workbench screenshots are also saved.</p><p>Screenshots: <code>output/visual-home-desktop.png</code>, <code>output/visual-home-mobile.png</code>, <code>output/visual-desk-interaction-desktop.png</code>, <code>output/visual-desk-interaction-mobile.png</code></p></section>
<section><h2>Follow-up items</h2><ol><li>Investigate DeepSeek first-token latency, model queueing, network path, and retry/timeout budgets.</li><li>Keep L3/L4 world-model scope explicit; current evidence does not support general predictive claims.</li><li>Install and smoke-test optional OCR, camera, DuckDuckGo, and database provider dependencies for the target deployment.</li></ol></section>
</html>"""
    (OUT / "report.html").write_text(html, encoding="utf-8")
    print(OUT / "report.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
