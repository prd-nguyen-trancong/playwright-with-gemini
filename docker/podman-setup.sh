#!/usr/bin/env bash
# ============================================================
# Podman Setup for Gemini Go Tools (macOS)
# ============================================================
# This script helps set up Podman on macOS and build the
# container image for the Gemini Go tools.
#
# Prerequisites:
#   brew install podman podman-compose
#
# Usage:
#   ./docker/podman-setup.sh          # Full setup
#   ./docker/podman-setup.sh build    # Build only
#   ./docker/podman-setup.sh test     # Test the container
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Check prerequisites ──────────────────────────────────────
check_prerequisites() {
    log_info "Checking prerequisites..."

    if ! command -v podman &>/dev/null; then
        log_error "Podman not found. Install with: brew install podman"
        exit 1
    fi
    log_info "  podman: $(podman --version)"

    if ! command -v podman-compose &>/dev/null; then
        log_warn "  podman-compose not found. Install with: brew install podman-compose"
        log_warn "  You can still use 'podman' directly."
    else
        log_info "  podman-compose: $(podman-compose --version 2>/dev/null || echo 'installed')"
    fi

    # Check if Podman machine is running
    if ! podman machine info &>/dev/null 2>&1; then
        log_warn "Podman machine not initialized."
        log_info "Initializing Podman machine..."
        podman machine init --cpus 4 --memory 4096 --disk-size 50
        podman machine start
    else
        # Check if machine is running
        if ! podman info &>/dev/null 2>&1; then
            log_info "Starting Podman machine..."
            podman machine start
        fi
    fi

    log_info "  Podman machine: running"
}

# ── Build container image ────────────────────────────────────
build_image() {
    log_info "Building container image..."
    cd "$PROJECT_DIR"

    podman build \
        -f docker/Dockerfile \
        -t gemini-go-tools:latest \
        .

    log_info "Image built: gemini-go-tools:latest"
    podman images gemini-go-tools
}

# ── Build with docker-compose ────────────────────────────────
build_compose() {
    log_info "Building with podman-compose..."
    cd "$SCRIPT_DIR"

    podman-compose build

    log_info "All services built!"
}

# ── Test the container ───────────────────────────────────────
test_container() {
    log_info "Testing container..."

    echo ""
    log_info "1. Testing go-ai-ask --help:"
    podman run --rm gemini-go-tools:latest go-ai-ask --help
    echo ""

    log_info "2. Testing go-ai-gem --help:"
    podman run --rm gemini-go-tools:latest go-ai-gem --help
    echo ""

    log_info "3. Testing go-story-summary --help:"
    podman run --rm gemini-go-tools:latest go-story-summary --help
    echo ""

    log_info "4. Testing go-ai-stop:"
    podman run --rm gemini-go-tools:latest go-ai-stop
    echo ""

    log_info "All tests passed!"
}

# ── Show usage examples ──────────────────────────────────────
show_usage() {
    echo ""
    echo "============================================================"
    echo "  Gemini Go Tools - Podman Usage"
    echo "============================================================"
    echo ""
    echo "# Text chat:"
    echo "  podman run --rm -v browser-data:/home/gemini/app/.browser-data \\"
    echo "    --shm-size=2g gemini-go-tools:latest \\"
    echo "    go-ai-ask \"What is Python?\""
    echo ""
    echo "# Gem chat:"
    echo "  podman run --rm -v browser-data:/home/gemini/app/.browser-data \\"
    echo "    --shm-size=2g gemini-go-tools:latest \\"
    echo "    go-ai-gem dcca1e614968 \"tóm tắt chương này\""
    echo ""
    echo "# Story summary (batch):"
    echo "  podman run --rm \\"
    echo "    -v browser-data:/home/gemini/app/.browser-data \\"
    echo "    -v ./output_summary_story:/home/gemini/app/output_summary_story \\"
    echo "    --shm-size=2g gemini-go-tools:latest \\"
    echo "    go-story-summary --from 1201 --to 1211 \\"
    echo "    \"https://truyenfull.vision/pham-nhan-tu-tien-chi-tien-gioi-thien-pham-nhan-tu-tien-2/\""
    echo ""
    echo "# With podman-compose:"
    echo "  cd docker/"
    echo "  podman-compose run --rm gemini-ask \"What is Python?\""
    echo "  podman-compose run --rm gemini-gem dcca1e614968 \"tóm tắt\""
    echo "  podman-compose run --rm gemini-story --from 1201 --to 1211 \"https://...\""
    echo ""
    echo "# Login (first time - needs display):"
    echo "  podman-compose run --rm gemini-login \"hello\""
    echo ""
    echo "============================================================"
}

# ── Main ─────────────────────────────────────────────────────
case "${1:-setup}" in
    setup)
        check_prerequisites
        build_image
        show_usage
        ;;
    build)
        build_image
        ;;
    compose)
        check_prerequisites
        build_compose
        show_usage
        ;;
    test)
        test_container
        ;;
    usage)
        show_usage
        ;;
    *)
        echo "Usage: $0 {setup|build|compose|test|usage}"
        echo ""
        echo "  setup   - Full setup: check prerequisites, build image"
        echo "  build   - Build container image only"
        echo "  compose - Build with podman-compose"
        echo "  test    - Test the container"
        echo "  usage   - Show usage examples"
        exit 1
        ;;
esac
