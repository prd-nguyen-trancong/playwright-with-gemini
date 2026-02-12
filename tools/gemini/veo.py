"""
Gemini Veo - Generate videos using Gemini's "Create videos (Veo 3.1)" tool.

Activates the video creation tool from the Tools dropdown, sends a prompt,
waits for the video to be generated, and downloads it.

Usage:
    poetry run python -m tools.gemini.veo "a man dancing in the street"
    poetry run python -m tools.gemini.veo --output output/dance.mp4 "a man dancing"
    poetry run python -m tools.gemini.veo --quiet "a cat playing piano"
"""

import argparse
import os
import sys
import time

from tools.gemini.base import GeminiBase


class GeminiVeo(GeminiBase):
    """Generate videos using Gemini's built-in Create videos (Veo) tool."""

    TOOL_NAME = "Create videos"
    TOOL_LABEL = "veo"
    DEFAULT_EXT = ".mp4"

    def _wait_for_response(self, page, **kwargs):
        """Wait for Gemini to generate a video and download it."""
        output_path = kwargs.get("output_path") or self.default_output_path()
        output_path = self.resolve_output_path(output_path, self.default_output_path())

        self.log("      Waiting for video generation (this may take a few minutes)", end="")

        start = time.time()
        timeout_seconds = 300  # 5 minutes for video generation
        stable_count = 0
        last_state = ""

        while time.time() - start < timeout_seconds:
            try:
                result = page.evaluate("""() => {
                    const stopBtn = document.querySelector('button[aria-label*="Stop"]');
                    const isGenerating = stopBtn && stopBtn.offsetParent !== null;

                    const modelResp = document.querySelectorAll('model-response');
                    let videos = [];
                    let videoSrcs = [];

                    for (const resp of modelResp) {
                        const vids = resp.querySelectorAll('video');
                        for (const vid of vids) {
                            const src = vid.src || vid.currentSrc || '';
                            const sources = vid.querySelectorAll('source');
                            let sourceSrc = '';
                            for (const s of sources) {
                                sourceSrc = s.src || sourceSrc;
                            }
                            const finalSrc = src || sourceSrc;
                            videos.push({
                                src: finalSrc.substring(0, 800),
                                width: vid.videoWidth || vid.width || 0,
                                height: vid.videoHeight || vid.height || 0,
                            });
                            if (finalSrc) videoSrcs.push(finalSrc);
                        }
                    }

                    // Get text response
                    let text = '';
                    if (modelResp.length > 0) {
                        text = (modelResp[modelResp.length - 1].innerText || '').trim();
                    }

                    // Detect "generating" state from text (Gemini shows this message)
                    const isTextGenerating = text.includes('generating your video');

                    return {
                        isGenerating: isGenerating || isTextGenerating,
                        videoCount: videos.length,
                        videoSrcs: videoSrcs,
                        text: text.substring(0, 500),
                    };
                }""")

                is_generating = result.get("isGenerating", False)
                video_count = result.get("videoCount", 0)
                video_srcs = result.get("videoSrcs", [])
                text = result.get("text", "")

                state = f"{video_count}:{is_generating}:{len(text)}"

                # Video element appeared and generation is done
                if video_count > 0 and not is_generating:
                    if state == last_state:
                        stable_count += 1
                        if stable_count >= 2:
                            self.log(" done!")
                            time.sleep(3)

                            saved = self._download_video(page, output_path, video_srcs)
                            if saved:
                                return saved

                            if text:
                                self.log("      WARNING: Could not download video, returning text")
                                return self._clean_response(text)
                            return None
                    else:
                        stable_count = 0
                    last_state = state

                # Text-only response (Gemini refused or can't generate)
                elif not is_generating and video_count == 0 and text and len(text) > 20:
                    # Exclude the "generating" intermediate message
                    if "generating your video" not in text:
                        if state == last_state:
                            stable_count += 1
                            if stable_count >= 3:
                                self.log(" done (text response)!")
                                return self._clean_response(text)
                        else:
                            stable_count = 0
                        last_state = state

            except Exception:
                pass

            self.log(".", end="")
            time.sleep(5)

        # Timeout
        try:
            text = page.evaluate("""() => {
                const modelResp = document.querySelectorAll('model-response');
                if (modelResp.length > 0)
                    return (modelResp[modelResp.length - 1].innerText || '').trim();
                return '';
            }""")
            if text:
                self.log(" done (timeout, text response)!")
                return self._clean_response(text)
        except Exception:
            pass

        self.log(" timeout (no video generated)")
        return None

    def _download_video(self, page, output_path, video_srcs=None):
        """Download the generated video from Gemini's response."""
        abs_output = os.path.abspath(output_path)

        # Method 1: Use Playwright's download event via the download button (most reliable)
        try:
            download_btn = page.locator(
                'model-response button[aria-label*="Download"], '
                'model-response button[aria-label*="download"], '
                'model-response a[download]'
            ).last

            if download_btn.is_visible(timeout=5000):
                self.log("      Downloading video...")
                with page.expect_download(timeout=60000) as download_info:
                    download_btn.click()
                download = download_info.value
                download.save_as(abs_output)
                size_mb = os.path.getsize(abs_output) / (1024 * 1024)
                self.log(f"      Video saved: {abs_output} ({size_mb:.1f} MB)")
                return abs_output
        except Exception as e:
            self.log(f"      WARNING: Download button failed: {e}")

        # Method 2: Fetch video from src URL
        if not video_srcs:
            try:
                video_srcs = page.evaluate("""() => {
                    const videos = document.querySelectorAll('model-response video');
                    const srcs = [];
                    for (const v of videos) {
                        const src = v.src || v.currentSrc || '';
                        if (src) srcs.push(src);
                    }
                    return srcs;
                }""")
            except Exception:
                video_srcs = []

        for src in (video_srcs or []):
            if src and src.startswith("http"):
                try:
                    self.log("      Downloading video via URL...")
                    video_data = page.evaluate("""(url) => {
                        return new Promise((resolve, reject) => {
                            fetch(url)
                                .then(r => {
                                    if (!r.ok) reject('HTTP ' + r.status);
                                    return r.arrayBuffer();
                                })
                                .then(buf => {
                                    const bytes = new Uint8Array(buf);
                                    let binary = '';
                                    const chunkSize = 8192;
                                    for (let i = 0; i < bytes.length; i += chunkSize) {
                                        const chunk = bytes.subarray(i, i + chunkSize);
                                        binary += String.fromCharCode.apply(null, chunk);
                                    }
                                    resolve(btoa(binary));
                                })
                                .catch(e => reject(String(e)));
                        });
                    }""", src)

                    if video_data:
                        import base64

                        video_bytes = base64.b64decode(video_data)
                        with open(abs_output, "wb") as f:
                            f.write(video_bytes)
                        size_mb = len(video_bytes) / (1024 * 1024)
                        self.log(f"      Video saved: {abs_output} ({size_mb:.1f} MB)")
                        return abs_output
                except Exception as e:
                    self.log(f"      WARNING: URL download failed: {e}")

        # Method 3: Save thumbnail as evidence
        try:
            video_el = page.locator("model-response video").last
            if video_el.is_visible(timeout=3000):
                thumb_path = abs_output.replace(".mp4", "_thumb.png")
                video_el.screenshot(path=thumb_path)
                self.log(f"      Video thumbnail saved: {thumb_path}")
                self.log("      NOTE: Full video may need manual download from browser")
        except Exception:
            pass

        return None


def main():
    parser = argparse.ArgumentParser(
        description="Gemini Veo - Generate videos using Create videos (Veo 3.1) tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  poetry run python -m tools.gemini.veo "a man dancing in the street"
  poetry run python -m tools.gemini.veo --output output/dance.mp4 "a cat playing piano"
  poetry run python -m tools.gemini.veo --quiet "a sunset timelapse"
  poetry run python -m tools.gemini.veo --login "a bird flying"
""",
    )
    parser.add_argument("prompt", help="The video generation prompt")
    parser.add_argument("--no-headless", action="store_true", default=False, help="Show browser")
    parser.add_argument("--output", type=str, default=None, help="Output video path")
    parser.add_argument("--screenshot", type=str, default=None, help="Save page screenshot")
    parser.add_argument("--login", action="store_true", default=False, help="Force re-login")
    parser.add_argument("--quiet", action="store_true", default=False, help="Only print output path")

    args = parser.parse_args()

    tool = GeminiVeo(quiet=args.quiet)
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
