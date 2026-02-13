// Package gemini provides the core Gemini automation logic.
//
// Mirrors the Python tools/gemini/base.py - shared login detection,
// prompt sending, response waiting, and dialog dismissal.
package gemini

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/input"
	"github.com/go-rod/rod/lib/proto"
	"github.com/prd-nguyen-trancong/gemini-tools/internal/browser"
)

// Base provides shared Gemini automation methods.
type Base struct {
	Quiet bool
}

// Log prints a message if not in quiet mode (no newline).
func (b *Base) Log(format string, args ...interface{}) {
	if !b.Quiet {
		fmt.Printf(format, args...)
	}
}

// LogLn prints a message with newline if not in quiet mode.
func (b *Base) LogLn(format string, args ...interface{}) {
	if !b.Quiet {
		fmt.Printf(format+"\n", args...)
	}
}

// IsLoggedIn checks if the user is logged in to Gemini.
// NOTE: Gemini shows an input field even when NOT logged in (as a "try it" feature),
// so we must check for the ABSENCE of "Sign in" button to confirm real login.
func (b *Base) IsLoggedIn(page *rod.Page) bool {
	// Check URL first - if on accounts.google.com, definitely not logged in
	info, err := page.Info()
	if err != nil {
		return false
	}
	url := info.URL
	if strings.Contains(url, "accounts.google.com") {
		return false
	}
	if !strings.Contains(url, "gemini.google.com") {
		return false
	}

	// Use JavaScript to check login state more reliably
	result, err := page.Eval(`() => {
		// Check if "Sign in" button exists - if yes, NOT logged in
		const links = document.querySelectorAll('a, button');
		for (const el of links) {
			const text = (el.textContent || '').trim().toLowerCase();
			if (text === 'sign in') return { loggedIn: false, reason: 'sign_in_button_found' };
		}

		// Check for user avatar/profile picture (logged-in indicator)
		const avatar = document.querySelector('img[alt*="Account"], img[alt*="Google Account"], [data-ogsr-up]');
		if (avatar) return { loggedIn: true, reason: 'avatar_found' };

		// Check for the chat input AND no sign-in button (strong indicator)
		const editor = document.querySelector('.ql-editor[contenteditable="true"]');
		if (editor) return { loggedIn: true, reason: 'editor_no_signin' };

		// Check for model-response elements (only present when logged in and chatting)
		const responses = document.querySelectorAll('model-response');
		if (responses.length > 0) return { loggedIn: true, reason: 'model_responses' };

		return { loggedIn: false, reason: 'unknown' };
	}`)

	if err != nil {
		return false
	}

	loggedIn := result.Value.Get("loggedIn").Bool()
	reason := result.Value.Get("reason").String()
	b.LogLn("  Login check: %v (reason: %s)", loggedIn, reason)
	return loggedIn
}

// DismissDialogs dismisses any Gemini welcome/cookie/terms dialogs.
func (b *Base) DismissDialogs(page *rod.Page) {
	selectors := []string{
		`button[aria-label="Got it"]`,
		`button[aria-label="Close"]`,
		`button[aria-label="Dismiss"]`,
	}

	for _, sel := range selectors {
		el, err := page.Timeout(1 * time.Second).Element(sel)
		if err == nil && el != nil {
			_ = el.Click(proto.InputMouseButtonLeft, 1)
			time.Sleep(300 * time.Millisecond)
		}
	}

	// Also try text-based buttons via JS evaluation
	_, _ = page.Eval(`() => {
		const btns = document.querySelectorAll('button');
		for (const btn of btns) {
			const text = (btn.textContent || '').trim().toLowerCase();
			if (['got it', 'i agree', 'accept all', 'ok', 'continue', 'dismiss'].includes(text)) {
				btn.click();
				break;
			}
		}
	}`)
	time.Sleep(300 * time.Millisecond)
}

// SendPromptFast sends a prompt using the fast method (minimal sleeps).
func (b *Base) SendPromptFast(page *rod.Page, promptText string) bool {
	// First dismiss any overlays that might block interaction
	b.DismissDialogs(page)

	// Clear any leftover text in the input field and focus it
	page.Eval(`() => {
		const el = document.querySelector('.ql-editor[contenteditable="true"]');
		if (el) {
			el.innerHTML = '<p><br></p>';
			el.focus();
		}
	}`)
	time.Sleep(200 * time.Millisecond)

	// Wait for input field to be ready
	_, err := page.Timeout(10 * time.Second).Element(`.ql-editor[contenteditable="true"]`)
	if err != nil {
		b.LogLn("  ERROR: Could not find input field: %v", err)
		return false
	}

	// Use CDP InsertText for contenteditable divs
	if err := page.InsertText(promptText); err != nil {
		b.LogLn("  ERROR: Could not insert text: %v", err)
		return false
	}
	time.Sleep(300 * time.Millisecond)

	// Primary: use Enter key to send (most reliable in headless mode)
	_ = page.Keyboard.Press(input.Enter)
	time.Sleep(500 * time.Millisecond)

	// Verify the prompt was sent by checking if the input field is now empty
	cleared, _ := page.Eval(`() => {
		const el = document.querySelector('.ql-editor[contenteditable="true"]');
		if (!el) return true;
		const text = (el.innerText || '').trim();
		return text.length === 0;
	}`)
	if cleared != nil && cleared.Value.Bool() {
		return true
	}

	// If Enter didn't work, try clicking the send button with Rod (with timeout)
	sendBtn, err := page.Timeout(3 * time.Second).Element(`button[aria-label="Send message"]`)
	if err == nil && sendBtn != nil {
		done := make(chan bool, 1)
		go func() {
			_ = sendBtn.Click(proto.InputMouseButtonLeft, 1)
			done <- true
		}()
		select {
		case <-done:
			// click succeeded
		case <-time.After(3 * time.Second):
			b.LogLn("  [send] Button click timed out")
		}
	}
	time.Sleep(500 * time.Millisecond)
	return true
}

// WaitForTextResponse waits for a text response from Gemini.
// prevResponseCount is the number of model-response elements before the prompt.
func (b *Base) WaitForTextResponse(page *rod.Page, timeoutSec int, prevResponseCount int) string {
	if timeoutSec == 0 {
		timeoutSec = 120
	}

	start := time.Now()
	lastText := ""
	stableCount := 0
	debugLogged := false

	for time.Since(start).Seconds() < float64(timeoutSec) {
		// Embed prevResponseCount directly in JS to avoid parameter passing issues
		js := fmt.Sprintf(`() => {
			const prevCount = %d;
			const stopBtn = document.querySelector('button[aria-label*="Stop"]');
			const isGenerating = stopBtn && stopBtn.offsetParent !== null;

			const modelResp = document.querySelectorAll('model-response');
			let text = '';
			if (modelResp.length > prevCount) {
				const last = modelResp[modelResp.length - 1];
				// Try message-content first (cleaner, avoids header artifacts)
				const content = last.querySelector('message-content');
				if (content) {
					const ct = (content.innerText || '').trim();
					if (ct.length > 0) text = ct;
				}
				// Fallback to full model-response innerText
				if (!text) {
					text = (last.innerText || '').trim();
				}
			}
			if (!text) {
				const msgs = document.querySelectorAll('message-content');
				if (msgs.length > prevCount) {
					text = (msgs[msgs.length - 1].innerText || '').trim();
				}
			}
			return { g: isGenerating, t: text, c: modelResp.length };
		}`, prevResponseCount)

		result, err := page.Eval(js)

		if err == nil {
			text := result.Value.Get("t").String()
			generating := result.Value.Get("g").Bool()
			count := result.Value.Get("c").Int()

			// Debug: log first time we see model-response elements
			if !debugLogged && count > prevResponseCount {
				b.LogLn("\n  [debug] model-response count: %d, generating: %v, text_len: %d", count, generating, len(text))
				debugLogged = true
			}

			if len(text) > 5 {
				if text == lastText {
					stableCount++
					// Return if text is stable: 2 checks when not generating, 5 when still "generating"
					// (Stop button can be stale/phantom visible)
					stableThreshold := 2
					if generating {
						stableThreshold = 5
					}
					if stableCount >= stableThreshold {
						return CleanResponse(text)
					}
				} else {
					stableCount = 0
				}
				lastText = text
			}
		}

		b.Log(".")
		time.Sleep(1 * time.Second)
	}

	if lastText != "" {
		return CleanResponse(lastText)
	}
	return ""
}

// DebugScreenshot takes a screenshot for debugging purposes.
func (b *Base) DebugScreenshot(page *rod.Page, name string) {
	dir := filepath.Join(browser.ScriptDir(), "debug")
	os.MkdirAll(dir, 0o755)
	path := filepath.Join(dir, fmt.Sprintf("go_%s.png", name))
	data, err := page.Screenshot(true, &proto.PageCaptureScreenshot{})
	if err != nil {
		b.LogLn("  DEBUG: Screenshot failed: %v", err)
		return
	}
	os.WriteFile(path, data, 0o644)
	b.LogLn("  DEBUG: Screenshot saved: %s", path)
}

// DebugPageInfo prints page URL and basic DOM info for debugging.
func (b *Base) DebugPageInfo(page *rod.Page) {
	info, err := page.Info()
	if err != nil {
		b.LogLn("  DEBUG: Could not get page info: %v", err)
		return
	}
	b.LogLn("  DEBUG: URL = %s", info.URL)

	// Check for key elements
	hasInput, _, _ := page.Has(`.ql-editor[contenteditable="true"]`)
	hasModel, _, _ := page.Has(`model-response`)
	hasSend, _, _ := page.Has(`button[aria-label="Send message"]`)
	b.LogLn("  DEBUG: input=%v model-response=%v send-btn=%v", hasInput, hasModel, hasSend)
}

// CleanResponse removes UI artifacts from Gemini responses.
func CleanResponse(text string) string {
	// Remove trailing UI button text
	trailingPatterns := []string{
		`\n*thumb_up\s*$`,
		`\n*thumb_down\s*$`,
		`\n*content_copy\s*$`,
		`\n*Share\s*$`,
		`\n*more_vert\s*$`,
		`\n*volume_up\s*$`,
		`\n*Google Search\s*$`,
		`\n*flag\s*$`,
		`\n*Modify response\s*$`,
	}

	result := text
	for _, p := range trailingPatterns {
		re := regexp.MustCompile(p)
		result = re.ReplaceAllString(result, "")
	}

	// Remove leading UI artifacts (Gemini toolbar text captured by innerText)
	leadingArtifacts := []string{
		"Show code\n",
		"Analysis\n",
		"Query successful\n",
		"Gemini said\n",
		"Show drafts\n",
		"Edit in Canvas\n",
	}
	for _, artifact := range leadingArtifacts {
		for strings.HasPrefix(result, artifact) {
			result = strings.TrimPrefix(result, artifact)
		}
	}

	// Remove inline UI artifacts that appear on their own lines
	lines := strings.Split(result, "\n")
	inlineArtifacts := map[string]bool{
		"Show code":         true,
		"Analysis":          true,
		"Query successful":  true,
		"Gemini said":       true,
		"Show drafts":       true,
		"Edit in Canvas":    true,
		"thumb_up":          true,
		"thumb_down":        true,
		"content_copy":      true,
		"more_vert":         true,
		"volume_up":         true,
		"flag":              true,
		"Sources":           true,
		"Modify response":   true,
		"Share":             true,
		"Google Search":     true,
		"+1":                true,
		"-1":                true,
		"Custom Gem":        true,
	}
	// Also remove single-character lines at the start (avatar/icon artifacts)
	// and known Gem header patterns
	var cleanLines []string
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if _, isArtifact := inlineArtifacts[trimmed]; !isArtifact {
			cleanLines = append(cleanLines, line)
		}
	}
	result = strings.Join(cleanLines, "\n")

	return strings.TrimSpace(result)
}
