import os
from fastapi import FastAPI, HTTPException, Query
from pathlib import Path

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL")

app = FastAPI(
    title="Aurora Log API",
    version="0.1.0",
    servers=[{"url": PUBLIC_BASE_URL}] if PUBLIC_BASE_URL else [],
)

# Directories
BASE_DIR = Path(__file__).parent.resolve()
LOG_FILE_NAME = os.environ.get("LOG_FILE", "aurora_trades.log")
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = (LOG_DIR / LOG_FILE_NAME).resolve()
DOCS_DIR = BASE_DIR / "docs"
CONFIG_DIR = BASE_DIR / "config"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/logs/tail")
def tail_log(lines: int = Query(200, ge=1, le=2000)):
    if not LOG_FILE.exists():
        raise HTTPException(404, "Log file not found")

    with LOG_FILE.open(
        "r",
        encoding="utf-8",
        errors="replace"
    ) as f:
        data = f.readlines()[-lines:]

    return {
        "file": str(LOG_FILE),
        "lines": len(data),
        "data": data
    }

@app.get("/debug/file_check")
def debug_file_check():
    """Дебаг endpoint для діагностики лог-файлу"""
    import os as os_module
    
    log_dir = LOG_FILE.parent
    log_files = []
    if log_dir.exists():
        log_files = [f.name for f in log_dir.iterdir() if f.suffix == ".log"]
    
    return {
        "config": {
            "LOG_FILE_NAME": LOG_FILE_NAME,
            "LOG_FILE_PATH": str(LOG_FILE),
            "LOG_FILE_RESOLVED": str(LOG_FILE.resolve()),
        },
        "process": {
            "cwd": os_module.getcwd(),
            "pid": os_module.getpid(),
        },
        "file_status": {
            "exists": LOG_FILE.exists(),
            "is_file": LOG_FILE.is_file(),
            "readable": os_module.access(LOG_FILE, os_module.R_OK) if LOG_FILE.exists() else False,
            "size_bytes": LOG_FILE.stat().st_size if LOG_FILE.exists() else 0,
        },
        "logs_directory": {
            "path": str(log_dir),
            "exists": log_dir.exists(),
            "log_files": log_files,
        }
    }

def _safe_path(base_dir: Path, relative_path: str) -> Path:
    """Secure path resolution: ensure file is within base_dir"""
    target = (base_dir / relative_path).resolve()
    if not str(target).startswith(str(base_dir)):
        raise HTTPException(403, "Access denied: path outside allowed directory")
    return target

@app.get("/docs/list")
def docs_list():
    """List all files in docs directory (recursive)"""
    if not DOCS_DIR.exists():
        return {"path": str(DOCS_DIR), "exists": False, "files": []}
    
    files = []
    for root, dirs, filenames in os.walk(DOCS_DIR):
        for fname in filenames:
            fpath = Path(root) / fname
            rel_path = fpath.relative_to(DOCS_DIR)
            files.append({
                "path": str(rel_path),
                "absolute": str(fpath),
                "size": fpath.stat().st_size,
                "ext": fpath.suffix,
            })
    
    return {
        "path": str(DOCS_DIR),
        "exists": True,
        "count": len(files),
        "files": files
    }

@app.get("/docs/read")
def docs_read(path: str = Query(..., description="Relative path within docs/")):
    """Read a specific file from docs directory"""
    if not DOCS_DIR.exists():
        raise HTTPException(404, "docs directory not found")
    
    target = _safe_path(DOCS_DIR, path)
    if not target.exists():
        raise HTTPException(404, f"File not found: {path}")
    if not target.is_file():
        raise HTTPException(400, "Path is not a file")
    
    try:
        with target.open("r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "path": str(target.relative_to(DOCS_DIR)),
            "absolute": str(target),
            "size": target.stat().st_size,
            "content": content
        }
    except Exception as e:
        raise HTTPException(500, f"Error reading file: {str(e)}")

@app.get("/config/list")
def config_list():
    """List all config files (yaml, json, ini, toml, etc.)"""
    if not CONFIG_DIR.exists():
        return {"path": str(CONFIG_DIR), "exists": False, "files": []}
    
    config_extensions = {".yaml", ".yml", ".json", ".ini", ".toml", ".env", ".conf"}
    files = []
    
    for root, dirs, filenames in os.walk(CONFIG_DIR):
        for fname in filenames:
            if Path(fname).suffix.lower() in config_extensions:
                fpath = Path(root) / fname
                rel_path = fpath.relative_to(CONFIG_DIR)
                files.append({
                    "path": str(rel_path),
                    "absolute": str(fpath),
                    "size": fpath.stat().st_size,
                    "ext": fpath.suffix,
                })
    
    return {
        "path": str(CONFIG_DIR),
        "exists": True,
        "count": len(files),
        "files": files
    }

@app.get("/config/read")
def config_read(path: str = Query(..., description="Relative path within config/")):
    """Read a specific config file"""
    if not CONFIG_DIR.exists():
        raise HTTPException(404, "config directory not found")
    
    target = _safe_path(CONFIG_DIR, path)
    if not target.exists():
        raise HTTPException(404, f"Config file not found: {path}")
    if not target.is_file():
        raise HTTPException(400, "Path is not a file")
    
    try:
        with target.open("r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "path": str(target.relative_to(CONFIG_DIR)),
            "absolute": str(target),
            "size": target.stat().st_size,
            "content": content
        }
    except Exception as e:
        raise HTTPException(500, f"Error reading config: {str(e)}")
