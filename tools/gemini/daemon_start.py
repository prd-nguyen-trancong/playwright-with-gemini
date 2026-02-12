"""
Browser daemon process.

This script is launched as a detached subprocess by BrowserDaemon.
It uses Playwright's launch_persistent_context with CDP port exposed,
then sleeps forever to keep the browser alive.

The browser stays alive until this process is killed.
"""

import os
import signal
import sys
import time

# Add project root to path
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, SCRIPT_DIR)

BROWSER_DATA_DIR = os.path.join(SCRIPT_DIR, ".browser-data", "gemini")
CDP_PORT = 9222
GEMINI_URL = "https://gemini.google.com/app"


def _clean_locks():
    """Remove Chrome profile lock files."""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = os.path.join(BROWSER_DATA_DIR, name)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def main():
    from playwright.sync_api import sync_playwright

    os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
    _clean_locks()

    pw = sync_playwright().start()

    ctx = pw.chromium.launch_persistent_context(
        BROWSER_DATA_DIR,
        headless=True,
        channel="chrome",
        viewport={"width": 1440, "height": 900},
        args=[
            "--disable-blink-features=AutomationControlled",
            f"--remote-debugging-port={CDP_PORT}",
        ],
    )

    # Navigate to Gemini so the page is ready
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    try:
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(1)

    # Handle SIGTERM gracefully
    def shutdown(signum, frame):
        try:
            ctx.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass
        _clean_locks()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Sleep forever - keep browser alive
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
