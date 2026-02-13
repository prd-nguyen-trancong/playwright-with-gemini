// Package browser manages the persistent Chrome daemon for fast Gemini automation.
//
// Architecture mirrors the Python tools/gemini/browser.py:
//
//	daemon_start (background) -> Chrome with persistent profile + CDP port 9222
//	ai-ask (foreground)       -> connect via CDP [ask tab]
//	ai-gem (foreground)       -> connect via CDP [gem tab]
package browser

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sync"
)

// DaemonState holds the persistent state of the browser daemon.
type DaemonState struct {
	PID      int            `json:"pid,omitempty"`
	AskCount int            `json:"ask_count"`
	GemCount int            `json:"gem_count"`
	GemID    string         `json:"gem_id,omitempty"`
	RoleMap  map[string]int `json:"role_map,omitempty"`
}

var (
	stateMu sync.Mutex
)

func stateFilePath() string {
	return filepath.Join(BrowserDataDir(), "daemon_state.json")
}

// BrowserDataDir returns the path to the Go/Rod browser profile directory.
// Separate from Python/Playwright which uses .browser-data/gemini/
func BrowserDataDir() string {
	return filepath.Join(ScriptDir(), ".browser-data", "gemini-go")
}

// ScriptDir returns the project root directory.
func ScriptDir() string {
	// Priority 1: PROJECT_ROOT environment variable (set by shell scripts)
	if d := os.Getenv("PROJECT_ROOT"); d != "" {
		return d
	}

	// Priority 2: Derive from executable path
	// Binary is at go-dev-tools/bin/go-ai-ask -> go up 2 levels to project root
	dir, err := os.Executable()
	if err == nil {
		// Resolve symlinks
		dir, _ = filepath.EvalSymlinks(dir)
		candidate := filepath.Dir(filepath.Dir(filepath.Dir(dir)))
		// Verify this looks like the project root
		if _, err := os.Stat(filepath.Join(candidate, ".browser-data")); err == nil {
			return candidate
		}
		// Try 2 levels up (go-dev-tools/bin/ -> project root)
		candidate = filepath.Dir(filepath.Dir(dir))
		if _, err := os.Stat(filepath.Join(candidate, ".browser-data")); err == nil {
			return candidate
		}
	}

	// Priority 3: Current working directory
	d, _ := os.Getwd()
	return d
}

// LoadState reads daemon state from the JSON file.
func LoadState() DaemonState {
	stateMu.Lock()
	defer stateMu.Unlock()
	return loadStateUnsafe()
}

func loadStateUnsafe() DaemonState {
	data, err := os.ReadFile(stateFilePath())
	if err != nil {
		return DaemonState{RoleMap: make(map[string]int)}
	}
	var s DaemonState
	if err := json.Unmarshal(data, &s); err != nil {
		return DaemonState{RoleMap: make(map[string]int)}
	}
	if s.RoleMap == nil {
		s.RoleMap = make(map[string]int)
	}
	return s
}

// SaveState writes daemon state to the JSON file.
func SaveState(s DaemonState) error {
	stateMu.Lock()
	defer stateMu.Unlock()
	return saveStateUnsafe(s)
}

func saveStateUnsafe(s DaemonState) error {
	if s.RoleMap == nil {
		s.RoleMap = make(map[string]int)
	}
	dir := filepath.Dir(stateFilePath())
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return fmt.Errorf("create state dir: %w", err)
	}
	data, err := json.MarshalIndent(s, "", "  ")
	if err != nil {
		return fmt.Errorf("marshal state: %w", err)
	}
	return os.WriteFile(stateFilePath(), data, 0o644)
}

// UpdateState merges the given fields into the existing state.
func UpdateState(updates map[string]interface{}) error {
	stateMu.Lock()
	defer stateMu.Unlock()

	s := loadStateUnsafe()

	for k, v := range updates {
		switch k {
		case "ask_count":
			if n, ok := v.(int); ok {
				s.AskCount = n
			}
		case "gem_count":
			if n, ok := v.(int); ok {
				s.GemCount = n
			}
		case "gem_id":
			if str, ok := v.(string); ok {
				s.GemID = str
			}
		case "pid":
			if n, ok := v.(int); ok {
				s.PID = n
			}
		}
	}

	return saveStateUnsafe(s)
}
