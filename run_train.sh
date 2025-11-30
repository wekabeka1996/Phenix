#!/bin/bash
export PYTORCH_ALLOC_CONF=expandable_segments:True,max_split_size_mb:32
echo "Starting training with Aggressive Offloading..."
.venv/bin/python3 deepseek_workspace/offline_analysis/train_qlora.py > train_offload.log 2>&1
