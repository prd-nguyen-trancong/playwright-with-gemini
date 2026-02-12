"""
Gemini Fast Ask - Speed-optimized text chat using a persistent browser daemon.

Keeps Chrome alive between calls. Reuses the same conversation for up to 20
prompts before starting fresh. Uses a dedicated "ask" tab in the daemon so
it never interferes with ai-gem or other tools.

First call:  ~10-15s (launches browser + navigates)
Subsequent:  ~4-5s (connect + send prompt + wait response)

Usage:
    poetry run python -m tools.gemini.fast_ask "What is Python?"
    poetry run python -m tools.gemini.fast_ask --quiet "2+2"
    poetry run python -m tools.gemini.fast_ask --new "start fresh conversation"
"""

import argparse
import functools
import sys
import time

from tools.gemini.base import GeminiBase
from tools.gemini.browser import BrowserDaemon, GEMINI_URL

_print = functools.partial(print, flush=True)

MAX_PROMPTS_PER_CONVERSATION = 20
ROLE = "ask"


class GeminiFastAsk(GeminiBase):
    """Speed-optimized Gemini text chat using persistent browser daemon."""

    TOOL_NAME = None
    TOOL_LABEL = "fast_ask"
    DEFAULT_EXT = ".txt"

    def __init__(self, quiet=False):
        super().__init__(quiet=quiet)
        self._daemon = BrowserDaemon(quiet=quiet)

    def run_fast(
        self,
        prompt: str,
        force_new: bool = False,
        file_path: str | None = None,
    ):
        """
        Send a prompt and get a response using the persistent browser.

        Parameters
        ----------
        prompt : str
            The text prompt to send.
        force_new : bool
            Force a new conversation even if under the prompt limit.
        file_path : str, optional
            Path to a text file whose content will be used as the prompt.
        """
        # If file_path provided, read content
        if file_path:
            try:
                with open(file_path, encoding="utf-8") as f:
                    file_content = f.read().strip()
                if prompt:
                    prompt = f"{prompt}\n\n{file_content}"
                else:
                    prompt = file_content
            except Exception as e:
                self.log(f"  ERROR: Could not read file: {e}")
                return None

        try:
            # Step 1: Ensure browser daemon is running
            state = self._daemon.ensure_browser()
            count = state.get("ask_count", 0)

            # Step 2: Decide whether to reuse or start new conversation
            need_new = force_new or count >= MAX_PROMPTS_PER_CONVERSATION

            if need_new:
                self.log("  Starting new conversation...")
                browser, page = self._daemon.new_conversation(ROLE, GEMINI_URL)
                count = 0
            else:
                browser, page = self._daemon.get_page(ROLE, GEMINI_URL)

            # Step 3: Check login (skip on 2nd+ calls - already verified)
            if count == 0:
                if not self.is_logged_in(page):
                    self.log("  ERROR: Not logged in. Run: ai-ask --login \"hello\"")
                    self._daemon.release()
                    return None
                # Dismiss dialogs only on first use
                self._dismiss_dialogs(page)

            # Step 4: Send prompt
            self.log(f"  Sending prompt ({count + 1}/{MAX_PROMPTS_PER_CONVERSATION})...")
            success = self._send_prompt_fast(page, prompt)
            if not success:
                self.log("  ERROR: Failed to send prompt")
                self._daemon.release()
                return None

            # Step 5: Wait for response
            self.log("  Waiting for response", end="")
            response = self._wait_for_text_response(page)

            # Step 6: Update state
            BrowserDaemon.update_state(ask_count=count + 1)

            # Print response
            if response:
                self.log("")  # newline after dots
                _print(response)
            else:
                self.log("\n  (No response captured)")

            self._daemon.release()
            return response

        except Exception as e:
            self.log(f"  ERROR (daemon): {e}")
            try:
                self._daemon.release()
            except Exception:
                pass
            # If daemon failed, fall back to standard mode
            self.log("  Falling back to standard mode (no daemon)...")
            try:
                BrowserDaemon.stop()
            except Exception:
                pass
            return self._fallback_run(prompt)

    def _fallback_run(self, prompt):
        """Fall back to standard GeminiAsk when daemon is unavailable."""
        from tools.gemini.ask import GeminiAsk

        tool = GeminiAsk(quiet=self._quiet)
        return tool.run(prompt=prompt, headless=True)

    def _send_prompt_fast(self, page, prompt_text):
        """Fast prompt sending - minimal sleeps for speed."""
        try:
            input_el = page.locator('.ql-editor[contenteditable="true"]').first
            input_el.click(timeout=5000)

            if len(prompt_text) > 200:
                input_el.fill(prompt_text)
            else:
                page.keyboard.type(prompt_text)
            time.sleep(0.3)

            # Click send button (avoid matching the "Stop response" button)
            send_btn = page.locator(
                'button[aria-label="Send message"]:not([aria-label*="Stop"])'
            ).first
            try:
                if send_btn.is_visible(timeout=3000):
                    send_btn.click(timeout=5000)
                    time.sleep(0.3)
                    return True
            except Exception:
                pass

            # Fallback: Enter key (most reliable)
            page.keyboard.press("Enter")
            time.sleep(0.3)
            return True

        except Exception as e:
            self.log(f"  ERROR sending: {e}")
            return False

    def _wait_for_text_response(self, page, timeout_seconds=120):
        """Wait for text response - fast polling version."""
        start = time.time()
        last_text = ""
        stable_count = 0

        while time.time() - start < timeout_seconds:
            try:
                result = page.evaluate("""() => {
                    const stopBtn = document.querySelector('button[aria-label*="Stop"]');
                    const isGenerating = stopBtn && stopBtn.offsetParent !== null;

                    const modelResp = document.querySelectorAll('model-response');
                    let text = '';
                    if (modelResp.length > 0) {
                        text = (modelResp[modelResp.length - 1].innerText || '').trim();
                    }
                    if (!text) {
                        const msgs = document.querySelectorAll('message-content');
                        if (msgs.length > 0) {
                            text = (msgs[msgs.length - 1].innerText || '').trim();
                        }
                    }
                    return { g: isGenerating, t: text };
                }""")

                text = result.get("t", "")
                generating = result.get("g", False)

                if text and len(text) > 5 and not generating:
                    if text == last_text:
                        stable_count += 1
                        if stable_count >= 2:
                            return self._clean_response(text)
                    else:
                        stable_count = 0
                    last_text = text

            except Exception:
                pass

            self.log(".", end="")
            time.sleep(1)

        if last_text:
            return self._clean_response(last_text)
        return None

    # Keep compatibility with base class
    def _wait_for_response(self, page, **kwargs):
        return self._wait_for_text_response(page)


def main():
    parser = argparse.ArgumentParser(
        description="Gemini Fast Ask - Speed-optimized text chat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python -m tools.gemini.fast_ask "What is Python?"
  poetry run python -m tools.gemini.fast_ask --quiet "2+2"
  poetry run python -m tools.gemini.fast_ask --new "fresh conversation"
  poetry run python -m tools.gemini.fast_ask --stop   # Kill browser daemon
  poetry run python -m tools.gemini.fast_ask --status # Check daemon status

For Gem usage, use: ai-gem (tools.gemini.fast_gem)
""",
    )
    parser.add_argument("prompt", nargs="?", default=None, help="The prompt to send")
    parser.add_argument("--file", type=str, default=None, help="Read prompt from text file")
    parser.add_argument("--new", action="store_true", default=False, help="Force new conversation")
    parser.add_argument("--quiet", action="store_true", default=False, help="Only print response")
    parser.add_argument("--stop", action="store_true", default=False, help="Stop browser daemon")
    parser.add_argument("--status", action="store_true", default=False, help="Show daemon status")
    parser.add_argument("--login", action="store_true", default=False, help="Force re-login (uses slow mode)")

    args = parser.parse_args()

    if args.stop:
        BrowserDaemon.stop()
        return

    if args.status:
        BrowserDaemon.status()
        return

    if args.login:
        # Stop daemon first (it locks the profile)
        BrowserDaemon.stop()
        # Fall back to regular GeminiAsk for login flow
        from tools.gemini.ask import GeminiAsk
        tool = GeminiAsk(quiet=args.quiet)
        response = tool.run(
            prompt=args.prompt or "hello",
            headless=False,
            force_login=True,
        )
        if not response:
            sys.exit(1)
        return

    if not args.prompt and not args.file:
        parser.print_help()
        sys.exit(1)

    tool = GeminiFastAsk(quiet=args.quiet)
    response = tool.run_fast(
        prompt=args.prompt or "",
        force_new=args.new,
        file_path=args.file,
    )

    if not response:
        sys.exit(1)


if __name__ == "__main__":
    main()
