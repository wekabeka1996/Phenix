#!/usr/bin/env python
"""Remove extra indentation from lines that should be de-indented."""

import re

with open('apps/reference/domains/execution_position/binance_execution_adapter.py', 'r') as f:
    content = f.read()

# Find patterns where we have extra indentation due to removed async with
# Pattern: lines that start with 16+ spaces where 12 spaces would be right
# This is a bit risky but we'll be conservative

lines = content.split('\n')
output = []

# Track indentation context
for i, line in enumerate(lines):
    # Skip empty lines
    if not line.strip():
        output.append(line)
        continue

    # Count leading spaces
    spaces = len(line) - len(line.lstrip())

    # If we have 20 spaces or more and the first token isn't a continuation,
    # and next non-empty line starts with 16 spaces, we probably have extra indent
    # This is too risky, let me just manually check specific patterns

    # Better: look for lines with "resp = await client" that have wrong indent
    if 'resp = await client' in line and spaces >= 20:
        # De-indent by 4 spaces
        output.append(line[4:])
    elif ('try:' in line or 'except' in line or 'if ' in line or 'elif ' in line or 'else:' in line) and spaces >= 20:
        # These control structures probably have wrong indent too
        output.append(line[4:])
    else:
        output.append(line)

with open('apps/reference/domains/execution_position/binance_execution_adapter.py', 'w') as f:
    f.write('\n'.join(output))

print('✅ De-indented excess indentation')
