// go-story-summary: Scrape story chapters and summarize via Gemini Gem.
//
// Usage:
//
//	go-story-summary "https://truyenfull.vision/.../chuong-1201/"
//	go-story-summary --from 1201 --to 1211 "https://truyenfull.vision/.../"
//	go-story-summary --gem dcca1e614968 "https://truyenfull.vision/.../chuong-1201/"
package main

import (
	"flag"
	"fmt"
	"os"
	"strings"

	"github.com/prd-nguyen-trancong/gemini-tools/internal/story"
)

func main() {
	gemID := flag.String("gem", story.DefaultGemID, "Gem ID for summarization")
	fromChap := flag.Int("from", 0, "Starting chapter number (batch mode)")
	toChap := flag.Int("to", 0, "Ending chapter number (batch mode, inclusive)")
	quiet := flag.Bool("quiet", false, "Only print summaries")

	flag.Usage = func() {
		fmt.Fprintf(os.Stderr, `go-story-summary - Scrape and summarize story chapters via Gemini Gem

Usage:
  go-story-summary [flags] "url"

Examples:
  # Single chapter
  go-story-summary "https://truyenfull.vision/pham-nhan-tu-tien-.../chuong-1201/"

  # Batch: chapters 1201 to 1211
  go-story-summary --from 1201 --to 1211 \
    "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"

  # With custom Gem
  go-story-summary --gem dcca1e614968 --from 1201 --to 1211 \
    "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"

Flags:
`)
		flag.PrintDefaults()
	}

	flag.Parse()

	url := strings.Join(flag.Args(), " ")
	if url == "" {
		flag.Usage()
		os.Exit(1)
	}

	tool := story.NewSummary(*quiet, *gemID)

	if *fromChap > 0 && *toChap > 0 {
		// Batch mode
		tool.RunBatch(url, *fromChap, *toChap)
	} else {
		// Single chapter mode
		_, err := tool.RunSingle(url)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Error: %v\n", err)
			os.Exit(1)
		}
	}
}
