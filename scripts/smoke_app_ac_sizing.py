# -----------------------------------------------------------------------------
# Personal Open-Source Notice — see repository LICENSE.
# -----------------------------------------------------------------------------

"""Real-app smoke check for the AC Sizing page (the "run the real app" gate).

Launches the actual Streamlit app and drives it as a user would — guest mode →
DC Sizing (POI inputs) → AC Sizing — then asserts the AC Sizing page renders the
single trunk flow plus the optional standard-product preset checkbox. This is the
verification mechanism Change Discipline §2 step "run the real app" points to: it
caught a real UI bug (duration read from DC nameplate capacity instead of POI
energy) that the function-level tests could not.

It is NOT part of the pytest suite (it needs a running server + a browser). Run
it manually / in a dedicated CI stage:

    python scripts/smoke_app_ac_sizing.py

Exit code 0 = PASS, 1 = FAIL, 2 = SKIPPED (playwright / chromium unavailable).
It reuses an already-running server on :8511 or launches its own.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import time
import urllib.request

PORT = 8511
BASE = f"http://127.0.0.1:{PORT}/"


def _find_chrome() -> str | None:
    root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")
    hits = sorted(glob.glob(f"{root}/chromium-*/chrome-linux/chrome"))
    return hits[-1] if hits else None


def _server_up() -> bool:
    try:
        with urllib.request.urlopen(BASE, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _wait_up(timeout_s: int = 40) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if _server_up():
            return True
        time.sleep(1.5)
    return False


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("SKIP: playwright not installed")
        return 2
    chrome = _find_chrome()
    if not chrome:
        print("SKIP: chromium not found under PLAYWRIGHT_BROWSERS_PATH")
        return 2

    proc = None
    if not _server_up():
        proc = subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "app.py",
             "--server.port", str(PORT), "--server.address", "127.0.0.1",
             "--server.headless", "true", "--browser.gatherUsageStats", "false"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if not _wait_up():
            print("FAIL: server did not come up")
            if proc:
                proc.terminate()
            return 1

    failures: list[str] = []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
            pg = b.new_page(viewport={"width": 1440, "height": 1250})
            pg.goto(BASE, wait_until="load", timeout=60000)
            pg.wait_for_selector('[data-testid="stApp"]', timeout=25000)
            pg.wait_for_timeout(2500)

            # Guest mode (bootstrap admin first if this is a fresh DB).
            body = pg.inner_text('[data-testid="stApp"]')
            if "Create Admin Account" in body:
                pg.get_by_label("Admin Username").fill("smoke")
                pwds = pg.locator('input[type="password"]')
                pwds.nth(0).fill("Smoke12345!")
                pwds.nth(1).fill("Smoke12345!")
                pg.get_by_role("button", name="Create Admin Account").click()
                pg.wait_for_timeout(3500)
            pg.get_by_role("button", name="Continue as Guest — DC / AC Sizing only").click()
            pg.wait_for_timeout(3500)

            # DC Sizing: POI 100 MW / 400 MWh, run.
            pg.locator('input[aria-label="POI Required Power (MW)"]').first.fill("100")
            pg.locator('input[aria-label="POI Required Capacity (MWh)"]').first.fill("400")
            pg.wait_for_timeout(600)
            pg.get_by_role("button", name="Run Sizing").click()
            pg.wait_for_timeout(6500)

            # AC Sizing page.
            pg.get_by_role("button", name="AC Sizing").first.click()
            pg.wait_for_timeout(5000)
            ac = pg.inner_text('[data-testid="stApp"]')

            checks = {
                "preset checkbox present": "Use a standard product AC Block preset" in ac,
                "trunk grouping present": "AC Block Grouping" in ac,
                "grouping computed": "AC Blocks" in ac and "DC Block" in ac,
                "run button present": "Run AC Sizing" in ac or "Run AC Sizing (Governed)" in ac,
                "no fabricated duration steer": "currently covers 4 h systems" not in ac,
            }
            for name, ok in checks.items():
                print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
                if not ok:
                    failures.append(name)
            b.close()
    finally:
        if proc:
            proc.terminate()

    if failures:
        print(f"FAIL: {len(failures)} check(s) failed: {failures}")
        return 1
    print("PASS: AC Sizing real-app smoke green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
