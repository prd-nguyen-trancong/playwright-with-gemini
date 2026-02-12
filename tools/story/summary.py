"""
Story Summary - Scrape story chapters and summarize via Gemini Gem service.

Uses GeminiFastGem as a service for summarization (reuses the "gem" role tab
and all speed optimizations). No duplicated Gem interaction code.

Workflow:
1. Scrape chapter content from truyenfull.vision
2. Send content to GeminiFastGem for summarization
3. Save summary to output_summary_story/<slug>.txt
4. Limit 10 requests per Gem session (auto-resets via fast_gem)

Usage:
    # Single chapter
    poetry run python -m tools.story.summary \\
        "https://truyenfull.vision/pham-nhan-tu-tien-.../chuong-1201/"

    # Batch: chapters 1201 to 1211
    poetry run python -m tools.story.summary \\
        --from 1201 --to 1211 \\
        "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"
"""

import argparse
import functools
import os
import sys

from tools.gemini.fast_gem import GeminiFastGem
from tools.story.scraper import StoryScraper

_print = functools.partial(print, flush=True)

SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_SUMMARY_DIR = os.path.join(SCRIPT_DIR, "output_summary_story")

DEFAULT_GEM_ID = "dcca1e614968"  # Tóm tắt truyện V3


class StorySummary:
    """Scrape story chapters and summarize using GeminiFastGem as a service."""

    def __init__(self, quiet=False, gem_id=None):
        self._quiet = quiet
        self.gem_id = gem_id or DEFAULT_GEM_ID
        self._scraper = StoryScraper(quiet=quiet)
        self._gem = GeminiFastGem(quiet=quiet)

    def log(self, msg="", end="\n"):
        if not self._quiet:
            _print(msg, end=end)

    def get_summary(self, content):
        """
        Use GeminiFastGem service to summarize content.

        Parameters
        ----------
        content : str
            The raw chapter text to summarize.

        Returns
        -------
        str or None
            The summary text, or None on failure.
        """
        return self._gem.run_fast(
            prompt=content,
            gem_id=self.gem_id,
        )

    def save_summary(self, slug, summary):
        """Save summary to output_summary_story/<slug>.txt."""
        os.makedirs(OUTPUT_SUMMARY_DIR, exist_ok=True)
        filename = f"{slug}.txt"
        filepath = os.path.join(OUTPUT_SUMMARY_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(summary)
        self.log(f"  Summary saved: {filepath}")
        return filepath

    def run_single(self, url):
        """
        Full workflow for a single chapter: scrape -> summarize -> save.

        Returns the summary text or None.
        """
        self.log(f"\n{'=' * 60}")
        self.log("  Story Summary")
        self.log(f"{'=' * 60}")
        self.log(f"  URL     : {url}")
        self.log(f"  Gem     : {self.gem_id}")
        self.log(f"{'=' * 60}\n")

        # Step 1: Scrape
        self.log("[1/3] Scraping chapter...")
        slug, title, content = self._scraper.scrape_chapter(url)
        if not slug or not content:
            self.log("  ERROR: Failed to scrape chapter")
            return None

        # Step 2: Check if summary already exists (resume support)
        summary_path = os.path.join(OUTPUT_SUMMARY_DIR, f"{slug}.txt")
        if os.path.exists(summary_path):
            self.log(f"  SKIP: Summary already exists: {summary_path}")
            with open(summary_path, encoding="utf-8") as f:
                return f.read()

        # Step 3: Summarize via Gem service (prepend title to content)
        self.log("\n[2/3] Summarizing with Gem...")
        prompt_content = f"{title}\n\n{content}" if title else content
        summary = self.get_summary(prompt_content)
        if not summary:
            self.log("  ERROR: Failed to get summary")
            return None

        # Step 4: Save summary
        self.log("\n[3/3] Saving summary...")
        self.save_summary(slug, summary)

        self.log(f"\n{'=' * 60}")
        self.log("  Done!")
        self.log(f"  Summary: output_summary_story/{slug}.txt")
        self.log(f"{'=' * 60}\n")

        return summary

    def run_batch(self, base_url, from_chap, to_chap):
        """
        Scrape and summarize a range of chapters.

        Parameters
        ----------
        base_url : str
            Base URL without the chapter suffix.
            e.g. "https://truyenfull.vision/pham-nhan-tu-tien-.../".
        from_chap : int
            Starting chapter number.
        to_chap : int
            Ending chapter number (inclusive).
        """
        # Ensure base_url ends with /
        if not base_url.endswith("/"):
            base_url += "/"

        total = to_chap - from_chap + 1
        self.log(f"\n{'=' * 60}")
        self.log(f"  Batch Story Summary")
        self.log(f"{'=' * 60}")
        self.log(f"  Base URL : {base_url}")
        self.log(f"  Chapters : {from_chap} to {to_chap} ({total} chapters)")
        self.log(f"  Gem      : {self.gem_id}")
        self.log(f"{'=' * 60}\n")

        success_count = 0
        skip_count = 0
        fail_count = 0

        for n in range(from_chap, to_chap + 1):
            chapter_url = f"{base_url}chuong-{n}/"
            slug = f"chuong-{n}"

            self.log(f"\n--- Chapter {n}/{to_chap} ({slug}) ---")

            # Check if summary already exists
            summary_path = os.path.join(OUTPUT_SUMMARY_DIR, f"{slug}.txt")
            if os.path.exists(summary_path):
                self.log(f"  SKIP: Summary already exists")
                skip_count += 1
                continue

            # Scrape
            self.log("  Scraping...")
            scraped_slug, title, content = self._scraper.scrape_chapter(chapter_url)
            if not content:
                self.log(f"  FAIL: Could not scrape chapter {n}")
                fail_count += 1
                continue

            # Summarize via Gem service (prepend title to content)
            self.log("  Summarizing...")
            prompt_content = f"{title}\n\n{content}" if title else content
            summary = self.get_summary(prompt_content)
            if not summary:
                self.log(f"  FAIL: Could not summarize chapter {n}")
                fail_count += 1
                continue

            # Save - use the slug from URL (chuong-N) for consistency
            self.save_summary(slug, summary)
            success_count += 1
            self.log(f"  OK: {slug}.txt")

        self.log(f"\n{'=' * 60}")
        self.log(f"  Batch Complete!")
        self.log(f"  Success: {success_count} | Skipped: {skip_count} | Failed: {fail_count}")
        self.log(f"  Output: output_summary_story/")
        self.log(f"{'=' * 60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Story Summary - Scrape and summarize story chapters via Gemini Gem",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single chapter
  poetry run python -m tools.story.summary \\
    "https://truyenfull.vision/pham-nhan-tu-tien-.../chuong-1201/"

  # Batch: chapters 1201 to 1211
  poetry run python -m tools.story.summary \\
    --from 1201 --to 1211 \\
    "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"

  # With custom Gem
  poetry run python -m tools.story.summary \\
    --gem dcca1e614968 --from 1201 --to 1211 \\
    "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"
""",
    )
    parser.add_argument("url", help="Chapter URL or base URL (for batch mode)")
    parser.add_argument(
        "--gem", type=str, default=DEFAULT_GEM_ID,
        help=f"Gem ID for summarization (default: {DEFAULT_GEM_ID})"
    )
    parser.add_argument("--from", type=int, default=None, dest="from_chap",
                        help="Starting chapter number (batch mode)")
    parser.add_argument("--to", type=int, default=None, dest="to_chap",
                        help="Ending chapter number (batch mode, inclusive)")
    parser.add_argument("--quiet", action="store_true", default=False, help="Only print summaries")

    args = parser.parse_args()

    tool = StorySummary(quiet=args.quiet, gem_id=args.gem)

    if args.from_chap is not None and args.to_chap is not None:
        # Batch mode
        tool.run_batch(
            base_url=args.url,
            from_chap=args.from_chap,
            to_chap=args.to_chap,
        )
    else:
        # Single chapter mode
        summary = tool.run_single(url=args.url)
        if not summary:
            sys.exit(1)


if __name__ == "__main__":
    main()
