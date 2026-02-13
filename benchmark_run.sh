#!/bin/bash
# Benchmark: Python ai-ask vs Go go-ai-ask (10 requests each)
# Runs each request as a separate process with timing

cd "$(dirname "$0")"
export PROJECT_ROOT="$(pwd)"

PROMPTS=(
  "What is 2+2?"
  "Name 3 colors"
  "What is Python?"
  "Hello"
  "What is 10*5?"
  "Name a planet"
  "What is AI?"
  "Say hi"
  "What is Go?"
  "Name a fruit"
)

RESULTS_FILE="benchmark_results.txt"
> "$RESULTS_FILE"

run_request() {
  local tool="$1"
  local prompt="$2"
  local idx="$3"
  local tmpfile="/tmp/bench_${tool}_${idx}.txt"
  
  local start end elapsed resp_len
  start=$(python3 -c "import time; print(time.time())")
  
  if [ "$tool" = "python" ]; then
    poetry run python -m tools.gemini.fast_ask --quiet "$prompt" > "$tmpfile" 2>/dev/null
  else
    ./go-dev-tools/bin/go-ai-ask --quiet "$prompt" > "$tmpfile" 2>/dev/null
  fi
  
  end=$(python3 -c "import time; print(time.time())")
  elapsed=$(python3 -c "print(f'{$end - $start:.2f}')")
  resp_len=$(wc -c < "$tmpfile" | tr -d ' ')
  
  echo "$elapsed"
  echo "  R${idx}: ${elapsed}s (${resp_len} chars)" >> "$RESULTS_FILE"
}

echo "=== Benchmark: Python ai-ask vs Go go-ai-ask ===" | tee -a "$RESULTS_FILE"
echo "Date: $(date)" | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"

# ─── Python Benchmark ───────────────────────────────────────────
echo "=== PYTHON (ai-ask) ===" | tee -a "$RESULTS_FILE"

# Ensure clean start
poetry run python -m tools.gemini.fast_ask --stop 2>/dev/null || true
pkill -f "user-data-dir.*gemini[^-]" 2>/dev/null || true
sleep 3

PY_TIMES=()
for i in $(seq 0 9); do
  prompt="${PROMPTS[$i]}"
  printf "  Python %2d/10: %-20s" "$((i+1))" "\"$prompt\""
  
  t=$(run_request "python" "$prompt" "$((i+1))")
  PY_TIMES+=("$t")
  echo " → ${t}s"
done

# Python summary
PY_COLD="${PY_TIMES[0]}"
PY_TOTAL=$(python3 -c "t=[${PY_TIMES[*]/%/,}]; print(f'{sum(t):.2f}')")
PY_WARM_AVG=$(python3 -c "t=[${PY_TIMES[*]/%/,}]; w=t[1:]; print(f'{sum(w)/len(w):.2f}' if w else '0')")
echo "" | tee -a "$RESULTS_FILE"
echo "  Python: Total=${PY_TOTAL}s | Cold=${PY_COLD}s | Warm avg=${PY_WARM_AVG}s" | tee -a "$RESULTS_FILE"

# Stop Python daemon
poetry run python -m tools.gemini.fast_ask --stop 2>/dev/null || true
pkill -f "user-data-dir.*gemini[^-]" 2>/dev/null || true
sleep 5

# ─── Go Benchmark ───────────────────────────────────────────────
echo "" | tee -a "$RESULTS_FILE"
echo "=== GO (go-ai-ask) ===" | tee -a "$RESULTS_FILE"

# Ensure clean start
./go-dev-tools/bin/go-ai-stop 2>/dev/null || true
pkill -f "user-data-dir.*gemini-go" 2>/dev/null || true
sleep 3

GO_TIMES=()
for i in $(seq 0 9); do
  prompt="${PROMPTS[$i]}"
  printf "  Go     %2d/10: %-20s" "$((i+1))" "\"$prompt\""
  
  t=$(run_request "go" "$prompt" "$((i+1))")
  GO_TIMES+=("$t")
  echo " → ${t}s"
done

# Go summary
GO_COLD="${GO_TIMES[0]}"
GO_TOTAL=$(python3 -c "t=[${GO_TIMES[*]/%/,}]; print(f'{sum(t):.2f}')")
GO_WARM_AVG=$(python3 -c "t=[${GO_TIMES[*]/%/,}]; w=t[1:]; print(f'{sum(w)/len(w):.2f}' if w else '0')")
echo "" | tee -a "$RESULTS_FILE"
echo "  Go: Total=${GO_TOTAL}s | Cold=${GO_COLD}s | Warm avg=${GO_WARM_AVG}s" | tee -a "$RESULTS_FILE"

# Stop Go daemon
./go-dev-tools/bin/go-ai-stop 2>/dev/null || true

# ─── Summary ────────────────────────────────────────────────────
echo "" | tee -a "$RESULTS_FILE"
echo "=== COMPARISON ===" | tee -a "$RESULTS_FILE"
echo "  Python: Total=${PY_TOTAL}s | Cold=${PY_COLD}s | Warm avg=${PY_WARM_AVG}s" | tee -a "$RESULTS_FILE"
echo "  Go:     Total=${GO_TOTAL}s | Cold=${GO_COLD}s | Warm avg=${GO_WARM_AVG}s" | tee -a "$RESULTS_FILE"
SPEEDUP=$(python3 -c "py=${PY_WARM_AVG}; go=${GO_WARM_AVG}; print(f'{py/go:.2f}x' if go > 0 else 'N/A')")
echo "  Warm speedup: Go is ${SPEEDUP} faster" | tee -a "$RESULTS_FILE"
echo "" | tee -a "$RESULTS_FILE"
echo "Done! Results in: $RESULTS_FILE"
