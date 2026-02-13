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


def _find_chrome():
    """Find system Chrome binary."""
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None


def main():
    import subprocess as sp

    os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
    _clean_locks()

    chrome_bin = os.environ.get("CHROME_PATH") or _find_chrome()
    if not chrome_bin:
        print("ERROR: Chrome not found. Set CHROME_PATH or install Google Chrome.")
        sys.exit(1)

    # Launch Chrome directly (no Playwright launcher = no --enable-automation flag).
    # This avoids Gemini's bot detection which blocks send when automation is detected.
    chrome_args = [
        chrome_bin,
        "--headless=new",  # Chrome 112+ new headless mode
        f"--user-data-dir={BROWSER_DATA_DIR}",
        f"--remote-debugging-port={CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--window-size=1440,900",
    ]

    if os.environ.get("CHROME_NO_SANDBOX") == "true":
        chrome_args.append("--no-sandbox")

    proc = sp.Popen(chrome_args, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    # Wait for CDP port
    import socket

    for _ in range(60):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                s.connect(("localhost", CDP_PORT))
                break
        except (socket.error, ConnectionRefusedError, OSError):
            time.sleep(0.5)
    else:
        print("ERROR: Chrome failed to start on CDP port")
        proc.kill()
        sys.exit(1)

    # Connect via Playwright CDP and navigate to Gemini
    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
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
            browser.close()
        except Exception:
            pass
        try:
            pw.stop()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        _clean_locks()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Sleep forever - keep browser alive
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
