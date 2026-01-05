# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
Python UTF-8 Header Template для LLA
Додавати на початок launch-скриптів для стабільного кодування
"""

import os
import sys
import logging
import json
from typing import Any, Dict, Optional

# 🔧 Безпечні дефолти ще до імпорту решти
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 🔧 Консоль reconfigure (Python 3.7+)
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    # ок на старих Python
    pass

def setup_utf8_logging(log_file: str = "logs/run.log", level: int = logging.INFO) -> None:
    """
    Налаштування логування з UTF-8 для файлу і консолі
    
    Args:
        log_file: шлях до лог-файлу
        level: рівень логування
    """
    # Створюємо logs/ якщо не існує
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Логи (файл і консоль) з явним encoding
    logging.basicConfig(
        level=level,
        handlers=[
            logging.StreamHandler(),  # stdout уже UTF-8
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
        ],
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    
    # Тест кодування
    logging.info("UTF-8 логування активовано: кирилиця + емодзі ✅")

def dump_json_utf8(path: str, data: Dict[str, Any]) -> None:
    """
    JSON без ASCII-екранів (емодзі/кирилиця збережуться коректно)
    
    Args:
        path: шлях до JSON файлу (append mode)
        data: дані для збереження
    """
    # Створюємо папку якщо не існує
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=None) + "\n")

def test_utf8_encoding() -> bool:
    """
    Швидкий тест кодування
    
    Returns:
        True якщо кодування працює коректно
    """
    try:
        test_str = "Тест кирилиці + емодзі 🎯"
        print(f"UTF-8 тест: {test_str}")
        return True
    except UnicodeEncodeError:
        print("⚠ UTF-8 проблема виявлена")
        return False

# 🎯 Прапор для вимкнення емодзі якщо драйвери/бібліотеки ламають юнікод
USE_EMOJI = os.environ.get("LLA_USE_EMOJI", "1").lower() in ("1", "true", "yes")

def safe_emoji(emoji: str, fallback: str = "") -> str:
    """
    Безпечні емодзі з fallback
    
    Args:
        emoji: емодзі символ
        fallback: fallback текст
        
    Returns:
        emoji або fallback залежно від USE_EMOJI
    """
    return emoji if USE_EMOJI else fallback

if __name__ == "__main__":
    # Демо використання
    setup_utf8_logging()
    test_utf8_encoding()
    
    demo_data = {
        "test": "кирилиця працює",
        "emoji": safe_emoji("🎯", "[target]"),
        "timestamp": "2025-08-24T18:00:00"
    }
    
    dump_json_utf8("logs/utf8_test.json", demo_data)
    logging.info("UTF-8 header template готовий до використання")