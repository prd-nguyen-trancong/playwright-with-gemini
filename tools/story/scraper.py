"""
Story Scraper - Scrape story chapters from truyenfull.vision.

Uses the browser daemon's "scrape" role tab to navigate to chapter URLs
and extract the raw text content.

Usage:
    from tools.story.scraper import StoryScraper

    scraper = StoryScraper()
    title, content = scraper.scrape_chapter(url)
"""

import functools
import re
import time

from tools.gemini.browser import BrowserDaemon

_print = functools.partial(print, flush=True)


def _slug_from_url(url):
    """
    Extract a slug from a chapter URL.

    For 'https://truyenfull.vision/.../chuong-1201/', returns 'chuong-1201'.
    """
    # Remove trailing slash and get the last path segment
    path = url.rstrip("/").split("/")[-1]
    # Clean: keep only alphanumeric, hyphens, underscores
    slug = re.sub(r"[^a-zA-Z0-9\-_]", "", path)
    return slug or "unknown-chapter"


class StoryScraper:
    """Scrape story chapters from truyenfull.vision using the browser daemon."""

    def __init__(self, quiet=False):
        self._quiet = quiet
        self._daemon = BrowserDaemon(quiet=quiet)

    def log(self, msg="", end="\n"):
        if not self._quiet:
            _print(msg, end=end)

    def scrape_chapter(self, url):
        """
        Scrape a chapter from truyenfull.vision.

        Returns
        -------
        tuple : (slug, title, content) or (None, None, None) on failure
            slug is derived from the URL (e.g. "chuong-1201")
            title is the chapter title (e.g. "Chương 1201: Lộ ra manh mối")
            content is the raw chapter text
        """
        slug = _slug_from_url(url)
        self.log(f"  Scraping: {url}")
        self.log(f"  Slug: {slug}")

        try:
            self._daemon.ensure_browser()
            browser, scrape_page = self._daemon.get_page("scrape", url)

            # Always navigate to the chapter URL (the tab may be reused)
            scrape_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                scrape_page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(2)

            # Extract chapter title and content
            result = scrape_page.evaluate("""() => {
                // Get chapter title from a.chapter-title element
                let title = '';
                const titleLink = document.querySelector('a.chapter-title');
                if (titleLink) {
                    title = titleLink.textContent.trim();
                }
                // Fallback: h2 or other heading
                if (!title) {
                    const h2 = document.querySelector('h2, .chapter-title');
                    if (h2) title = h2.textContent.trim();
                }
                // Fallback: document title
                if (!title) {
                    title = document.title.split(' - ')[0].trim();
                }

                // Get chapter content
                let content = '';

                // Method 1: chapter-c div (truyenfull standard)
                const chapterDiv = document.querySelector('#chapter-c, .chapter-c');
                if (chapterDiv) {
                    // Clone and remove ads/scripts
                    const clone = chapterDiv.cloneNode(true);
                    const removeEls = clone.querySelectorAll(
                        'script, style, .ads-responsive, .ads-mobile, [id^="ads-"], .incontent-ad'
                    );
                    removeEls.forEach(el => el.remove());
                    content = clone.innerText.trim();
                }

                // Method 2: fallback - main content area
                if (!content) {
                    const main = document.querySelector('.chapter-content, article, .reading-detail');
                    if (main) content = main.innerText.trim();
                }

                return { title: title, content: content };
            }""")

            self._daemon.release()

            title = result.get("title", "")
            content = result.get("content", "")

            if not content:
                self.log("  ERROR: Could not extract chapter content")
                return None, None, None

            self.log(f"  Title: {title}")
            self.log(f"  Content: {len(content)} chars")
            return slug, title, content

        except Exception as e:
            self.log(f"  ERROR scraping: {e}")
            try:
                self._daemon.release()
            except Exception:
                pass
            return None, None, None
