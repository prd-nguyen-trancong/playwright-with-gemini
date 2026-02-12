"""
Gemini Image - Generate images using Gemini's "Create images" tool.

Activates the "Create images" tool from the Tools dropdown before sending
the prompt, which produces higher quality results than plain text prompts.

Usage:
    poetry run python -m tools.gemini.image "a cute banana cartoon"
    poetry run python -m tools.gemini.image --output output/banana.png "image of a banana"
    poetry run python -m tools.gemini.image --quiet "image of a cat"
"""

import argparse
import base64
import os
import sys
import time

from tools.gemini.base import GeminiBase


class GeminiImage(GeminiBase):
    """Generate images using Gemini's built-in Create images tool."""

    TOOL_NAME = "Create images"
    TOOL_LABEL = "image"
    DEFAULT_EXT = ".png"

    def _wait_for_response(self, page, **kwargs):
        """Wait for Gemini to generate an image and download it."""
        output_path = kwargs.get("output_path") or self.default_output_path()
        output_path = self.resolve_output_path(output_path, self.default_output_path())

        self.log("      Waiting for image generation", end="")

        start = time.time()
        stable_count = 0
        last_img_count = 0
        timeout_seconds = 180

        while time.time() - start < timeout_seconds:
            try:
                result = page.evaluate("""() => {
                    const stopBtn = document.querySelector('button[aria-label*="Stop"]');
                    const isGenerating = stopBtn && stopBtn.offsetParent !== null;

                    const modelResp = document.querySelectorAll('model-response');
                    let images = [];
                    for (const resp of modelResp) {
                        const imgs = resp.querySelectorAll('img');
                        for (const img of imgs) {
                            const src = img.src || '';
                            if (img.naturalWidth > 100 || img.width > 100 ||
                                src.startsWith('data:') || src.includes('blob:')) {
                                images.push({
                                    src: src.substring(0, 200),
                                    width: img.naturalWidth || img.width,
                                    height: img.naturalHeight || img.height,
                                });
                            }
                        }
                    }

                    let text = '';
                    if (modelResp.length > 0) {
                        text = (modelResp[modelResp.length - 1].innerText || '').trim();
                    }

                    return {
                        isGenerating: isGenerating,
                        imageCount: images.length,
                        images: images,
                        text: text,
                    };
                }""")

                is_generating = result.get("isGenerating", False)
                img_count = result.get("imageCount", 0)

                if img_count > 0 and not is_generating:
                    if img_count == last_img_count:
                        stable_count += 1
                        if stable_count >= 2:
                            self.log(" done!")
                            time.sleep(2)

                            saved = self._download_image(page, output_path)
                            if saved:
                                return saved
                            else:
                                self.log("      WARNING: Could not save image, returning text")
                                return self._clean_response(result.get("text", ""))
                    else:
                        stable_count = 0
                    last_img_count = img_count

            except Exception:
                pass

            self.log(".", end="")
            time.sleep(3)

        # Timeout - check for text response
        try:
            text = page.evaluate("""() => {
                const modelResp = document.querySelectorAll('model-response');
                if (modelResp.length > 0)
                    return (modelResp[modelResp.length - 1].innerText || '').trim();
                return '';
            }""")
            if text:
                self.log(" done (text response only)!")
                return self._clean_response(text)
        except Exception:
            pass

        self.log(" timeout (no image generated)")
        return None

    def _download_image(self, page, output_path):
        """Download the last generated image from Gemini's response."""
        try:
            img_info = page.evaluate("""() => {
                const modelResp = document.querySelectorAll('model-response');
                let lastImg = null;
                for (const resp of modelResp) {
                    const imgs = resp.querySelectorAll('img');
                    for (const img of imgs) {
                        if (img.naturalWidth > 100 || img.width > 100) {
                            lastImg = img;
                        }
                    }
                }
                if (!lastImg) return null;

                try {
                    const canvas = document.createElement('canvas');
                    canvas.width = lastImg.naturalWidth || lastImg.width;
                    canvas.height = lastImg.naturalHeight || lastImg.height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(lastImg, 0, 0);
                    return {
                        dataUrl: canvas.toDataURL('image/png'),
                        width: canvas.width,
                        height: canvas.height,
                    };
                } catch(e) {
                    const rect = lastImg.getBoundingClientRect();
                    return {
                        rect: {
                            x: rect.x, y: rect.y,
                            width: rect.width, height: rect.height,
                        },
                        width: lastImg.naturalWidth,
                        height: lastImg.naturalHeight,
                    };
                }
            }""")

            if not img_info:
                return None

            if "dataUrl" in img_info:
                data_url = img_info["dataUrl"]
                _, data = data_url.split(",", 1)
                img_bytes = base64.b64decode(data)
                abs_output = os.path.abspath(output_path)
                with open(abs_output, "wb") as f:
                    f.write(img_bytes)
                self.log(
                    f"      Image saved: {abs_output} "
                    f"({img_info['width']}x{img_info['height']})"
                )
                return abs_output

            if "rect" in img_info:
                abs_output = os.path.abspath(output_path)
                img_el = page.locator("model-response img").last
                img_el.screenshot(path=abs_output)
                self.log(f"      Image saved: {abs_output}")
                return abs_output

        except Exception as e:
            self.log(f"      WARNING: Image download failed: {e}")

        return None


def main():
    parser = argparse.ArgumentParser(
        description="Gemini Image - Generate images using Create images tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python -m tools.gemini.image "a cute banana cartoon"
  poetry run python -m tools.gemini.image --output output/banana.png "image of a banana"
  poetry run python -m tools.gemini.image --quiet "image of a cat"
  poetry run python -m tools.gemini.image --login "image of a dog"
""",
    )
    parser.add_argument("prompt", help="The image generation prompt")
    parser.add_argument("--no-headless", action="store_true", default=False, help="Show browser")
    parser.add_argument("--output", type=str, default=None, help="Output image path")
    parser.add_argument("--screenshot", type=str, default=None, help="Save page screenshot")
    parser.add_argument("--login", action="store_true", default=False, help="Force re-login")
    parser.add_argument("--quiet", action="store_true", default=False, help="Only print output path")

    args = parser.parse_args()

    tool = GeminiImage(quiet=args.quiet)
    response = tool.run(
        prompt=args.prompt,
        headless=not args.no_headless,
        save_screenshot=args.screenshot,
        force_login=args.login,
        output_path=args.output,
    )

    if not response:
        sys.exit(1)


if __name__ == "__main__":
    main()
