# -*- coding: utf-8 -*-
"""
gui_main.py — Główne GUI w PySide6 do generowania krzyżówek
NOWA WERSJA: Większa liczba opcji konfiguracji
"""

import sys
import os
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QMessageBox,
    QFileDialog,
    QTextEdit,
    QProgressBar,
    QCheckBox,
    QComboBox,
    QScrollArea,
    QGroupBox,
    QColorDialog,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QPixmap, QFontDatabase

from crossword_orchestrator import CrosswordOrchestrator
from image_renderer import CrosswordImageRenderer

class GeneratorThread(QThread):
    """Wątek do generowania krzyżówek w tle."""

    finished = Signal(bool, str)  # success, message
    progress = Signal(str)        # progress message

    def __init__(
        self,
        orchestrator: CrosswordOrchestrator,
        width: int,
        height: int,
        source_file: str,
        word_file: str,
        num_variants: int,
        multi_strategy: bool = False,
        use_api: bool = False,
        min_word_length: int = 2,
        use_extra: bool = False,
        color_empty: tuple = None,
        color_tile: tuple = None,
        color_black: tuple = None,
        color_text: tuple = None,
        color_clue_num: tuple = None,
        font_name: str = "Arial",
        progressive_mode: bool = False,
        progressive_phases: int = 3,
        max_total_variants: int = 100,
        edge_first_mode: bool = False,
        edge_first_variants: int = 3,
    ):
        super().__init__()
        self.orchestrator = orchestrator
        self.width = width
        self.height = height
        self.source_file = source_file
        self.word_file = word_file
        self.num_variants = num_variants
        self.multi_strategy = multi_strategy
        self.use_api = use_api
        self.min_word_length = min_word_length
        self.use_extra = use_extra
        self.color_empty = color_empty
        self.color_tile = color_tile
        self.color_black = color_black
        self.color_text = color_text
        self.color_clue_num = color_clue_num
        self.font_name = font_name
        self.progressive_mode = progressive_mode
        self.progressive_phases = progressive_phases
        self.max_total_variants = max_total_variants
        self.edge_first_mode = edge_first_mode
        self.edge_first_variants = edge_first_variants

    def run(self):
        """Wykonaj generowanie."""
        try:
            self.progress.emit("Generowanie w toku...")

            # Ustaw kolory i czcionkę w orchestrator
            self.orchestrator.renderer_color_empty = self.color_empty
            self.orchestrator.renderer_color_tile = self.color_tile
            self.orchestrator.renderer_color_black = self.color_black
            self.orchestrator.renderer_color_text = self.color_text
            self.orchestrator.renderer_color_clue_num = self.color_clue_num
            self.orchestrator.renderer_font_name = self.font_name

            success = self.orchestrator.generate_and_export(
                self.width,
                self.height,
                self.source_file,
                self.word_file if self.word_file else None,
                self.num_variants,
                multi_strategy=self.multi_strategy,
                progress_callback=self.progress.emit,
                use_api=self.use_api,
                use_extra=self.use_extra,
                min_word_length=self.min_word_length,
                progressive_mode=self.progressive_mode,
                progressive_phases=self.progressive_phases,
                max_total_variants=self.max_total_variants,
                edge_first_mode=self.edge_first_mode,
                edge_first_variants=self.edge_first_variants,
            )

            if success:
                self.finished.emit(True, f"Krzyżówka wygenerowana! Wyniki w: {self.orchestrator.output_dir}")
            else:
                self.finished.emit(False, "Błąd podczas generowania")

        except Exception as e:
            self.finished.emit(False, f"Błąd: {str(e)}")


class CrosswordGeneratorGUI(QMainWindow):
    """Główne okno aplikacji z rozszerzonymi opcjami."""

    def __init__(self):
        super().__init__()
        self.orchestrator = CrosswordOrchestrator(
            os.path.dirname(os.path.abspath(__file__))
        )
        self.generator_thread = None

        # Domyślny plik
        self.default_word_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "baza_wyrazow", "baza.txt"
        )

        # Domyślne kolory (RGB tuples)
        # NOTA: Kolory są mapowane z drop-downów, te są tylko dla preview
        self.colors = {
            "unavailable": (128, 128, 128),  # Szare (zmienione z czarnego)
            "tile": (245, 222, 179),  # Beżowe
            "text": (40, 40, 40),  # Czarny tekst
            "clue_num": (255, 0, 0),  # CzerwoneNumery
        }

        # Mapa rozszerzona do animułowania previewów
        self.extended_color_map = {
            # Graye
            "szare": (128, 128, 128),
            "jasnoszare": (192, 192, 192),
            "ciemnoszare": (64, 64, 64),
            "czarne": (0, 0, 0),
            "białe": (255, 255, 255),
            # Czerwone
            "czerwone": (255, 0, 0),
            "ciemnoczerwone": (139, 0, 0),
            "jasnoróżowe": (255, 192, 203),
            # Niebieskie
            "niebieskie": (0, 0, 255),
            "ciemnoniebieskie": (0, 0, 139),
            "jasnoniebieskie": (173, 216, 230),
            # Zielone
            "zielone": (0, 128, 0),
            "ciemnozielone": (0, 100, 0),
            "jasnozielone": (144, 238, 144),
            # Żółte
            "żółte": (255, 255, 0),
            "jasnożółte": (255, 255, 153),
            # Pomarańczowe
            "pomarańczowe": (255, 165, 0),
            "ciemnopomarańczowe": (255, 140, 0),
            # Fioletowe
            "fioletowe": (128, 0, 128),
            "ciemnofioletowe": (75, 0, 130),
            # Brązowe
            "brązowe": (165, 42, 42),
            "ciemnobrązowe": (101, 67, 33),
            # Inne
            "turkusowe": (64, 224, 208),
            "limonkowe": (50, 205, 50),
            # Beże/Kremowe
            "beżowe": (245, 222, 179),
            "jasnokremowe": (255, 250, 240),
            "kremawe": (240, 230, 200),
            "jasnobrązowe": (210, 180, 140),
            "jasny szary": (211, 211, 211),
        }

        self.init_ui()

    def init_ui(self):
        """Inicjalizuj interfejs użytkownika."""
        self.setWindowTitle("Generator Krzyżówek (v2.0)")
        self.setGeometry(100, 100, 900, 1000)

        # Central widget w ScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        central = QWidget()
        scroll.setWidget(central)
        self.setCentralWidget(scroll)

        layout = QVBoxLayout()

        # Tytuł
        title = QLabel("Generator Krzyżówek v2.0")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        layout.addWidget(title)

        # GPU/CPU Status
        gpu_status_label = QLabel()
        backend = getattr(self.orchestrator, 'gpu_backend', 'numpy')
        if self.orchestrator.use_cuda:
            gpu_status_label.setText(f"✓ GPU (CUDA) + {backend.upper()} — przyspieszenie aktywne!")
            gpu_status_label.setStyleSheet(
                "color: green; font-weight: bold; font-size: 12px;"
            )
        elif backend == "cupy":
            gpu_status_label.setText(f"✓ CuPy (GPU bez CUDA torch) — przyspieszenie aktywne!")
            gpu_status_label.setStyleSheet("color: darkgreen; font-weight: bold; font-size: 12px;")
        else:
            gpu_status_label.setText(f"⚠ CPU (NumPy) — brak GPU/CUDA")
            gpu_status_label.setStyleSheet(
                "color: orange; font-weight: bold; font-size: 12px;"
            )
        layout.addWidget(gpu_status_label)

        # --- Sekcja: Wymiary siatki (BEZ LIMITU) ---
        layout.addSpacing(15)

        size_group = QGroupBox("Wymiary siatki")
        size_layout = QHBoxLayout()

        size_layout.addWidget(QLabel("Szerokość:"))
        self.width_spin = QSpinBox()
        self.width_spin.setValue(15)
        self.width_spin.setMinimum(5)
        self.width_spin.setMaximum(999)  # BEZ LIMITU (prawie)
        size_layout.addWidget(self.width_spin)

        size_layout.addSpacing(20)

        size_layout.addWidget(QLabel("Wysokość:"))
        self.height_spin = QSpinBox()
        self.height_spin.setValue(15)
        self.height_spin.setMinimum(5)
        self.height_spin.setMaximum(999)  # BEZ LIMITU (prawie)
        size_layout.addWidget(self.height_spin)

        size_layout.addStretch()
        size_group.setLayout(size_layout)
        layout.addWidget(size_group)

        # --- Sekcja: Plik słów ---
        layout.addSpacing(15)

        file_group = QGroupBox("Źródło słów")
        file_layout = QVBoxLayout()

        # Checkbox: Dobieraj z bazy danych
        self.use_db_check = QCheckBox("Dobieraj wyrazy z bazy danych polskich słów")
        self.use_db_check.setChecked(True)
        self.use_db_check.setToolTip(
            "Jeśli zaznaczone, program będzie używać wbudowaną bazę słów"
        )
        file_layout.addWidget(self.use_db_check)

        # Parametr: Minimalna długość słowa
        params_layout = QHBoxLayout()
        params_layout.addWidget(QLabel("Dobieraj wyrazy:"))
        self.min_length_spin = QSpinBox()
        self.min_length_spin.setValue(2)
        self.min_length_spin.setMinimum(1)
        self.min_length_spin.setMaximum(20)
        params_layout.addWidget(self.min_length_spin)
        params_layout.addWidget(QLabel("liter i większe"))
        params_layout.addStretch()
        file_layout.addLayout(params_layout)

        # Wybór pliku
        file_select_layout = QHBoxLayout()
        self.file_label = QLineEdit()
        self.file_label.setReadOnly(True)
        self.file_label.setText(self.default_word_file)
        file_select_layout.addWidget(self.file_label)

        self.browse_btn = QPushButton("Przeglądaj...")
        self.browse_btn.clicked.connect(self.on_browse_file)
        file_select_layout.addWidget(self.browse_btn)

        file_layout.addLayout(file_select_layout)
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)

        # --- Sekcja: Liczba wariantów ---
        layout.addSpacing(15)

        variants_group = QGroupBox("Liczba wariantów i intensywność szukania")
        variants_vlay = QVBoxLayout()

        variants_layout = QHBoxLayout()
        variants_layout.addWidget(QLabel("Liczba wariantów do wygenerowania:"))
        self.variants_spin = QSpinBox()
        self.variants_spin.setValue(100)
        self.variants_spin.setMinimum(1)
        self.variants_spin.setMaximum(10000)  # Obsługa do 10000 wariantów (zapis do pliku)
        self.variants_spin.setToolTip(
            "Liczba wariantów krzyżówki do wygenerowania.\n"
            "Przy dużych liczbach (>100) warianty są zapisywane do pliku\n"
            "i pamięć jest zwalniana na bieżąco."
        )
        variants_layout.addWidget(self.variants_spin)
        variants_layout.addWidget(QLabel("(>100: zapis do pliku, brak limitu RAM)"))
        variants_layout.addStretch()
        variants_vlay.addLayout(variants_layout)

        # Informacja o GPU
        gpu_info = QLabel()
        variants_vlay.addWidget(gpu_info)
        self._gpu_info_label = gpu_info

        variants_group.setLayout(variants_vlay)
        layout.addWidget(variants_group)

        # --- Sekcja: Multi-strategy checkbox ---
        layout.addSpacing(10)

        self.multi_strategy_check = QCheckBox("Używać 6 strategii umieszczania wyrazów")
        self.multi_strategy_check.setChecked(True)  # Domyślnie ON - najlepsze rezultaty
        self.multi_strategy_check.setToolTip(
            "Jeśli zaznaczone, program generuje krzyżówki 6 różnymi metodami:\n"
            "1. CENTERED, 2. TOP_LEFT, 3. TOP_CENTER,\n"
            "4. MIDDLE_LEFT, 5. DENSE_MODE, 6. RANDOM"
        )
        layout.addWidget(self.multi_strategy_check)

        # --- Sekcja: Tryb EXTRA ---
        self.extra_mode_check = QCheckBox("Tryb EXTRA - szukaj lepszych rozwiązań")
        self.extra_mode_check.setChecked(True)  # Domyślnie ON - szuka najlepszych rozwiązań
        self.extra_mode_check.setToolTip(
            "Włącz, aby program przeprowadzał więcej prób i wybierał bardziej zagęszczone rozwiązania."
        )
        layout.addWidget(self.extra_mode_check)

        # --- Sekcja: Tryb PROGRESYWNY =---
        layout.addSpacing(10)

        self.progressive_check = QCheckBox(
            "Tryb PROGRESYWNY - uzupełnianie fazami (Dalsze_uzupelnianie1-5)"
        )
        self.progressive_check.setChecked(False)
        self.progressive_check.setToolTip(
            "Faza 1: Krzyżówka z baza.txt\n"
            "Fazy 2+: Coraz bardziej wypełniona w podkatalogach\n"
            "Każda faza tworzy nowy katalog na bieżąco"
        )
        layout.addWidget(self.progressive_check)

        # Liczba faz progresywnych
        phases_layout = QHBoxLayout()
        phases_layout.addWidget(QLabel("Liczba faz (gdy progresywny):"))
        self.phases_spin = QSpinBox()
        self.phases_spin.setValue(3)
        self.phases_spin.setMinimum(2)
        self.phases_spin.setMaximum(6)
        phases_layout.addWidget(self.phases_spin)
        phases_layout.addStretch()
        layout.addLayout(phases_layout)

        # --- Sekcja: Strategia od brzegów (EDGE_FIRST) ---
        layout.addSpacing(10)

        self.edge_first_check = QCheckBox(
            "Strategia od brzegów — maksymalne zagęszczenie siatki"
        )
        self.edge_first_check.setChecked(False)
        self.edge_first_check.setToolTip(
            "Nowa strategia: najdłuższe wyrazy trafiają na górne krawędzie i boki planszy,\n"
            "do nich krzyżowane są pozostałe słowa — od najdłuższych.\n"
            "Wolne pola wypełniane resztą bazy.\n"
            "Cel: siatka zwarta, gęsta, dużo przeplotu, minimum pustych pól.\n"
            "Wyniki zapisywane w osobnym katalogu EdgeFirst/."
        )
        layout.addWidget(self.edge_first_check)

        edge_variants_layout = QHBoxLayout()
        edge_variants_layout.addWidget(QLabel("Liczba wariantów od brzegów:"))
        self.edge_variants_spin = QSpinBox()
        self.edge_variants_spin.setValue(3)
        self.edge_variants_spin.setMinimum(1)
        self.edge_variants_spin.setMaximum(50)
        self.edge_variants_spin.setToolTip(
            "Ile wariantów strategii EDGE_FIRST wygenerować.\n"
            "Każdy wariant to niezależna próba maksymalnego zagęszczenia siatki.\n"
            "Więcej wariantów = większa szansa na najgęstszy układ."
        )
        edge_variants_layout.addWidget(self.edge_variants_spin)
        edge_variants_layout.addWidget(QLabel("(więcej = gęstsze szukanie)"))
        edge_variants_layout.addStretch()
        layout.addLayout(edge_variants_layout)

        # --- Sekcja: API & DeepSeek ---
        layout.addSpacing(10)

        self.use_api_check = QCheckBox(
            "Używać DeepSeek do generowania pytań krzyżówkowych"
        )
        self.use_api_check.setChecked(True)  # Domyślnie ON - podpowiedzi DeepSeek
        self.use_api_check.setToolTip("Wymaga klucza w API_klucz/deepseek.txt")
        layout.addWidget(self.use_api_check)

        # --- Sekcja: Grafika (KOLORY) ---
        layout.addSpacing(15)

        graphics_group = QGroupBox("Ustawienia grafiki - Pola kratownicy")
        graphics_layout = QVBoxLayout()

        # Pola niedostępne (puste kratki - bez liter)
        unavailable_layout = QHBoxLayout()
        unavailable_layout.addWidget(QLabel("Pola niedostępne (bez liter):"))
        self.unavailable_color_combo = QComboBox()

        # Rozszerzona paleta kolorów
        extended_colors = [
            "szare",
            "czarne",
            "białe",
            "jasnoszare",
            "ciemnoszare",
            "czerwone",
            "ciemnoczerwone",
            "jasnoróżowe",
            "niebieskie",
            "ciemnoniebieskie",
            "jasnoniebieskie",
            "zielone",
            "ciemnozielone",
            "jasnozielone",
            "żółte",
            "jasnożółte",
            "pomarańczowe",
            "ciemnopomarańczowe",
            "fioletowe",
            "ciemnofioletowe",
            "brązowe",
            "ciemnobrązowe",
            "turkusowe",
            "limonkowe",
        ]
        self.unavailable_color_combo.addItems(extended_colors)
        self.unavailable_color_combo.setCurrentText("szare")
        unavailable_layout.addWidget(self.unavailable_color_combo)
        self._add_color_preview(unavailable_layout, "unavailable")
        self.unavailable_preview = unavailable_layout.itemAt(
            unavailable_layout.count() - 1
        ).widget()
        unavailable_layout.addStretch()
        graphics_layout.addLayout(unavailable_layout)

        # Komórki z literami
        tile_layout = QHBoxLayout()
        tile_layout.addWidget(QLabel("Komórki z literami:"))
        self.tile_color_combo = QComboBox()

        tile_colors = [
            "beżowe",
            "białe",
            "jasnokremowe",
            "kremawe",
            "jasnobrązowe",
            "jasny szary",
        ]
        self.tile_color_combo.addItems(tile_colors)
        self.tile_color_combo.setCurrentText("beżowe")
        tile_layout.addWidget(self.tile_color_combo)
        self._add_color_preview(tile_layout, "tile")
        self.tile_preview = tile_layout.itemAt(tile_layout.count() - 1).widget()
        tile_layout.addStretch()
        graphics_layout.addLayout(tile_layout)

        # Cyfry pomocnicze
        clue_num_layout = QHBoxLayout()
        clue_num_layout.addWidget(QLabel("Numery pytań (małe cyfry):"))
        self.clue_num_color_combo = QComboBox()
        clue_num_colors = [
            "czerwone",
            "ciemnoczerwone",
            "niebieskie",
            "zielone",
            "czarne",
            "fioletowe",
        ]
        self.clue_num_color_combo.addItems(clue_num_colors)
        self.clue_num_color_combo.setCurrentText("czerwone")
        clue_num_layout.addWidget(self.clue_num_color_combo)
        self._add_color_preview(clue_num_layout, "clue_num")
        self.clue_num_preview = clue_num_layout.itemAt(
            clue_num_layout.count() - 1
        ).widget()
        clue_num_layout.addStretch()
        graphics_layout.addLayout(clue_num_layout)

        graphics_group.setLayout(graphics_layout)
        layout.addWidget(graphics_group)

        # --- Sekcja: Czcionka ---
        layout.addSpacing(15)

        font_group = QGroupBox("Czcionka")
        font_layout = QHBoxLayout()
        font_layout.addWidget(QLabel("Wybierz czcionkę:"))
        self.font_combo = QComboBox()

        # Polskie czcionki i inne popularne
        polish_fonts = [
            "Arial",
            "Calibri",
            "Cambria",
            "Courier New",
            "Garamond",
            "Georgia",
            "Times New Roman",
            "Trebuchet MS",
            "Verdana",
            "Consolas",
            "Impact",
            "Palatino Linotype",
            "Book Antiqua",
        ]

        # Dodaj wszystkie dostępne czcionki systemowe
        all_fonts = QFontDatabase().families()
        all_fonts_sorted = sorted(set(polish_fonts + all_fonts))

        self.font_combo.addItems(all_fonts_sorted)
        self.font_combo.setCurrentText("Arial")
        font_layout.addWidget(self.font_combo)
        font_layout.addStretch()
        font_group.setLayout(font_layout)
        layout.addWidget(font_group)

        # --- Sekcja: Przycisk START ---
        layout.addSpacing(20)

        self.generate_btn = QPushButton("Generuj Krzyżówkę")
        self.generate_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        self.generate_btn.clicked.connect(self.on_generate)
        layout.addWidget(self.generate_btn)

        # --- Progress bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # --- Output text ---
        layout.addSpacing(15)

        layout.addWidget(QLabel("Log:"))

        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMaximumHeight(150)
        layout.addWidget(self.output_text)

        layout.addStretch()

        central.setLayout(layout)

    def _add_color_preview(self, layout, color_key):
        """Dodaj mini preview koloru do layoutu."""
        preview = QLabel("  ")

        # Pobierz kolor z klucza lub z combo boxa
        if color_key == "unavailable":
            color_name = self.unavailable_color_combo.currentText()
        elif color_key == "tile":
            color_name = self.tile_color_combo.currentText()
        elif color_key == "clue_num":
            color_name = self.clue_num_color_combo.currentText()
        else:
            color_name = None

        # Pobierz RGB z mapy
        if color_name:
            rgb = self.extended_color_map.get(
                color_name, self.colors.get(color_key, (192, 192, 192))
            )
        else:
            rgb = self.colors.get(color_key, (192, 192, 192))

        preview.setStyleSheet(
            f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); "
            f"border: 1px solid black; width: 20px; height: 20px;"
        )

        # Podepnij sygnały by preview się updatował
        if color_key == "unavailable":
            self.unavailable_color_combo.currentTextChanged.connect(
                lambda: self._update_color_preview(preview, color_key)
            )
        elif color_key == "tile":
            self.tile_color_combo.currentTextChanged.connect(
                lambda: self._update_color_preview(preview, color_key)
            )
        elif color_key == "clue_num":
            self.clue_num_color_combo.currentTextChanged.connect(
                lambda: self._update_color_preview(preview, color_key)
            )

        layout.addWidget(preview)

    def _update_color_preview(self, preview_widget, color_key):
        """Aktualizuj wygląd preview'u."""
        # Pobierz bieżący kolor z combo boxa
        if color_key == "unavailable":
            color_name = self.unavailable_color_combo.currentText()
        elif color_key == "tile":
            color_name = self.tile_color_combo.currentText()
        elif color_key == "clue_num":
            color_name = self.clue_num_color_combo.currentText()
        else:
            return

        rgb = self.extended_color_map.get(color_name, (192, 192, 192))
        preview_widget.setStyleSheet(
            f"background-color: rgb({rgb[0]}, {rgb[1]}, {rgb[2]}); "
            f"border: 1px solid black; width: 20px; height: 20px;"
        )

    def on_browse_file(self):
        """Otwórz dialog do wyboru pliku."""
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Wybierz plik ze słowami",
            os.path.expanduser("~"),
            "Text Files (*.txt);;All Files (*)"
        )

        if filepath:
            self.file_label.setText(filepath)

    def on_generate(self):
        """Wciśnięto przycisk Generuj."""
        width = self.width_spin.value()
        height = self.height_spin.value()

        # Pobierz pełną ścieżkę pliku
        word_file = (
            self.default_word_file
            if self.use_db_check.isChecked()
            else self.file_label.text()
        )
        source_file = os.path.basename(word_file)  # Nazwa do katalogu wyników

        num_variants = self.variants_spin.value()
        multi_strategy = self.multi_strategy_check.isChecked()
        use_api = self.use_api_check.isChecked()
        progressive_mode = self.progressive_check.isChecked()
        progressive_phases = self.phases_spin.value()
        edge_first_mode = self.edge_first_check.isChecked()
        edge_first_variants = self.edge_variants_spin.value()

        # Validacja
        if width < 5 or height < 5:
            QMessageBox.warning(self, "Błąd", "Wymiary muszą być co najmniej 5×5")
            return

        if not os.path.exists(word_file):
            QMessageBox.warning(self, "Błąd", f"Plik nie istnieje: {word_file}")
            return

        # Wyłącz przycisk i pokaż progress
        self.generate_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.output_text.clear()
        self.output_text.append("Generator Krzyżówek v2.0 — Uruchomiony")
        self.output_text.append("-" * 60)

        if multi_strategy:
            self.output_text.append("Tryb: 6 STRATEGII")
            self.output_text.append("")
            self.output_text.append("Będą generowane krzyżówki z:")
            self.output_text.append("  1. CENTERED — wyrazy od środka")
            self.output_text.append("  2. TOP_LEFT — z górnego lewego rogu")
            self.output_text.append("  3. TOP_CENTER — od góry pośrodku")
            self.output_text.append("  4. MIDDLE_LEFT — ze środka lewej krawędzi")
            self.output_text.append("  5. DENSE_MODE — maksymalna gęstość")
            self.output_text.append("  6. RANDOM — losowe umieszczenie")
            self.output_text.append("")
            self.output_text.append("Postęp:")
        elif edge_first_mode:
            self.output_text.append("Tryb: EDGE_FIRST (od brzegów)")
            self.output_text.append(f"Wariantów: {edge_first_variants}")
            self.output_text.append("")
            self.output_text.append("Algorytm:")
            self.output_text.append("  1. Najdłuższe wyrazy → górna krawędź i boki")
            self.output_text.append("  2. Krzyżowanie ku środkowi — od najdłuższych")
            self.output_text.append("  3. Agresywne wypełnianie wnętrza siatki")
            self.output_text.append("  4. Minimalizacja pustych pól")
            self.output_text.append("  Wyniki: katalog EdgeFirst/")
            self.output_text.append("")
            self.output_text.append("Postęp:")
        elif progressive_mode:
            self.output_text.append("Tryb: PROGRESYWNY")
            self.output_text.append(f"Faz: {progressive_phases}")
            self.output_text.append("")
            self.output_text.append("Układ:")
            self.output_text.append("  Faza 1: Krzyżówka z baza.txt")
            self.output_text.append("  Fazy 2+: Coraz bardziej wypełniona")
            self.output_text.append(
                "  Katalogi: Dalsze_uzupelnianie1, Dalsze_uzupelnianie2, ..."
            )
            self.output_text.append("")
            self.output_text.append("Postęp:")
        else:
            self.output_text.append("Tryb: STANDARDOWY")

        if use_api:
            self.output_text.append("DeepSeek: WŁĄCZONE (pytania z AI)")

        if self.extra_mode_check.isChecked():
            self.output_text.append(
                "Tryb EXTRA: WŁĄCZONY - dłuższe szukanie najlepszej krzyżówki"
            )

        # Rozszerzona mapa kolorów (24+ kolory)
        color_map = {
            # Graye
            "szare": (128, 128, 128),
            "jasnoszare": (192, 192, 192),
            "ciemnoszare": (64, 64, 64),
            "czarne": (0, 0, 0),
            "białe": (255, 255, 255),
            # Czerwone
            "czerwone": (255, 0, 0),
            "ciemnoczerwone": (139, 0, 0),
            "jasnoróżowe": (255, 192, 203),
            # Niebieskie
            "niebieskie": (0, 0, 255),
            "ciemnoniebieskie": (0, 0, 139),
            "jasnoniebieskie": (173, 216, 230),
            # Zielone
            "zielone": (0, 128, 0),
            "ciemnozielone": (0, 100, 0),
            "jasnozielone": (144, 238, 144),
            # Żółte
            "żółte": (255, 255, 0),
            "jasnożółte": (255, 255, 153),
            # Pomarańczowe
            "pomarańczowe": (255, 165, 0),
            "ciemnopomarańczowe": (255, 140, 0),
            # Fioletowe
            "fioletowe": (128, 0, 128),
            "ciemnofioletowe": (75, 0, 130),
            # Brązowe
            "brązowe": (165, 42, 42),
            "ciemnobrązowe": (101, 67, 33),
            # Inne
            "turkusowe": (64, 224, 208),
            "limonkowe": (50, 205, 50),
            # Beże/Kremowe
            "beżowe": (245, 222, 179),
            "jasnokremowe": (255, 250, 240),
            "kremawe": (240, 230, 200),
            "jasnobrązowe": (210, 180, 140),
            "jasny szary": (211, 211, 211),
        }

        # Pobierz aktualne kolory z comboboxów
        color_unavailable = color_map.get(
            self.unavailable_color_combo.currentText(), (128, 128, 128)
        )
        color_tile = color_map.get(self.tile_color_combo.currentText(), (245, 222, 179))
        color_clue_num = color_map.get(
            self.clue_num_color_combo.currentText(), (255, 0, 0)
        )

        # Uruchom w wątku
        self.generator_thread = GeneratorThread(
            self.orchestrator,
            width,
            height,
            source_file,
            word_file,
            num_variants,
            multi_strategy=multi_strategy,
            use_api=use_api,
            min_word_length=self.min_length_spin.value(),
            use_extra=self.extra_mode_check.isChecked(),
            color_empty=color_unavailable,  # Pola niedostępne = pola puste
            color_tile=color_tile,
            color_black=color_unavailable,  # Pola niedostępne (nieużywane polach)
            color_text=(40, 40, 40),  # Domyślnie czarny tekst
            color_clue_num=color_clue_num,
            font_name=self.font_combo.currentText(),
            progressive_mode=progressive_mode,
            progressive_phases=progressive_phases,
            max_total_variants=num_variants,
            edge_first_mode=edge_first_mode,
            edge_first_variants=edge_first_variants,
        )
        self.generator_thread.progress.connect(self.on_progress)
        self.generator_thread.finished.connect(self.on_finished)
        self.generator_thread.start()

    def on_progress(self, message: str):
        """Aktualizuj log progressu."""
        self.output_text.append(message)

    def on_finished(self, success: bool, message: str):
        """Generowanie skończone."""
        self.generate_btn.setEnabled(True)
        self.progress_bar.setVisible(False)

        self.output_text.append("")
        self.output_text.append(message)

        if success:
            QMessageBox.information(self, "Sukces", message)

            # Otwórz katalog z wynikami
            if self.orchestrator.output_dir and os.path.exists(
                self.orchestrator.output_dir
            ):
                try:
                    if sys.platform == "win32":
                        os.startfile(self.orchestrator.output_dir)
                    elif sys.platform == "darwin":  # macOS
                        os.system(f'open "{self.orchestrator.output_dir}"')
                    else:  # Linux
                        os.system(f'xdg-open "{self.orchestrator.output_dir}"')
                except Exception as e:
                    self.output_text.append(f"Nie można otworzyć folderu: {str(e)}")
        else:
            QMessageBox.critical(self, "Błąd", message)


def main():
    app = QApplication(sys.argv)
    window = CrosswordGeneratorGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
