# path: ppo_library/ppo_system/utils/logging.py
import logging
import sys

def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Створює та налаштовує стандартний логер."""
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger # Уникаємо дублювання хендлерів

    logger.setLevel(level)
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger