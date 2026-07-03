"""Measure and compare the SvelteKit and Astro frontends.

Collects, for each app and route, the number of network requests, transferred
bytes per resource type, and whether Leaflet loads eagerly or only after the
map is toggled. Optionally times production builds and captures the visible
error state when the backend is down.

Both apps must be built beforehand (`npm run build`); the script starts and
stops the preview servers itself. Results are printed as markdown tables.

Usage:
    uv run python scripts/measure_frontends.py [--build-runs N] [--scenario up|down]
"""

import argparse
import io
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

REPO_ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class AppConfig:
    dir: Path
    port: int


APPS = {
    "sveltekit": AppConfig(REPO_ROOT / "apps" / "frontend", 4173),
    "astro": AppConfig(REPO_ROOT / "apps" / "astro-frontend", 4321),
}

ROUTES = ["/", "/places", "/health"]

SHOW_MAP_LABELS = ["Show map", "Pokaż mapę"]


@dataclass
class RouteMetrics:
    requests_total: int = 0
    bytes_by_type: dict[str, int] = field(default_factory=dict)
    requests_by_type: dict[str, int] = field(default_factory=dict)
    leaflet_before_toggle: bool = False
    leaflet_after_toggle: bool | None = None
    leaflet_extra_requests: int = 0
    leaflet_extra_bytes: int = 0
    map_visible_by_default: bool | None = None
    visible_text: str = ""


def npm_command() -> str:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm not found on PATH")
    return npm


def wait_for_server(port: int, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    url = f"http://localhost:{port}/"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except urllib.error.URLError, OSError:
            time.sleep(0.3)
    sys.exit(f"Preview server on port {port} did not become ready within {timeout_s}s")


def start_preview(app: str) -> subprocess.Popen:
    config = APPS[app]
    port = config.port
    proc = subprocess.Popen(
        [npm_command(), "run", "preview", "--", "--port", str(port)],
        cwd=config.dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for_server(port)
    return proc


def stop_preview(proc: subprocess.Popen) -> None:
    # npm spawns the actual server as a child process, so kill the whole tree.
    subprocess.run(
        ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def measure_route(page: Page, base_url: str, route: str, capture_text: bool) -> RouteMetrics:
    metrics = RouteMetrics()
    responses: list[tuple[str, str, int]] = []

    def on_response(response) -> None:
        try:
            size = len(response.body())
        except Exception:
            size = 0
        responses.append((response.request.resource_type, response.url, size))

    page.on("response", on_response)
    page.goto(f"{base_url}{route}", wait_until="networkidle")
    page.wait_for_timeout(1000)

    for resource_type, _url, size in responses:
        metrics.requests_by_type[resource_type] = metrics.requests_by_type.get(resource_type, 0) + 1
        metrics.bytes_by_type[resource_type] = metrics.bytes_by_type.get(resource_type, 0) + size
    metrics.requests_total = len(responses)

    if route == "/places":
        initial_count = len(responses)
        metrics.leaflet_before_toggle = any("leaflet" in url.lower() for _t, url, _s in responses)

        toggle = None
        for label in SHOW_MAP_LABELS:
            candidate = page.get_by_role("button", name=label)
            if candidate.count() > 0:
                toggle = candidate.first
                break
        metrics.map_visible_by_default = toggle is None

        if toggle is not None and not metrics.leaflet_before_toggle:
            toggle.click()
            page.wait_for_timeout(3000)
            extra = responses[initial_count:]
            metrics.leaflet_after_toggle = any("leaflet" in url.lower() for _t, url, _s in extra)
            metrics.leaflet_extra_requests = len(extra)
            metrics.leaflet_extra_bytes = sum(size for _t, _u, size in extra)
        else:
            metrics.leaflet_after_toggle = metrics.leaflet_before_toggle

    if capture_text:
        metrics.visible_text = " ".join(page.inner_text("body").split())[:600]

    page.remove_listener("response", on_response)
    return metrics


def measure_app(app: str, capture_text: bool) -> dict[str, RouteMetrics]:
    port = APPS[app].port
    base_url = f"http://localhost:{port}"
    results: dict[str, RouteMetrics] = {}

    proc = start_preview(app)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            for route in ROUTES:
                page = browser.new_page()
                results[route] = measure_route(page, base_url, route, capture_text)
                page.close()
            browser.close()
    finally:
        stop_preview(proc)

    return results


def time_builds(app: str, runs: int) -> list[float]:
    durations = []
    for _ in range(runs):
        started = time.perf_counter()
        subprocess.run(
            [npm_command(), "run", "build"],
            cwd=APPS[app].dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        durations.append(time.perf_counter() - started)
    return durations


def fmt_kb(size: int) -> str:
    return f"{size / 1024:.1f}"


def print_results(all_results: dict[str, dict[str, RouteMetrics]], capture_text: bool) -> None:
    print("\n## Per-route metrics\n")
    print("| App | Route | Requests | JS kB | CSS kB | HTML kB | Fetch/XHR kB | Total kB |")
    print("|---|---|---|---|---|---|---|---|")
    for app, routes in all_results.items():
        for route, m in routes.items():
            js = m.bytes_by_type.get("script", 0)
            css = m.bytes_by_type.get("stylesheet", 0)
            html = m.bytes_by_type.get("document", 0)
            api = m.bytes_by_type.get("fetch", 0) + m.bytes_by_type.get("xhr", 0)
            total = sum(m.bytes_by_type.values())
            print(
                f"| {app} | {route} | {m.requests_total} | {fmt_kb(js)} | {fmt_kb(css)} "
                f"| {fmt_kb(html)} | {fmt_kb(api)} | {fmt_kb(total)} |"
            )

    print("\n## Leaflet loading on /places\n")
    print("| App | Map visible by default | Leaflet before toggle | Leaflet after toggle | Extra requests | Extra kB |")
    print("|---|---|---|---|---|---|")
    for app, routes in all_results.items():
        m = routes.get("/places")
        if m is None:
            continue
        print(
            f"| {app} | {m.map_visible_by_default} | {m.leaflet_before_toggle} "
            f"| {m.leaflet_after_toggle} | {m.leaflet_extra_requests} | {fmt_kb(m.leaflet_extra_bytes)} |"
        )

    if capture_text:
        print("\n## Visible page text (backend down)\n")
        for app, routes in all_results.items():
            for route, m in routes.items():
                print(f"**{app} {route}**\n\n> {m.visible_text}\n")


def main() -> None:
    # Captured page text may contain characters outside the Windows console codepage.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-runs", type=int, default=0, help="number of timed npm run build runs per app")
    parser.add_argument("--scenario", choices=["up", "down"], default="up", help="expected backend state")
    parser.add_argument("--apps", default="sveltekit,astro", help="comma-separated subset of apps to measure")
    args = parser.parse_args()

    apps = [a.strip() for a in args.apps.split(",") if a.strip()]
    unknown = [a for a in apps if a not in APPS]
    if unknown:
        sys.exit(f"Unknown apps: {unknown}; available: {list(APPS)}")

    if args.build_runs > 0:
        print("\n## Build times (seconds)\n")
        print("| App | Runs | Median |")
        print("|---|---|---|")
        for app in apps:
            durations = time_builds(app, args.build_runs)
            runs = ", ".join(f"{d:.1f}" for d in durations)
            print(f"| {app} | {runs} | {statistics.median(durations):.1f} |")

    capture_text = args.scenario == "down"
    all_results = {app: measure_app(app, capture_text) for app in apps}
    print_results(all_results, capture_text)


if __name__ == "__main__":
    main()
