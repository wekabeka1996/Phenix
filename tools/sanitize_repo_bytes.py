from pathlib import Path

TARGET_EXT = {".yaml", ".yml", ".md", ".toml", ".ini", ".cfg"}


def sanitize(path: Path):
    b = path.read_bytes()
    b2 = b.replace(b"\x81", b" ")
    if b2 != b:
        path.write_bytes(b2)
        print("Sanitized:", path)


if __name__ == "__main__":
    root = Path(".")
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in TARGET_EXT:
            try:
                sanitize(p)
            except Exception:
                pass
