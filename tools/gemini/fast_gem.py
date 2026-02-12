"""
Gemini Fast Gem - Speed-optimized Gem chat using a persistent browser daemon.

Uses a dedicated "gem" tab in the daemon so it never interferes with ai-ask.
Both ai-ask and ai-gem can run in parallel on the same daemon.

First call:  ~10-15s (launches browser + navigates to Gem)
Subsequent:  ~4-5s (connect + send prompt + wait response)

Usage:
    poetry run python -m tools.gemini.fast_gem dcca1e614968 "Summarize this"
    poetry run python -m tools.gemini.fast_gem --quiet dcca1e614968 "2+2"
    poetry run python -m tools.gemini.fast_gem --new dcca1e614968 "fresh conversation"
    poetry run python -m tools.gemini.fast_gem --file story.txt dcca1e614968 "summarize"
"""

import argparse
import functools
import sys
import time

from tools.gemini.base import GeminiBase
from tools.gemini.browser import BrowserDaemon

_print = functools.partial(print, flush=True)

MAX_PROMPTS_PER_GEM = 10
ROLE = "gem"


class GeminiFastGem(GeminiBase):
    """Speed-optimized Gemini Gem chat using persistent browser daemon."""

    TOOL_NAME = None
    TOOL_LABEL = "fast_gem"
    DEFAULT_EXT = ".txt"

    def __init__(self, quiet=False):
        super().__init__(quiet=quiet)
        self._daemon = BrowserDaemon(quiet=quiet)

    def run_fast(
        self,
        prompt: str,
        gem_id: str,
        force_new: bool = False,
        file_path: str | None = None,
    ):
        """
        Send a prompt to a Gem and get a response using the persistent browser.

        Parameters
        ----------
        prompt : str
            The text prompt to send.
        gem_id : str
            Gem ID to use (e.g. "dcca1e614968").
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

        gem_url = f"https://gemini.google.com/gem/{gem_id}"

        try:
            # Step 1: Ensure browser daemon is running
            state = self._daemon.ensure_browser()
            count = state.get("gem_count", 0)
            current_gem = state.get("gem_id")

            # Step 2: Decide whether to reuse or start new conversation
            gem_changed = current_gem is not None and current_gem != gem_id
            need_new = force_new or count >= MAX_PROMPTS_PER_GEM or gem_changed

            if need_new:
                reason = "limit reached" if count >= MAX_PROMPTS_PER_GEM else (
                    "gem changed" if gem_changed else "forced"
                )
                self.log(f"  Starting new Gem conversation ({reason})...")
                browser, page = self._daemon.new_conversation(ROLE, gem_url)
                count = 0
                # Wait for the Gem page to fully load after navigation
                time.sleep(2)
            else:
                browser, page = self._daemon.get_page(ROLE, gem_url)

                # If the gem tab isn't on the right Gem, navigate
                if f"/gem/{gem_id}" not in page.url:
                    self.log(f"  Navigating to Gem: {gem_id}")
                    browser, page = self._daemon.new_conversation(ROLE, gem_url)
                    count = 0
                    time.sleep(2)

            # Step 3: Check login and dismiss dialogs on fresh conversations
            if count == 0:
                if not self.is_logged_in(page):
                    self.log("  ERROR: Not logged in. Run: ai-ask --login \"hello\"")
                    self._daemon.release()
                    return None
                self._dismiss_dialogs(page)

            # Step 4: Count existing responses before sending
            prev_count = page.evaluate(
                "() => document.querySelectorAll('model-response').length"
            )

            # Step 5: Send prompt
            self.log(f"  Gem: {gem_id} | Sending prompt ({count + 1}/{MAX_PROMPTS_PER_GEM})...")
            success = self._send_prompt_fast(page, prompt)
            if not success:
                self.log("  ERROR: Failed to send prompt")
                self._daemon.release()
                return None

            # Step 6: Wait for response (only look at responses after prev_count)
            self.log("  Waiting for response", end="")
            response = self._wait_for_text_response(page, prev_response_count=prev_count)

            # Step 6: Update state (track gem_id so we detect gem switches)
            BrowserDaemon.update_state(gem_count=count + 1, gem_id=gem_id)

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

    def _wait_for_text_response(self, page, timeout_seconds=120, prev_response_count=0):
        """Wait for text response - fast polling version.

        Parameters
        ----------
        page : Page
            The Playwright page to poll.
        timeout_seconds : int
            Maximum time to wait.
        prev_response_count : int
            Number of model-response elements that existed before the prompt
            was sent. Only responses after this index are considered.
        """
        start = time.time()
        last_text = ""
        stable_count = 0

        while time.time() - start < timeout_seconds:
            try:
                result = page.evaluate("""(prevCount) => {
                    const stopBtn = document.querySelector('button[aria-label*="Stop"]');
                    const isGenerating = stopBtn && stopBtn.offsetParent !== null;

                    const modelResp = document.querySelectorAll('model-response');
                    let text = '';
                    // Only look at responses AFTER prevCount (new responses)
                    if (modelResp.length > prevCount) {
                        text = (modelResp[modelResp.length - 1].innerText || '').trim();
                    }
                    if (!text && modelResp.length > prevCount) {
                        const msgs = document.querySelectorAll('message-content');
                        if (msgs.length > prevCount) {
                            text = (msgs[msgs.length - 1].innerText || '').trim();
                        }
                    }
                    return { g: isGenerating, t: text, c: modelResp.length };
                }""", prev_response_count)

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
        description="Gemini Fast Gem - Speed-optimized Gem chat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python -m tools.gemini.fast_gem dcca1e614968 "Tóm tắt chương này"
  poetry run python -m tools.gemini.fast_gem --quiet dcca1e614968 "2+2"
  poetry run python -m tools.gemini.fast_gem --new dcca1e614968 "fresh conversation"
  poetry run python -m tools.gemini.fast_gem --file story.txt dcca1e614968 "summarize"

For regular chat (no Gem), use: ai-ask (tools.gemini.fast_ask)
""",
    )
    parser.add_argument("gem_id", help="Gem ID (e.g. dcca1e614968)")
    parser.add_argument("prompt", nargs="?", default=None, help="The prompt to send")
    parser.add_argument("--file", type=str, default=None, help="Read prompt from text file")
    parser.add_argument("--new", action="store_true", default=False, help="Force new conversation")
    parser.add_argument("--quiet", action="store_true", default=False, help="Only print response")

    args = parser.parse_args()

    if not args.prompt and not args.file:
        parser.print_help()
        sys.exit(1)

    tool = GeminiFastGem(quiet=args.quiet)
    response = tool.run_fast(
        prompt=args.prompt or "",
        gem_id=args.gem_id,
        force_new=args.new,
        file_path=args.file,
    )

    if not response:
        sys.exit(1)


if __name__ == "__main__":
    main()
