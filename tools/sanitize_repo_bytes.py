from pathlib import Path

TARGET_EXT = {".yaml", ".yml", ".md", ".toml", ".ini", ".cfg"}


def sanitize(path: Path):
    b = path.read_bytes()
    # Replace various problematic bytes that cause Unicode decode errors
    replacements = [
        (b"\x81", b" "),  # Original target
        (b"\xd1", b" "),  # Cyrillic character encoding issue
        (b"\xd0", b" "),  # More Cyrillic encoding issues
        (b"\xbf", b" "),  # Additional problematic byte
        (b"\x80", b" "),  # More encoding issues
        (b"\xb0", b" "),  # Degree symbol or other encoding issue
    ]
    b2 = b
    for old, new in replacements:
        b2 = b2.replace(old, new)
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
