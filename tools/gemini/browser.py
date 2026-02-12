"""
Browser daemon manager for fast Gemini automation.

Uses Playwright's launch_persistent_context with CDP port exposed,
so subsequent calls can connect_over_cdp without re-launching.

Supports multiple independent pages by role (e.g. "ask", "gem") so
that ai-ask and ai-gem use separate tabs and never cross-contaminate.

Architecture:
  daemon_start.py (background) -> Chrome with persistent profile + CDP port 9222
  fast_ask.py (foreground)     -> connect_over_cdp("http://localhost:9222")  [ask tab]
  fast_gem.py (foreground)     -> connect_over_cdp("http://localhost:9222")  [gem tab]

Usage:
    from tools.gemini.browser import BrowserDaemon

    daemon = BrowserDaemon()
    browser, page = daemon.get_page("ask")    # dedicated ask tab
    browser, page = daemon.get_page("gem")    # dedicated gem tab
    daemon.release()
"""

import json
import os
import signal
import socket
import subprocess
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BROWSER_DATA_DIR = os.path.join(SCRIPT_DIR, ".browser-data", "gemini")
STATE_FILE = os.path.join(BROWSER_DATA_DIR, "daemon_state.json")
DAEMON_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daemon_start.py")
CDP_PORT = 9222
GEMINI_URL = "https://gemini.google.com/app"


def _is_port_open(port):
    """Check if CDP port is listening."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(("localhost", port))
            return True
    except (socket.error, ConnectionRefusedError, OSError):
        return False


def _load_state():
    """Load daemon state from file."""
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_state(state):
    """Save daemon state to file."""
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _is_pid_alive(pid):
    """Check if a process is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class BrowserDaemon:
    """
    Manages a persistent Playwright-driven Chrome daemon for fast Gemini access.

    On first call, launches a daemon process that uses Playwright's
    launch_persistent_context with CDP port exposed. Subsequent calls
    connect via connect_over_cdp for instant access.
    """

    def __init__(self, quiet=False):
        self._quiet = quiet
        self._pw_instance = None
        self._browser = None
        self._page = None

    def log(self, msg="", end="\n"):
        if not self._quiet:
            print(msg, flush=True, end=end)

    # ── Lifecycle ────────────────────────────────────────────────────

    def ensure_browser(self):
        """Ensure daemon is running, launch if needed. Returns state."""
        state = _load_state()
        pid = state.get("pid")

        # Check if existing daemon is alive and CDP port is open
        if pid and _is_pid_alive(pid) and _is_port_open(CDP_PORT):
            self.log(f"  Browser daemon running (pid={pid})")
            return state

        # Clean up stale state and orphaned Chrome processes
        self.log("  Cleaning up stale processes...")
        _kill_orphan_chromes()
        _clean_locks()

        # Launch new daemon
        self.log("  Launching browser daemon...")

        # Launch daemon_start.py as a detached subprocess
        proc = subprocess.Popen(
            [sys.executable, DAEMON_SCRIPT],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            cwd=SCRIPT_DIR,
        )

        # Wait for CDP port to open
        for i in range(60):  # up to 30 seconds
            if _is_port_open(CDP_PORT):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"Daemon failed to start on port {CDP_PORT}")

        # Brief wait for the Gemini page to start loading
        time.sleep(1)

        state = {"pid": proc.pid, "ask_count": 0, "gem_count": 0, "role_map": {}}
        _save_state(state)
        self.log(f"  Browser daemon started (pid={proc.pid})")
        return state

    def connect(self):
        """Connect to the running Chrome via CDP."""
        from playwright.sync_api import sync_playwright

        self._pw_instance = sync_playwright().start()
        self._browser = self._pw_instance.chromium.connect_over_cdp(
            f"http://localhost:{CDP_PORT}"
        )
        return self._browser

    # ── Role-based page management ─────────────────────────────────
    #
    # Each role ("ask", "gem", "story", "scrape") gets its own browser
    # tab. We track which tab belongs to which role by page index,
    # stored in the daemon state file. This survives page navigations
    # and reconnects.

    def _get_role_map(self):
        """Get role -> page_index mapping from state."""
        state = _load_state()
        return state.get("role_map", {})

    def _set_role_index(self, role, index):
        """Save role -> page_index mapping to state."""
        state = _load_state()
        role_map = state.get("role_map", {})
        role_map[role] = index
        state["role_map"] = role_map
        _save_state(state)

    def _get_page_by_index(self, browser, index):
        """Get a page by its index across all contexts."""
        all_pages = []
        for ctx in browser.contexts:
            all_pages.extend(ctx.pages)
        if 0 <= index < len(all_pages):
            return all_pages[index]
        return None

    def _get_page_index(self, browser, page):
        """Get the index of a page across all contexts."""
        all_pages = []
        for ctx in browser.contexts:
            all_pages.extend(ctx.pages)
        for i, p in enumerate(all_pages):
            if p == page:
                return i
        return -1

    def get_page(self, role, target_url=None):
        """
        Get or create a page for the given role.

        Each role ("ask", "gem", "scrape", etc.) gets its own dedicated
        browser tab. Tabs are tracked by index in the state file so the
        mapping survives page navigations and CDP reconnects.

        Returns (browser, page).
        """
        target_url = target_url or GEMINI_URL
        browser = self.connect()

        role_map = self._get_role_map()

        # 1. Look for an existing tab assigned to this role
        if role in role_map:
            page = self._get_page_by_index(browser, role_map[role])
            if page is not None:
                self._page = page
                return browser, page

        # 2. No tab for this role yet.
        #    For "ask", claim the daemon's initial page (index 0) if unclaimed.
        if role == "ask":
            claimed_indices = set(role_map.values())
            all_pages = []
            for ctx in browser.contexts:
                all_pages.extend(ctx.pages)
            for i, page in enumerate(all_pages):
                if i not in claimed_indices and "gemini.google.com" in page.url:
                    self._set_role_index(role, i)
                    self._page = page
                    return browser, page

        # 3. Create a brand-new tab for this role
        ctx = browser.contexts[0] if browser.contexts else browser.new_context()
        page = ctx.new_page()
        page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass

        # Record the index of the new page
        idx = self._get_page_index(browser, page)
        self._set_role_index(role, idx)
        self._page = page
        return browser, page

    def new_conversation(self, role, target_url=None):
        """Start a fresh conversation for the given role by navigating its tab."""
        target_url = target_url or GEMINI_URL
        browser = self._browser
        if not browser:
            browser = self.connect()

        role_map = self._get_role_map()

        # Find the tab for this role and navigate it
        if role in role_map:
            page = self._get_page_by_index(browser, role_map[role])
            if page is not None:
                page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                time.sleep(1)
                self._page = page
                return browser, page

        # No existing tab for this role - create one
        return self.get_page(role, target_url)

    # ── Backward-compatible aliases ──────────────────────────────

    def get_gemini_page(self, target_url=None):
        """Get or create a Gemini page (backward compat - uses 'ask' role)."""
        return self.get_page("ask", target_url)

    def release(self):
        """Disconnect from browser WITHOUT killing it. Fast - skips browser.close()."""
        try:
            if self._pw_instance:
                self._pw_instance.stop()
        except Exception:
            pass
        self._browser = None
        self._pw_instance = None
        self._page = None

    @staticmethod
    def stop():
        """Kill the browser daemon and any orphaned Chrome processes."""
        state = _load_state()
        pid = state.get("pid")
        killed = False
        if pid and _is_pid_alive(pid):
            try:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                killed = True
            except Exception:
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed = True
                except Exception:
                    pass

        # Also kill any orphaned Chrome processes using our profile
        _kill_orphan_chromes()

        if killed:
            print(f"Browser daemon stopped (pid={pid})", flush=True)
        else:
            print("No browser daemon running (cleaned up orphans).", flush=True)

        _save_state({})
        _clean_locks()

    @staticmethod
    def status():
        """Print daemon status."""
        state = _load_state()
        pid = state.get("pid")
        if pid and _is_pid_alive(pid) and _is_port_open(CDP_PORT):
            print(f"Browser daemon: RUNNING (pid={pid}, port={CDP_PORT})", flush=True)
            print(f"  Ask prompt count: {state.get('ask_count', 0)}", flush=True)
            print(f"  Gem prompt count: {state.get('gem_count', 0)}", flush=True)
        else:
            print("Browser daemon: STOPPED", flush=True)

    @staticmethod
    def get_state():
        return _load_state()

    @staticmethod
    def update_state(**kwargs):
        state = _load_state()
        state.update(kwargs)
        _save_state(state)


def _clean_locks():
    """Remove Chrome profile lock files."""
    for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
        path = os.path.join(BROWSER_DATA_DIR, name)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


def _kill_orphan_chromes():
    """Kill any Chrome/Chromium processes using our browser-data profile.

    This catches orphaned processes that survive after the daemon PID
    is lost (e.g. state file cleared, daemon crashed, etc.).
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"user-data-dir=.*{os.path.basename(BROWSER_DATA_DIR)}"],
            capture_output=True, text=True, timeout=5,
        )
        pids = [int(p) for p in result.stdout.strip().split("\n") if p.strip()]
        for pid in pids:
            try:
                os.kill(pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass
        if pids:
            time.sleep(1)
            # Force kill any survivors
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except (OSError, ProcessLookupError):
                    pass
    except Exception:
        pass
