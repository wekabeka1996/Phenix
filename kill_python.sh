#!/bin/bash
# Kill all Python processes related to this project

echo -e "\033[33mKilling all Python processes...\033[0m"

# Find and kill all python processes
pids=$(pgrep -f "python.*apps.reference" 2>/dev/null)

if [ -n "$pids" ]; then
    for pid in $pids; do
        echo -e "\033[31mTerminating Python process: $pid\033[0m"
        kill -15 "$pid" 2>/dev/null  # SIGTERM first
    done
    
    sleep 1
    
    # Force kill if still running
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "\033[31mForce killing process: $pid\033[0m"
            kill -9 "$pid" 2>/dev/null  # SIGKILL
        fi
    done
else
    echo -e "\033[33mNo matching Python processes found.\033[0m"
fi

# Also kill any orphaned MarketDataWorker processes
worker_pids=$(pgrep -f "MarketDataWorker" 2>/dev/null)
if [ -n "$worker_pids" ]; then
    echo -e "\033[33mKilling orphaned MarketDataWorker processes...\033[0m"
    for pid in $worker_pids; do
        echo -e "\033[31mTerminating MarketDataWorker: $pid\033[0m"
        kill -9 "$pid" 2>/dev/null
    done
fi

# Kill any python processes in .venv
venv_pids=$(pgrep -f "Phenix/.venv.*python" 2>/dev/null)
if [ -n "$venv_pids" ]; then
    echo -e "\033[33mKilling Python processes in .venv...\033[0m"
    for pid in $venv_pids; do
        echo -e "\033[31mTerminating: $pid\033[0m"
        kill -15 "$pid" 2>/dev/null
        sleep 0.5
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
    done
fi

echo -e "\033[32mDone killing Python processes.\033[0m"
