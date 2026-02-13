package story

import (
	"fmt"
	"os"
	"path/filepath"

	"github.com/prd-nguyen-trancong/gemini-tools/internal/browser"
	"github.com/prd-nguyen-trancong/gemini-tools/internal/gemini"
)

const (
	DefaultGemID = "dcca1e614968" // Tóm tắt truyện V3
)

// Summary orchestrates scraping and summarization using Scraper and FastGem.
type Summary struct {
	quiet    bool
	GemID    string
	scraper  *Scraper
	gem      *gemini.FastGem
	outputDir string
}

// NewSummary creates a new Summary instance.
func NewSummary(quiet bool, gemID string) *Summary {
	if gemID == "" {
		gemID = DefaultGemID
	}
	return &Summary{
		quiet:    quiet,
		GemID:    gemID,
		scraper:  NewScraper(quiet),
		gem:      gemini.NewFastGem(quiet),
		outputDir: filepath.Join(browser.ScriptDir(), "output_summary_story"),
	}
}

func (s *Summary) log(format string, args ...interface{}) {
	if !s.quiet {
		fmt.Printf(format+"\n", args...)
	}
}

// GetSummary uses FastGem to summarize content.
func (s *Summary) GetSummary(content string) (string, error) {
	return s.gem.RunFast(content, s.GemID, false, "")
}

// SaveSummary saves summary to output_summary_story/<slug>.txt.
func (s *Summary) SaveSummary(slug, summary string) (string, error) {
	os.MkdirAll(s.outputDir, 0o755)
	filename := slug + ".txt"
	outPath := filepath.Join(s.outputDir, filename)
	if err := os.WriteFile(outPath, []byte(summary), 0o644); err != nil {
		return "", fmt.Errorf("write summary: %w", err)
	}
	s.log("  Summary saved: %s", outPath)
	return outPath, nil
}

// RunSingle performs the full workflow for a single chapter: scrape -> summarize -> save.
func (s *Summary) RunSingle(url string) (string, error) {
	s.log("\n%s", sep())
	s.log("  Story Summary")
	s.log("%s", sep())
	s.log("  URL     : %s", url)
	s.log("  Gem     : %s", s.GemID)
	s.log("%s\n", sep())

	// Step 1: Scrape
	s.log("[1/3] Scraping chapter...")
	result, err := s.scraper.ScrapeChapter(url)
	if err != nil {
		s.log("  ERROR: Failed to scrape chapter: %v", err)
		return "", err
	}

	// Step 2: Check if summary already exists (resume support)
	summaryPath := filepath.Join(s.outputDir, result.Slug+".txt")
	if _, err := os.Stat(summaryPath); err == nil {
		s.log("  SKIP: Summary already exists: %s", summaryPath)
		data, _ := os.ReadFile(summaryPath)
		return string(data), nil
	}

	// Step 3: Summarize via Gem service (prepend title to content)
	s.log("\n[2/3] Summarizing with Gem...")
	promptContent := result.Content
	if result.Title != "" {
		promptContent = result.Title + "\n\n" + result.Content
	}
	summary, err := s.GetSummary(promptContent)
	if err != nil {
		s.log("  ERROR: Failed to get summary: %v", err)
		return "", err
	}

	// Step 4: Save summary
	s.log("\n[3/3] Saving summary...")
	s.SaveSummary(result.Slug, summary)

	s.log("\n%s", sep())
	s.log("  Done!")
	s.log("  Summary: output_summary_story/%s.txt", result.Slug)
	s.log("%s\n", sep())

	return summary, nil
}

// RunBatch scrapes and summarizes a range of chapters.
func (s *Summary) RunBatch(baseURL string, fromChap, toChap int) {
	if baseURL[len(baseURL)-1] != '/' {
		baseURL += "/"
	}

	total := toChap - fromChap + 1
	s.log("\n%s", sep())
	s.log("  Batch Story Summary")
	s.log("%s", sep())
	s.log("  Base URL : %s", baseURL)
	s.log("  Chapters : %d to %d (%d chapters)", fromChap, toChap, total)
	s.log("  Gem      : %s", s.GemID)
	s.log("%s\n", sep())

	successCount := 0
	skipCount := 0
	failCount := 0

	for n := fromChap; n <= toChap; n++ {
		chapterURL := fmt.Sprintf("%schuong-%d/", baseURL, n)
		slug := fmt.Sprintf("chuong-%d", n)

		s.log("\n--- Chapter %d/%d (%s) ---", n, toChap, slug)

		// Check if summary already exists
		summaryPath := filepath.Join(s.outputDir, slug+".txt")
		if _, err := os.Stat(summaryPath); err == nil {
			s.log("  SKIP: Summary already exists")
			skipCount++
			continue
		}

		// Scrape
		s.log("  Scraping...")
		result, err := s.scraper.ScrapeChapter(chapterURL)
		if err != nil {
			s.log("  FAIL: Could not scrape chapter %d: %v", n, err)
			failCount++
			continue
		}

		// Summarize via Gem service (prepend title to content)
		s.log("  Summarizing...")
		promptContent := result.Content
		if result.Title != "" {
			promptContent = result.Title + "\n\n" + result.Content
		}
		summary, err := s.GetSummary(promptContent)
		if err != nil {
			s.log("  FAIL: Could not summarize chapter %d: %v", n, err)
			failCount++
			continue
		}

		// Save
		s.SaveSummary(slug, summary)
		successCount++
		s.log("  OK: %s.txt", slug)
	}

	s.log("\n%s", sep())
	s.log("  Batch Complete!")
	s.log("  Success: %d | Skipped: %d | Failed: %d", successCount, skipCount, failCount)
	s.log("  Output: output_summary_story/")
	s.log("%s\n", sep())
}

func sep() string {
	return "============================================================"
}
