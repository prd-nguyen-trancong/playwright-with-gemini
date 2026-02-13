# Makefile for go-dev-tools
# Build all Gemini automation tools as Go binaries

BINARY_DIR := bin
GO := go
GOFLAGS := -ldflags="-s -w"

# All commands to build (directory names under cmd/)
CMDS := go-ai-ask go-ai-gem go-ai-stop go-story-summary

.PHONY: all clean build deps test fmt lint help

## Build all binaries
all: build

## Download dependencies
deps:
	$(GO) mod tidy
	$(GO) mod download

## Build all binaries into bin/
build: deps
	@mkdir -p $(BINARY_DIR)
	@for cmd in $(CMDS); do \
		echo "Building $$cmd..."; \
		$(GO) build $(GOFLAGS) -o $(BINARY_DIR)/$$cmd ./cmd/$$cmd; \
	done
	@echo "Done! Binaries in $(BINARY_DIR)/"
	@ls -la $(BINARY_DIR)/

## Build for Linux (Docker/container)
build-linux: deps
	@mkdir -p $(BINARY_DIR)
	@for cmd in $(CMDS); do \
		echo "Building $$cmd (linux/amd64)..."; \
		GOOS=linux GOARCH=amd64 $(GO) build $(GOFLAGS) -o $(BINARY_DIR)/$$cmd ./cmd/$$cmd; \
	done
	@echo "Done! Linux binaries in $(BINARY_DIR)/"

## Build for macOS ARM (Apple Silicon)
build-darwin-arm: deps
	@mkdir -p $(BINARY_DIR)
	@for cmd in $(CMDS); do \
		echo "Building $$cmd (darwin/arm64)..."; \
		GOOS=darwin GOARCH=arm64 $(GO) build $(GOFLAGS) -o $(BINARY_DIR)/$$cmd ./cmd/$$cmd; \
	done
	@echo "Done! macOS ARM binaries in $(BINARY_DIR)/"

## Run tests
test:
	$(GO) test ./... -v

## Format code
fmt:
	$(GO) fmt ./...

## Run linter (requires golangci-lint)
lint:
	golangci-lint run ./...

## Clean build artifacts
clean:
	rm -rf $(BINARY_DIR)
	$(GO) clean

## Install binaries to /usr/local/bin
install: build
	@for cmd in $(CMDS); do \
		echo "Installing $$cmd -> /usr/local/bin/$$cmd"; \
		sudo cp $(BINARY_DIR)/$$cmd /usr/local/bin/$$cmd; \
	done
	@echo "Installed! Run: go-ai-ask, go-ai-gem, go-ai-stop, go-story-summary"

## Show help
help:
	@echo "Available targets:"
	@echo "  make build           - Build all binaries"
	@echo "  make build-linux     - Build for Linux (Docker)"
	@echo "  make build-darwin-arm - Build for macOS ARM"
	@echo "  make deps            - Download dependencies"
	@echo "  make test            - Run tests"
	@echo "  make fmt             - Format code"
	@echo "  make lint            - Run linter"
	@echo "  make clean           - Clean build artifacts"
	@echo "  make install         - Install to /usr/local/bin"
	@echo ""
	@echo "Binaries:"
	@echo "  go-ai-ask           - Fast Gemini text chat"
	@echo "  go-ai-gem           - Fast Gemini Gem chat"
	@echo "  go-ai-stop          - Stop browser daemon"
	@echo "  go-story-summary    - Story scrape + summarize"
