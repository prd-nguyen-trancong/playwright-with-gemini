// go-ai-ask: Speed-optimized Gemini text chat using persistent browser daemon (Go/Rod).
//
// Usage:
//
//	go-ai-ask "What is Python?"
//	go-ai-ask --file story.txt "summarize this"
//	go-ai-ask --new "start fresh conversation"
//	go-ai-ask --login "hello"
//	go-ai-ask --stop
//	go-ai-ask --status
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/prd-nguyen-trancong/gemini-tools/internal/browser"
	"github.com/prd-nguyen-trancong/gemini-tools/internal/gemini"
)

func main() {
	// Manual arg parsing so flags can appear anywhere (before or after prompt).
	var filePath, prompt string
	var forceNew, quiet, stop, status, login bool
	var positional []string

	for i := 1; i < len(os.Args); i++ {
		arg := os.Args[i]
		switch {
		case arg == "--file" || arg == "-file":
			if i+1 < len(os.Args) {
				i++
				filePath = os.Args[i]
			}
		case strings.HasPrefix(arg, "--file=") || strings.HasPrefix(arg, "-file="):
			filePath = strings.SplitN(arg, "=", 2)[1]
		case arg == "--new" || arg == "-new":
			forceNew = true
		case arg == "--quiet" || arg == "-quiet":
			quiet = true
		case arg == "--stop" || arg == "-stop":
			stop = true
		case arg == "--status" || arg == "-status":
			status = true
		case arg == "--login" || arg == "-login":
			login = true
		case arg == "--help" || arg == "-help" || arg == "-h":
			printUsage()
			os.Exit(0)
		default:
			positional = append(positional, arg)
		}
	}

	if stop {
		browser.Stop()
		return
	}

	if status {
		browser.Status()
		return
	}

	prompt = strings.Join(positional, " ")

	if login {
		if prompt == "" {
			prompt = "hello"
		}
		tool := gemini.NewFastAsk(quiet)
		_, err := tool.Login(prompt)
		if err != nil {
			fmt.Fprintf(os.Stderr, "Login failed: %v\n", err)
			os.Exit(1)
		}
		return
	}

	if prompt == "" && filePath == "" {
		printUsage()
		os.Exit(1)
	}

	tool := gemini.NewFastAsk(quiet)
	_, err := tool.RunFast(prompt, forceNew, filePath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func printUsage() {
	fmt.Fprintf(os.Stderr, `go-ai-ask - Speed-optimized Gemini text chat (Go/Rod)

Usage:
  go-ai-ask [flags] "prompt"

Examples:
  go-ai-ask "What is Python?"
  go-ai-ask --file story.txt "summarize this"
  go-ai-ask "summarize this" --file story.txt
  go-ai-ask --new "start fresh conversation"
  go-ai-ask --login "hello"
  go-ai-ask --stop
  go-ai-ask --status

Flags:
  --file string   Read content from text file (as prompt or appended to prompt)
  --login         Force re-login (opens visible browser)
  --new           Force new conversation
  --quiet         Only print response (no debug output)
  --status        Show daemon status
  --stop          Stop browser daemon
`)
}
