from pathlib import Path


def sanitize(path: Path):
    b = path.read_bytes()
    b2 = b.replace(b"\x81", b" ")  # замінюємо на пробіл
    if b2 != b:
        path.write_bytes(b2)
        print("Sanitized:", path)


if __name__ == "__main__":
    for p in Path("configs").rglob("*.yaml"):
        sanitize(p)
