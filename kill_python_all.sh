#!/bin/bash

# Kill ALL Python processes (equivalent to kill_python.ps1 for Linux)
echo "Killing all Python processes..." >&2

# Kill python processes
python_pids=$(pgrep python 2>/dev/null)
if [ -n "$python_pids" ]; then
    echo "Found python processes: $python_pids" >&2
    for pid in $python_pids; do
        echo "Terminating Python process: $pid" >&2
        kill -9 "$pid" 2>/dev/null && echo "Successfully terminated process $pid" >&2 || echo "Process $pid already terminated or access denied" >&2
    done
else
    echo "No python processes found." >&2
fi

# Kill python3 processes (common on Linux)
python3_pids=$(pgrep python3 2>/dev/null)
if [ -n "$python3_pids" ]; then
    echo "Found python3 processes: $python3_pids" >&2
    for pid in $python3_pids; do
        echo "Terminating Python3 process: $pid" >&2
        kill -9 "$pid" 2>/dev/null && echo "Successfully terminated process $pid" >&2 || echo "Process $pid already terminated or access denied" >&2
    done
else
    echo "No python3 processes found." >&2
fi

echo "Done killing Python processes." >&2