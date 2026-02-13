package gemini

import (
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/go-rod/rod"
	"github.com/prd-nguyen-trancong/gemini-tools/internal/browser"
)

const (
	MaxPromptsPerGem = 10
	RoleGem          = "gem"
)

// FastGem provides speed-optimized Gemini Gem chat using the persistent daemon.
type FastGem struct {
	Base
	daemon *browser.Daemon
}

// NewFastGem creates a new FastGem instance.
func NewFastGem(quiet bool) *FastGem {
	return &FastGem{
		Base:   Base{Quiet: quiet},
		daemon: browser.NewDaemon(quiet),
	}
}

// RunFast sends a prompt to a Gem and returns the response.
func (fg *FastGem) RunFast(prompt, gemID string, forceNew bool, filePath string) (string, error) {
	// If filePath provided, read content
	if filePath != "" {
		data, err := os.ReadFile(filePath)
		if err != nil {
			return "", fmt.Errorf("read file: %w", err)
		}
		fileContent := strings.TrimSpace(string(data))
		if prompt != "" {
			prompt = prompt + "\n\n" + fileContent
		} else {
			prompt = fileContent
		}
	}

	gemURL := fmt.Sprintf("https://gemini.google.com/gem/%s", gemID)

	// Step 1: Ensure browser daemon is running
	state, err := fg.daemon.EnsureBrowser()
	if err != nil {
		return "", fmt.Errorf("ensure browser: %w", err)
	}
	count := state.GemCount
	currentGem := state.GemID

	// Step 2: Decide whether to reuse or start new conversation
	gemChanged := currentGem != "" && currentGem != gemID
	needNew := forceNew || count >= MaxPromptsPerGem || gemChanged

	var page *rod.Page

	if needNew {
		reason := "forced"
		if count >= MaxPromptsPerGem {
			reason = "limit reached"
		} else if gemChanged {
			reason = "gem changed"
		}
		fg.LogLn("  Starting new Gem conversation (%s)...", reason)
		_, page, err = fg.daemon.NewConversation(RoleGem, gemURL)
		if err != nil {
			return "", fmt.Errorf("new conversation: %w", err)
		}
		count = 0
		time.Sleep(2 * time.Second) // Wait for Gem page to load
	} else {
		_, page, err = fg.daemon.GetPage(RoleGem, gemURL)
		if err != nil {
			return "", fmt.Errorf("get page: %w", err)
		}

		// If the gem tab isn't on the right Gem, navigate
		info, infoErr := page.Info()
		if infoErr == nil && !strings.Contains(info.URL, "/gem/"+gemID) {
			fg.LogLn("  Navigating to Gem: %s", gemID)
			_, page, err = fg.daemon.NewConversation(RoleGem, gemURL)
			if err != nil {
				return "", fmt.Errorf("navigate to gem: %w", err)
			}
			count = 0
			time.Sleep(2 * time.Second)
		}
	}

	// Step 3: Check login on fresh conversations
	if count == 0 {
		if !fg.IsLoggedIn(page) {
			fg.LogLn("  ERROR: Not logged in. Run: go-ai-ask --login \"hello\"")
			fg.daemon.Release()
			return "", fmt.Errorf("not logged in")
		}
		fg.DismissDialogs(page)
	}

	// Step 4: Count existing responses before sending
	prevCount := countModelResponses(page)

	// Step 5: Send prompt
	fg.LogLn("  Gem: %s | Sending prompt (%d/%d)...", gemID, count+1, MaxPromptsPerGem)
	if !fg.SendPromptFast(page, prompt) {
		fg.daemon.Release()
		return "", fmt.Errorf("failed to send prompt")
	}

	// Step 6: Wait for response
	fg.Log("  Waiting for response")
	response := fg.WaitForTextResponse(page, 120, prevCount)

	// Step 7: Update state
	browser.UpdateState(map[string]interface{}{
		"gem_count": count + 1,
		"gem_id":    gemID,
	})

	fg.daemon.Release()

	if response != "" {
		fg.LogLn("")
		fmt.Println(response)
	} else {
		fg.LogLn("\n  (No response captured)")
	}
	return response, nil
}

func countModelResponses(page *rod.Page) int {
	result, err := page.Eval(`() => document.querySelectorAll('model-response').length`)
	if err != nil {
		return 0
	}
	return result.Value.Int()
}
