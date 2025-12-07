#!/bin/bash

# Kill ALL Python processes on Linux (equivalent to kill_python.ps1)
echo -e "\033[33mKilling ALL Python processes...\033[0m"

# Function to kill processes gracefully
kill_python_processes() {
    local process_pattern="$1"
    local pids

    # Get PIDs of matching processes
    pids=$(pgrep -f "$process_pattern" 2>/dev/null)

    if [ -z "$pids" ]; then
        echo -e "\033[33mNo $process_pattern processes found.\033[0m"
        return 0
    fi

    echo -e "\033[33mFound $process_pattern processes: $pids\033[0m"

    # First try SIGTERM (graceful termination)
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "\033[31mSending SIGTERM to $process_pattern process: $pid\033[0m"
            kill -TERM "$pid" 2>/dev/null
        fi
    done

    # Wait a bit for graceful shutdown
    sleep 2

    # Check if any processes are still running and force kill them
    for pid in $pids; do
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "\033[31mProcess $pid still running, sending SIGKILL...\033[0m"
            kill -KILL "$pid" 2>/dev/null && echo -e "\033[32mSuccessfully terminated process $pid\033[0m" || echo -e "\033[33mFailed to terminate process $pid\033[0m"
        else
            echo -e "\033[32mProcess $pid terminated gracefully\033[0m"
        fi
    done
}

# Kill python processes
kill_python_processes "python"

# Kill python3 processes (common on Linux)
kill_python_processes "python3"

# Kill any process with python in the command line (catches virtual environments, scripts, etc.)
echo -e "\033[33mChecking for any remaining Python-related processes...\033[0m"
remaining=$(pgrep -f python 2>/dev/null)
if [ -n "$remaining" ]; then
    echo -e "\033[33mFound remaining Python processes: $remaining\033[0m"
    echo -e "\033[33mForce killing remaining processes...\033[0m"
    kill -KILL $remaining 2>/dev/null
fi

echo -e "\033[32mDone killing Python processes.\033[0m"

echo -e "\033[32mDone killing Python processes.\033[0m"
