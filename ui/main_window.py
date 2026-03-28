"""
Главное окно приложения.
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QComboBox, QPushButton,
    QSpinBox, QDoubleSpinBox, QTextEdit, QStatusBar, QSplitter
)
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QFont, QIcon
import logging
import serial.tools.list_ports
from collections import deque
import time

from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from modbus.modbus_worker import ModbusWorker
from modbus.modbus_client import DeviceData, CoilState
import config

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Главное окно приложения."""

    def __init__(self):
        super().__init__()

        self.worker: ModbusWorker = None
        self.settings = QSettings("settings.ini", QSettings.Format.IniFormat)

        # Буферы для графиков (время, значения)
        self.noise_data = deque(maxlen=100)
        self.motion_data = deque(maxlen=100)
        self.time_data = deque(maxlen=100)
        self.start_time = time.time()

        self.init_ui()
        self.load_settings()

    def init_ui(self):
        """Инициализация пользовательского интерфейса."""
        self.setWindowTitle(config.WINDOW_TITLE)
        self.setMinimumSize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Основной layout
        main_layout = QVBoxLayout(central_widget)

        # Splitter для разделения на панели
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)

        # Верхняя панель - настройки подключения и управление
        top_panel = QWidget()
        top_layout = QVBoxLayout(top_panel)
        top_layout.addWidget(self.create_connection_group())
        top_layout.addWidget(self.create_control_group())
        splitter.addWidget(top_panel)

        # Средняя панель - отображение данных
        splitter.addWidget(self.create_data_group())

        # Нижняя панель - лог
        splitter.addWidget(self.create_log_group())

        # Установка пропорций
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)

        # Статусная строка
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Готов к работе")

    def create_connection_group(self) -> QGroupBox:
        """Создание группы настроек подключения."""
        group = QGroupBox("Настройки подключения")
        layout = QHBoxLayout()

        # COM-порт
        layout.addWidget(QLabel("COM-порт:"))
        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self.port_combo.setMinimumWidth(120)
        self.refresh_ports()
        layout.addWidget(self.port_combo)

        # Кнопка обновления портов
        self.refresh_ports_btn = QPushButton("🔄")
        self.refresh_ports_btn.setMaximumWidth(40)
        self.refresh_ports_btn.setToolTip("Обновить список портов")
        self.refresh_ports_btn.clicked.connect(self.refresh_ports)
        layout.addWidget(self.refresh_ports_btn)

        layout.addSpacing(20)

        # Адрес устройства
        layout.addWidget(QLabel("Адрес устройства:"))
        self.address_spin = QSpinBox()
        self.address_spin.setRange(1, 247)
        self.address_spin.setValue(config.DEFAULT_SLAVE_ADDRESS)
        self.address_spin.setMinimumWidth(80)
        layout.addWidget(self.address_spin)

        layout.addSpacing(20)

        # Скорость
        layout.addWidget(QLabel("Скорость:"))
        self.baudrate_combo = QComboBox()
        for baudrate in config.BAUDRATES:
            self.baudrate_combo.addItem(str(baudrate), baudrate)
        self.baudrate_combo.setCurrentText(str(config.DEFAULT_BAUDRATE))
        self.baudrate_combo.setMinimumWidth(100)
        layout.addWidget(self.baudrate_combo)

        layout.addSpacing(20)

        # Четность
        layout.addWidget(QLabel("Четность:"))
        self.parity_combo = QComboBox()
        self.parity_combo.addItem("None", 'N')
        self.parity_combo.addItem("Even", 'E')
        self.parity_combo.addItem("Odd", 'O')
        self.parity_combo.setCurrentIndex(0)
        self.parity_combo.setMinimumWidth(80)
        layout.addWidget(self.parity_combo)

        layout.addSpacing(20)

        # Интервал опроса
        layout.addWidget(QLabel("Интервал опроса (сек):"))
        self.poll_interval_spin = QDoubleSpinBox()
        self.poll_interval_spin.setRange(0.1, 60.0)
        self.poll_interval_spin.setSingleStep(0.5)
        self.poll_interval_spin.setValue(config.DEFAULT_POLL_INTERVAL)
        self.poll_interval_spin.setMinimumWidth(80)
        self.poll_interval_spin.valueChanged.connect(self.on_poll_interval_changed)
        layout.addWidget(self.poll_interval_spin)

        layout.addStretch()

        # Кнопка подключения
        self.connect_btn = QPushButton("Подключить")
        self.connect_btn.setMinimumWidth(120)
        self.connect_btn.clicked.connect(self.toggle_connection)
        layout.addWidget(self.connect_btn)

        group.setLayout(layout)
        return group

    def create_control_group(self) -> QGroupBox:
        """Создание группы управления выходами."""
        group = QGroupBox("Управление выходами")
        layout = QHBoxLayout()

        # Пищалка
        self.buzzer_check = QPushButton("Пищалка")
        self.buzzer_check.setCheckable(True)
        self.buzzer_check.setEnabled(False)
        self.buzzer_check.clicked.connect(self.on_buzzer_changed)
        layout.addWidget(self.buzzer_check)

        layout.addSpacing(30)

        # Красный светодиод
        self.red_led_check = QPushButton("Красный LED")
        self.red_led_check.setCheckable(True)
        self.red_led_check.setEnabled(False)
        self.red_led_check.clicked.connect(self.on_red_led_changed)
        layout.addWidget(self.red_led_check)

        layout.addSpacing(30)

        # Зеленый светодиод
        self.green_led_check = QPushButton("Зеленый LED")
        self.green_led_check.setCheckable(True)
        self.green_led_check.setEnabled(False)
        self.green_led_check.clicked.connect(self.on_green_led_changed)
        layout.addWidget(self.green_led_check)

        layout.addStretch()

        # Кнопка обновления статусов
        refresh_status_btn = QPushButton("Обновить статусы")
        refresh_status_btn.setEnabled(False)
        refresh_status_btn.clicked.connect(self.on_refresh_coils)
        self.refresh_status_btn = refresh_status_btn
        layout.addWidget(refresh_status_btn)

        group.setLayout(layout)
        return group

    def create_data_group(self) -> QGroupBox:
        """Создание группы отображения данных."""
        group = QGroupBox("Данные датчика")
        main_layout = QHBoxLayout()

        # Левая часть - текущие значения
        values_widget = QWidget()
        layout = QGridLayout(values_widget)

        # Стиль для заголовков
        label_font = QFont()
        label_font.setBold(True)

        # Стиль для значений
        value_font = QFont()
        value_font.setPointSize(12)

        # Создание полей для отображения данных
        row = 0

        # Шум
        label = QLabel("Уровень шума:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.noise_label = QLabel("—")
        self.noise_label.setFont(value_font)
        layout.addWidget(self.noise_label, row, 1)
        layout.addWidget(QLabel("дБ"), row, 2)

        # Температура
        row += 1
        label = QLabel("Температура:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.temp_label = QLabel("—")
        self.temp_label.setFont(value_font)
        layout.addWidget(self.temp_label, row, 1)
        layout.addWidget(QLabel("°C"), row, 2)

        # Влажность
        row += 1
        label = QLabel("Влажность:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.humidity_label = QLabel("—")
        self.humidity_label.setFont(value_font)
        layout.addWidget(self.humidity_label, row, 1)
        layout.addWidget(QLabel("%RH"), row, 2)

        # CO2
        row += 1
        label = QLabel("CO₂:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.co2_label = QLabel("—")
        self.co2_label.setFont(value_font)
        layout.addWidget(self.co2_label, row, 1)
        layout.addWidget(QLabel("ppm"), row, 2)

        # Освещенность
        row += 1
        label = QLabel("Освещенность:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.illuminance_label = QLabel("—")
        self.illuminance_label.setFont(value_font)
        layout.addWidget(self.illuminance_label, row, 1)
        layout.addWidget(QLabel("лк"), row, 2)

        # Качество воздуха
        row += 1
        label = QLabel("Качество воздуха:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.air_quality_label = QLabel("—")
        self.air_quality_label.setFont(value_font)
        layout.addWidget(self.air_quality_label, row, 1)
        layout.addWidget(QLabel("ppb"), row, 2)

        # Движение
        row += 1
        label = QLabel("Движение:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.motion_label = QLabel("—")
        self.motion_label.setFont(value_font)
        layout.addWidget(self.motion_label, row, 1)
        layout.addWidget(QLabel(""), row, 2)

        # Время работы
        row += 1
        label = QLabel("Время работы:")
        label.setFont(label_font)
        layout.addWidget(label, row, 0)
        self.uptime_label = QLabel("—")
        self.uptime_label.setFont(value_font)
        layout.addWidget(self.uptime_label, row, 1)
        layout.addWidget(QLabel(""), row, 2)

        layout.setColumnStretch(3, 1)

        # Добавление левой части в главный layout
        main_layout.addWidget(values_widget)

        # Правая часть - графики
        charts_widget = self.create_charts()
        main_layout.addWidget(charts_widget)

        # Пропорции: значения 40%, графики 60%
        main_layout.setStretch(0, 4)
        main_layout.setStretch(1, 6)

        group.setLayout(main_layout)
        return group

    def create_charts(self) -> QWidget:
        """Создание виджета с графиками."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # График шума
        noise_group = QGroupBox("Уровень шума")
        noise_layout = QVBoxLayout(noise_group)

        self.noise_figure = Figure(figsize=(5, 2), facecolor='white')
        self.noise_canvas = FigureCanvas(self.noise_figure)
        self.noise_ax = self.noise_figure.add_subplot(111)
        self.noise_ax.set_ylabel('дБ')
        self.noise_ax.set_xlabel('Время, сек')
        self.noise_ax.grid(True, alpha=0.3)
        self.noise_figure.tight_layout()

        noise_layout.addWidget(self.noise_canvas)
        layout.addWidget(noise_group)

        # График движения
        motion_group = QGroupBox("Датчик движения")
        motion_layout = QVBoxLayout(motion_group)

        self.motion_figure = Figure(figsize=(5, 2), facecolor='white')
        self.motion_canvas = FigureCanvas(self.motion_figure)
        self.motion_ax = self.motion_figure.add_subplot(111)
        self.motion_ax.set_ylabel('Значение')
        self.motion_ax.set_xlabel('Время, сек')
        self.motion_ax.grid(True, alpha=0.3)
        self.motion_figure.tight_layout()

        motion_layout.addWidget(self.motion_canvas)
        layout.addWidget(motion_group)

        return widget

    def update_charts(self, data: DeviceData):
        """Обновление графиков."""
        current_time = time.time() - self.start_time

        # Добавление данных
        self.time_data.append(current_time)

        if data.noise_level is not None:
            self.noise_data.append(data.noise_level)
        else:
            self.noise_data.append(None)

        if data.motion is not None:
            self.motion_data.append(data.motion)
        else:
            self.motion_data.append(None)

        # Обновление графика шума
        self.noise_ax.clear()
        self.noise_ax.set_ylabel('дБ')
        self.noise_ax.set_xlabel('Время, сек')
        self.noise_ax.grid(True, alpha=0.3)

        if len(self.time_data) > 0 and len(self.noise_data) > 0:
            # Фильтрация None значений
            valid_times = []
            valid_noise = []
            for t, n in zip(self.time_data, self.noise_data):
                if n is not None:
                    valid_times.append(t)
                    valid_noise.append(n)

            if valid_times:
                self.noise_ax.plot(valid_times, valid_noise, 'b-', linewidth=1.5)
                self.noise_ax.fill_between(valid_times, valid_noise, alpha=0.3)

        self.noise_figure.tight_layout()
        self.noise_canvas.draw_idle()

        # Обновление графика движения
        self.motion_ax.clear()
        self.motion_ax.set_ylabel('Значение')
        self.motion_ax.set_xlabel('Время, сек')
        self.motion_ax.grid(True, alpha=0.3)

        if len(self.time_data) > 0 and len(self.motion_data) > 0:
            # Фильтрация None значений
            valid_times = []
            valid_motion = []
            for t, m in zip(self.time_data, self.motion_data):
                if m is not None:
                    valid_times.append(t)
                    valid_motion.append(m)

            if valid_times:
                self.motion_ax.step(valid_times, valid_motion, 'r-', linewidth=2, where='post')
                self.motion_ax.fill_between(valid_times, valid_motion, alpha=0.3, step='post', color='red')

        self.motion_figure.tight_layout()
        self.motion_canvas.draw_idle()

    def create_log_group(self) -> QGroupBox:
        """Создание группы лога."""
        group = QGroupBox("Лог событий")
        layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)

        # Кнопка очистки лога
        clear_btn = QPushButton("Очистить лог")
        clear_btn.clicked.connect(self.log_text.clear)
        layout.addWidget(clear_btn)

        group.setLayout(layout)
        return group

    def refresh_ports(self):
        """Обновление списка доступных COM-портов."""
        current_text = self.port_combo.currentText()
        self.port_combo.clear()

        ports = serial.tools.list_ports.comports()
        for port in sorted(ports):
            self.port_combo.addItem(f"{port.device} - {port.description}", port.device)

        # Восстановление выбранного порта
        index = self.port_combo.findData(current_text)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        elif self.port_combo.count() > 0:
            self.port_combo.setCurrentIndex(0)

        logger.info(f"Найдено портов: {self.port_combo.count()}")
        self.add_log(f"Обновлен список портов: найдено {self.port_combo.count()}")

    def toggle_connection(self):
        """Переключение состояния подключения."""
        if self.worker is None or not self.worker.is_running():
            self.connect_device()
        else:
            self.disconnect_device()

    def connect_device(self):
        """Подключение к устройству."""
        # Получение параметров
        port = self.port_combo.currentData()
        if port is None:
            port = self.port_combo.currentText()

        if not port:
            self.add_log("Ошибка: не выбран COM-порт", "error")
            return

        address = self.address_spin.value()
        baudrate = int(self.baudrate_combo.currentText())
        parity = self.parity_combo.currentData()
        poll_interval = self.poll_interval_spin.value()

        self.add_log(f"Подключение к {port}, адрес {address}, скорость {baudrate}, четность {parity}...")

        # Создание и настройка рабочего потока
        self.worker = ModbusWorker()
        self.worker.configure(port, address, baudrate, parity, poll_interval)

        # Подключение сигналов
        self.worker.data_received.connect(self.on_data_received)
        self.worker.coil_status_received.connect(self.on_coil_status_received)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.connection_status.connect(self.on_connection_status)

        # Запуск потока
        self.worker.start()

        # Блокировка настроек
        self.port_combo.setEnabled(False)
        self.refresh_ports_btn.setEnabled(False)
        self.address_spin.setEnabled(False)
        self.baudrate_combo.setEnabled(False)
        self.parity_combo.setEnabled(False)
        self.connect_btn.setText("Отключить")

    def disconnect_device(self):
        """Отключение от устройства."""
        if self.worker is not None:
            self.add_log("Отключение...")
            self.worker.stop()
            self.worker.wait()
            self.worker = None

        # Разблокировка настроек
        self.port_combo.setEnabled(True)
        self.refresh_ports_btn.setEnabled(True)
        self.parity_combo.setEnabled(True)
        self.address_spin.setEnabled(True)
        self.baudrate_combo.setEnabled(True)
        self.connect_btn.setText("Подключить")

        # Отключение элементов управления
        self.buzzer_check.setEnabled(False)
        self.red_led_check.setEnabled(False)
        self.green_led_check.setEnabled(False)
        self.refresh_status_btn.setEnabled(False)

        self.status_bar.showMessage("Отключено")
        self.add_log("Отключено от устройства")

    def on_data_received(self, data: DeviceData):
        """Обработка полученных данных."""
        # Обновление отображаемых значений
        self.noise_label.setText(f"{data.noise_level:.2f}" if data.noise_level is not None else "—")
        self.temp_label.setText(f"{data.temperature:.2f}" if data.temperature is not None else "ошибка")
        self.humidity_label.setText(f"{data.humidity:.2f}" if data.humidity is not None else "ошибка")
        self.co2_label.setText(str(data.co2) if data.co2 is not None else "ошибка")
        self.illuminance_label.setText(f"{data.illuminance:.2f}" if data.illuminance is not None else "ошибка")
        self.air_quality_label.setText(str(data.air_quality) if data.air_quality is not None else "ошибка")
        self.motion_label.setText(str(data.motion) if data.motion is not None else "ошибка")

        # Форматирование времени работы
        if data.uptime is not None:
            hours = data.uptime // 3600
            minutes = (data.uptime % 3600) // 60
            seconds = data.uptime % 60
            self.uptime_label.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self.uptime_label.setText("—")

        # Обновление графиков
        self.update_charts(data)

        self.status_bar.showMessage("Данные обновлены")

    def on_coil_status_received(self, coil_state: CoilState):
        """Обработка полученных состояний coils."""
        # Временно отключаем обработчики сигналов
        self.buzzer_check.blockSignals(True)
        self.red_led_check.blockSignals(True)
        self.green_led_check.blockSignals(True)

        # Обновление состояний
        self.buzzer_check.setChecked(coil_state.buzzer)
        self.red_led_check.setChecked(coil_state.red_led)
        self.green_led_check.setChecked(coil_state.green_led)

        # Включение обработчиков обратно
        self.buzzer_check.blockSignals(False)
        self.red_led_check.blockSignals(False)
        self.green_led_check.blockSignals(False)

        # Включение элементов управления
        self.buzzer_check.setEnabled(True)
        self.red_led_check.setEnabled(True)
        self.green_led_check.setEnabled(True)
        self.refresh_status_btn.setEnabled(True)

        self.add_log(f"Статусы coils: Пищалка={coil_state.buzzer}, "
                    f"Красный={coil_state.red_led}, Зеленый={coil_state.green_led}")

    def on_error(self, error_msg: str):
        """Обработка ошибок."""
        self.add_log(f"Ошибка: {error_msg}", "error")

    def on_connection_status(self, connected: bool, message: str):
        """Обработка изменения статуса соединения."""
        if connected:
            self.status_bar.showMessage(f"✓ {message}")
            self.add_log(message, "success")
        else:
            self.status_bar.showMessage(f"✗ {message}")
            self.add_log(message, "error")

            # При потере связи отключаем элементы управления и меняем кнопку
            self.buzzer_check.setEnabled(False)
            self.red_led_check.setEnabled(False)
            self.green_led_check.setEnabled(False)
            self.refresh_status_btn.setEnabled(False)

            # Возвращаем кнопку в состояние "Подключить" и разблокируем настройки
            self.port_combo.setEnabled(True)
            self.refresh_ports_btn.setEnabled(True)
            self.address_spin.setEnabled(True)
            self.baudrate_combo.setEnabled(True)
            self.parity_combo.setEnabled(True)
            self.connect_btn.setText("Подключить")

            # При потере связи отключаем worker
            if self.worker is not None and not self.worker.is_running():
                self.worker = None

    def on_poll_interval_changed(self, value: float):
        """Изменение интервала опроса."""
        if self.worker is not None and self.worker.is_running():
            self.worker.set_poll_interval(value)
            self.add_log(f"Интервал опроса изменен: {value} сек")

    def on_buzzer_changed(self, checked):
        """Изменение состояния пищалки."""
        if self.worker is not None:
            self.worker.request_coil_write(0, checked)
            self.add_log(f"Пищалка: {'ВКЛ' if checked else 'ВЫКЛ'}")

    def on_red_led_changed(self, checked):
        """Изменение состояния красного светодиода."""
        if self.worker is not None:
            self.worker.request_coil_write(10, checked)
            self.add_log(f"Красный LED: {'ВКЛ' if checked else 'ВЫКЛ'}")

    def on_green_led_changed(self, checked):
        """Изменение состояния зеленого светодиода."""
        if self.worker is not None:
            self.worker.request_coil_write(11, checked)
            self.add_log(f"Зеленый LED: {'ВКЛ' if checked else 'ВЫКЛ'}")

    def on_refresh_coils(self):
        """Обновление состояний coils."""
        if self.worker is not None:
            self.worker.request_coil_read()
            self.add_log("Запрошено обновление статусов coils")

    def add_log(self, message: str, msg_type: str = "info"):
        """
        Добавление сообщения в лог.

        Args:
            message: Текст сообщения
            msg_type: Тип сообщения (info, error, success)
        """
        # Проверка, что виджет лога уже создан
        if not hasattr(self, 'log_text') or self.log_text is None:
            return

        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Форматирование в зависимости от типа
        if msg_type == "error":
            formatted = f'<span style="color: red;">[{timestamp}] ❌ {message}</span>'
        elif msg_type == "success":
            formatted = f'<span style="color: green;">[{timestamp}] ✓ {message}</span>'
        else:
            formatted = f"[{timestamp}] {message}"

        self.log_text.append(formatted)

        # Автопрокрутка вниз
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.log_text.setTextCursor(cursor)

    def load_settings(self):
        """Загрузка сохраненных настроек."""
        port = self.settings.value("port", config.DEFAULT_PORT)
        address = self.settings.value("address", config.DEFAULT_SLAVE_ADDRESS, type=int)
        baudrate = self.settings.value("baudrate", config.DEFAULT_BAUDRATE, type=int)
        parity = self.settings.value("parity", config.DEFAULT_PARITY)
        poll_interval = self.settings.value("poll_interval", config.DEFAULT_POLL_INTERVAL, type=float)

        # Применение настроек
        index = self.port_combo.findData(port)
        if index >= 0:
            self.port_combo.setCurrentIndex(index)
        else:
            self.port_combo.setCurrentText(port)

        self.address_spin.setValue(address)
        self.baudrate_combo.setCurrentText(str(baudrate))

        parity_index = self.parity_combo.findData(parity)
        if parity_index >= 0:
            self.parity_combo.setCurrentIndex(parity_index)

        self.poll_interval_spin.setValue(poll_interval)

        logger.info("Настройки загружены")

    def save_settings(self):
        """Сохранение настроек."""
        port = self.port_combo.currentData()
        if port is None:
            port = self.port_combo.currentText()

        self.settings.setValue("port", port)
        self.settings.setValue("address", self.address_spin.value())
        self.settings.setValue("baudrate", int(self.baudrate_combo.currentText()))
        self.settings.setValue("parity", self.parity_combo.currentData())
        self.settings.setValue("poll_interval", self.poll_interval_spin.value())

        logger.info("Настройки сохранены")

    def closeEvent(self, event):
        """Обработка закрытия окна."""
        # Отключение от устройства
        if self.worker is not None:
            self.worker.stop()
            self.worker.wait(2000)

        # Сохранение настроек
        self.save_settings()

        event.accept()
