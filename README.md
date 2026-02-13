# Gemini AI Automation

Interact with Google Gemini AI (text chat, image generation, video generation, story summarization) using browser automation with persistent authentication.

Available in **two implementations**:
- **Python** (Playwright) - Original, full-featured
- **Go** (Rod) - High-performance rewrite, faster startup and lower memory

## Quick Start

### Go (Recommended - High Performance)

```bash
# 1. Build Go binaries
cd go-dev-tools && make build && cd ..

# 2. First-time login (opens visible Chrome for Google login)
go-ai-ask --login "hello"

# 3. Text chat
go-ai-ask "What is Python?"
go-ai-ask --quiet "What is 2+2?"

# 4. Translate (Japanese/Chinese → Vietnamese)
go-ai-translate "こんにちは世界"
go-ai-translate --file document.txt

# 5. Correct English grammar
go-ai-english "I has go to school yesterday"

# 6. Story summarization
go-ai-story-summary "https://truyenfull.vision/.../chuong-1201/"

# 7. Stop daemon
go-ai-stop
```

### Python

```bash
# 1. Install dependencies
poetry install
poetry run playwright install chromium

# 2. First-time login (opens browser for Google login)
poetry run python -m tools.gemini.fast_ask --login "hello"

# 3. Text chat
poetry run python -m tools.gemini.fast_ask "What is Python?"
poetry run python -m tools.gemini.fast_ask --quiet "What is 2+2?"

# 4. Gem chat (separate tab)
poetry run python -m tools.gemini.fast_gem dcca1e614968 "summarize this"

# 5. Story summarization
poetry run python -m tools.story.summary "https://truyenfull.vision/.../chuong-1201/"

# 6. Stop daemon
poetry run python -m tools.gemini.fast_ask --stop
```

---

## Shell Aliases (Run from Anywhere)

Add to `~/.zshrc` and `~/.bash_profile`:

```bash
# Gemini AI Tools (Go)
export PROJECT_ROOT="/Users/n.tran/paradox/source/olivia-some-auto-playwright"
export PATH="$PATH:$PROJECT_ROOT/go-dev-tools/bin"

# Gemini AI Tool Aliases
alias go-ai-translate='go-ai-gem --quiet 3f9e2319b62e'       # Translate → Vietnamese
alias go-ai-english='go-ai-gem --quiet ad4d96a4c35e'         # Correct English grammar
alias go-ai-story-summary='go-story-summary --gem dcca1e614968'  # Story summary
```

### Available Commands

| Command | Description |
|---|---|
| `go-ai-ask "prompt"` | Text chat with Gemini |
| `go-ai-gem <gem_id> "prompt"` | Chat with a specific Gem |
| `go-ai-translate "text"` | Translate to Vietnamese (Gem `3f9e2319b62e`) |
| `go-ai-translate --file doc.txt` | Translate file content |
| `go-ai-english "text"` | Correct English grammar (Gem `ad4d96a4c35e`) |
| `go-ai-story-summary "url"` | Summarize story chapter (Gem `dcca1e614968`) |
| `go-ai-stop` | Stop browser daemon |

### Common Flags

All commands support these flags in **any position**:

```bash
--quiet       # Only print response (no debug output)
--file path   # Read content from file
--new         # Force new conversation
--login       # Force re-login (go-ai-ask only)
--stop        # Stop daemon (go-ai-ask only)
--status      # Show daemon status (go-ai-ask only)
```

### Examples

```bash
# Translate a Japanese file
go-ai-translate --file japanese.txt

# Correct English with file input
go-ai-english --file draft.txt "fix grammar and improve clarity"

# Ask with file context
go-ai-ask --quiet --file code.py "explain this code"

# Gem with flags in any order
go-ai-gem 3f9e2319b62e --quiet --file content.txt "translate this"

# Story batch: chapters 1201 to 1211
go-ai-story-summary --from 1201 --to 1211 \
  "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"
```

---

## Go Tools - Detailed Usage

### Text Chat (go-ai-ask)

```bash
go-ai-ask "What is Python?"
go-ai-ask --quiet "What is 2+2?"
go-ai-ask --file story.txt "summarize this"
go-ai-ask --new "start fresh conversation"
go-ai-ask --login "hello"
go-ai-ask --stop
go-ai-ask --status
```

### Gem Chat (go-ai-gem)

```bash
go-ai-gem dcca1e614968 "summarize this chapter"
go-ai-gem --quiet dcca1e614968 "summarize"
go-ai-gem --file story.txt dcca1e614968 "summarize"
go-ai-gem --new dcca1e614968 "fresh conversation"
```

### Story Summarization (go-story-summary)

```bash
# Single chapter
go-story-summary "https://truyenfull.vision/.../chuong-1201/"

# Batch: chapters 1201 to 1211
go-story-summary --from 1201 --to 1211 \
  "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"

# Custom Gem
go-story-summary --gem dcca1e614968 --from 1201 --to 1211 \
  "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"
```

### Building Go Tools

```bash
cd go-dev-tools

make build              # Build for current platform
make build-linux        # Build for Linux (Docker)
make build-darwin-arm   # Build for macOS Apple Silicon
make install            # Install to /usr/local/bin
make clean              # Clean build artifacts
make help               # Show all targets
```

---

## Python Tools - Detailed Usage

### Text Chat (fast_ask)

```bash
poetry run python -m tools.gemini.fast_ask "What is Python?"
poetry run python -m tools.gemini.fast_ask --quiet "What is 2+2?"
poetry run python -m tools.gemini.fast_ask --file story.txt "summarize this"
poetry run python -m tools.gemini.fast_ask --new "start fresh"
poetry run python -m tools.gemini.fast_ask --login "hello"
poetry run python -m tools.gemini.fast_ask --stop
poetry run python -m tools.gemini.fast_ask --status
```

### Gem Chat (fast_gem)

```bash
poetry run python -m tools.gemini.fast_gem dcca1e614968 "summarize this chapter"
poetry run python -m tools.gemini.fast_gem --quiet dcca1e614968 "summarize"
poetry run python -m tools.gemini.fast_gem --file story.txt dcca1e614968 "summarize"
poetry run python -m tools.gemini.fast_gem --new dcca1e614968 "fresh conversation"
```

### Image Generation (image)

```bash
poetry run python -m tools.gemini.image "a cute banana cartoon"
poetry run python -m tools.gemini.image --output output/banana.png "banana"
```

### Video Generation (veo)

```bash
poetry run python -m tools.gemini.veo "a man dancing in the street"
poetry run python -m tools.gemini.veo --output output/dance.mp4 "cat playing piano"
```

### Story Summarization (story.summary)

```bash
poetry run python -m tools.story.summary "https://truyenfull.vision/.../chuong-1201/"
poetry run python -m tools.story.summary --from 1201 --to 1211 \
  "https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/"
```

---

## Architecture

### Browser Profiles (Separate)

Python and Go use **separate browser profiles** to avoid conflicts:

| | Profile Directory | CDP Port |
|---|---|---|
| **Python** (Playwright) | `.browser-data/gemini/` | 9222 |
| **Go** (Rod) | `.browser-data/gemini-go/` | 9223 |

Login separately for each tool:
```bash
poetry run python -m tools.gemini.fast_ask --login "hello"   # Python
go-ai-ask --login "hello"                                     # Go
```

### Speed Architecture (BrowserDaemon)

Chrome runs as a persistent headless daemon (`--headless=new`). Each tool gets its own dedicated tab:

```
Python (port 9222)                    Go (port 9223)
┌─────────────┐                       ┌─────────────┐
│  fast_ask    │ ── Tab 1: "ask"      │  go-ai-ask  │ ── Tab 1: "ask"
│  fast_gem    │ ── Tab 2: "gem"      │  go-ai-gem  │ ── Tab 2: "gem"
│  story       │ ── Tab 3: "story"    │  go-story   │ ── Tab 3: "story"
└─────────────┘                       └─────────────┘
```

### Gem IDs

| Gem | ID | Alias |
|---|---|---|
| Translate to Vietnamese | `3f9e2319b62e` | `go-ai-translate` |
| Correct English Grammar | `ad4d96a4c35e` | `go-ai-english` |
| Story Summary (Tóm tắt truyện V3) | `dcca1e614968` | `go-ai-story-summary` |

---

## Gemini Login

```bash
# Python login
poetry run python -m tools.gemini.fast_ask --login "hello"

# Go login
go-ai-ask --login "hello"
```

1. A Chrome browser window opens
2. Log in to your Google account (passkey may close browser - that's OK)
3. Session saved and reused automatically
4. Login once per tool (Python and Go have separate sessions)

---

## Troubleshooting

### Not logged in
```bash
poetry run python -m tools.gemini.fast_ask --login "hello"   # Python
go-ai-ask --login "hello"                                     # Go
```

### Browser daemon issues
```bash
# Python
poetry run python -m tools.gemini.fast_ask --status
poetry run python -m tools.gemini.fast_ask --stop

# Go
go-ai-ask --status
go-ai-stop
```

### Browser not found (Python)
```bash
poetry run playwright install chromium
```

### Go build issues
```bash
cd go-dev-tools
go mod download
make build
```

---

## Project Structure

```
.
├── tools/                          # Python tools (Playwright)
│   ├── gemini/                     # Core Gemini automation
│   │   ├── base.py                 # GeminiBase class
│   │   ├── browser.py              # BrowserDaemon (CDP manager)
│   │   ├── fast_ask.py             # Fast text chat (daemon)
│   │   ├── fast_gem.py             # Fast Gem chat (daemon)
│   │   ├── image.py                # Image generation
│   │   └── veo.py                  # Video generation
│   └── story/                      # Story tools
│       ├── scraper.py              # Chapter scraper
│       └── summary.py              # Scrape + Gem summary
├── go-dev-tools/                   # Go tools (Rod)
│   ├── cmd/                        # CLI entry points
│   │   ├── go-ai-ask/main.go
│   │   ├── go-ai-gem/main.go
│   │   ├── go-ai-stop/main.go
│   │   └── go-story-summary/main.go
│   ├── internal/                   # Internal packages
│   │   ├── browser/                # Chrome daemon (Rod + CDP)
│   │   ├── gemini/                 # Gemini automation
│   │   └── story/                  # Story scraper + summary
│   ├── bin/                        # Compiled Go binaries (gitignored)
│   ├── go.mod
│   └── Makefile
├── docker/                         # Docker/Podman setup
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── podman-setup.sh
├── .browser-data/                  # Persistent browser profiles (gitignored)
│   ├── gemini/                     # Python profile (port 9222)
│   └── gemini-go/                  # Go profile (port 9223)
├── output/                         # Generated images & videos
├── output_summary_story/           # Story summaries
├── pyproject.toml                  # Poetry config (Python)
└── README.md
```

## Dependencies

### Python
- Python 3.11+
- [Playwright](https://playwright.dev/python/)

### Go
- Go 1.22+
- [Rod](https://go-rod.github.io/) (browser automation via CDP)
