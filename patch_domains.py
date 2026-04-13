import re

with open('config/aurora/domains.yaml', 'r', encoding='utf-8') as f:
    text = f.read()

text = text.replace(
    "check_full_ready_invariant: true\n",
    "check_full_ready_invariant: true\n    degraded_allowed_strategies:\n      - \"md_amr\"\n"
)

with open('config/aurora/domains.yaml', 'w', encoding='utf-8') as f:
    f.write(text)

print("Domains patched")
