#!/usr/bin/env python3
from apps.reference.config_loader import get_config

cfg = get_config()
cfg_dict = cfg.to_dict()

print("Config keys:", list(cfg_dict.keys()))
print("\nTop-level sections:")
for key in cfg_dict.keys():
    if isinstance(cfg_dict[key], dict):
        print(f"  {key}: {list(cfg_dict[key].keys())[:5]}...")
    else:
        print(f"  {key}: {type(cfg_dict[key]).__name__}")
