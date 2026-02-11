"""
Gemini Ask - Send text prompts and get text responses.

Usage:
    poetry run python -m tools.ask "What is Python?"
    poetry run python -m tools.ask --file image.png "describe this image"
    poetry run python -m tools.ask --quiet "2+2"
    poetry run python -m tools.ask --login "Hello"
"""

import argparse
import sys
import time

from tools.base import GeminiBase


class GeminiAsk(GeminiBase):
    """Send a text prompt to Gemini and get a text response."""

    TOOL_NAME = None  # No tool activation needed (plain chat)
    TOOL_LABEL = "ask"
    DEFAULT_EXT = ".txt"

    def _wait_for_response(self, page, **kwargs):
        """Wait for Gemini to finish generating a text response."""
        self.log("      Waiting for response", end="")

        start = time.time()
        last_text = ""
        stable_count = 0
        timeout_seconds = 120

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

                    return { isGenerating: isGenerating, text: text };
                }""")

                response_text = result.get("text", "")
                is_generating = result.get("isGenerating", False)

                if response_text and len(response_text) > 5:
                    if not is_generating:
                        if response_text == last_text:
                            stable_count += 1
                            if stable_count >= 2:
                                self.log(" done!")
                                time.sleep(1)
                                return self._clean_response(response_text)
                        else:
                            stable_count = 0
                        last_text = response_text

            except Exception:
                pass

            self.log(".", end="")
            time.sleep(2)

        if last_text:
            self.log(" done (timeout, returning partial)!")
            return self._clean_response(last_text)

        self.log(" timeout (no response detected)")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Gemini Ask - Send prompts and get text responses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python -m tools.ask "What is Python?"
  poetry run python -m tools.ask --file photo.jpg "describe this image"
  poetry run python -m tools.ask --quiet "Hello"
  poetry run python -m tools.ask --login "Hello"
""",
    )
    parser.add_argument("prompt", help="The prompt to send to Gemini")
    parser.add_argument("--no-headless", action="store_true", default=False, help="Show browser")
    parser.add_argument("--file", type=str, default=None, help="Attach image file to prompt")
    parser.add_argument("--screenshot", type=str, default=None, help="Save page screenshot")
    parser.add_argument("--login", action="store_true", default=False, help="Force re-login")
    parser.add_argument("--quiet", action="store_true", default=False, help="Only print the response")

    args = parser.parse_args()

    tool = GeminiAsk(quiet=args.quiet)
    response = tool.run(
        prompt=args.prompt,
        headless=not args.no_headless,
        image_path=args.file,
        save_screenshot=args.screenshot,
        force_login=args.login,
    )

    if not response:
        sys.exit(1)


if __name__ == "__main__":
    main()
