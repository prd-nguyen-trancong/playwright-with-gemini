# ============================================================
# Multi-stage Dockerfile for Gemini Go Tools
# ============================================================
# Stage 1: Build Go binaries
# Stage 2: Runtime with Chromium for browser automation
# ============================================================

# ── Stage 1: Builder ──────────────────────────────────────────
FROM golang:1.22-bookworm AS builder

WORKDIR /build

# Copy Go module files first (cache deps)
COPY go-dev-tools/go.mod go-dev-tools/go.sum* ./
RUN go mod download

# Copy source code
COPY go-dev-tools/ .

# Build all binaries (static for Alpine compatibility)
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /out/go-ai-ask ./cmd/ai-ask && \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /out/go-ai-gem ./cmd/ai-gem && \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /out/go-ai-stop ./cmd/ai-stop && \
    CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" -o /out/go-story-summary ./cmd/story-summary

# ── Stage 2: Runtime ──────────────────────────────────────────
FROM debian:bookworm-slim

# Install Chromium and dependencies for headless browser automation
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-sandbox \
    fonts-liberation \
    fonts-noto-cjk \
    fonts-noto-color-emoji \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    ca-certificates \
    dumb-init \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r gemini && useradd -r -g gemini -G audio,video gemini \
    && mkdir -p /home/gemini/app /home/gemini/.browser-data \
    && chown -R gemini:gemini /home/gemini

WORKDIR /home/gemini/app

# Copy built binaries from builder stage
COPY --from=builder /out/go-ai-ask /usr/local/bin/go-ai-ask
COPY --from=builder /out/go-ai-gem /usr/local/bin/go-ai-gem
COPY --from=builder /out/go-ai-stop /usr/local/bin/go-ai-stop
COPY --from=builder /out/go-story-summary /usr/local/bin/go-story-summary

# Set environment variables
ENV PROJECT_ROOT=/home/gemini/app
ENV CHROME_PATH=/usr/bin/chromium
ENV CHROME_NO_SANDBOX=true

# Create output directories
RUN mkdir -p output output_summary_story .browser-data/gemini \
    && chown -R gemini:gemini .

# Switch to non-root user
USER gemini

# Default entrypoint with dumb-init for proper signal handling
ENTRYPOINT ["dumb-init", "--"]

# Default command shows help
CMD ["go-ai-ask", "--help"]
