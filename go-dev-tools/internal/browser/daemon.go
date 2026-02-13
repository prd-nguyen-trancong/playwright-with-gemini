package browser

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"

	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/launcher"
	"github.com/go-rod/rod/lib/proto"
)

const (
	// CDPPort uses 9223 to avoid conflict with Python/Playwright daemon on 9222
	CDPPort   = 9223
	GeminiURL = "https://gemini.google.com/app"
)

// Daemon manages a persistent Chrome browser for fast Gemini access.
//
// On first call, launches Chrome with a persistent profile and CDP port.
// Subsequent calls connect via CDP for instant access.
// Each role ("ask", "gem", "story", "scrape") gets its own dedicated tab.
type Daemon struct {
	quiet   bool
	browser *rod.Browser
}

// NewDaemon creates a new Daemon manager.
func NewDaemon(quiet bool) *Daemon {
	return &Daemon{quiet: quiet}
}

func (d *Daemon) log(format string, args ...interface{}) {
	if !d.quiet {
		fmt.Printf(format+"\n", args...)
	}
}

// ── Lifecycle ──────────────────────────────────────────────────────

// EnsureBrowser ensures the daemon is running, launching if needed.
// Launches Chrome DIRECTLY as a subprocess (bypassing Rod's launcher) to avoid
// Rod injecting --enable-automation and other flags that Gemini detects.
func (d *Daemon) EnsureBrowser() (DaemonState, error) {
	state := LoadState()

	// Check if existing daemon is alive and CDP port is open
	if state.PID > 0 && isPIDAlive(state.PID) && isPortOpen(CDPPort) {
		d.log("  Browser daemon running (pid=%d)", state.PID)
		return state, nil
	}

	// Clean up stale state and orphaned Chrome processes
	d.log("  Cleaning up stale processes...")
	killOrphanChromes()
	cleanLocks()

	// Launch new daemon
	d.log("  Launching browser daemon...")

	dataDir := BrowserDataDir()
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		return DaemonState{}, fmt.Errorf("create data dir: %w", err)
	}

	chromeBin := findChromeBinary()
	if chromeBin == "" {
		// Fallback to Rod's auto-download
		chromeBin = launcher.NewBrowser().MustGet()
	}
	d.log("  Using Chrome: %s", chromeBin)

	// Launch Chrome directly as a subprocess with --headless=new.
	// This avoids Rod's launcher which injects --enable-automation
	// (detected by Gemini as bot) and --no-startup-window.
	// --headless=new (Chrome 112+) shares the same rendering engine,
	// cookie store, and macOS Keychain access as visible Chrome.
	args := []string{
		"--headless=new",
		fmt.Sprintf("--remote-debugging-port=%d", CDPPort),
		fmt.Sprintf("--user-data-dir=%s", dataDir),
		"--no-first-run",
		"--no-default-browser-check",
		"--disable-background-timer-throttling",
		"--disable-backgrounding-occluded-windows",
		"--disable-renderer-backgrounding",
		"--window-size=1280,900",
	}
	if os.Getenv("CHROME_NO_SANDBOX") == "true" {
		args = append(args, "--no-sandbox")
	}

	cmd := exec.Command(chromeBin, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true} // Detach process group
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		return DaemonState{}, fmt.Errorf("launch chrome: %w", err)
	}
	pid := cmd.Process.Pid

	// Detach: don't wait for Chrome to exit (daemon mode)
	go cmd.Wait()

	// Wait for CDP port to become available
	d.log("  Waiting for Chrome CDP port %d...", CDPPort)
	for i := 0; i < 30; i++ {
		if isPortOpen(CDPPort) {
			break
		}
		time.Sleep(500 * time.Millisecond)
	}
	if !isPortOpen(CDPPort) {
		return DaemonState{}, fmt.Errorf("chrome did not start (CDP port %d not open after 15s)", CDPPort)
	}

	// Connect via Rod
	wsURL, err := launcher.ResolveURL(fmt.Sprintf("http://localhost:%d", CDPPort))
	if err != nil {
		return DaemonState{}, fmt.Errorf("resolve CDP URL: %w", err)
	}
	browser := rod.New().ControlURL(wsURL)
	if err := browser.Connect(); err != nil {
		return DaemonState{}, fmt.Errorf("connect to chrome: %w", err)
	}

	// Navigate the first page to Gemini
	pages, pErr := browser.Pages()
	if pErr == nil && len(pages) > 0 {
		_ = pages[0].Navigate(GeminiURL)
		_ = pages[0].WaitLoad()
		// Wait for Gemini SPA to fully initialize (input field to appear)
		for i := 0; i < 25; i++ {
			has, _, _ := pages[0].Has(`.ql-editor[contenteditable="true"]`)
			if has {
				d.log("  Gemini page ready (input field found)")
				break
			}
			time.Sleep(1 * time.Second)
		}
	}

	// Save state
	state = DaemonState{
		PID:      pid,
		AskCount: 0,
		GemCount: 0,
		RoleMap:  make(map[string]int),
	}
	if err := SaveState(state); err != nil {
		return state, fmt.Errorf("save state: %w", err)
	}

	d.browser = browser
	d.log("  Browser daemon started (pid=%d)", pid)
	return state, nil
}

// Connect connects to the running Chrome via CDP.
func (d *Daemon) Connect() (*rod.Browser, error) {
	if d.browser != nil {
		return d.browser, nil
	}

	// Discover the websocket URL from Chrome's CDP endpoint
	wsURL, err := launcher.ResolveURL(fmt.Sprintf("http://localhost:%d", CDPPort))
	if err != nil {
		return nil, fmt.Errorf("resolve CDP URL: %w", err)
	}

	browser := rod.New().ControlURL(wsURL)
	if err := browser.Connect(); err != nil {
		return nil, fmt.Errorf("connect to CDP: %w", err)
	}
	d.browser = browser
	return browser, nil
}

// ── Role-based page management ────────────────────────────────────

// GetPage gets or creates a page for the given role.
// Each role ("ask", "gem", "scrape", etc.) gets its own dedicated tab.
func (d *Daemon) GetPage(role, targetURL string) (*rod.Browser, *rod.Page, error) {
	if targetURL == "" {
		targetURL = GeminiURL
	}

	browser, err := d.Connect()
	if err != nil {
		return nil, nil, err
	}

	state := LoadState()
	roleMap := state.RoleMap

	// 1. Look for an existing tab assigned to this role
	if idx, ok := roleMap[role]; ok {
		pages, err := browser.Pages()
		if err == nil && idx >= 0 && idx < len(pages) {
			return browser, pages[idx], nil
		}
	}

	// 2. For "ask", claim the daemon's initial page (index 0) if unclaimed
	if role == "ask" {
		claimed := make(map[int]bool)
		for _, idx := range roleMap {
			claimed[idx] = true
		}
		pages, err := browser.Pages()
		if err == nil {
			for i, page := range pages {
				if !claimed[i] {
					info, infoErr := page.Info()
					if infoErr == nil && strings.Contains(info.URL, "gemini.google.com") {
						roleMap[role] = i
						state.RoleMap = roleMap
						SaveState(state)
						return browser, page, nil
					}
				}
			}
		}
	}

	// 3. Create a brand-new tab for this role
	page, err := browser.Page(proto.TargetCreateTarget{URL: targetURL})
	if err != nil {
		return nil, nil, fmt.Errorf("create page for role %s: %w", role, err)
	}
	// Wait for load, but don't panic if it fails (page may redirect)
	_ = page.WaitLoad()
	// Wait for Gemini SPA to initialize (input field to appear)
	for i := 0; i < 15; i++ {
		has, _, _ := page.Has(`.ql-editor[contenteditable="true"]`)
		if has {
			break
		}
		time.Sleep(1 * time.Second)
	}

	// Record the index of the new page
	pages, _ := browser.Pages()
	idx := len(pages) - 1
	roleMap[role] = idx
	state.RoleMap = roleMap
	SaveState(state)

	return browser, page, nil
}

// NewConversation starts a fresh conversation for the given role.
func (d *Daemon) NewConversation(role, targetURL string) (*rod.Browser, *rod.Page, error) {
	if targetURL == "" {
		targetURL = GeminiURL
	}

	browser, err := d.Connect()
	if err != nil {
		return nil, nil, err
	}

	state := LoadState()
	roleMap := state.RoleMap

	// Find the tab for this role and navigate it
	if idx, ok := roleMap[role]; ok {
		pages, err := browser.Pages()
		if err == nil && idx >= 0 && idx < len(pages) {
			page := pages[idx]
			_ = page.Navigate(targetURL)
			_ = page.WaitLoad()
			// Wait for Gemini SPA to initialize (input field to appear)
			for i := 0; i < 15; i++ {
				has, _, _ := page.Has(`.ql-editor[contenteditable="true"]`)
				if has {
					break
				}
				time.Sleep(1 * time.Second)
			}
			return browser, page, nil
		}
	}

	// No existing tab - create one
	return d.GetPage(role, targetURL)
}

// Release disconnects from the browser WITHOUT killing it.
func (d *Daemon) Release() {
	d.browser = nil
}

// ── Static operations ─────────────────────────────────────────────

// StopGraceful sends SIGTERM and waits for Chrome to exit cleanly (flush cookies).
func StopGraceful() {
	state := LoadState()
	pid := state.PID

	if pid > 0 && isPIDAlive(pid) {
		_ = syscall.Kill(pid, syscall.SIGTERM)
		// Wait up to 10 seconds for graceful exit
		for i := 0; i < 20; i++ {
			if !isPIDAlive(pid) {
				break
			}
			time.Sleep(500 * time.Millisecond)
		}
		// Force kill if still alive
		if isPIDAlive(pid) {
			_ = syscall.Kill(pid, syscall.SIGKILL)
			time.Sleep(1 * time.Second)
		}
	}
	killOrphanChromes()
	SaveState(DaemonState{RoleMap: make(map[string]int)})
	cleanLocks()
}

// Stop kills the browser daemon and any orphaned Chrome processes.
func Stop() {
	state := LoadState()
	pid := state.PID
	killed := false

	if pid > 0 && isPIDAlive(pid) {
		// Try to kill the process group
		pgid, err := syscall.Getpgid(pid)
		if err == nil {
			_ = syscall.Kill(-pgid, syscall.SIGTERM)
			killed = true
		} else {
			_ = syscall.Kill(pid, syscall.SIGTERM)
			killed = true
		}
	}

	killOrphanChromes()

	if killed {
		fmt.Printf("Browser daemon stopped (pid=%d)\n", pid)
	} else {
		fmt.Println("No browser daemon running (cleaned up orphans).")
	}

	SaveState(DaemonState{RoleMap: make(map[string]int)})
	cleanLocks()
}

// Status prints daemon status.
func Status() {
	state := LoadState()
	pid := state.PID
	if pid > 0 && isPIDAlive(pid) && isPortOpen(CDPPort) {
		fmt.Printf("Browser daemon: RUNNING (pid=%d, port=%d)\n", pid, CDPPort)
		fmt.Printf("  Ask prompt count: %d\n", state.AskCount)
		fmt.Printf("  Gem prompt count: %d\n", state.GemCount)
	} else {
		fmt.Println("Browser daemon: STOPPED")
	}
}

// ── Helpers ───────────────────────────────────────────────────────

// IsPortOpen checks if a TCP port is accepting connections.
func IsPortOpen(port int) bool {
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("localhost:%d", port), 500*time.Millisecond)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

// IsPIDAlive checks if a process with the given PID is running.
func IsPIDAlive(pid int) bool {
	process, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	err = process.Signal(syscall.Signal(0))
	return err == nil
}

// Keep lowercase aliases for internal use
func isPortOpen(port int) bool { return IsPortOpen(port) }
func isPIDAlive(pid int) bool  { return IsPIDAlive(pid) }

func cleanLocks() {
	dataDir := BrowserDataDir()
	for _, name := range []string{"SingletonLock", "SingletonSocket", "SingletonCookie"} {
		os.Remove(filepath.Join(dataDir, name))
	}
}

func killOrphanChromes() {
	profileBase := filepath.Base(BrowserDataDir())
	out, err := exec.Command("pgrep", "-f", fmt.Sprintf("user-data-dir=.*%s", profileBase)).Output()
	if err != nil {
		return
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	for _, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		pid, err := strconv.Atoi(line)
		if err != nil {
			continue
		}
		_ = syscall.Kill(pid, syscall.SIGTERM)
	}
	if len(lines) > 0 && lines[0] != "" {
		time.Sleep(1 * time.Second)
		for _, line := range lines {
			pid, err := strconv.Atoi(strings.TrimSpace(line))
			if err != nil {
				continue
			}
			_ = syscall.Kill(pid, syscall.SIGKILL)
		}
	}
}

func findChromePID() int {
	profileBase := filepath.Base(BrowserDataDir())
	out, err := exec.Command("pgrep", "-f", fmt.Sprintf("user-data-dir=.*%s", profileBase)).Output()
	if err != nil {
		return 0
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	if len(lines) > 0 {
		re := regexp.MustCompile(`\d+`)
		match := re.FindString(lines[0])
		pid, _ := strconv.Atoi(match)
		return pid
	}
	return 0
}

// EnsureBrowserVisible launches a VISIBLE (non-headless) browser for login.
// Launches Chrome directly (no Rod launcher) to avoid --enable-automation
// and --use-mock-keychain, ensuring cookies persist to headless mode.
func (d *Daemon) EnsureBrowserVisible() (DaemonState, error) {
	// Clean up any existing daemon first
	d.log("  Cleaning up stale processes...")
	killOrphanChromes()
	cleanLocks()

	d.log("  Launching VISIBLE browser for login...")

	dataDir := BrowserDataDir()
	if err := os.MkdirAll(dataDir, 0o755); err != nil {
		return DaemonState{}, fmt.Errorf("create data dir: %w", err)
	}

	chromeBin := findChromeBinary()
	if chromeBin == "" {
		chromeBin = launcher.NewBrowser().MustGet()
	}
	d.log("  Using Chrome: %s", chromeBin)

	// Launch Chrome directly as a visible window (no --headless).
	// No --enable-automation, no --use-mock-keychain so cookies persist.
	args := []string{
		fmt.Sprintf("--remote-debugging-port=%d", CDPPort),
		fmt.Sprintf("--user-data-dir=%s", dataDir),
		"--no-first-run",
		"--no-default-browser-check",
		GeminiURL,
	}
	if os.Getenv("CHROME_NO_SANDBOX") == "true" {
		args = append(args, "--no-sandbox")
	}

	cmd := exec.Command(chromeBin, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Stdout = nil
	cmd.Stderr = nil
	if err := cmd.Start(); err != nil {
		return DaemonState{}, fmt.Errorf("launch chrome visible: %w", err)
	}
	pid := cmd.Process.Pid

	// Detach
	go cmd.Wait()

	// Wait for CDP port
	d.log("  Waiting for Chrome CDP port %d...", CDPPort)
	for i := 0; i < 30; i++ {
		if isPortOpen(CDPPort) {
			break
		}
		time.Sleep(500 * time.Millisecond)
	}
	if !isPortOpen(CDPPort) {
		return DaemonState{}, fmt.Errorf("chrome did not start (CDP port %d not open)", CDPPort)
	}

	// Connect via Rod
	wsURL, err := launcher.ResolveURL(fmt.Sprintf("http://localhost:%d", CDPPort))
	if err != nil {
		return DaemonState{}, fmt.Errorf("resolve CDP URL: %w", err)
	}
	browser := rod.New().ControlURL(wsURL)
	if err := browser.Connect(); err != nil {
		return DaemonState{}, fmt.Errorf("connect to chrome: %w", err)
	}

	// Wait for page to load
	time.Sleep(3 * time.Second)

	state := DaemonState{
		PID:      pid,
		AskCount: 0,
		GemCount: 0,
		RoleMap:  make(map[string]int),
	}
	SaveState(state)

	d.browser = browser
	d.log("  Visible browser launched (pid=%d)", pid)
	return state, nil
}

// findChromeBinary finds the Chrome/Chromium binary to use.
// Priority: CHROME_PATH env > system Google Chrome > Rod's bundled Chromium
func findChromeBinary() string {
	// 1. Explicit env var
	if p := os.Getenv("CHROME_PATH"); p != "" {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}

	// 2. System Google Chrome (macOS)
	macChrome := "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
	if _, err := os.Stat(macChrome); err == nil {
		return macChrome
	}

	// 3. Linux Chrome locations
	linuxPaths := []string{
		"/usr/bin/google-chrome-stable",
		"/usr/bin/google-chrome",
		"/usr/bin/chromium-browser",
		"/usr/bin/chromium",
	}
	for _, p := range linuxPaths {
		if _, err := os.Stat(p); err == nil {
			return p
		}
	}

	// 4. Fall back to Rod's auto-download (will download if needed)
	return ""
}

// Version returns basic info about the connected browser.
func (d *Daemon) Version() (string, error) {
	if d.browser == nil {
		return "", fmt.Errorf("not connected")
	}
	info, err := d.browser.Version()
	if err != nil {
		return "", err
	}
	return fmt.Sprintf("Browser: %s, Protocol: %s", info.Product, info.ProtocolVersion), nil
}
