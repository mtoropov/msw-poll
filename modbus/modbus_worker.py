"""
Рабочий поток для циклического опроса датчика Modbus.
Использует QThread для работы в фоновом режиме без блокировки GUI.
"""

from PyQt6.QtCore import QThread, pyqtSignal, QMutex, QWaitCondition
import time
import logging
from typing import Optional

from .modbus_client import ModbusClient, DeviceData, CoilState
import config

logger = logging.getLogger(__name__)


class ModbusWorker(QThread):
    """
    Рабочий поток для опроса Modbus-устройства.
    
    Сигналы:
        data_received: Отправляется при успешном чтении данных (DeviceData)
        coil_status_received: Отправляется при чтении состояний coils (CoilState)
        error_occurred: Отправляется при ошибке (str)
        connection_status: Отправляется при изменении статуса соединения (bool, str)
    """
    
    # Сигналы (потокобезопасная связь с GUI)
    data_received = pyqtSignal(object)  # DeviceData
    coil_status_received = pyqtSignal(object)  # CoilState
    error_occurred = pyqtSignal(str)  # Сообщение об ошибке
    connection_status = pyqtSignal(bool, str)  # (connected, message)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.client = ModbusClient()
        self._running = False
        self._stopping = False
        
        # Параметры подключения
        self.port: str = ""
        self.slave_address: int = 1
        self.baudrate: int = 9600
        self.parity: str = 'N'
        self.timeout: float = config.DEFAULT_TIMEOUT
        self.poll_interval: float = 1.0  # Интервал опроса в секундах
        
        # Потокобезопасность
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        
        # Флаги для управления
        self._read_coils_once = False  # Флаг для однократного чтения coils
        self._coil_write_queue = []  # Очередь команд записи coils
        
    def configure(self, port: str, slave_address: int, baudrate: int, 
                  parity: str = 'N', poll_interval: float = 1.0, 
                  timeout: float = None) -> None:
        """
        Настройка параметров подключения.
        
        Args:
            port: COM-порт
            slave_address: Адрес устройства
            baudrate: Скорость передачи
            parity: Четность ('N', 'E', 'O')
            poll_interval: Интервал опроса в секундах
            timeout: Таймаут операций в секундах
        """
        if timeout is None:
            timeout = config.DEFAULT_TIMEOUT
            
        self.mutex.lock()
        self.port = port
        self.slave_address = slave_address
        self.baudrate = baudrate
        self.parity = parity
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.mutex.unlock()
        
        logger.info(f"Настройка: {port}, адрес {slave_address}, скорость {baudrate}, "
                   f"четность {parity}, таймаут {timeout}с, интервал {poll_interval}с")
    
    def request_coil_read(self) -> None:
        """Запрос однократного чтения состояний coils."""
        self.mutex.lock()
        self._read_coils_once = True
        self.condition.wakeOne()
        self.mutex.unlock()
        logger.debug("Запрошено чтение coils")
    
    def request_coil_write(self, coil_address: int, value: bool) -> None:
        """
        Запрос на запись coil-регистра из другого потока.
        
        Args:
            coil_address: Адрес coil (0, 10, 11)
            value: Значение (True/False)
        """
        self.mutex.lock()
        self._coil_write_queue.append((coil_address, value))
        self.condition.wakeOne()
        self.mutex.unlock()
        logger.debug(f"Запрошена запись coil {coil_address} = {value}")
    
    def run(self) -> None:
        """
        Основной цикл рабочего потока.
        Выполняется в отдельном потоке, не блокирует GUI.
        """
        logger.info("Рабочий поток запущен")
        self._running = True
        self._stopping = False
        
        # Попытка подключения
        try:
            self.client.connect(self.port, self.slave_address, self.baudrate, 
                              self.timeout, self.parity)
            self.connection_status.emit(True, "Подключено")
            
            # Однократное чтение состояний coils при подключении
            try:
                coil_state = self.client.read_coil_states()
                self.coil_status_received.emit(coil_state)
            except Exception as e:
                logger.warning(f"Не удалось прочитать состояния coils: {e}")
                
        except Exception as e:
            error_msg = f"Ошибка подключения: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            self.connection_status.emit(False, error_msg)
            self._running = False
            return
        
        # Основной цикл опроса
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self._running and not self._stopping:
            try:
                # Обработка очереди записи coils
                self.mutex.lock()
                write_queue = self._coil_write_queue.copy()
                self._coil_write_queue.clear()
                read_coils_flag = self._read_coils_once
                self._read_coils_once = False
                self.mutex.unlock()
                
                # Выполнение записи coils
                for coil_address, value in write_queue:
                    try:
                        self.client.write_coil(coil_address, value)
                        logger.info(f"Coil {coil_address} записан: {value}")
                    except Exception as e:
                        error_msg = f"Ошибка записи coil {coil_address}: {e}"
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                
                # Чтение coils по запросу
                if read_coils_flag:
                    try:
                        coil_state = self.client.read_coil_states()
                        self.coil_status_received.emit(coil_state)
                    except Exception as e:
                        error_msg = f"Ошибка чтения coils: {e}"
                        logger.error(error_msg)
                        self.error_occurred.emit(error_msg)
                
                # Чтение данных датчика
                data = self.client.read_all_data()
                self.data_received.emit(data)
                
                # Сброс счетчика ошибок при успешном чтении
                consecutive_errors = 0
                
            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Ошибка опроса ({consecutive_errors}/{max_consecutive_errors}): {e}"
                logger.error(error_msg)
                self.error_occurred.emit(error_msg)
                
                # Если слишком много ошибок подряд - отключаемся
                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Превышено количество последовательных ошибок, отключение")
                    self.connection_status.emit(False, "Потеря связи с устройством")
                    break
            
            # Ожидание перед следующим опросом
            self.mutex.lock()
            if self._running and not self._stopping:
                # Ждем указанный интервал или пока не разбудят для записи
                self.condition.wait(self.mutex, int(self.poll_interval * 1000))
            self.mutex.unlock()
        
        # Отключение
        try:
            self.client.disconnect()
            logger.info("Отключено от устройства")
        except Exception as e:
            logger.error(f"Ошибка при отключении: {e}")
        
        self._running = False
        logger.info("Рабочий поток завершен")
    
    def stop(self) -> None:
        """
        Остановка рабочего потока.
        Вызывается из главного потока GUI.
        """
        logger.info("Запрос на остановку рабочего потока")
        self.mutex.lock()
        self._stopping = True
        self._running = False
        self.condition.wakeOne()
        self.mutex.unlock()
        
        # Ждем завершения потока (максимум 5 секунд)
        if not self.wait(5000):
            logger.warning("Поток не завершился за 5 секунд, принудительное завершение")
            self.terminate()
            self.wait()
    
    def is_running(self) -> bool:
        """Проверка, выполняется ли поток."""
        return self._running
    
    def set_poll_interval(self, interval: float) -> None:
        """
        Изменение интервала опроса во время работы.
        
        Args:
            interval: Новый интервал в секундах
        """
        self.mutex.lock()
        self.poll_interval = interval
        self.condition.wakeOne()
        self.mutex.unlock()
        logger.info(f"Интервал опроса изменен: {interval}с")
