"""
Base class for Gemini automation tools.

Provides shared browser management, login handling, prompt sending,
and response detection. Subclasses override tool-specific behavior.
"""

import functools
import os
import sys
import time
import uuid

from playwright.sync_api import TimeoutError as PTE
from playwright.sync_api import sync_playwright

# Unbuffered print
_print = functools.partial(print, flush=True)

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GEMINI_URL = "https://gemini.google.com/app"
BROWSER_DATA_DIR = os.path.join(SCRIPT_DIR, ".browser-data", "gemini")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")


class GeminiBase:
    """
    Base class for all Gemini automation tools.

    Handles browser lifecycle, persistent login, navigation,
    prompt input, and dialog dismissal. Subclasses implement
    tool activation and response handling.
    """

    # Override in subclasses
    TOOL_NAME = None  # e.g. "Create images", "Create videos"
    TOOL_LABEL = "gemini"  # Used in output filenames
    DEFAULT_EXT = ".txt"  # Default file extension for output

    def __init__(self, quiet=False):
        self._quiet = quiet
        self._page = None
        self._ctx = None

    # ── Logging ──────────────────────────────────────────────────────

    def log(self, msg="", end="\n"):
        """Print only when not in quiet mode."""
        if not self._quiet:
            _print(msg, end=end)

    # ── Output path helpers ──────────────────────────────────────────

    @classmethod
    def default_output_path(cls, ext=None):
        """Generate a default output path in the output/ directory."""
        ext = ext or cls.DEFAULT_EXT
        short_id = uuid.uuid4().hex[:8]
        filename = f"{cls.TOOL_LABEL}_{short_id}{ext}"
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        return os.path.join(OUTPUT_DIR, filename)

    @staticmethod
    def resolve_output_path(user_path, default_path):
        """Resolve user-provided path or use default, ensuring parent dir exists."""
        path = user_path or default_path
        abs_path = os.path.abspath(path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        return abs_path

    # ── Login detection ──────────────────────────────────────────────

    @staticmethod
    def is_logged_in(page) -> bool:
        """Check if the user is logged into Gemini and can chat."""
        try:
            current_url = page.url
            if "accounts.google.com" in current_url:
                return False
            if "gemini.google.com" not in current_url:
                return False

            # Check if the chat editor is available (most reliable indicator)
            return page.evaluate("""() => {
                const editor = document.querySelector('.ql-editor[contenteditable="true"]');
                if (editor) return true;

                // Fallback: check for model-response or chat elements
                const chatEls = document.querySelectorAll('model-response, message-content');
                if (chatEls.length > 0) return true;

                return false;
            }""")
        except Exception:
            return False

    def _wait_for_manual_login(self, ctx, page):
        """Wait for user to manually log in via the open browser window."""
        self.log("\n  Please log in to your Google account in the browser window.")
        self.log("  (Passkey login may close the browser - that's OK, it will re-check.)\n")

        for attempt in range(180):
            time.sleep(2)
            try:
                # Check all pages in the context
                pages_alive = False
                for pg in ctx.pages:
                    try:
                        url = pg.url
                        pages_alive = True
                    except Exception:
                        continue

                    if "gemini.google.com" not in url:
                        continue

                    if self.is_logged_in(pg):
                        self.log("  Login detected!")
                        time.sleep(3)
                        return pg

                # If no pages are alive, the browser may have been closed by passkey
                if not pages_alive:
                    self.log("  Browser closed (passkey flow). Will re-check session...")
                    return "BROWSER_CLOSED"

            except Exception as e:
                err_msg = str(e).lower()
                if "target closed" in err_msg or "closed" in err_msg or "crash" in err_msg:
                    self.log("  Browser closed (passkey flow). Will re-check session...")
                    return "BROWSER_CLOSED"

            if attempt > 0 and attempt % 30 == 0:
                self.log(f"  Still waiting for login... ({attempt * 2}s)")

        self.log("  Timeout waiting for login.")
        return None

    # ── Browser lifecycle ────────────────────────────────────────────

    def _launch_context(self, playwright, headless=True):
        """Launch a persistent browser context."""
        os.makedirs(BROWSER_DATA_DIR, exist_ok=True)
        # Clean up lock files that may have been left by a crashed browser
        for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
            try:
                os.remove(os.path.join(BROWSER_DATA_DIR, name))
            except FileNotFoundError:
                pass
        return playwright.chromium.launch_persistent_context(
            BROWSER_DATA_DIR,
            headless=headless,
            channel="chrome",
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )

    def _navigate_to_gemini(self, page):
        """Navigate to Gemini and wait for load."""
        page.goto(GEMINI_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except PTE:
            pass
        time.sleep(1)

    def _ensure_login(self, playwright, page, ctx, headless, force_login):
        """Ensure the user is logged in, opening visible browser if needed."""
        if self.is_logged_in(page) and not force_login:
            return page, ctx

        if headless or force_login:
            self.log("\n  Not logged in. Restarting with visible browser...")
            try:
                ctx.close()
            except Exception:
                pass

            ctx = self._launch_context(playwright, headless=False)
            page = ctx.new_page()
            self._navigate_to_gemini(page)

        logged_in_page = self._wait_for_manual_login(ctx, page)

        if logged_in_page == "BROWSER_CLOSED":
            # Passkey login closed the browser - re-launch headless and verify
            self.log("      Re-launching browser to verify login...")
            try:
                ctx.close()
            except Exception:
                pass
            time.sleep(2)

            # Clean up lock files left by crashed browser
            for name in ("SingletonLock", "SingletonSocket", "SingletonCookie"):
                lock_path = os.path.join(BROWSER_DATA_DIR, name)
                try:
                    os.remove(lock_path)
                except FileNotFoundError:
                    pass

            ctx = self._launch_context(playwright, headless=headless)
            page = ctx.new_page()
            self._navigate_to_gemini(page)

            if self.is_logged_in(page):
                self.log("      Login verified after passkey!")
                self._ctx = ctx
                self._page = page
                return page, ctx
            else:
                self.log("  Login not detected after passkey. Retrying with visible browser...")
                try:
                    ctx.close()
                except Exception:
                    pass
                # Give user one more chance with visible browser
                ctx = self._launch_context(playwright, headless=False)
                page = ctx.new_page()
                self._navigate_to_gemini(page)

                if self.is_logged_in(page):
                    self.log("      Login verified!")
                    self._ctx = ctx
                    self._page = page
                    return page, ctx

                logged_in_page = self._wait_for_manual_login(ctx, page)
                if not logged_in_page or logged_in_page == "BROWSER_CLOSED":
                    self.log("  ERROR: Login failed after passkey retry.")
                    sys.exit(1)
                page = logged_in_page

        elif not logged_in_page:
            self.log("  ERROR: Login failed or timed out.")
            sys.exit(1)
        else:
            page = logged_in_page

        self.log("      Navigating to Gemini chat...")
        self._navigate_to_gemini(page)

        # Retry login check a few times (page may still be loading)
        for retry in range(5):
            if self.is_logged_in(page):
                break
            self.log(f"      Waiting for login to propagate... ({retry + 1}/5)")
            time.sleep(3)
        else:
            if not self.is_logged_in(page):
                self.log("  ERROR: Still not logged in after login attempt.")
                page.screenshot(path="debug_gemini_login.png")
                sys.exit(1)

        self._ctx = ctx
        self._page = page
        return page, ctx

    def _dismiss_dialogs(self, page):
        """Dismiss any overlay dialogs (Got it, OK, Continue, etc.)."""
        try:
            dismiss_btns = page.locator(
                'button:has-text("Got it"), '
                'button:has-text("OK"), '
                'button:has-text("Continue"), '
                'button:has-text("Skip"), '
                'button:has-text("Dismiss")'
            )
            for i in range(dismiss_btns.count()):
                try:
                    dismiss_btns.nth(i).click(timeout=2000)
                    time.sleep(1)
                except Exception:
                    pass
        except Exception:
            pass

    # ── Tool activation ──────────────────────────────────────────────

    def _activate_tool(self, page):
        """
        Activate the Gemini tool via the Tools dropdown.

        Override in subclasses if the tool needs special activation.
        If TOOL_NAME is None, no tool is activated (plain chat).
        """
        if not self.TOOL_NAME:
            return

        self.log(f"      Activating tool: {self.TOOL_NAME}...")

        # Click the "Tools" dropdown button
        tools_btn = page.locator('button:has-text("Tools")').first
        try:
            if tools_btn.is_visible(timeout=4000):
                tools_btn.click()
                time.sleep(1)

                # Click the specific tool menu item
                tool_item = page.locator(f'text={self.TOOL_NAME}').first
                if tool_item.is_visible(timeout=3000):
                    tool_item.click()
                    time.sleep(2)
                    self.log(f"      Tool activated: {self.TOOL_NAME}")
                else:
                    self.log(f"  WARNING: Tool '{self.TOOL_NAME}' not found in menu")
            else:
                self.log("  WARNING: Tools button not found")
        except Exception as e:
            self.log(f"  WARNING: Could not activate tool: {e}")

    # ── Prompt input ─────────────────────────────────────────────────

    def _send_prompt(self, page, prompt_text):
        """Type a prompt into the Gemini input and send it."""
        input_selectors = [
            '.ql-editor[contenteditable="true"]',
            'div[contenteditable="true"][aria-label*="prompt"]',
            'div[contenteditable="true"][aria-label*="Gemini"]',
            'div[contenteditable="true"][role="textbox"]',
            'div.ql-editor[contenteditable="true"]',
            'rich-textarea div[contenteditable="true"]',
            "textarea",
        ]

        input_el = None
        for sel in input_selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=5000):
                    input_el = el
                    break
            except Exception:
                continue

        if not input_el:
            # Check for rate limit message
            try:
                limit_msg = page.evaluate("""() => {
                    const body = document.body.innerText;
                    const match = body.match(/reached.*?limit.*?(?:PM|AM|\\d{1,2}:\\d{2})/i);
                    return match ? match[0] : '';
                }""")
                if limit_msg:
                    self.log(f"  ERROR: Rate limited - {limit_msg}")
                    return False
            except Exception:
                pass

            self.log("  ERROR: Could not find Gemini input field")
            page.screenshot(path="debug_gemini_input.png")
            self.log("  Debug screenshot saved: debug_gemini_input.png")
            return False

        input_el.click()
        time.sleep(0.5)
        page.keyboard.type(prompt_text)
        time.sleep(1)

        try:
            send_btn = page.locator(
                'button[aria-label="Send message"], button.send-button'
            ).first
            if send_btn.is_visible(timeout=5000):
                send_btn.click()
                time.sleep(2)
                return True
        except Exception:
            pass

        page.keyboard.press("Enter")
        time.sleep(2)
        return True

    def _upload_image_and_prompt(self, page, image_path, prompt_text):
        """Upload an image and send a prompt about it."""
        abs_path = os.path.abspath(image_path)
        if not os.path.exists(abs_path):
            self.log(f"  ERROR: Image file not found: {abs_path}")
            return False

        try:
            upload_menu_btn = page.locator(
                'button[aria-label="Open upload file menu"]'
            ).first
            if upload_menu_btn.is_visible(timeout=3000):
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    upload_menu_btn.click()
                    time.sleep(1)
                    upload_item = page.locator(
                        '[role="menuitem"][aria-label*="Upload files"]'
                    ).first
                    upload_item.click()

                file_chooser = fc_info.value
                file_chooser.set_files(abs_path)
                time.sleep(4)
                self.log(f"      Uploaded: {os.path.basename(image_path)}")
            else:
                file_input = page.locator('input[type="file"]').first
                file_input.set_input_files(abs_path)
                time.sleep(3)
                self.log(f"      Uploaded: {os.path.basename(image_path)}")
        except Exception as e:
            self.log(f"  ERROR: Could not upload file: {e}")
            return False

        return self._send_prompt(page, prompt_text)

    # ── Response handling (override in subclasses) ───────────────────

    def _wait_for_response(self, page, **kwargs):
        """
        Wait for and return the tool's response.

        Override in subclasses for tool-specific response handling.
        Returns the response string or file path.
        """
        raise NotImplementedError("Subclasses must implement _wait_for_response")

    @staticmethod
    def _clean_response(text):
        """Strip Gemini UI prefixes from response text."""
        import re

        # Strip known Gem/tool UI headers (e.g. "T\nTóm tắt truyện V3\nCustom Gem\nGemini said")
        # Pattern: single char line + Gem name + "Custom Gem" + "Gemini said"
        text = re.sub(
            r"^[A-Z]\n.+\nCustom Gem\nGemini said\n+",
            "",
            text,
            count=1,
        )

        prefixes_to_strip = [
            "Show code\n",
            "Analysis\n",
            "Query successful\n",
            "Gemini said\n\n",
            "Gemini said\n",
            "Custom Gem\n",
        ]
        changed = True
        while changed:
            changed = False
            for prefix in prefixes_to_strip:
                if text.startswith(prefix):
                    text = text[len(prefix):]
                    changed = True
        return text.strip()

    # ── Main execution flow ──────────────────────────────────────────

    def run(
        self,
        prompt: str,
        headless: bool = True,
        image_path: str | None = None,
        save_screenshot: str | None = None,
        force_login: bool = False,
        output_path: str | None = None,
    ):
        """
        Run the Gemini tool automation.

        Parameters
        ----------
        prompt : str
            The text prompt to send.
        headless : bool
            Run browser in headless mode.
        image_path : str, optional
            Path to an image file to attach.
        save_screenshot : str, optional
            Save a page screenshot to this path.
        force_login : bool
            Force re-login even if session exists.
        output_path : str, optional
            Output file path (for image/video tools).
        """
        tool_display = self.TOOL_NAME or "Chat"
        self.log(f"\n{'=' * 60}")
        self.log(f"  Gemini {tool_display}")
        self.log(f"{'=' * 60}")
        self.log(f"  Prompt    : {prompt[:80]}{'...' if len(prompt) > 80 else ''}")
        self.log(f"  Headless  : {headless}")
        if image_path:
            self.log(f"  Image     : {image_path}")
        if output_path:
            self.log(f"  Output    : {output_path}")
        self.log(f"{'=' * 60}\n")

        os.makedirs(BROWSER_DATA_DIR, exist_ok=True)

        with sync_playwright() as p:
            use_headless = headless and not force_login

            self.log("[1/5] Launching browser...")
            ctx = self._launch_context(p, headless=use_headless)
            page = ctx.new_page()

            try:
                self.log("[2/5] Navigating to Gemini...")
                self._navigate_to_gemini(page)

                current_url = page.url
                title = page.title()
                self.log(f"      URL: {current_url[:80]}")
                self.log(f"      Title: {title}")

                page, ctx = self._ensure_login(p, page, ctx, use_headless, force_login)
                self.log("      Login verified!")

                self._dismiss_dialogs(page)
                time.sleep(1)

                # Activate the tool (if any)
                self._activate_tool(page)

                # Send prompt (with optional image attachment)
                if image_path:
                    self.log("\n[3/5] Uploading image and sending prompt...")
                    success = self._upload_image_and_prompt(page, image_path, prompt)
                else:
                    self.log("\n[3/5] Sending prompt...")
                    success = self._send_prompt(page, prompt)

                if not success:
                    self.log("  ERROR: Failed to send prompt")
                    sys.exit(1)
                self.log("      Prompt sent!")

                # Wait for response
                self.log("\n[4/5] Waiting for response...")
                response = self._wait_for_response(page, output_path=output_path)

                if save_screenshot:
                    try:
                        page.screenshot(path=save_screenshot, full_page=True)
                        self.log(f"      Screenshot saved: {save_screenshot}")
                    except Exception:
                        pass

                self.log(f"\n[5/5] Response:")
                self.log(f"{'=' * 60}")
                if response:
                    _print(response)
                    if not self._quiet:
                        self.log(f"{'=' * 60}")
                else:
                    self.log("  (No response captured)")
                    try:
                        page.screenshot(path="debug_gemini_response.png")
                        self.log("  Debug screenshot: debug_gemini_response.png")
                    except Exception:
                        pass
                    if not self._quiet:
                        self.log(f"{'=' * 60}")

                if not headless:
                    wait = 10
                    self.log(f"\n  Browser open for {wait}s. Ctrl+C to close.\n")
                    try:
                        time.sleep(wait)
                    except KeyboardInterrupt:
                        pass

                return response

            finally:
                ctx.close()
