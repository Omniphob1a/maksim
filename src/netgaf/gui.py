"""Russian Qt desktop. Long-running jobs never execute on the GUI thread."""

import sys
import time
from pathlib import Path
from threading import Event

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .capture import CancelledError, read_capture
from .config import FEATURES, AnalysisConfig
from .demo import generate_demo
from .evaluation import evaluate_demo
from .model import analyze, load_detector, reconstruct, save_detector, train_detector
from .reports import export_csv, export_json, utc_time
from .resources import find_demo_directory, user_guide

BG, PANEL, TEXT, MUTED, ACCENT = "#101923", "#182532", "#e7eef6", "#98adbf", "#4dd8c5"
COLORS = ["#4dd8c5", "#6ca7ff", "#f5b96b"]
STYLE = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 12px; }}
QMainWindow {{ background: {BG}; }}
QGroupBox {{ border: 1px solid #304151; border-radius: 9px; margin-top: 12px; padding: 12px 9px 7px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; color: {MUTED}; }}
QPushButton {{ background: #23384a; border: 1px solid #3b5265; border-radius: 6px; padding: 8px 10px; }}
QPushButton:hover {{ background: #2e4a60; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #657886; background: #1a2834; border-color: #253442; }}
QPushButton[primary="true"] {{ background: #198375; color: white; border-color: #29a995; font-weight: bold; }}
QPushButton[primary="true"]:disabled {{ background: #204d49; color: #7b9d98; }}
QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QPlainTextEdit {{
 background: {PANEL}; border: 1px solid #344a5e; border-radius: 5px; padding: 5px; }}
QComboBox QAbstractItemView {{ background: {PANEL}; selection-background-color: #315d6b; }}
QTabWidget::pane {{ border: 1px solid #304151; border-radius: 7px; }}
QTabBar::tab {{ padding: 10px 16px; color: {MUTED}; background: {BG}; }}
QTabBar::tab:selected {{ color: {ACCENT}; background: {PANEL}; border-bottom: 2px solid {ACCENT}; }}
QTableView {{ background: {BG}; alternate-background-color: {PANEL}; border: 0; gridline-color: #293c4d;
 selection-background-color: #2c5265; selection-color: white; }}
QHeaderView::section {{ background: #223546; color: {MUTED}; padding: 9px; border: 0; }}
QLabel[muted="true"] {{ color: {MUTED}; }}
QFrame[card="true"] {{ background: {PANEL}; border: 1px solid #304151; border-radius: 8px; }}
QFrame[card="true"] QLabel {{ background: transparent; }}
QCheckBox {{ spacing: 7px; }}
QScrollArea {{ border: none; }}
QToolTip {{ color: {TEXT}; background: #23384a; border: 1px solid #4a677e; }}
"""


class Worker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    message = Signal(str)
    done = Signal()

    def __init__(self, operation, cancelled):
        super().__init__()
        self.operation = operation
        self.cancelled = cancelled

    @Slot()
    def run(self):
        try:
            self.completed.emit(self.operation(self.message.emit, self.cancelled.is_set))
        except CancelledError:
            self.message.emit("Операция отменена.")
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.done.emit()


class ResultsModel(QAbstractTableModel):
    HEADERS = (
        "Узел",
        "Начало · UTC",
        "Конец · UTC",
        "MSE",
        "MSE / порог",
        "Вне диапазона",
        "Результат",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = []

    def replace(self, results):
        self.beginResetModel()
        self.results = results
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.results)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r = self.results[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return (
                r.window.node,
                r.window.start_ns,
                r.window.end_ns,
                r.score,
                r.score / r.threshold,
                sum(r.below) + sum(r.above),
                int(r.anomalous),
            )[col]
        if role == Qt.ItemDataRole.ForegroundRole and r.anomalous:
            return QColor("#ffad9e")
        if role == Qt.ItemDataRole.DisplayRole:
            return (
                r.window.node,
                utc_time(r.window.start_ns).replace("+00:00", "").replace("T", " "),
                utc_time(r.window.end_ns).replace("+00:00", "").replace("T", " "),
                f"{r.score:.6f}",
                f"{r.score / r.threshold:.3f}",
                str(sum(r.below) + sum(r.above)),
                "Подозрительное" if r.anomalous else "В пределах порога",
            )[col]
        return None


class ResultFilter(QSortFilterProxyModel):
    only_anomalies = False

    def filterAcceptsRow(self, row, parent):
        return not self.only_anomalies or self.sourceModel().results[row].anomalous

    def set_only_anomalies(self, enabled):
        self.only_anomalies = enabled
        self.invalidate()


class Plot(FigureCanvasQTAgg):
    def __init__(self):
        self.figure = Figure(facecolor=BG, layout="constrained")
        super().__init__(self.figure)
        self.setMinimumHeight(240)
        self.empty("Результаты появятся после анализа захвата")

    def prepare(self, rows, columns):
        self.figure.clear()
        axes = np.asarray(self.figure.subplots(rows, columns, squeeze=False))
        for ax in axes.flat:
            ax.set_facecolor(BG)
            ax.tick_params(colors=MUTED, labelsize=8)
            ax.title.set_color(TEXT)
            ax.xaxis.label.set_color(MUTED)
            ax.yaxis.label.set_color(MUTED)
            for spine in ax.spines.values():
                spine.set_color("#344a5e")
        return axes

    def empty(self, message):
        ax = self.prepare(1, 1)[0, 0]
        ax.axis("off")
        ax.text(0.5, 0.5, message, ha="center", va="center", color=MUTED, transform=ax.transAxes)
        self.draw_idle()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NetGAF · Анализ сетевых аномалий")
        self.resize(1440, 980)
        self.setMinimumSize(1080, 760)
        self.detector = None
        self.capture = None
        self.results = []
        self.analysis_path = None
        self._thread = None
        self._worker = None
        self._cancel = Event()
        self._close_after_job = False
        self._buttons = []
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(22, 16, 22, 14)
        root.setSpacing(14)
        self.setCentralWidget(central)
        help_action = self.menuBar().addMenu("Справка").addAction("Инструкция", self.open_guide)
        help_action.setShortcut("F1")
        header = QHBoxLayout()
        title = QLabel("Net<span style='color:#4dd8c5'>GAF</span>")
        title.setStyleSheet("font-size: 30px; font-weight: 700;")
        header.addWidget(title)
        subtitle = QLabel("АНАЛИЗ СЕТЕВЫХ АНОМАЛИЙ\nТрафик → временные ряды → изображения")
        subtitle.setProperty("muted", True)
        header.addWidget(subtitle)
        header.addStretch()
        self.model_label = QLabel("Модель не загружена")
        self.model_label.setProperty("muted", True)
        header.addWidget(self.model_label)
        root.addLayout(header)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(350)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sidebar = QWidget()
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(0, 0, 12, 0)
        scroll.setWidget(sidebar)
        split.addWidget(scroll)

        sources = QGroupBox("01 / Нормальный трафик для обучения")
        source_layout = QVBoxLayout(sources)
        self.files = QListWidget()
        self.files.setMaximumHeight(100)
        source_layout.addWidget(self.files)
        row = QHBoxLayout()
        row.addWidget(self.button("Добавить файлы", self.add_files))
        row.addWidget(self.button("Удалить", self.remove_file))
        source_layout.addLayout(row)
        self.normal_confirm = QCheckBox("Подтверждаю: трафик нормальный")
        self.normal_confirm.setToolTip("Наличие атак в обучении искажает модель нормы и порог.")
        source_layout.addWidget(self.normal_confirm)
        left.addWidget(sources)

        parameters = QGroupBox("02 / Параметры нового обучения")
        form = QFormLayout(parameters)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.001, 3600)
        self.interval.setDecimals(3)
        self.interval.setValue(1)
        self.interval.setSuffix(" с")
        self.window_size = QComboBox()
        for value in (16, 32, 64):
            self.window_size.addItem(str(value), value)
        self.window_size.setCurrentIndex(1)
        self.stride = QSpinBox()
        self.stride.setRange(1, 32)
        self.stride.setValue(16)
        self.window_size.currentIndexChanged.connect(
            lambda: self.stride.setMaximum(self.window_size.currentData())
        )
        self.direction = QComboBox()
        self.direction.addItem("Исходящий", "outgoing")
        self.direction.addItem("Входящий", "incoming")
        self.method = QComboBox()
        self.method.addItem("GASF · сумма углов", "gasf")
        self.method.addItem("GADF · разность углов", "gadf")
        self.epochs = QSpinBox()
        self.epochs.setRange(1, 1000)
        self.epochs.setValue(20)
        self.quantile = QDoubleSpinBox()
        self.quantile.setRange(90, 100)
        self.quantile.setDecimals(1)
        self.quantile.setValue(99)
        self.quantile.setSuffix(" %")
        for name, widget in (
            ("Интервал", self.interval),
            ("Отсчётов в окне", self.window_size),
            ("Шаг окна", self.stride),
            ("Направление", self.direction),
            ("Преобразование", self.method),
            ("Эпохи", self.epochs),
            ("Квантиль порога", self.quantile),
        ):
            form.addRow(name, widget)
        self.train_button = self.button("Обучить модель на CPU", self.train, primary=True)
        form.addRow(self.train_button)
        left.addWidget(parameters)

        model_box = QGroupBox("03 / Модель и демонстрация")
        model_layout = QVBoxLayout(model_box)
        model_layout.addWidget(self.button("Открыть модель .ngaf", self.open_model))
        self.save_model_button = self.button("Сохранить модель", self.save_model)
        model_layout.addWidget(self.save_model_button)
        self.example_button = self.button("Открыть готовый пример", self.open_example, True)
        model_layout.addWidget(self.example_button)
        model_layout.addWidget(self.button("Создать демоданные", self.create_demo))
        self.evaluate_button = self.button("Проверить демосценарии", self.evaluate_scenarios)
        model_layout.addWidget(self.evaluate_button)
        note = QLabel(
            "Порог калибруется на последних 30%\nнормального захвата. Анализ использует\nсохранённые параметры модели."
        )
        note.setProperty("muted", True)
        model_layout.addWidget(note)
        left.addWidget(model_box)
        left.addStretch()

        right = QWidget()
        content = QVBoxLayout(right)
        content.setContentsMargins(8, 0, 0, 0)
        split.addWidget(right)
        split.setSizes([350, 1000])
        analysis_bar = QHBoxLayout()
        self.file_label = QLabel("Выберите захват для анализа")
        self.file_label.setProperty("muted", True)
        analysis_bar.addWidget(self.file_label, 1)
        self.analyze_button = self.button(
            "Открыть PCAP и анализировать", self.choose_analysis, True
        )
        analysis_bar.addWidget(self.analyze_button)
        content.addLayout(analysis_bar)

        cards = QHBoxLayout()
        self.count_value = self.card(cards, "ПРОАНАЛИЗИРОВАНО ОКОН", "—")
        self.flagged_value = self.card(cards, "ПОДОЗРИТЕЛЬНЫХ ОКОН", "—")
        self.threshold_value = self.card(cards, "ПОРОГ MSE", "—")
        content.addLayout(cards)
        self.tabs = QTabWidget()
        content.addWidget(self.tabs, 1)
        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        self.timeline = Plot()
        overview_layout.addWidget(self.timeline, 1)
        self.series_plot = Plot()
        overview_layout.addWidget(self.series_plot, 2)
        self.tabs.addTab(overview, "Обзор трафика")
        self.images_plot = Plot()
        self.tabs.addTab(self.images_plot, "GAF и реконструкция")
        self.history_plot = Plot()
        self.history_plot.empty("История появится после обучения или загрузки модели")
        self.tabs.addTab(self.history_plot, "Обучение")
        self.benchmark = QWidget()
        benchmark_layout = QVBoxLayout(self.benchmark)
        benchmark_note = QLabel(
            "Синтетические сценарии проверяют работу программы.\n"
            "Качество на реальной сети требует независимого размеченного датасета.\n"
            "Метка окна: любое пересечение с размеченным интервалом. Порог фиксирован моделью."
        )
        benchmark_note.setWordWrap(True)
        benchmark_note.setProperty("muted", True)
        benchmark_layout.addWidget(benchmark_note)
        self.benchmark_table = QTableWidget(0, 8)
        self.benchmark_table.setHorizontalHeaderLabels(
            ["Сценарий", "TP", "FP", "FN", "Precision", "Recall", "F1", "FPR"]
        )
        self.benchmark_table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self.benchmark_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.benchmark_table.horizontalHeader().setStretchLastSection(True)
        benchmark_layout.addWidget(self.benchmark_table, 1)
        self.tabs.addTab(self.benchmark, "Демосценарии")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        self.tabs.addTab(self.log, "Журнал")

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Результаты по узлам и временным окнам"))
        filters.addStretch()
        self.only_anomalies = QCheckBox("Только подозрительные")
        filters.addWidget(self.only_anomalies)
        self.export_button = self.button("Экспорт CSV / JSON", self.export)
        filters.addWidget(self.export_button)
        content.addLayout(filters)
        self.table_model = ResultsModel(self)
        self.proxy = ResultFilter(self)
        self.proxy.setSourceModel(self.table_model)
        self.proxy.setSortRole(Qt.ItemDataRole.UserRole)
        self.only_anomalies.toggled.connect(self.proxy.set_only_anomalies)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setMinimumHeight(170)
        self.table.setMaximumHeight(260)
        self.table.selectionModel().currentRowChanged.connect(self.select_result)
        content.addWidget(self.table)
        footer = QHBoxLayout()
        self.status = QLabel("Готово к работе · добавьте нормальный захват или создайте демоданные")
        self.status.setProperty("muted", True)
        footer.addWidget(self.status, 1)
        self.cancel_button = QPushButton("Отменить")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel.set)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)
        self._set_busy(False)

    def button(self, text, action, primary=False):
        button = QPushButton(text)
        button.setProperty("primary", primary)
        button.clicked.connect(action)
        self._buttons.append(button)
        return button

    def card(self, layout, title, value):
        frame = QFrame()
        frame.setProperty("card", True)
        box = QVBoxLayout(frame)
        label = QLabel(title)
        label.setStyleSheet(f"font-size: 10px; color: {MUTED};")
        box.addWidget(label)
        number = QLabel(value)
        number.setStyleSheet("font-size: 25px; font-weight: 600;")
        box.addWidget(number)
        layout.addWidget(frame, 1)
        return number

    def current_config(self):
        return AnalysisConfig(
            interval=self.interval.value(),
            window_size=self.window_size.currentData(),
            stride=self.stride.value(),
            direction=self.direction.currentData(),
            representation=self.method.currentData(),
        )

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Нормальные захваты", "", "Захваты (*.pcap *.pcapng);;Все файлы (*)"
        )
        existing = {self.files.item(i).text() for i in range(self.files.count())}
        for path in files:
            if path not in existing:
                self.files.addItem(path)
                existing.add(path)

    def remove_file(self):
        self.files.takeItem(self.files.currentRow())

    def train(self):
        if not self.files.count() or not self.normal_confirm.isChecked():
            self.error("Добавьте нормальные захваты и подтвердите состав обучающих данных.")
            return
        config = self.current_config()
        paths = [self.files.item(i).text() for i in range(self.files.count())]
        epochs, quantile = self.epochs.value(), self.quantile.value() / 100

        def operation(progress, cancel):
            captures = [read_capture(path, config, progress, cancel) for path in paths]
            return "model", train_detector(
                captures, config, epochs, quantile, progress=progress, cancel=cancel
            )

        self.run_job(operation, "Обучение модели…")
        self.tabs.setCurrentWidget(self.log)

    def open_model(self):
        path, _ = QFileDialog.getOpenFileName(self, "Открыть модель", "", "Модель NetGAF (*.ngaf)")
        if path:
            self.run_job(
                lambda progress, cancel: ("model", load_detector(path)), "Загрузка модели…"
            )

    def save_model(self):
        if self.detector is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить модель", "model.ngaf", "Модель NetGAF (*.ngaf)"
        )
        if path:
            try:
                save_detector(self.detector, path)
                self.message(f"Модель сохранена: {path}")
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def choose_analysis(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Захват для анализа",
            self.analysis_path or "",
            "Захваты (*.pcap *.pcapng);;Все файлы (*)",
        )
        if path:
            self.start_analysis(path)

    def start_analysis(self, path):
        detector = self.detector
        if detector is None:
            return
        self.analysis_path = str(path)

        def operation(progress, cancel):
            started = time.perf_counter()
            capture = read_capture(path, detector.config, progress, cancel)
            results = analyze(capture, detector, progress, cancel)
            return "results", (capture, results, time.perf_counter() - started)

        self.run_job(operation, "Анализ захвата…")

    def create_demo(self):
        path = QFileDialog.getExistingDirectory(self, "Пустая папка для синтетического набора")
        if path:
            self.run_job(
                lambda progress, cancel: ("demo", generate_demo(path, cancel=cancel)),
                "Создание демоданных…",
            )

    def open_guide(self):
        path = user_guide()
        if not path.is_file() or not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.error(f"Не удалось открыть инструкцию: {path}")

    def open_example(self):
        directory = find_demo_directory()
        if directory is None:
            self.error("Готовый пример не найден. Создайте демоданные и обучите модель.")
            return

        def operation(progress, cancel):
            started = time.perf_counter()
            detector = load_detector(directory / "model.ngaf")
            capture = read_capture(directory / "mixed.pcap", detector.config, progress, cancel)
            results = analyze(capture, detector, progress, cancel)
            return "example", (detector, capture, results, time.perf_counter() - started, directory)

        self.run_job(operation, "Загрузка готового примера…")

    def evaluate_scenarios(self):
        path = QFileDialog.getExistingDirectory(self, "Папка созданного демонстрационного набора")
        if path and self.detector is not None:
            detector = self.detector
            self.run_job(
                lambda progress, cancel: (
                    "evaluation",
                    evaluate_demo(path, detector, progress, cancel),
                ),
                "Проверка демонстрационных сценариев…",
            )

    def run_job(self, operation, message):
        if self._thread is not None:
            return
        self._cancel = Event()
        self._thread = QThread(self)
        self._worker = Worker(operation, self._cancel)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.message.connect(self.message)
        self._worker.completed.connect(self.receive)
        self._worker.failed.connect(self.error)
        self._worker.done.connect(self._thread.quit)
        self._worker.done.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._job_finished)
        self._thread.finished.connect(self._thread.deleteLater)
        self._set_busy(True)
        self.message(message)
        self._thread.start()

    @Slot()
    def _job_finished(self):
        self._thread = None
        self._worker = None
        self._set_busy(False)
        if self._close_after_job:
            self.close()

    def _set_busy(self, busy):
        for button in self._buttons:
            button.setEnabled(not busy)
        self.save_model_button.setEnabled(not busy and self.detector is not None)
        self.example_button.setEnabled(not busy and find_demo_directory() is not None)
        self.analyze_button.setEnabled(not busy and self.detector is not None)
        self.evaluate_button.setEnabled(not busy and self.detector is not None)
        self.export_button.setEnabled(not busy and bool(self.results))
        self.cancel_button.setEnabled(busy)
        self.files.setEnabled(not busy)
        for widget in (
            self.interval,
            self.window_size,
            self.stride,
            self.method,
            self.direction,
            self.epochs,
            self.quantile,
            self.normal_confirm,
        ):
            widget.setEnabled(not busy)

    @Slot(str)
    def message(self, message):
        self.status.setText(message)
        self.status.setToolTip(message)
        self.log.appendPlainText(message)

    @Slot(str)
    def error(self, message):
        self.message(f"Ошибка: {message}")
        QMessageBox.warning(self, "NetGAF", message)

    @Slot(object)
    def receive(self, payload):
        kind, value = payload
        if kind == "example":
            detector, capture, results, duration, directory = value
            self.receive(("model", detector))
            self.files.clear()
            self.files.addItem(str(directory / "normal.pcap"))
            self.normal_confirm.setChecked(True)
            self.analysis_path = capture.source
            self.receive(("results", (capture, results, duration)))
        elif kind == "model":
            self.detector = value
            self.results = []
            self.capture = None
            self.table_model.replace([])
            self.benchmark_table.setRowCount(0)
            self.file_label.setText("Выберите захват для анализа")
            self.count_value.setText("—")
            self.flagged_value.setText("—")
            self.timeline.empty("Выберите отдельный захват для анализа")
            self.series_plot.empty("Выберите окно после анализа")
            self.images_plot.empty("Выберите окно после анализа")
            config = value.config
            self.interval.setValue(config.interval)
            self.window_size.setCurrentIndex(self.window_size.findData(config.window_size))
            self.stride.setValue(config.stride)
            self.direction.setCurrentIndex(self.direction.findData(config.direction))
            self.method.setCurrentIndex(self.method.findData(config.representation))
            self.threshold_value.setText(f"{value.threshold:.5f}")
            self.model_label.setText(
                f"{config.representation.upper()} · {config.window_size}×{config.window_size}×3 · CPU"
            )
            ax = self.history_plot.prepare(1, 1)[0, 0]
            history = value.metadata.get("history", [])
            for key, label, color in (
                ("train_mse", "Обучение", COLORS[0]),
                ("validation_mse", "Валидация", COLORS[1]),
            ):
                ax.plot(
                    [h["epoch"] for h in history],
                    [h[key] for h in history],
                    label=label,
                    color=color,
                )
            ax.set(xlabel="Эпоха", ylabel="MSE", title="Ошибка восстановления GAF")
            ax.legend(facecolor=PANEL, labelcolor=TEXT)
            self.history_plot.draw_idle()
            self.tabs.setCurrentWidget(self.history_plot)
            self.message(
                f"Модель готова. Обучающих окон: {value.metadata['train_windows']}; "
                f"валидационных: {value.metadata['validation_windows']}; порог: {value.threshold:.6f}"
            )
        elif kind == "demo":
            self.files.clear()
            self.files.addItem(str(value["normal.pcap"]))
            self.normal_confirm.setChecked(True)
            self.analysis_path = str(value["mixed.pcap"])
            self.message(
                "Демоданные созданы. Обучите модель, затем откройте mixed.pcap для анализа."
            )
        elif kind == "evaluation":
            self.benchmark_table.setRowCount(len(value["scenarios"]))
            for row, scenario in enumerate(value["scenarios"].values()):
                values = [scenario["title"]] + [str(scenario[k]) for k in ("tp", "fp", "fn")]
                values += [
                    f"{scenario[k]:.3f}" if scenario[k] is not None else "—"
                    for k in ("precision", "recall", "f1", "fpr")
                ]
                for column, text in enumerate(values):
                    self.benchmark_table.setItem(row, column, QTableWidgetItem(text))
            self.tabs.setCurrentWidget(self.benchmark)
            self.message(
                "Показательные тесты завершены. Результаты доступны на вкладке «Демосценарии»."
            )
        else:
            self.capture, self.results, duration = value
            self.only_anomalies.setChecked(False)
            self.table_model.replace(self.results)
            self.file_label.setText(Path(self.capture.source).name)
            self.file_label.setToolTip(self.capture.source)
            self.count_value.setText(str(len(self.results)))
            self.flagged_value.setText(str(sum(r.anomalous for r in self.results)))
            ax = self.timeline.prepare(1, 1)[0, 0]
            nodes = sorted({r.window.node for r in self.results})
            for index, node in enumerate(nodes[:8]):
                records = [r for r in self.results if r.window.node == node]
                origin = min(r.window.start_ns for r in self.results)
                ax.plot(
                    [(r.window.start_ns - origin) / 1e9 for r in records],
                    [r.score for r in records],
                    color=COLORS[index % 3],
                    label=node,
                    linewidth=1.5,
                )
            ax.axhline(self.detector.threshold, color="#ffad9e", linestyle="--", label="Порог")
            ax.set(
                xlabel="Начало окна, с от начала захвата",
                ylabel="MSE",
                title="Оценка аномальности"
                + (f" · первые 8 из {len(nodes)} узлов" if len(nodes) > 8 else ""),
            )
            ax.legend(facecolor=PANEL, labelcolor=TEXT, fontsize=8, loc="upper right")
            self.timeline.draw_idle()
            self.tabs.setCurrentIndex(0)
            self.table.selectRow(0)
            stats = self.capture.stats
            self.message(
                f"Анализ завершён за {duration:.2f} с · IP-пакетов: {stats.ip_packets:,} · "
                f"не-IP: {stats.skipped_non_ip:,} · укороченных кадров: {stats.truncated:,}"
            )

    @Slot(QModelIndex, QModelIndex)
    def select_result(self, current, previous=QModelIndex()):
        if not current.isValid() or self.detector is None:
            return
        source_row = self.proxy.mapToSource(current).row()
        if not 0 <= source_row < len(self.results):
            return
        result = self.results[source_row]
        axes = self.series_plot.prepare(3, 1)
        config = self.detector.config
        for channel, ax in enumerate(axes.flat):
            ax.plot(
                np.arange(config.window_size) * config.interval,
                result.window.values[:, channel],
                color=COLORS[channel],
                linewidth=1.5,
            )
            ax.set_ylabel(("Пакеты", "Байты", "Порты")[channel], fontsize=8)
            ax.grid(alpha=0.12, color=MUTED)
        axes[-1, 0].set_xlabel("Время от начала выбранного окна, с")
        self.series_plot.figure.suptitle(
            f"{result.window.node} · {utc_time(result.window.start_ns)}", color=TEXT, fontsize=10
        )
        self.series_plot.draw_idle()
        image, restored = reconstruct(self.detector, result.window)
        axes = self.images_plot.prepare(2, 3)
        for row, data in enumerate((image, restored)):
            for channel in range(3):
                ax = axes[row, channel]
                ax.imshow(data[channel], cmap="coolwarm", vmin=-1, vmax=1, origin="upper")
                label = FEATURES[channel] if row == 0 else "Реконструкция"
                ax.set_title(label, fontsize=10)
                ax.set_xlabel("Отсчёт j")
                ax.set_ylabel("Отсчёт i")
        self.images_plot.figure.suptitle(
            f"{config.representation.upper()} · шкала −1 … +1 · MSE {result.score:.6f} · "
            f"вне диапазона: {sum(result.below) + sum(result.above)} значений",
            color=TEXT,
            fontsize=11,
        )
        self.images_plot.draw_idle()

    def export(self):
        if not self.results:
            return
        path, selected = QFileDialog.getSaveFileName(
            self, "Экспорт результатов", "report.json", "JSON (*.json);;CSV (*.csv)"
        )
        if path:
            try:
                if path.lower().endswith(".csv") or selected.startswith("CSV"):
                    export_csv(path, self.results)
                else:
                    export_json(path, self.results, self.detector, self.capture.stats)
                self.message(f"Результаты сохранены: {path}")
            except (ValueError, OSError) as exc:
                self.error(str(exc))

    def closeEvent(self, event):
        if self._thread is not None:
            self._cancel.set()
            self._close_after_job = True
            self.message("Отмена операции перед закрытием…")
            event.ignore()
        else:
            event.accept()


def main():
    application = QApplication.instance() or QApplication(sys.argv)
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
