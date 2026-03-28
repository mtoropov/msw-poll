"""
Конфигурация и константы приложения.
"""

# Настройки по умолчанию
DEFAULT_PORT = "COM1"
DEFAULT_SLAVE_ADDRESS = 1
DEFAULT_BAUDRATE = 9600
DEFAULT_PARITY = 'N'  # N - none, E - even, O - odd
DEFAULT_TIMEOUT = 0.3  # секунды
DEFAULT_POLL_INTERVAL = 0.1  # секунды

# Доступные скорости передачи
BAUDRATES = [9600, 19200, 38400, 57600, 115200]

# Настройки окна
WINDOW_TITLE = "MSW Датчик - Мониторинг"
WINDOW_MIN_WIDTH = 800
WINDOW_MIN_HEIGHT = 600

# Настройки логирования
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
