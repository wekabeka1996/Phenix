#!/usr/bin/env python
"""Fix indentation issues from async with httpx.AsyncClient() replacement."""

import re

with open('apps/reference/domains/execution_position/binance_execution_adapter.py', 'r') as f:
    lines = f.readlines()

output = []
i = 0
fixed_count = 0

while i < len(lines):
    line = lines[i]

    # Check if this line contains 'async with httpx.AsyncClient()'
    if 'async with httpx.AsyncClient()' in line:
        # Get indentation level
        indent = len(line) - len(line.lstrip())
        indent_str = line[:indent]

        # Replace 'async with ... as client:' with 'client = await self.get_http_client()'
        output.append(indent_str + 'client = await self.get_http_client()\n')
        fixed_count += 1

        # Skip the 'async with' line and decrease indent of all following lines by 4 spaces
        i += 1

        # Collect indented block and dedent it by 4 spaces
        while i < len(lines):
            next_line = lines[i]

            # Check for dedent back to original level or less
            if next_line.strip() and not next_line.startswith(indent_str + '    '):
                # End of block - don't consume this line
                break

            # Dedent lines inside the block by 4 spaces
            if next_line.startswith(indent_str + '    '):
                # Remove 4 spaces of extra indentation
                output.append(next_line[4:])
            else:
                output.append(next_line)

            i += 1
    else:
        output.append(line)
        i += 1

with open('apps/reference/domains/execution_position/binance_execution_adapter.py', 'w') as f:
    f.writelines(output)

print(f'✅ Fixed {fixed_count} async with indentation issues')
