"""
Точка входа в приложение MSW Датчик - Мониторинг.
Графическое приложение для опроса датчика по Modbus RTU.
"""

import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
import logging

from ui.main_window import MainWindow
from utils.logger import setup_logging


def main():
    """Главная функция приложения."""
    # Настройка логирования
    setup_logging(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("Запуск приложения MSW Датчик - Мониторинг")
    
    # Создание приложения Qt
    app = QApplication(sys.argv)
    app.setApplicationName("MSW Датчик - Мониторинг")
    app.setOrganizationName("MSW")
    
    # Включение High DPI
    if hasattr(Qt, 'AA_EnableHighDpiScaling'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps, True)
    
    # Создание и показ главного окна
    window = MainWindow()
    window.show()
    
    logger.info("Главное окно отображено")
    
    # Запуск цикла событий
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
