// go-ai-gem: Speed-optimized Gemini Gem chat using persistent browser daemon (Go/Rod).
//
// Uses a dedicated "gem" tab - completely separate from go-ai-ask.
// Both can run in parallel without interference.
//
// Usage:
//
//	go-ai-gem dcca1e614968 "tóm tắt chương này"
//	go-ai-gem --file story.txt dcca1e614968 "summarize"
//	go-ai-gem --new dcca1e614968 "fresh conversation"
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/prd-nguyen-trancong/gemini-tools/internal/gemini"
)

func main() {
	// Pre-process args: extract flags that may appear after positional args.
	// Go's flag package stops at the first non-flag arg, so we need to
	// pull out known flags from anywhere in the arg list.
	var rawArgs []string
	var filePath, gemID, prompt string
	var forceNew, quiet bool

	rawArgs = os.Args[1:]
	var positional []string

	for i := 0; i < len(rawArgs); i++ {
		arg := rawArgs[i]
		switch {
		case arg == "--file" || arg == "-file":
			if i+1 < len(rawArgs) {
				i++
				filePath = rawArgs[i]
			}
		case strings.HasPrefix(arg, "--file=") || strings.HasPrefix(arg, "-file="):
			filePath = strings.SplitN(arg, "=", 2)[1]
		case arg == "--new" || arg == "-new":
			forceNew = true
		case arg == "--quiet" || arg == "-quiet":
			quiet = true
		case arg == "--help" || arg == "-help" || arg == "-h":
			printUsage()
			os.Exit(0)
		default:
			positional = append(positional, arg)
		}
	}

	if len(positional) < 1 {
		printUsage()
		os.Exit(1)
	}

	gemID = positional[0]
	if len(positional) > 1 {
		prompt = strings.Join(positional[1:], " ")
	}

	if prompt == "" && filePath == "" {
		printUsage()
		os.Exit(1)
	}

	tool := gemini.NewFastGem(quiet)
	_, err := tool.RunFast(prompt, gemID, forceNew, filePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintf(os.Stderr, `go-ai-gem - Speed-optimized Gemini Gem chat (Go/Rod)

Usage:
  go-ai-gem [flags] <gem_id> "prompt"
  go-ai-gem <gem_id> --file content.txt
  go-ai-gem <gem_id> --file content.txt "translate this"

Examples:
  go-ai-gem dcca1e614968 "tóm tắt chương này"
  go-ai-gem 3f9e2319b62e --file japanese.txt
  go-ai-gem --quiet --file story.txt dcca1e614968 "summarize"
  go-ai-gem --new dcca1e614968 "fresh conversation"

Flags:
  --file string   Read content from text file (as prompt or appended to prompt)
  --new           Force new conversation
  --quiet         Only print response (no debug output)

For regular chat (no Gem), use: go-ai-ask
`)
}
