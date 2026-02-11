# Gemini AI Automation

Interact with Google Gemini AI (text chat, image generation, video generation) using Python Playwright with persistent browser authentication.

## Available Tools

| Command | Tool | Description |
|---------|------|-------------|
| `ai-ask` | `GeminiAsk` | Text chat - send prompts, get responses |
| `ai-image` | `GeminiImage` | Image generation via "Create images" tool |
| `ai-veo` | `GeminiVeo` | Video generation via "Create videos (Veo 3.1)" tool |

## Quick Start

```bash
# 1. Install dependencies
poetry install

# 2. First-time Gemini login (opens browser for Google login)
ai-ask --login "hello"

# 3. Use Gemini tools
ai-ask "What is Python?"
ai-image "a cute banana cartoon"
ai-veo "a man dancing in the street"
```

## Global Commands Setup

```bash
# Option 1: Run setup script (creates symlinks in /usr/local/bin)
sudo ./bin/setup-commands.sh

# Option 2: Add to PATH (add to ~/.zshrc or ~/.bashrc)
export PATH="$PATH:/path/to/this-project/bin"
```

---

## ai-ask (Text Chat)

```bash
ai-ask "What is Python?"
ai-ask "translate to english: chào buổi sáng"
ai-ask --file photo.png "describe this image"
ai-ask --login "hello"                           # Force re-login
ai-ask --no-headless "your prompt"               # Show browser
ai-ask-debug "What is Python?"                   # Step-by-step output
```

## ai-image (Image Generation)

Uses Gemini's **Create images** tool for higher quality results.
Output defaults to `output/image_<id>.png`.

```bash
ai-image "a cute banana cartoon"
ai-image --output output/banana.png "image of a banana"
ai-image --login "image of a cat"
ai-image-debug "a cute banana cartoon"           # Step-by-step output
```

## ai-veo (Video Generation)

Uses Gemini's **Create videos (Veo 3.1)** tool.
Output defaults to `output/veo_<id>.mp4`. Video generation may take 1-3 minutes.

```bash
ai-veo "a man dancing in the street"
ai-veo --output output/dance.mp4 "a cat playing piano"
ai-veo --login "a bird flying"
ai-veo-debug "a man dancing in the street"       # Step-by-step output
```

---

## Architecture (OOP)

All tools inherit from `GeminiBase` in `tools/base.py`:

```
tools/
├── __init__.py
├── base.py      # GeminiBase - shared browser, login, prompt, response logic
├── ask.py       # GeminiAsk - text chat (no tool activation)
├── image.py     # GeminiImage - activates "Create images" tool
└── veo.py       # GeminiVeo - activates "Create videos (Veo 3.1)" tool
```

Each tool:
- Inherits browser management, login flow, and prompt sending from `GeminiBase`
- Activates its specific Gemini tool via the Tools dropdown (if applicable)
- Implements custom `_wait_for_response()` for its output type
- Outputs to `output/` directory with auto-generated filenames

### Python API

```python
from tools.ask import GeminiAsk
from tools.image import GeminiImage
from tools.veo import GeminiVeo

# Text chat
ask = GeminiAsk(quiet=True)
response = ask.run(prompt="What is Python?")

# Image generation
img = GeminiImage(quiet=True)
path = img.run(prompt="a cute banana", output_path="output/banana.png")

# Video generation
veo = GeminiVeo(quiet=True)
path = veo.run(prompt="a man dancing", output_path="output/dance.mp4")
```

---

## Gemini Login

Gemini uses a **persistent browser profile** - no cookies or env vars needed.

1. On first run, a Chromium browser window opens automatically
2. Log in to your Google account in that browser
3. The session is saved in `.browser-data/gemini/` and reused for future runs
4. To force re-login: `ai-ask --login "hello"`

---

## Troubleshooting

### Not logged in
```
Not logged in. Restarting with visible browser...
```
A browser window will open. Complete the Google login and the script continues automatically.

### Session expired
```bash
ai-ask --login "hello"
```

### Rate limited
```
ERROR: Rate limited - reached your video generation limit until ...
```
Wait until the specified time, then try again.

### Browser not found
```bash
poetry run playwright install chromium
```

---

## Project Structure

```
.
├── tools/                      # Gemini AI tools (OOP)
│   ├── __init__.py
│   ├── base.py                 # GeminiBase class
│   ├── ask.py                  # GeminiAsk - text chat
│   ├── image.py                # GeminiImage - image generation
│   └── veo.py                  # GeminiVeo - video generation
├── bin/
│   ├── ai-ask                  # Text chat (quiet mode)
│   ├── ai-ask-debug            # Text chat (verbose)
│   ├── ai-image                # Image generation (quiet mode)
│   ├── ai-image-debug          # Image generation (verbose)
│   ├── ai-veo                  # Video generation (quiet mode)
│   ├── ai-veo-debug            # Video generation (verbose)
│   └── setup-commands.sh       # Setup global commands
├── output/                     # Generated images & videos
├── todo-list/                  # Task specs
├── .browser-data/              # Persistent browser profiles
├── env.example                 # Environment template
├── pyproject.toml              # Poetry config
└── README.md
```

## Dependencies

- Python 3.11+
- [Playwright](https://playwright.dev/python/)
- [python-dotenv](https://github.com/theskumar/python-dotenv)
