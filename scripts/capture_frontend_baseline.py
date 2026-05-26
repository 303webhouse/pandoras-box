"""
Frontend baseline capture for the Pivot dashboard.

Drives a real Chrome instance via Playwright, captures a Chrome DevTools-format
trace (loadable in DevTools Performance panel) plus a JSON metrics block, and
appends a section to docs/strategy-reviews/perf-baseline-2026-05-24.txt.

Use this before each phase ships, and again after each phase ships, with
distinct --label values. The same script handles all captures so the numbers
are apples-to-apples.

Usage:
    python scripts/capture_frontend_baseline.py
    python scripts/capture_frontend_baseline.py --label phase1-post
    python scripts/capture_frontend_baseline.py --url http://localhost:8000/ --label local
    python scripts/capture_frontend_baseline.py --headed   (debug, visible browser)

Prereqs:
    pip install playwright
    Playwright uses the local Chrome install via channel="chrome", so the
    bundled-Chromium download is NOT required.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Playwright not installed. Run:", file=sys.stderr)
    print("    pip install playwright", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs" / "strategy-reviews"

DEFAULT_URL = "https://pandoras-box-production.up.railway.app/app"
DEFAULT_BASELINE_FILE = "perf-baseline-2026-05-24.txt"


# Web-vitals-style PerformanceObserver. Installed via add_init_script before
# the page navigates so we catch DCL/FCP/LCP/longtasks/CLS from frame zero.
PERF_OBSERVER_JS = r"""
(() => {
  window.__perfMetrics = {
    longTasks: [],
    lcp: null,
    fcp: null,
    dcl: null,
    loadEvent: null,
    cls: 0,
  };

  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        window.__perfMetrics.longTasks.push({
          startTime: entry.startTime,
          duration: entry.duration,
        });
      }
    }).observe({ type: 'longtask', buffered: true });
  } catch (e) {}

  try {
    new PerformanceObserver((list) => {
      const entries = list.getEntries();
      if (entries.length) {
        window.__perfMetrics.lcp = entries[entries.length - 1].startTime;
      }
    }).observe({ type: 'largest-contentful-paint', buffered: true });
  } catch (e) {}

  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.name === 'first-contentful-paint') {
          window.__perfMetrics.fcp = entry.startTime;
        }
      }
    }).observe({ type: 'paint', buffered: true });
  } catch (e) {}

  try {
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (!entry.hadRecentInput) {
          window.__perfMetrics.cls += entry.value;
        }
      }
    }).observe({ type: 'layout-shift', buffered: true });
  } catch (e) {}

  window.addEventListener('DOMContentLoaded', () => {
    window.__perfMetrics.dcl = performance.now();
  });
  window.addEventListener('load', () => {
    window.__perfMetrics.loadEvent = performance.now();
  });
})();
"""


METRICS_COLLECT_JS = r"""
(() => {
  const m = window.__perfMetrics || {};
  const fcp = m.fcp || 0;
  const tasks = m.longTasks || [];
  const tasksAfterFcp = tasks.filter(t => t.startTime >= fcp);
  // TBT = sum of (longtask.duration - 50ms) for tasks after FCP
  const tbt = tasksAfterFcp.reduce((acc, t) => acc + Math.max(0, t.duration - 50), 0);

  let nav = null;
  try { nav = performance.getEntriesByType('navigation')[0] || null; } catch (e) {}

  const resources = performance.getEntriesByType('resource');
  const transferTotal = resources.reduce((a, r) => a + (r.transferSize || 0), 0);
  const decodedTotal = resources.reduce((a, r) => a + (r.decodedBodySize || 0), 0);

  // Group resources by initiatorType for a coarse profile
  const byType = {};
  for (const r of resources) {
    const t = r.initiatorType || 'other';
    if (!byType[t]) byType[t] = { count: 0, transfer: 0 };
    byType[t].count += 1;
    byType[t].transfer += (r.transferSize || 0);
  }

  return {
    fcp_ms: m.fcp,
    lcp_ms: m.lcp,
    dcl_ms: m.dcl,
    load_event_ms: m.loadEvent,
    cls: m.cls,
    long_tasks_count: tasks.length,
    long_tasks_total_duration_ms: tasks.reduce((a, t) => a + t.duration, 0),
    total_blocking_time_ms: tbt,
    nav_request_start_ms: nav ? nav.requestStart : null,
    nav_response_end_ms: nav ? nav.responseEnd : null,
    nav_dom_interactive_ms: nav ? nav.domInteractive : null,
    nav_dom_complete_ms: nav ? nav.domComplete : null,
    resource_count: resources.length,
    resource_transfer_bytes: transferTotal,
    resource_decoded_bytes: decodedTotal,
    resource_by_initiator: byType,
  };
})()
"""


# Categories matching what Chrome DevTools Performance panel records.
# Includes screenshots so the saved trace renders the filmstrip.
DEVTOOLS_TRACE_CATEGORIES = [
    "devtools.timeline",
    "v8.execute",
    "disabled-by-default-devtools.timeline",
    "disabled-by-default-devtools.timeline.frame",
    "toplevel",
    "blink.console",
    "blink.user_timing",
    "latencyInfo",
    "disabled-by-default-v8.cpu_profiler",
    "disabled-by-default-devtools.timeline.stack",
    "disabled-by-default-devtools.screenshot",
    "loading",
    "blink.net",
]


def capture(url: str, label: str, headless: bool, idle_seconds: int):
    trace_path = DOCS_DIR / f"perf-trace-{label}.json"
    baseline_path = DOCS_DIR / DEFAULT_BASELINE_FILE

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        # channel="chrome" uses the system Chrome install — no bundled-Chromium download required.
        browser = p.chromium.launch(channel="chrome", headless=headless)
        context = browser.new_context()
        context.add_init_script(PERF_OBSERVER_JS)
        page = context.new_page()

        # Surface anything that breaks during page load
        console_errors = []
        page.on("pageerror", lambda exc: console_errors.append(f"pageerror: {exc}"))

        def _on_console(msg):
            if msg.type == "error":
                try:
                    console_errors.append(f"console.error: {msg.text}")
                except Exception:
                    pass

        page.on("console", _on_console)

        # Start Chrome DevTools tracing via CDP — produces a JSON loadable in
        # DevTools Performance panel (or chrome://tracing).
        client = context.new_cdp_session(page)
        trace_events: list = []
        tracing_done = {"v": False}

        def _on_data(params):
            value = params.get("value") or []
            trace_events.extend(value)

        def _on_complete(_params):
            tracing_done["v"] = True

        client.on("Tracing.dataCollected", _on_data)
        client.on("Tracing.tracingComplete", _on_complete)

        client.send(
            "Tracing.start",
            {
                "transferMode": "ReportEvents",
                "traceConfig": {
                    "recordMode": "recordAsMuchAsPossible",
                    "includedCategories": DEVTOOLS_TRACE_CATEGORIES,
                },
            },
        )

        try:
            page.goto(url, wait_until="networkidle", timeout=45000)
        except Exception as e:
            # Pollers may keep the network busy past networkidle — keep going.
            console_errors.append(f"goto: {e}")

        # Let it idle so post-load work shows up in the trace
        page.wait_for_timeout(idle_seconds * 1000)

        metrics = page.evaluate(METRICS_COLLECT_JS)

        try:
            visible_text_len = page.evaluate("document.body.innerText.length")
            title = page.title()
            current_url = page.url
        except Exception:
            visible_text_len = None
            title = None
            current_url = url

        # Stop tracing and wait for the final tracingComplete event
        client.send("Tracing.end")
        deadline = 20_000  # 20s safety margin
        waited = 0
        while not tracing_done["v"] and waited < deadline:
            page.wait_for_timeout(200)
            waited += 200

        browser.close()

    # Write the trace JSON in DevTools-loadable shape
    with trace_path.open("w", encoding="utf-8") as f:
        json.dump({"traceEvents": trace_events}, f)

    metrics["url"] = url
    metrics["final_url"] = current_url
    metrics["page_title"] = title
    metrics["label"] = label
    metrics["captured_at_utc"] = datetime.now(timezone.utc).isoformat()
    metrics["visible_text_chars"] = visible_text_len
    metrics["console_errors"] = console_errors
    metrics["trace_file"] = str(trace_path.relative_to(REPO_ROOT)).replace("\\", "/")
    metrics["trace_event_count"] = len(trace_events)

    return metrics, trace_path, baseline_path


def append_baseline(metrics: dict, baseline_path: Path) -> None:
    lines = []
    lines.append("")
    lines.append("=" * 80)
    lines.append(f"FRONTEND BASELINE (Playwright capture, label={metrics['label']})")
    lines.append("=" * 80)
    lines.append(f"Captured: {metrics['captured_at_utc']}")
    lines.append(f"URL:      {metrics['url']}")
    if metrics.get("final_url") and metrics["final_url"] != metrics["url"]:
        lines.append(f"Final URL: {metrics['final_url']}  (redirected)")
    if metrics.get("page_title"):
        lines.append(f"Title:    {metrics['page_title']}")
    lines.append(f"Trace:    {metrics['trace_file']}  ({metrics['trace_event_count']} events)")
    lines.append("          (open in Chrome DevTools → Performance panel → Load profile)")
    lines.append("")
    lines.append("Web vitals + paint metrics:")
    for key in (
        "fcp_ms", "lcp_ms", "dcl_ms", "load_event_ms", "cls",
        "long_tasks_count", "long_tasks_total_duration_ms", "total_blocking_time_ms",
    ):
        lines.append(f"  {key:<35} {metrics.get(key)}")
    lines.append("")
    lines.append("Navigation timing:")
    for key in (
        "nav_request_start_ms", "nav_response_end_ms",
        "nav_dom_interactive_ms", "nav_dom_complete_ms",
    ):
        lines.append(f"  {key:<35} {metrics.get(key)}")
    lines.append("")
    lines.append("Resource summary:")
    for key in ("resource_count", "resource_transfer_bytes", "resource_decoded_bytes"):
        lines.append(f"  {key:<35} {metrics.get(key)}")
    by_init = metrics.get("resource_by_initiator") or {}
    if by_init:
        lines.append("  by initiator:")
        for k in sorted(by_init):
            v = by_init[k]
            lines.append(f"    {k:<20} count={v.get('count')}  transfer_bytes={v.get('transfer')}")
    lines.append("")
    lines.append(f"visible_text_chars: {metrics.get('visible_text_chars')}")
    errs = metrics.get("console_errors") or []
    if errs:
        lines.append(f"console_errors ({len(errs)}):")
        for e in errs[:20]:
            lines.append(f"  - {e}")
        if len(errs) > 20:
            lines.append(f"  ... and {len(errs) - 20} more")
    else:
        lines.append("console_errors: none")
    lines.append("")

    with baseline_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Dashboard URL to capture")
    parser.add_argument("--label", default="baseline-2026-05-24",
                        help="Label appended to trace filename and section heading")
    parser.add_argument("--headed", action="store_true",
                        help="Show the browser window (debug). Default: headless.")
    parser.add_argument("--idle-seconds", type=int, default=10,
                        help="Seconds to let the page idle after networkidle, so pollers fire.")
    args = parser.parse_args()

    metrics, trace_path, baseline_path = capture(
        args.url, args.label, headless=not args.headed, idle_seconds=args.idle_seconds,
    )

    print(json.dumps(metrics, indent=2, default=str))
    print(f"\nTrace written:    {trace_path}")
    append_baseline(metrics, baseline_path)
    print(f"Baseline appended: {baseline_path}")

    # Early-warning flags
    warns = []
    if metrics.get("visible_text_chars") is not None and metrics["visible_text_chars"] < 200:
        warns.append("Dashboard renders <200 chars of visible text — possible auth wall or empty render.")
    if metrics.get("fcp_ms") is None:
        warns.append("No FCP captured — page may not have rendered.")
    if not metrics.get("trace_event_count"):
        warns.append("Trace has zero events — CDP Tracing.start may have failed.")
    for w in warns:
        print(f"[WARN] {w}", file=sys.stderr)

    if warns:
        sys.exit(2)


if __name__ == "__main__":
    main()
