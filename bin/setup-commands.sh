#!/bin/bash
# Setup script to add Gemini AI commands globally
#
# Run this once:
#   ./bin/setup-commands.sh
#
# This creates symlinks in /usr/local/bin (requires sudo)
# Or you can add this bin/ directory to your PATH instead.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "Setting up Gemini AI commands..."
echo "Project: $PROJECT_DIR"
echo ""

# Make scripts executable
chmod +x "$SCRIPT_DIR/ai-ask"
chmod +x "$SCRIPT_DIR/ai-ask-debug"
chmod +x "$SCRIPT_DIR/ai-gem"
chmod +x "$SCRIPT_DIR/ai-gem-debug"
chmod +x "$SCRIPT_DIR/ai-image"
chmod +x "$SCRIPT_DIR/ai-image-debug"
chmod +x "$SCRIPT_DIR/ai-veo"
chmod +x "$SCRIPT_DIR/ai-veo-debug"
chmod +x "$SCRIPT_DIR/ai-stop"
chmod +x "$SCRIPT_DIR/story-get-summary"

# Option 1: Symlink to /usr/local/bin (needs sudo)
if [ -w /usr/local/bin ] || [ "$EUID" -eq 0 ]; then
    ln -sf "$SCRIPT_DIR/ai-ask" /usr/local/bin/ai-ask
    ln -sf "$SCRIPT_DIR/ai-ask-debug" /usr/local/bin/ai-ask-debug
    ln -sf "$SCRIPT_DIR/ai-gem" /usr/local/bin/ai-gem
    ln -sf "$SCRIPT_DIR/ai-gem-debug" /usr/local/bin/ai-gem-debug
    ln -sf "$SCRIPT_DIR/ai-image" /usr/local/bin/ai-image
    ln -sf "$SCRIPT_DIR/ai-image-debug" /usr/local/bin/ai-image-debug
    ln -sf "$SCRIPT_DIR/ai-veo" /usr/local/bin/ai-veo
    ln -sf "$SCRIPT_DIR/ai-veo-debug" /usr/local/bin/ai-veo-debug
    ln -sf "$SCRIPT_DIR/ai-stop" /usr/local/bin/ai-stop
    ln -sf "$SCRIPT_DIR/story-get-summary" /usr/local/bin/story-get-summary
    echo "Created symlinks in /usr/local/bin:"
    echo "  ai-ask            -> $SCRIPT_DIR/ai-ask"
    echo "  ai-ask-debug      -> $SCRIPT_DIR/ai-ask-debug"
    echo "  ai-gem            -> $SCRIPT_DIR/ai-gem"
    echo "  ai-gem-debug      -> $SCRIPT_DIR/ai-gem-debug"
    echo "  ai-image          -> $SCRIPT_DIR/ai-image"
    echo "  ai-image-debug    -> $SCRIPT_DIR/ai-image-debug"
    echo "  ai-veo            -> $SCRIPT_DIR/ai-veo"
    echo "  ai-veo-debug      -> $SCRIPT_DIR/ai-veo-debug"
    echo "  ai-stop           -> $SCRIPT_DIR/ai-stop"
    echo "  story-get-summary -> $SCRIPT_DIR/story-get-summary"
    echo ""
    echo "Commands are now available globally!"
else
    echo "Cannot write to /usr/local/bin without sudo."
    echo ""
    echo "Option 1: Run with sudo:"
    echo "  sudo $0"
    echo ""
    echo "Option 2: Add to your PATH (add to ~/.zshrc or ~/.bashrc):"
    echo "  export PATH=\"\$PATH:$SCRIPT_DIR\""
    echo ""
    echo "Then restart your terminal or run: source ~/.zshrc"
fi

echo ""
echo "Usage:"
echo "  ai-ask \"prompt\"                  # Ask Gemini (fast, daemon mode)"
echo "  ai-gem <id> \"prompt\"             # Use a Gem (separate tab)"
echo "  ai-ask-debug \"prompt\"             # Ask Gemini (step-by-step)"
echo "  ai-gem-debug <id> \"prompt\"        # Gem debug output"
echo "  ai-image \"prompt\"                 # Generate image"
echo "  ai-veo \"prompt\"                   # Generate video (Veo 3.1)"
echo "  story-get-summary \"url\"           # Scrape + summarize story chapter"
echo "  story-get-summary --from N --to M \"base_url\"  # Batch mode"
echo "  ai-stop                            # Kill browser daemon"
echo ""
echo "Examples:"
echo "  ai-ask \"translate to english: chào buổi sáng\""
echo "  ai-gem dcca1e614968 \"tóm tắt chương này\""
echo "  ai-gem --file story.txt dcca1e614968 \"tóm tắt\""
echo "  ai-image \"image of a banana\""
echo "  ai-veo \"a man dancing in the street\""
echo "  story-get-summary \"https://truyenfull.vision/.../chuong-1201/\""
echo "  story-get-summary --from 1201 --to 1211 \"https://truyenfull.vision/.../\""
