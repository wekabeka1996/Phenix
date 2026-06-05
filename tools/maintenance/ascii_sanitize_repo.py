from pathlib import Path

EXT = {".yaml", ".yml", ".md", ".toml",
       ".ini", ".cfg", ".conf", ".json", ".txt"}


def to_ascii_bytes(b: bytes) -> bytes:
    # збережемо ASCII, інші байти замінимо на пробіли
    return bytes(ch if 32 <= ch <= 126 or ch in (9, 10, 13) else 32 for ch in b)


if __name__ == "__main__":
    root = Path(".")
    changed = 0
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in EXT:
            continue
        try:
            b = p.read_bytes()
            b2 = to_ascii_bytes(b)
            if b2 != b:
                p.write_bytes(b2)
                changed += 1
                print("Sanitized:", p)
        except Exception:
            pass
    print("Total sanitized:", changed)
