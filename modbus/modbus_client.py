"""
Клиент для работы с датчиком через Modbus RTU.
Использует библиотеку minimalmodbus.
"""

import minimalmodbus
import serial
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class DeviceData:
    """Структура данных устройства."""
    def __init__(self):
        self.noise_level: Optional[float] = None  # дБ
        self.temperature: Optional[float] = None  # °C
        self.humidity: Optional[float] = None  # %RH
        self.co2: Optional[int] = None  # ppm
        self.illuminance: Optional[float] = None  # лк
        self.air_quality: Optional[int] = None  # ppb
        self.motion: Optional[int] = None  # движение
        self.uptime: Optional[int] = None  # секунды

    def __repr__(self):
        return (f"DeviceData(noise={self.noise_level}, temp={self.temperature}, "
                f"humidity={self.humidity}, co2={self.co2}, "
                f"illuminance={self.illuminance}, air_quality={self.air_quality}, "
                f"motion={self.motion}, uptime={self.uptime})")


class CoilState:
    """Структура состояния coil-регистров."""
    def __init__(self):
        self.buzzer: bool = False  # Пищалка
        self.red_led: bool = False  # Красный светодиод
        self.green_led: bool = False  # Зеленый светодиод

    def __repr__(self):
        return f"CoilState(buzzer={self.buzzer}, red={self.red_led}, green={self.green_led})"


class ModbusClient:
    """
    Клиент для работы с датчиком по Modbus RTU.
    Обертка над minimalmodbus с обработкой специфики устройства.
    """

    # Адреса holding-регистров
    REG_NOISE = 3
    REG_TEMPERATURE = 4
    REG_HUMIDITY = 5
    REG_CO2 = 8
    REG_ILLUMINANCE_HIGH = 9  # Старшее слово u32
    REG_ILLUMINANCE_LOW = 10
    REG_AIR_QUALITY = 11
    REG_UPTIME_HIGH = 104  # Старшее слово u32
    REG_UPTIME_LOW = 105
    REG_MOTION = 283  # Движение

    # Адреса coil-регистров
    COIL_BUZZER = 0
    COIL_RED_LED = 10
    COIL_GREEN_LED = 11

    # Значения ошибок
    ERROR_TEMP = 0x7FFF
    ERROR_HUMIDITY = 0xFFFF
    ERROR_CO2 = 0xFFFF
    ERROR_AIR_QUALITY = 0xFFFF
    ERROR_ILLUMINANCE = 0xFFFFFFFF
    ERROR_MOTION = 0xFFFF

    def __init__(self):
        self.instrument: Optional[minimalmodbus.Instrument] = None
        self.is_connected: bool = False

    def connect(self, port: str, slave_address: int, baudrate: int = 9600,
                timeout: float = 2.0, parity: str = 'N') -> None:
        """
        Подключение к устройству.

        Args:
            port: COM-порт (например, 'COM3' или '/dev/ttyUSB0')
            slave_address: Адрес устройства Modbus (1-247)
            baudrate: Скорость передачи данных (9600, 19200, 38400, 57600, 115200)
            timeout: Таймаут операции в секундах
            parity: Четность ('N' - none, 'E' - even, 'O' - odd)

        Raises:
            serial.SerialException: Ошибка открытия порта
            ValueError: Некорректные параметры
        """
        if self.is_connected:
            self.disconnect()

        logger.info(f"Подключение к {port}, адрес {slave_address}, скорость {baudrate}, четность {parity}, таймаут {timeout}с")

        # Создание инструмента minimalmodbus
        self.instrument = minimalmodbus.Instrument(port, slave_address)
        self.instrument.serial.baudrate = baudrate
        self.instrument.serial.timeout = timeout

        # Настройка параметров порта
        if parity.upper() == 'N':
            self.instrument.serial.parity = serial.PARITY_NONE
        elif parity.upper() == 'E':
            self.instrument.serial.parity = serial.PARITY_EVEN
        elif parity.upper() == 'O':
            self.instrument.serial.parity = serial.PARITY_ODD
        else:
            raise ValueError(f"Неподдерживаемая четность: {parity}")

        self.instrument.serial.stopbits = 1
        self.instrument.serial.bytesize = 8

        # Настройки minimalmodbus
        self.instrument.mode = minimalmodbus.MODE_RTU
        self.instrument.clear_buffers_before_each_transaction = True
        self.instrument.close_port_after_each_call = False
        self.instrument.debug = False  # Для отладки можно включить True

        # Минимальная задержка между запросами (миллисекунды)
        self.instrument.serial.inter_byte_timeout = None

        self.is_connected = True
        logger.info("Подключение установлено успешно")

    def disconnect(self) -> None:
        """Отключение от устройства."""
        if self.instrument is not None and hasattr(self.instrument, 'serial'):
            try:
                self.instrument.serial.close()
                logger.info("Соединение закрыто")
            except Exception as e:
                logger.error(f"Ошибка при закрытии соединения: {e}")

        self.instrument = None
        self.is_connected = False

    def read_all_data(self) -> DeviceData:
        """
        Чтение всех параметров датчика.
        Читаем блоками, чтобы не запрашивать несуществующие регистры 6-7.

        Returns:
            DeviceData: Структура с данными датчика

        Raises:
            IOError: Ошибка связи с устройством
            ValueError: Некорректный ответ устройства
        """
        if not self.is_connected or self.instrument is None:
            raise IOError("Устройство не подключено")

        data = DeviceData()

        # Блок 1: Читаем регистры 3-5 (шум, температура, влажность)
        try:
            registers = self.instrument.read_registers(self.REG_NOISE, 3, functioncode=3)

            # Регистр 3 - уровень шума
            data.noise_level = registers[0] * 0.01

            # Регистр 4 - температура
            raw_temp = registers[1]
            if raw_temp == self.ERROR_TEMP:
                data.temperature = None
                logger.debug("Температура: ошибка датчика")
            else:
                if raw_temp > 32767:
                    raw_temp = raw_temp - 65536
                data.temperature = raw_temp * 0.01

            # Регистр 5 - влажность
            raw_hum = registers[2]
            if raw_hum == self.ERROR_HUMIDITY:
                data.humidity = None
                logger.debug("Влажность: ошибка датчика")
            else:
                data.humidity = raw_hum * 0.01

        except Exception as e:
            logger.error(f"Ошибка чтения регистров 3-5: {e}")
            raise

        # Блок 2: Читаем регистры 8-11 (CO2, освещенность, качество воздуха)
        try:
            registers = self.instrument.read_registers(self.REG_CO2, 4, functioncode=3)

            # Регистр 8 - CO2
            raw_co2 = registers[0]
            if raw_co2 == self.ERROR_CO2:
                data.co2 = None
                logger.debug("CO2: ошибка датчика")
            else:
                data.co2 = raw_co2

            # Регистры 9-10 - освещенность u32
            raw_illuminance = (registers[1] << 16) | registers[2]
            if raw_illuminance == self.ERROR_ILLUMINANCE:
                data.illuminance = None
                logger.debug("Освещенность: ошибка датчика")
            else:
                data.illuminance = raw_illuminance * 0.01

            # Регистр 11 - качество воздуха
            raw_aq = registers[3]
            if raw_aq == self.ERROR_AIR_QUALITY:
                data.air_quality = None
                logger.debug("Качество воздуха: ошибка датчика")
            else:
                data.air_quality = raw_aq

        except Exception as e:
            logger.error(f"Ошибка чтения регистров 8-11: {e}")
            raise

        # Блок 3: Чтение времени работы (регистры 104-105, u32)
        try:
            uptime_regs = self.instrument.read_registers(self.REG_UPTIME_HIGH, 2, functioncode=3)
            data.uptime = (uptime_regs[0] << 16) | uptime_regs[1]
        except Exception as e:
            logger.warning(f"Ошибка чтения времени работы: {e}")

        # Блок 4: Чтение движения (регистр 283)
        try:
            raw_motion = self.instrument.read_register(self.REG_MOTION, functioncode=3)
            if raw_motion == self.ERROR_MOTION:
                data.motion = None
                logger.debug("Движение: ошибка датчика")
            else:
                data.motion = raw_motion
        except Exception as e:
            logger.warning(f"Ошибка чтения движения: {e}")

        return data

    def read_coil_states(self) -> CoilState:
        """
        Чтение состояний coil-регистров.
        Читаем по одному coil, так как устройство не поддерживает групповое чтение.

        Returns:
            CoilState: Структура с состояниями выходов

        Raises:
            IOError: Ошибка связи с устройством
        """
        if not self.is_connected or self.instrument is None:
            raise IOError("Устройство не подключено")

        state = CoilState()
        errors = []

        # Читаем каждый coil отдельно
        try:
            state.buzzer = bool(self.instrument.read_bit(self.COIL_BUZZER, functioncode=1))
        except Exception as e:
            errors.append(f"пищалка: {e}")

        try:
            state.red_led = bool(self.instrument.read_bit(self.COIL_RED_LED, functioncode=1))
        except Exception as e:
            errors.append(f"красный LED: {e}")

        try:
            state.green_led = bool(self.instrument.read_bit(self.COIL_GREEN_LED, functioncode=1))
        except Exception as e:
            errors.append(f"зеленый LED: {e}")

        # Если все чтения провалились - устройство не отвечает
        if len(errors) == 3:
            raise IOError(f"Не удалось прочитать coils: {'; '.join(errors)}")

        # Если были частичные ошибки - логируем
        if errors:
            logger.warning(f"Частичные ошибки чтения coils: {'; '.join(errors)}")

        logger.info(f"Состояние coils: {state}")
        return state

    def write_coil(self, coil_address: int, value: bool) -> None:
        """
        Запись значения в coil-регистр.

        Args:
            coil_address: Адрес coil (0, 10, 11)
            value: Значение (True/False)

        Raises:
            IOError: Ошибка связи с устройством
            ValueError: Некорректный адрес
        """
        if not self.is_connected or self.instrument is None:
            raise IOError("Устройство не подключено")

        valid_coils = [self.COIL_BUZZER, self.COIL_RED_LED, self.COIL_GREEN_LED]
        if coil_address not in valid_coils:
            raise ValueError(f"Некорректный адрес coil: {coil_address}")

        logger.info(f"Запись coil {coil_address} = {value}")
        self.instrument.write_bit(coil_address, value, functioncode=5)

    def write_buzzer(self, enabled: bool) -> None:
        """Включение/выключение пищалки."""
        self.write_coil(self.COIL_BUZZER, enabled)

    def write_red_led(self, enabled: bool) -> None:
        """Включение/выключение красного светодиода."""
        self.write_coil(self.COIL_RED_LED, enabled)

    def write_green_led(self, enabled: bool) -> None:
        """Включение/выключение зеленого светодиода."""
        self.write_coil(self.COIL_GREEN_LED, enabled)
