# Gemini AI Automation

Interact with Google Gemini AI (text chat, image generation, video generation, story summarization) using Python Playwright with persistent browser authentication.

## Available Tools

| Command | Description |
|---------|-------------|
| `ai-ask` | Text chat (fast daemon mode, ~4-5s per call) |
| `ai-gem <id>` | Chat using a specific Gem (separate tab from ai-ask) |
| `ai-image` | Image generation via "Create images" tool |
| `ai-veo` | Video generation via "Create videos (Veo 3.1)" tool |
| `story-get-summary` | Scrape story chapter + summarize via Gem |
| `ai-stop` | Kill browser daemon to free memory |

## Quick Start

```bash
# 1. Install dependencies
poetry install

# 2. First-time Gemini login (opens browser for Google login)
ai-ask --login "hello"

# 3. Use Gemini tools
ai-ask "What is Python?"
ai-gem dcca1e614968 "tóm tắt chương này"
ai-image "a cute banana cartoon"
ai-veo "a man dancing in the street"
story-get-summary "https://truyenfull.vision/.../chuong-1090/"
```

## Global Commands Setup

```bash
# Option 1: Run setup script (creates symlinks in /usr/local/bin)
sudo ./bin/setup-commands.sh

# Option 2: Add to PATH (add to ~/.zshrc or ~/.bashrc)
export PATH="$PATH:/path/to/this-project/bin"
```

---

## ai-ask (Fast Text Chat)

Uses a **persistent browser daemon** for speed. First call ~10-15s, subsequent ~4-5s.
Reuses conversation for up to 20 prompts, then starts fresh.
Uses a dedicated "ask" tab - never interferes with `ai-gem`.

```bash
ai-ask "What is Python?"
ai-ask "translate to english: chào buổi sáng"
ai-ask --file story.txt "summarize this"          # Read prompt from file
ai-ask --new "start fresh conversation"           # Force new conversation
ai-ask --login "hello"                            # First-time login
ai-ask --stop                                     # Kill browser daemon
ai-ask --status                                   # Check daemon status
ai-ask-debug "What is Python?"                    # Step-by-step output
```

## ai-gem (Fast Gem Chat)

Uses a **dedicated "gem" tab** in the daemon - completely separate from `ai-ask`.
Both can run in parallel without interference.

```bash
ai-gem dcca1e614968 "tóm tắt chương này"
ai-gem --file story.txt dcca1e614968 "summarize"  # Read prompt from file
ai-gem --new dcca1e614968 "fresh conversation"    # Force new conversation
ai-gem-debug dcca1e614968 "tóm tắt"              # Step-by-step output
```

### Browser Daemon

`ai-ask` and `ai-gem` share the same Chrome daemon but use **separate tabs**:
- **First call**: launches Chrome (~10-15s), navigates to Gemini, sends prompt
- **Subsequent calls**: connects to running Chrome (~4-5s), sends prompt directly
- **After 20 prompts**: automatically starts a new conversation
- **ai-ask** uses the "ask" tab, **ai-gem** uses the "gem" tab
- **Kill daemon**: `ai-ask --stop` or `ai-stop`

## ai-image (Image Generation)

Uses Gemini's **Create images** tool. Output defaults to `output/image_<id>.png`.

```bash
ai-image "a cute banana cartoon"
ai-image --output output/banana.png "image of a banana"
ai-image-debug "a cute banana cartoon"
```

## ai-veo (Video Generation)

Uses Gemini's **Create videos (Veo 3.1)** tool. Output defaults to `output/veo_<id>.mp4`.

```bash
ai-veo "a man dancing in the street"
ai-veo --output output/dance.mp4 "a cat playing piano"
ai-veo-debug "a man dancing in the street"
```

## story-get-summary (Story Summarization)

Scrapes a story chapter from truyenfull.vision and summarizes it using a Gemini Gem.

```bash
# Summarize a chapter (uses default Gem: "Tóm tắt truyện V3")
story-get-summary "https://truyenfull.vision/pham-nhan-tu-tien-.../chuong-1090/"

# Use a specific Gem
story-get-summary --gem dcca1e614968 "https://truyenfull.vision/.../chuong-1205/"

# Quiet mode (only print summary)
story-get-summary --quiet "https://truyenfull.vision/.../chuong-1090/"
```

**Workflow:**
1. Scrapes chapter content from the URL
2. Saves raw text to `raw_content_story/<chapter_title>.txt`
3. Sends content to the Gem for summarization
4. Saves summary to `output_summary_story/<chapter_title>.txt`
5. Limits to 10 requests per Gem session (restarts for accuracy)

---

## Architecture

```
tools/
├── __init__.py
├── base.py              # GeminiBase - shared browser, login, prompt logic
├── browser.py           # BrowserDaemon - Chrome daemon via CDP (role-based tabs)
├── fast_ask.py          # GeminiFastAsk - speed-optimized text chat ("ask" tab)
├── fast_gem.py          # GeminiFastGem - speed-optimized Gem chat ("gem" tab)
├── ask.py               # GeminiAsk - standard text chat (login flow)
├── image.py             # GeminiImage - "Create images" tool
├── veo.py               # GeminiVeo - "Create videos (Veo 3.1)" tool
└── story_summary.py     # GeminiStorySummary - scrape + Gem summary ("story" tab)
```

### Speed Architecture (BrowserDaemon)

Each tool gets its own dedicated tab, so they never cross-contaminate:

```
┌─────────────┐     CDP (port 9222)     ┌──────────────────────────────┐
│   ai-ask    │ ──── connect ────────── │  Tab 1: "ask" (gemini.com)  │
└─────────────┘                         │                              │
┌─────────────┐     CDP (port 9222)     │  Tab 2: "gem" (gem/xxx)     │
│   ai-gem    │ ──── connect ────────── │                              │
└─────────────┘                         │  Tab 3: "story" (gem/xxx)   │
┌─────────────┐     CDP (port 9222)     │                              │
│ story-get-  │ ──── connect ────────── │  Chrome Daemon (stays alive) │
│  summary    │                         │  Profile: .browser-data/     │
└─────────────┘                         └──────────────────────────────┘
```

### Python API

```python
from tools.fast_ask import GeminiFastAsk
from tools.fast_gem import GeminiFastGem
from tools.image import GeminiImage
from tools.veo import GeminiVeo
from tools.story_summary import GeminiStorySummary

# Fast text chat (daemon mode - "ask" tab)
ask = GeminiFastAsk(quiet=True)
response = ask.run_fast(prompt="What is Python?")

# Fast Gem chat (daemon mode - "gem" tab, separate from ask)
gem = GeminiFastGem(quiet=True)
response = gem.run_fast(prompt="Summarize", gem_id="dcca1e614968")

# Image generation
img = GeminiImage(quiet=True)
path = img.run(prompt="a cute banana", output_path="output/banana.png")

# Video generation
veo = GeminiVeo(quiet=True)
path = veo.run(prompt="a man dancing", output_path="output/dance.mp4")

# Story summarization (uses its own "story" tab)
story = GeminiStorySummary(quiet=True, gem_id="dcca1e614968")
summary = story.run_summary(url="https://truyenfull.vision/.../chuong-1090/")
```

---

## Gemini Login

Gemini uses a **persistent browser profile** - no cookies or env vars needed.

```bash
# First-time login (stops daemon, opens visible browser)
ai-ask --login "hello"
```

1. A Chromium browser window opens
2. Log in to your Google account
3. Session saved in `.browser-data/gemini/` and reused
4. To re-login: `ai-ask --login "hello"` (stops daemon first)

---

## Troubleshooting

### Not logged in
```bash
ai-ask --login "hello"   # Opens browser for manual Google login
```

### Session expired
```bash
ai-ask --login "hello"   # Stops daemon, re-opens login browser
```

### Browser daemon issues
```bash
ai-ask --status          # Check if daemon is running
ai-ask --stop            # Kill daemon
ai-stop                  # Same as above
```

### Rate limited
Wait until the specified time, then try again.

### Browser not found
```bash
poetry run playwright install chromium
```

---

## Project Structure

```
.
├── tools/                          # Gemini AI tools (OOP)
│   ├── base.py                     # GeminiBase class
│   ├── browser.py                  # BrowserDaemon (CDP manager)
│   ├── fast_ask.py                 # Fast text chat (daemon)
│   ├── ask.py                      # Standard text chat (login)
│   ├── image.py                    # Image generation
│   ├── veo.py                      # Video generation
│   └── story_summary.py           # Story scraping + Gem summary
├── bin/
│   ├── ai-ask / ai-ask-debug       # Fast text chat (uses "ask" tab)
│   ├── ai-gem / ai-gem-debug       # Fast Gem chat (uses "gem" tab)
│   ├── ai-image / ai-image-debug   # Image generation
│   ├── ai-veo / ai-veo-debug       # Video generation
│   ├── story-get-summary           # Story summarization
│   ├── ai-stop                     # Kill browser daemon
│   └── setup-commands.sh           # Setup global commands
├── output/                         # Generated images & videos
├── raw_content_story/              # Scraped story chapters
├── output_summary_story/           # Story summaries
├── .browser-data/                  # Persistent browser profiles
├── pyproject.toml                  # Poetry config
└── README.md
```

## Dependencies

- Python 3.11+
- [Playwright](https://playwright.dev/python/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)
