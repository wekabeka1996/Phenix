#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Aurora Backtest Runner
# ═══════════════════════════════════════════════════════════════════════════════
# This script:
#   1. Activates the Python virtual environment
#   2. Runs the backtest simulation
#   3. Automatically summarizes the latest report
#
# Usage: ./run_backtest.sh
# ═══════════════════════════════════════════════════════════════════════════════

set -e  # Exit on error

# Get script directory (project root)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "═══════════════════════════════════════════════════════════════"
echo "🚀 AURORA BACKTEST RUNNER"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Step 1: Activate venv
if [ -d "venv" ]; then
    echo "📦 Activating virtual environment (venv/)..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "📦 Activating virtual environment (.venv/)..."
    source .venv/bin/activate
else
    echo "⚠️  No virtual environment found (venv/ or .venv/)"
    echo "   Running with system Python..."
fi

echo "   Python: $(which python3)"
echo ""

# Step 2: Run backtest
echo "═══════════════════════════════════════════════════════════════"
echo "🔄 Starting backtest simulation..."
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Backtest isolation: use dedicated WAL dir to avoid replaying large LIVE/dev WAL history.
export WAL_DIR="ops/wal_backtest"
mkdir -p "$WAL_DIR"
rm -f "$WAL_DIR"/*.jsonl 2>/dev/null || true

python3 -m apps.reference.main
BACKTEST_EXIT_CODE=$?

if [ $BACKTEST_EXIT_CODE -ne 0 ]; then
    echo ""
    echo "❌ Backtest failed with exit code $BACKTEST_EXIT_CODE"
    exit $BACKTEST_EXIT_CODE
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "📊 Finding latest backtest report..."
echo "═══════════════════════════════════════════════════════════════"

# Step 3: Find latest report and summarize
REPORTS_DIR="$SCRIPT_DIR/reports/backtests"
if [ ! -d "$REPORTS_DIR" ]; then
    echo "⚠️  Reports directory not found: $REPORTS_DIR"
    exit 0
fi

# Find most recent backtest_*.json (excluding .summary.json)
LATEST_REPORT=$(ls -t "$REPORTS_DIR"/backtest_*.json 2>/dev/null | grep -v ".summary.json" | head -1)

if [ -z "$LATEST_REPORT" ]; then
    echo "⚠️  No backtest report found in $REPORTS_DIR"
    exit 0
fi

echo "📄 Latest report: $LATEST_REPORT"
echo ""

# Step 4: Run summarizer
echo "═══════════════════════════════════════════════════════════════"
echo "📈 Generating summary..."
echo "═══════════════════════════════════════════════════════════════"
echo ""

python3 tools/backtest_summarize.py "$LATEST_REPORT"

SUMMARY_FILE="${LATEST_REPORT%.json}.summary.json"
if [ -f "$SUMMARY_FILE" ]; then
    echo ""
    echo "✅ Summary saved to: $SUMMARY_FILE"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "✅ BACKTEST COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
