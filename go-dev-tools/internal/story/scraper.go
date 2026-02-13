// Package story provides story scraping and summarization tools.
//
// Mirrors the Python tools/story/ package.
package story

import (
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/prd-nguyen-trancong/gemini-tools/internal/browser"
)

// Scraper scrapes story chapters from truyenfull.vision using the browser daemon.
type Scraper struct {
	quiet  bool
	daemon *browser.Daemon
}

// NewScraper creates a new Scraper instance.
func NewScraper(quiet bool) *Scraper {
	return &Scraper{
		quiet:  quiet,
		daemon: browser.NewDaemon(quiet),
	}
}

func (s *Scraper) log(format string, args ...interface{}) {
	if !s.quiet {
		fmt.Printf(format+"\n", args...)
	}
}

// ChapterResult holds the result of scraping a chapter.
type ChapterResult struct {
	Slug    string
	Title   string
	Content string
}

// ScrapeChapter scrapes a chapter from truyenfull.vision.
// Returns (slug, title, content) or an error.
func (s *Scraper) ScrapeChapter(url string) (*ChapterResult, error) {
	slug := SlugFromURL(url)
	s.log("  Scraping: %s", url)
	s.log("  Slug: %s", slug)

	_, err := s.daemon.EnsureBrowser()
	if err != nil {
		return nil, fmt.Errorf("ensure browser: %w", err)
	}

	_, scrapePage, err := s.daemon.GetPage("scrape", url)
	if err != nil {
		return nil, fmt.Errorf("get scrape page: %w", err)
	}

	// Always navigate to the chapter URL (the tab may be reused)
	scrapePage.MustNavigate(url).MustWaitLoad()
	time.Sleep(2 * time.Second)

	// Extract chapter title and content
	result, err := scrapePage.Eval(`() => {
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
	}`)

	s.daemon.Release()

	if err != nil {
		return nil, fmt.Errorf("evaluate scraper: %w", err)
	}

	title := result.Value.Get("title").String()
	content := result.Value.Get("content").String()

	if content == "" {
		return nil, fmt.Errorf("could not extract chapter content")
	}

	s.log("  Title: %s", title)
	s.log("  Content: %d chars", len(content))

	return &ChapterResult{
		Slug:    slug,
		Title:   title,
		Content: content,
	}, nil
}

// SlugFromURL extracts a slug from a chapter URL.
// For "https://truyenfull.vision/.../chuong-1201/", returns "chuong-1201".
func SlugFromURL(url string) string {
	// Remove trailing slash and get the last path segment
	url = strings.TrimRight(url, "/")
	parts := strings.Split(url, "/")
	path := parts[len(parts)-1]

	// Clean: keep only alphanumeric, hyphens, underscores
	re := regexp.MustCompile(`[^a-zA-Z0-9\-_]`)
	slug := re.ReplaceAllString(path, "")

	if slug == "" {
		return "unknown-chapter"
	}
	return slug
}

// GetDaemon returns the underlying daemon for shared use.
func (s *Scraper) GetDaemon() *browser.Daemon {
	return s.daemon
}

// SetDaemon sets a shared daemon instance.
func (s *Scraper) SetDaemon(d *browser.Daemon) {
	s.daemon = d
}
