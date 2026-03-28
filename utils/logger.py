"""
Настройка логирования приложения.
"""

import logging
import sys
from config import LOG_FORMAT, LOG_DATE_FORMAT


def setup_logging(level=logging.INFO):
    """
    Настройка системы логирования.

    Args:
        level: Уровень логирования (по умолчанию INFO)
    """
    # Базовая настройка
    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Отключение избыточного логирования библиотек
    logging.getLogger('PyQt6').setLevel(logging.WARNING)
    logging.getLogger('minimalmodbus').setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Логирование настроено")
