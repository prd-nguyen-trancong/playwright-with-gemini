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
chmod +x "$SCRIPT_DIR/ai-image"
chmod +x "$SCRIPT_DIR/ai-image-debug"
chmod +x "$SCRIPT_DIR/ai-veo"
chmod +x "$SCRIPT_DIR/ai-veo-debug"

# Option 1: Symlink to /usr/local/bin (needs sudo)
if [ -w /usr/local/bin ] || [ "$EUID" -eq 0 ]; then
    ln -sf "$SCRIPT_DIR/ai-ask" /usr/local/bin/ai-ask
    ln -sf "$SCRIPT_DIR/ai-ask-debug" /usr/local/bin/ai-ask-debug
    ln -sf "$SCRIPT_DIR/ai-image" /usr/local/bin/ai-image
    ln -sf "$SCRIPT_DIR/ai-image-debug" /usr/local/bin/ai-image-debug
    ln -sf "$SCRIPT_DIR/ai-veo" /usr/local/bin/ai-veo
    ln -sf "$SCRIPT_DIR/ai-veo-debug" /usr/local/bin/ai-veo-debug
    echo "Created symlinks in /usr/local/bin:"
    echo "  ai-ask         -> $SCRIPT_DIR/ai-ask"
    echo "  ai-ask-debug   -> $SCRIPT_DIR/ai-ask-debug"
    echo "  ai-image       -> $SCRIPT_DIR/ai-image"
    echo "  ai-image-debug -> $SCRIPT_DIR/ai-image-debug"
    echo "  ai-veo         -> $SCRIPT_DIR/ai-veo"
    echo "  ai-veo-debug   -> $SCRIPT_DIR/ai-veo-debug"
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
echo "  ai-ask \"prompt\"          # Ask Gemini (response only)"
echo "  ai-ask-debug \"prompt\"    # Ask Gemini (step-by-step)"
echo "  ai-image \"prompt\"        # Generate image (Create images tool)"
echo "  ai-image-debug \"prompt\"  # Generate image (step-by-step)"
echo "  ai-veo \"prompt\"          # Generate video (Veo 3.1 tool)"
echo "  ai-veo-debug \"prompt\"    # Generate video (step-by-step)"
echo ""
echo "Examples:"
echo "  ai-ask \"translate to english: chào buổi sáng\""
echo "  ai-ask --file photo.png \"describe this image\""
echo "  ai-image \"image of a banana\""
echo "  ai-veo \"a man dancing in the street\""
