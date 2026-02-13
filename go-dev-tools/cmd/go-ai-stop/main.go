// go-ai-stop: Kill the browser daemon to free memory.
//
// Usage:
//
//	go-ai-stop
package main

import (
	"github.com/prd-nguyen-trancong/gemini-tools/internal/browser"
)

func main() {
	browser.Stop()
}
