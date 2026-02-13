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
	MaxPromptsPerConversation = 20
	RoleAsk                   = "ask"
)

// FastAsk provides speed-optimized Gemini text chat using the persistent daemon.
type FastAsk struct {
	Base
	daemon *browser.Daemon
}

// NewFastAsk creates a new FastAsk instance.
func NewFastAsk(quiet bool) *FastAsk {
	return &FastAsk{
		Base:   Base{Quiet: quiet},
		daemon: browser.NewDaemon(quiet),
	}
}

// RunFast sends a prompt and returns the response using the persistent browser.
func (fa *FastAsk) RunFast(prompt string, forceNew bool, filePath string) (string, error) {
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

	// Step 1: Ensure browser daemon is running
	state, err := fa.daemon.EnsureBrowser()
	if err != nil {
		return "", fmt.Errorf("ensure browser: %w", err)
	}
	count := state.AskCount

	// Step 2: Decide whether to reuse or start new conversation
	needNew := forceNew || count >= MaxPromptsPerConversation

	if needNew {
		fa.LogLn("  Starting new conversation...")
		_, page, err := fa.daemon.NewConversation(RoleAsk, browser.GeminiURL)
		if err != nil {
			return "", fmt.Errorf("new conversation: %w", err)
		}
		count = 0

		// Check login on fresh conversations
		if !fa.IsLoggedIn(page) {
			fa.LogLn("  ERROR: Not logged in. Run: go-ai-ask --login \"hello\"")
			fa.daemon.Release()
			return "", fmt.Errorf("not logged in")
		}
		fa.DismissDialogs(page)

		return fa.sendAndWait(page, prompt, count)
	}

	// Reuse existing conversation
	_, page, err := fa.daemon.GetPage(RoleAsk, browser.GeminiURL)
	if err != nil {
		return "", fmt.Errorf("get page: %w", err)
	}

	// Check login on first call
	if count == 0 {
		if !fa.IsLoggedIn(page) {
			fa.LogLn("  ERROR: Not logged in. Run: go-ai-ask --login \"hello\"")
			fa.daemon.Release()
			return "", fmt.Errorf("not logged in")
		}
		fa.DismissDialogs(page)
	}

	return fa.sendAndWait(page, prompt, count)
}

func (fa *FastAsk) sendAndWait(page *rod.Page, prompt string, count int) (string, error) {
	// Count existing responses BEFORE sending (so we detect the NEW one)
	prevCount := countModelResponses(page)

	// Send prompt
	fa.LogLn("  Sending prompt (%d/%d)...", count+1, MaxPromptsPerConversation)
	if !fa.SendPromptFast(page, prompt) {
		fa.daemon.Release()
		return "", fmt.Errorf("failed to send prompt")
	}

	// Wait for response (pass prevCount so we only look at NEW responses)
	fa.Log("  Waiting for response")
	response := fa.WaitForTextResponse(page, 120, prevCount)

	// Update state
	browser.UpdateState(map[string]interface{}{"ask_count": count + 1})

	fa.daemon.Release()

	if response != "" {
		fa.LogLn("")
		fmt.Println(response)
	} else {
		fa.LogLn("\n  (No response captured)")
	}
	return response, nil
}

// Stop kills the browser daemon.
func (fa *FastAsk) Stop() {
	browser.Stop()
}

// Status prints daemon status.
func (fa *FastAsk) Status() {
	browser.Status()
}

// Login performs the login flow (opens VISIBLE browser for Google login).
//
// Flow:
//  1. Stop existing daemon → launch visible browser (on-screen) for user login
//  2. User logs in (passkey may crash browser - that's OK, cookies persist)
//  3. Stop visible browser → restart as headless daemon
//  4. Verify login in headless mode and send initial prompt
func (fa *FastAsk) Login(prompt string) (string, error) {
	browser.Stop()
	time.Sleep(2 * time.Second)

	fa.LogLn("============================================================")
	fa.LogLn("  Go Gemini Login")
	fa.LogLn("============================================================")
	fa.LogLn("  Profile: .browser-data/gemini-go/")
	fa.LogLn("  NOTE: Passkey login may close the browser - that's OK!")
	fa.LogLn("============================================================")

	// ── Step 1: Launch VISIBLE browser for manual login ──
	fa.LogLn("\n[Step 1] Opening visible browser for login...")
	loginResult := fa.waitForManualLogin()

	if loginResult == "BROWSER_CLOSED" {
		fa.LogLn("  Browser closed (passkey flow). Cookies should be saved.")
	} else if loginResult == "LOGGED_IN" {
		fa.LogLn("  Login detected in visible browser!")
	} else {
		return "", fmt.Errorf("login failed or timed out")
	}

	// ── Step 2: Stop visible browser gracefully and restart as headless daemon ──
	fa.LogLn("\n[Step 2] Flushing cookies and stopping visible browser...")
	// Give Chrome time to flush cookies/session to disk before killing
	time.Sleep(5 * time.Second)
	browser.StopGraceful()
	time.Sleep(3 * time.Second)

	headlessDaemon := browser.NewDaemon(false)
	_, err := headlessDaemon.EnsureBrowser()
	if err != nil {
		return "", fmt.Errorf("start headless daemon: %w", err)
	}

	_, page, err := headlessDaemon.GetPage(RoleAsk, browser.GeminiURL)
	if err != nil {
		return "", fmt.Errorf("get page: %w", err)
	}
	time.Sleep(3 * time.Second)

	if !fa.IsLoggedIn(page) {
		fa.LogLn("  Login not detected in headless mode. Please try again.")
		headlessDaemon.Release()
		return "", fmt.Errorf("login not persisted to headless mode")
	}

	fa.LogLn("  Login verified in headless mode!")
	fa.DismissDialogs(page)

	// ── Step 3: Send initial prompt ──
	return fa.loginSendPrompt(headlessDaemon, page, prompt)
}

// waitForManualLogin launches a visible browser and waits for login or browser crash.
// Returns: "LOGGED_IN", "BROWSER_CLOSED", or "" (timeout).
func (fa *FastAsk) waitForManualLogin() string {
	daemon := browser.NewDaemon(false)
	_, err := daemon.EnsureBrowserVisible()
	if err != nil {
		fa.LogLn("  ERROR: Could not launch visible browser: %v", err)
		return ""
	}

	// Connect and get the first page (already navigated to Gemini by EnsureBrowserVisible)
	brow, err := daemon.Connect()
	if err != nil {
		fa.LogLn("  ERROR: Could not connect to browser: %v", err)
		return ""
	}

	// Wait for at least one page to be available (Chrome may take a moment)
	var page *rod.Page
	for attempt := 0; attempt < 15; attempt++ {
		pages, pErr := brow.Pages()
		if pErr == nil && len(pages) > 0 {
			page = pages[0]
			break
		}
		time.Sleep(1 * time.Second)
	}
	if page == nil {
		fa.LogLn("  ERROR: No pages found in browser after waiting")
		return ""
	}

	fa.LogLn("  Please log in to your Google account in the browser window.")
	fa.LogLn("  (Passkey login may close the browser - that's OK!)")

	for i := 0; i < 300; i++ {
		// Check if Chrome process is still alive (fastest check)
		state := browser.LoadState()
		if state.PID > 0 && !browser.IsPIDAlive(state.PID) {
			fa.LogLn("  Chrome process exited (passkey flow detected).")
			return "BROWSER_CLOSED"
		}

		// Check if CDP port is still open
		if !browser.IsPortOpen(browser.CDPPort) {
			fa.LogLn("  CDP port closed (passkey flow detected).")
			return "BROWSER_CLOSED"
		}

		// Check if browser/page is still alive
		_, infoErr := page.Info()
		if infoErr != nil {
			errMsg := strings.ToLower(infoErr.Error())
			if strings.Contains(errMsg, "closed") ||
				strings.Contains(errMsg, "crash") ||
				strings.Contains(errMsg, "connection") ||
				strings.Contains(errMsg, "websocket") ||
				strings.Contains(errMsg, "eof") ||
				strings.Contains(errMsg, "target") {
				fa.LogLn("  Browser closed (passkey flow detected).")
				return "BROWSER_CLOSED"
			}
		}

		// Check if logged in (try all pages in case of redirect)
		allPages, pErr := brow.Pages()
		if pErr == nil {
			for _, pg := range allPages {
				if fa.IsLoggedIn(pg) {
					daemon.Release()
					return "LOGGED_IN"
				}
			}
		}

		if i > 0 && i%15 == 0 {
			fa.LogLn("  Still waiting for login... (%ds)", i)
		}
		time.Sleep(1 * time.Second)
	}

	daemon.Release()
	fa.LogLn("  Timeout waiting for login.")
	return ""
}

// loginSendPrompt sends the initial prompt after login and returns the response.
func (fa *FastAsk) loginSendPrompt(daemon *browser.Daemon, page *rod.Page, prompt string) (string, error) {
	fa.LogLn("\n[Final] Sending prompt: %s", prompt)

	if !fa.SendPromptFast(page, prompt) {
		fa.LogLn("  Warning: Could not send prompt, but login was saved.")
		daemon.Release()
		fa.LogLn("\n  Login session saved to .browser-data/gemini-go/")
		fa.LogLn("  You can now use go-ai-ask normally.")
		return "", nil
	}

	fa.Log("  Waiting for response")
	response := fa.WaitForTextResponse(page, 120, 0)

	browser.UpdateState(map[string]interface{}{"ask_count": 1})
	daemon.Release()

	fa.LogLn("\n============================================================")
	fa.LogLn("  Login successful! Session saved to .browser-data/gemini-go/")
	fa.LogLn("  You can now use go-ai-ask normally (headless mode).")
	fa.LogLn("============================================================")

	if response != "" {
		fa.LogLn("")
		fmt.Println(response)
	}
	return response, nil
}
