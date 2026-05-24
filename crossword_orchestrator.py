# -*- coding: utf-8 -*-
"""
crossword_orchestrator.py — Orkiestracja generowania i eksportu krzyżówek
Zarządza procesem od input do output katalogów WYNIKI_*

Obsługuje:
- Multi-strategy generation (6 podejść do umieszczania wyrazów)
- Automatyczne zaznaczanie pustych pól na czarno
- Nazewnictwo katalogów z procentem pustych i ilością użytych liter
"""

import os
import datetime
from typing import Optional, List, Callable, Set, Dict, Any
import requests
import json
import time
from pathlib import Path
from word_source import WordSource, BinaryWordSource
from crossword_grid import CrosswordGrid, Direction
from crossword_generator import CrosswordGenerator
from crossword_new import CrosswordGeneratorNew
from crossword_strategies import MultiStrategyGenerator, StrategyResult
from image_renderer import CrosswordImageRenderer
from excel_exporter import ExcelExporter
from html_exporter import HTMLExporter


class CrosswordOrchestrator:
    """Zarządza całym procesem generowania i eksportu krzyżówek."""

    def __init__(self, base_dir: str = "."):
        """
        Args:
            base_dir: Katalog bazowy projektu
        """
        self.base_dir = base_dir
        self.word_source: Optional[WordSource] = None
        self.bin_source: Optional[BinaryWordSource] = None
        self.output_dir: Optional[str] = None
        self.use_api_enabled: bool = False
        self._api_cache: Dict[str, str] = {}
        self._api_cache_loaded: bool = False
        self._api_cache_path: str = os.path.join(self.base_dir, "api_cache.json")
        self._api_dry_run: bool = False
        self._api_log_path: Optional[str] = None  # Ścieżka do logu API

        # Kolory i czcionka dla renderera
        self.renderer_color_empty: Optional[tuple] = None
        self.renderer_color_tile: Optional[tuple] = None
        self.renderer_color_black: Optional[tuple] = None
        self.renderer_color_text: Optional[tuple] = None
        self.renderer_color_clue_num: Optional[tuple] = None
        self.renderer_font_name: str = "Arial"

    def setup_word_source(self, word_file: Optional[str] = None) -> bool:
        """
        Załaduj źródło słów.
        
        Args:
            word_file: Ścieżka do pliku z wyrazami, lub None dla domyślnego
        
        Returns:
            True jeśli OK
        """
        try:
            if word_file is None:
                # Spróbuj bazę w katalogu baza_wyrazow, a potem dane.txt
                project_dir = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.join(project_dir, "baza_wyrazow", "baza.txt")
                if os.path.exists(candidate):
                    word_file = candidate
                else:
                    word_file = os.path.join(project_dir, "dane.txt")

            self.word_source = WordSource(word_file)

            if not self.word_source.loaded:
                return False

            print(f"[Orchestrator] Źródło słów: OK ({len(self.word_source.get_all_words())} słów)")
            return True

        except Exception as e:
            print(f"[Orchestrator] BŁĄD ładowania źródła: {e}")
            return False

    def setup_bin_source(self, bin_file: Optional[str] = None) -> bool:
        """Załaduj binarną bazę słów slowa.bin do silnika wypełniania."""
        if bin_file is None:
            bin_file = os.path.join(self.base_dir, "baza_wyrazow", "slowa.bin")

        if not os.path.exists(bin_file):
            print(f"[Orchestrator] Uwaga: Brak pliku binarny słownika: {bin_file}")
            self.bin_source = None
            return False

        try:
            self.bin_source = BinaryWordSource(bin_file)
            if not self.bin_source.loaded:
                self.bin_source = None
                return False
            print(f"[Orchestrator] Binarna baza słów: OK")
            return True
        except Exception as e:
            print(f"[Orchestrator] BŁĄD ładowania binary word source: {e}")
            self.bin_source = None
            return False

    def create_output_directory(self, source_filename: str) -> bool:
        """
        Utwórz katalog wyjściowy w formacie backup/WYNIKI_data_godzina_nazwa.

        Args:
            source_filename: Nazwa pliku źródłowego (bez rozszerzenia)

        Returns:
            True jeśli OK
        """

        try:
            now = datetime.datetime.now()
            date_time = now.strftime("%Y%m%d_%H%M%S")

            # Wyczyść nazwę
            clean_name = Path(source_filename).stem  # Bez rozszerzenia

            output_name = f"WYNIKI_{date_time}_{clean_name}"
            backup_dir = os.path.join(self.base_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)
            self.output_dir = os.path.join(backup_dir, output_name)

            os.makedirs(self.output_dir, exist_ok=True)
            print(f"[Orchestrator] Katalog wyjściowy: {self.output_dir}")
            return True

        except Exception as e:
            print(f"[Orchestrator] BŁĄD tworzenia katalogu: {e}")
            return False

    def generate_and_export(
        self,
        width: int,
        height: int,
        source_filename: str = "dane.txt",
        word_file: Optional[str] = None,
        num_variants: int = 3,
        multi_strategy: bool = False,
        progress_callback: Optional[Callable] = None,
        use_api: bool = False,
        use_api_dry_run: bool = False,
        time_limit: float = 3.0,
        max_attempts: int = 5,
        target_valid_variants: Optional[int] = None,
        use_extra: bool = False,
        min_word_length: int = 2,
    ) -> bool:
        """
        Wygeneruj krzyżówkę(i) i wyeksportuj do wszystkich formatów.
        
        Args:
            width: Szerokość siatki
            height: Wysokość siatki
            source_filename: Nazwa pliku źródłowego (do nazwy katalogu)
            word_file: Ścieżka do pliku słów, lub None dla domyślnego
            num_variants: Liczba wariantów do wygenerowania
            multi_strategy: Czy używać multi-strategy generation (6 strategii)?
            progress_callback: Funkcja(message: str) do tracking postępu
        
        Returns:
            True jeśli OK
        """
        # Krok 1: Załaduj słowa
        if not self.setup_word_source(word_file):
            print("[Orchestrator] BŁĄD: Nie mogę załadować słów")
            return False

        # Krok 2: Utwórz katalog wyjściowy
        if not self.create_output_directory(source_filename):
            print("[Orchestrator] BŁĄD: Nie mogę utworzyć katalogu wyjściowego")
            return False

        # Krok 2b: Załaduj binarną bazę słów dla silnika wypełniania
        self.setup_bin_source()
        # Czy używać integracji z zewnętrznym API do generowania podpowiedzi?
        self.use_api_enabled = bool(use_api)
        self._api_dry_run = bool(use_api_dry_run)

        # Krok 3: Wygeneruj warianty
        if multi_strategy:
            return self._generate_multi_strategy(
                width, height, num_variants, progress_callback, use_extra=use_extra
            )
        else:
            # jeśli nie podano target_valid_variants, użyj num_variants
            if target_valid_variants is None:
                target_valid_variants = num_variants
            return self._generate_single_strategy(
                width,
                height,
                num_variants,
                progress_callback,
                time_limit=time_limit,
                max_attempts=max_attempts,
                target_valid_variants=target_valid_variants,
                use_extra=use_extra,
                min_word_length=min_word_length,
            )

    def _generate_single_strategy(
        self,
        width: int,
        height: int,
        num_variants: int,
        progress_callback: Optional[Callable] = None,
        time_limit: float = 3.0,
        max_attempts: int = 5,
        target_valid_variants: Optional[int] = None,
        use_extra: bool = False,
        min_word_length: int = 2,
    ) -> bool:
        """Nowy generator - prawidłowa krzyżówka z genxword-like algorytmem."""
        msg = f"[Orchestrator] Generuję {num_variants} wariantów krzyżówki ({width}x{height})..."
        print(msg)
        if progress_callback:
            progress_callback(msg)

        # Nowy, prawidłowy generator
        generator = CrosswordGeneratorNew(self.word_source)
        generator.min_word_length = max(2, min_word_length)

        if use_extra:
            max_attempts = max(max_attempts, 15)
            time_limit = max(time_limit, 8.0)

        variants = []
        for i in range(num_variants):
            msg = f"  Wariant {i+1}/{num_variants}..."
            print(msg)
            if progress_callback:
                progress_callback(msg)

            # Spróbuj wygenerować siatkę zgodną z zasadami Scrabble
            max_attempts_var = max_attempts if use_extra else 5
            grid = None
            for attempt in range(1, max_attempts_var + 1):
                grid = generator.generate(width, height, time_limit=time_limit)
                # Najpierw szybka walidacja
                valid, invalid_words = self._is_grid_scrabble_valid(grid)
                if valid:
                    # Dodatkowe sprawdzenia dla EXTRA mode
                    if use_extra:
                        if self._has_good_intersections(
                            grid
                        ) and not self._has_duplicate_words(grid):
                            break
                    else:
                        break

                # Jeśli mamy binarny silnik, spróbuj uzupełnić
                if self.bin_source and self.bin_source.loaded:
                    grid = self._fill_grid_with_engine(grid)
                    valid, invalid_words = self._is_grid_scrabble_valid(grid)
                    if valid:
                        if use_extra:
                            if self._has_good_intersections(
                                grid
                            ) and not self._has_duplicate_words(grid):
                                break
                        else:
                            break

                print(
                    f"    Próba {attempt}/{max_attempts_var} - niezgodna z regułami Scrabble. Nieprawidłowe wyrazy: {invalid_words}"
                )

            if not grid:
                print(
                    f"[Orchestrator] Błąd: nie udało się wygenerować siatki dla wariantu {i+1}"
                )
                continue

            if not self._is_grid_scrabble_valid(grid)[0]:
                print(
                    f"[Orchestrator] Ostrzeżenie: Wariant {i+1} nadal zawiera nieprawidłowe wyrazy, pomijam eksport tego wariantu."
                )
                # Nie dodajemy do listy wariantów
                continue

            variants.append(grid)

        print(f"[Orchestrator] Wygenerowano warianty")

        used_words: Set[str] = set()
        # Eksportuj każdy wariant i jego wersję silnikową
        for i, grid in enumerate(variants, 1):
            self._export_variant(grid, i, width, height)
            self._export_engine_variant(grid, i, width, height)
            used_words.update(w.upper() for w, _, _, _, _ in grid.placed_words)

        self._save_unused_words(used_words)

        print(f"[Orchestrator] Gotowe! Wyniki w: {self.output_dir}")
        return True

    def _generate_multi_strategy(
        self,
        width: int,
        height: int,
        num_variants: int,
        progress_callback: Optional[Callable] = None,
        use_extra: bool = False,
    ) -> bool:
        """Nowe podejście - lata multi-strategy (6 strategii)."""
        msg = f"[Orchestrator] Generuję krzyżówki z {num_variants} strategiami ({width}x{height})..."
        print(msg)
        if progress_callback:
            progress_callback(msg)

        # Utwórz generator multi-strategy
        multi_gen = MultiStrategyGenerator(self.word_source)

        # Funkcja progress do generator
        def strategy_progress(strategy_name: str, current: int, total: int):
            msg = f"  [{current}/{total}] Generuję: {strategy_name}..."
            print(msg)
            if progress_callback:
                progress_callback(msg)

        # Wygeneruj wszystkie strategie - NIE sortuj aby zobaczyć różne podejścia
        results = multi_gen.generate_all_strategies(
            width,
            height,
            progress_callback=strategy_progress,
            sort_by_density=use_extra,
        )

        # Wyświetl statystyki
        print(f"[Orchestrator] Wyniki generowania:")
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result}")

        # ZMIANA: Zamiast brać top num_variants po gęstości,
        # weź pierwsze num_variants strategii w oryginalnej kolejności
        # To pokazuje różne podejścia
        selected_results = results[:num_variants]

        # Jeśli mamy mniej wyników niż variants, uzupełnij
        if len(selected_results) < num_variants:
            selected_results = results

        # Eksportuj wybrane warianty
        used_words: Set[str] = set()
        for i, result in enumerate(selected_results, 1):
            self._export_variant_multi_strategy(
                result.grid,
                i,
                result.strategy_name,
                result.empty_percent,
                result.letter_count,
                width,
                height
            )
            self._export_engine_variant(result.grid, i, width, height)
            used_words.update(w.upper() for w, _, _, _, _ in result.grid.placed_words)

        self._save_unused_words(used_words)
        print(f"[Orchestrator] Gotowe! Wyniki w: {self.output_dir}")
        return True

    def _export_variant_multi_strategy(
        self,
        grid: CrosswordGrid,
        variant_num: int,
        strategy_name: str,
        empty_percent: float,
        letter_count: int,
        width: int,
        height: int
    ) -> None:
        """
        Eksportuj wariant z multi-strategy.
        
        Nazwa katalogu zawiera: _xx_ (procent pustych), _yyy_ (ilość liter)
        """
        # Zaokrąglij procent do całkowitej liczby
        empty_percent_int = int(round(empty_percent))

        # Formatuj nazwy z metadanes
        empty_marker = f"_{empty_percent_int:02d}_"
        letter_marker = f"_{letter_count:03d}"

        # Prefiks pliku
        variant_prefix = f"{variant_num:03d}"

        # Print strategii
        print(f"  Wariant {variant_num}: {strategy_name} | "
              f"Puste: {empty_percent:.1f}% | Litery: {letter_count}")

        # PNG uzupełniona
        renderer = CrosswordImageRenderer(
            cell_size=40,
            font_name=self.renderer_font_name,
            color_empty=self.renderer_color_empty,
            color_tile=self.renderer_color_tile,
            color_black=self.renderer_color_black,
            color_text=self.renderer_color_text,
            color_clue_num=self.renderer_color_clue_num,
        )
        img_filled = renderer.render(grid, filled=True)
        png_filled_name = f"{variant_prefix}{empty_marker}{letter_marker}_completed.png"
        png_filled_path = os.path.join(self.output_dir, png_filled_name)
        img_filled.save(png_filled_path, "PNG")

        # PNG pusta
        img_blank = renderer.render(grid, filled=False)
        png_blank_name = f"{variant_prefix}{empty_marker}{letter_marker}_blank.png"
        png_blank_path = os.path.join(self.output_dir, png_blank_name)
        img_blank.save(png_blank_path, "PNG")

        # TXT
        txt_name = f"{variant_prefix}{empty_marker}{letter_marker}.txt"
        txt_path = os.path.join(self.output_dir, txt_name)
        self._save_clues_txt(
            grid,
            txt_path,
            highlight_words=set(w.upper() for w in self.word_source.get_all_words()),
        )

        # XLSX (tylko dla wariantu 1)
        if variant_num == 1:
            xlsx_name = f"krizowka{empty_marker}{letter_marker}.xlsx"
            xlsx_path = os.path.join(self.output_dir, xlsx_name)
            exporter = ExcelExporter()
            exporter.export(grid, xlsx_path)

            # HTML (tylko dla wariantu 1)
            html_name = f"krizowka{empty_marker}{letter_marker}.html"
            html_path = os.path.join(self.output_dir, html_name)
            HTMLExporter.export(grid, html_path)

    def _needs_api_clue(self, clue: str, word: str) -> bool:
        """Sprawdź czy pytanie powinno pochodzić z API DeepSeek."""
        if not clue or clue.strip() == "":
            return True
        if clue.strip().upper() == word.strip().upper():
            return True
        if clue.strip().startswith("(") and "liter" in clue.lower():
            return True
        return False

    def _save_clues_txt(
        self,
        grid: CrosswordGrid,
        filepath: str,
        highlight_words: Optional[Set[str]] = None,
    ) -> None:
        """Zapisz pytania do pliku TXT (bez duplikatów) + lista słów alfabetycznie."""
        try:
            h_clues, v_clues = grid.get_clues_list()

            # Deduplikuj pytania (jeśli tego samego numeru pojawia się wiele razy)
            h_clues_unique = {}
            for num, clue, word in h_clues:
                if num not in h_clues_unique:
                    h_clues_unique[num] = (clue, word)

            v_clues_unique = {}
            for num, clue, word in v_clues:
                if num not in v_clues_unique:
                    v_clues_unique[num] = (clue, word)

            lines = []
            lines.append("KRZYŻÓWKA - PYTANIA")
            lines.append("=" * 60)
            lines.append("")
            lines.append("POZIOMO:")
            lines.append("-" * 60)

            highlight = highlight_words or set()
            used_words = set()

            for num in sorted(h_clues_unique.keys()):
                clue, word = h_clues_unique[num]
                used_words.add(word.upper())

                if self._needs_api_clue(clue, word):
                    if getattr(self, "use_api_enabled", False):
                        try:
                            generated = self._generate_clue_via_api(word)
                            if generated:
                                clue = generated
                        except Exception:
                            pass

                if self._needs_api_clue(clue, word):
                    # Jeśli nic nie wygenerowano, pokaż sam wyraz
                    clue = word

                if word.upper() in highlight:
                    clue = f"*{clue}*"
                lines.append(f"{num:2d}. {clue} ({len(word)} liter)")

            lines.append("")
            lines.append("PIONOWO:")
            lines.append("-" * 60)

            if v_clues_unique:
                for num in sorted(v_clues_unique.keys()):
                    clue, word = v_clues_unique[num]
                    used_words.add(word.upper())

                    if self._needs_api_clue(clue, word):
                        if getattr(self, "use_api_enabled", False):
                            try:
                                generated = self._generate_clue_via_api(word)
                                if generated:
                                    clue = generated
                            except Exception:
                                pass

                    if self._needs_api_clue(clue, word):
                        # Jeśli nic nie wygenerowano, pokaż sam wyraz
                        clue = word

                    if word.upper() in highlight:
                        clue = f"*{clue}*"
                    lines.append(f"{num:2d}. {clue} ({len(word)} liter)")
            else:
                lines.append("(brak)")

            # Dodaj listę wyrażów alfabetycznie
            lines.append("")
            lines.append("=" * 60)
            lines.append("WYRAZY UŻYTE W KRZYŻÓWCE (alfabetycznie):")
            lines.append("=" * 60)

            sorted_words = sorted(used_words)
            for word in sorted_words:
                lines.append(f"  • {word}")

            with open(filepath, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

        except Exception as e:
            print(f"[Orchestrator] BŁĄD zapisu TXT: {e}")

    def _export_variant(
        self,
        grid: CrosswordGrid,
        variant_num: int,
        width: int,
        height: int,
        file_prefix: Optional[str] = None,
    ) -> None:
        """Eksportuj jeden wariant do wszystkich formatów (stare nazewnictwo)."""
        # Waliduj przed eksportem
        valid, invalid_words = self._is_grid_scrabble_valid(grid)
        if not valid:
            print(
                f"  Eksport pominięty dla wariantu {variant_num}: nieprawidłowe wyrazy: {invalid_words}"
            )
            return

        variant_prefix = file_prefix if file_prefix else f"{variant_num:03d}"

        # PNG krzyżówki - wersja uzupełniona (z literami)
        print(f"  Exportuję wariant {variant_num}: PNG (uzupełniona)...")
        renderer = CrosswordImageRenderer(
            cell_size=40,
            font_name=self.renderer_font_name,
            color_empty=self.renderer_color_empty,
            color_tile=self.renderer_color_tile,
            color_black=self.renderer_color_black,
            color_text=self.renderer_color_text,
            color_clue_num=self.renderer_color_clue_num,
        )
        img_filled = renderer.render(grid, filled=True)
        png_filled_path = os.path.join(self.output_dir, f"{variant_prefix}_completed.png")
        img_filled.save(png_filled_path, "PNG")
        print(f"    {png_filled_path}")

        # PNG krzyżówki - wersja pusta (do wypełniania)
        print(f"  Exportuję wariant {variant_num}: PNG (pusta)...")
        img_blank = renderer.render(grid, filled=False)
        png_blank_path = os.path.join(self.output_dir, f"{variant_prefix}_blank.png")
        img_blank.save(png_blank_path, "PNG")
        print(f"    {png_blank_path}")

        # TXT z pytaniami
        print(f"  Exportuję wariant {variant_num}: TXT...")
        txt_path = os.path.join(self.output_dir, f"{variant_prefix}.txt")
        self._save_clues_txt(
            grid,
            txt_path,
            highlight_words=set(w.upper() for w in self.word_source.get_all_words()),
        )
        print(f"    {txt_path}")

        # XLSX (tylko dla pierwszego wariantu)
        if variant_num == 1:
            print(f"  Exportuję wariant {variant_num}: XLSX...")
            if file_prefix:
                xlsx_path = os.path.join(
                    self.output_dir, f"krizowka_{variant_prefix}.xlsx"
                )
            else:
                xlsx_path = os.path.join(self.output_dir, "krizowka.xlsx")
            exporter = ExcelExporter()
            exporter.export(grid, xlsx_path)
            print(f"    {xlsx_path}")

            # HTML (tylko dla pierwszego wariantu)
            print(f"  Exportuję wariant {variant_num}: HTML...")
            if file_prefix:
                html_path = os.path.join(
                    self.output_dir, f"krizowka_{variant_prefix}.html"
                )
            else:
                html_path = os.path.join(self.output_dir, "krizowka.html")
            HTMLExporter.export(grid, html_path)
            print(f"    {html_path}")

    def _export_engine_variant(
        self, grid: CrosswordGrid, variant_num: int, width: int, height: int
    ) -> None:
        """Wygeneruj i wyeksportuj wersję silnika uzupełniającego."""
        if not self.bin_source or not self.bin_source.loaded:
            print(
                f"  Silnik binarny pominięty dla wariantu {variant_num}: brak slowa.bin"
            )
            return

        print(f"  Silnik wypełniania dla wariantu {variant_num}...")
        engine_grid = self._fill_grid_with_engine(grid.copy())
        engine_grid.refresh_clues(self.word_source)

        # Waliduj przed eksportem wersji silnikowej
        valid, invalid_words = self._is_grid_scrabble_valid(engine_grid)
        if not valid:
            print(
                f"  Eksport silnikowy pominięty dla wariantu {variant_num}: nieprawidłowe wyrazy: {invalid_words}"
            )
            return

        prefix = f"silnik_{variant_num:03d}"
        self._export_variant(
            engine_grid, variant_num, width, height, file_prefix=prefix
        )

    def _fill_grid_with_engine(self, grid: CrosswordGrid) -> CrosswordGrid:
        """Spróbuj wypełnić wolne pola słowami ze słownika binarnego."""
        if not self.bin_source or not self.bin_source.loaded:
            return grid

        grid.refresh_clues(self.word_source)
        changed = True
        while changed:
            changed = False
            candidate_slots = self._collect_engine_slots(grid)
            for slot in candidate_slots:
                pattern = slot["pattern"]
                if pattern.count(".") == 0:
                    continue
                if all(ch == "." for ch in pattern):
                    continue

                matches = self.bin_source.find_matching(pattern, max_results=20)
                if not matches:
                    continue

                # Wybierz pierwsze dopasowanie; preferuj dłuższe słowa i sloty z więcej literami
                match = matches[0]
                if grid.place_word(
                    match,
                    slot["row"],
                    slot["col"],
                    slot["direction"],
                    self.word_source.get_word(match) or f"({len(match)} liter)",
                ):
                    changed = True
                    grid.refresh_clues(self.word_source)
                    break

        return grid

    def _collect_engine_slots(self, grid: CrosswordGrid) -> List[dict]:
        """Zbierz otwarte sloty do wypełnienia przez silnik binarny."""
        slots: List[dict] = []

        for row in range(grid.height):
            for col in range(grid.width):
                if grid.grid[row][col] is None:
                    continue

                # Poziomo
                if col == 0 or grid.grid[row][col - 1] is None:
                    pattern, length = self._build_slot_pattern(
                        grid, row, col, Direction.HORIZONTAL
                    )
                    if (
                        length >= 2
                        and "." in pattern
                        and any(ch != "." for ch in pattern)
                    ):
                        slots.append(
                            {
                                "direction": Direction.HORIZONTAL,
                                "row": row,
                                "col": col,
                                "pattern": pattern,
                                "fixed": pattern.count("."),
                            }
                        )

                # Pionowo
                if row == 0 or grid.grid[row - 1][col] is None:
                    pattern, length = self._build_slot_pattern(
                        grid, row, col, Direction.VERTICAL
                    )
                    if (
                        length >= 2
                        and "." in pattern
                        and any(ch != "." for ch in pattern)
                    ):
                        slots.append(
                            {
                                "direction": Direction.VERTICAL,
                                "row": row,
                                "col": col,
                                "pattern": pattern,
                                "fixed": pattern.count("."),
                            }
                        )

        # Preferuj sloty z najdłuższym wzorem i większą liczbą ustalonych liter
        slots.sort(key=lambda s: (-len(s["pattern"]), s["pattern"].count(".")))
        return slots

    def _build_slot_pattern(
        self, grid: CrosswordGrid, row: int, col: int, direction: Direction
    ) -> tuple:
        pattern = []
        length = 0

        if direction == Direction.HORIZONTAL:
            c = col
            while c < grid.width and grid.grid[row][c] is not None:
                cell = grid.grid[row][c]
                if cell == "":
                    pattern.append(".")
                else:
                    pattern.append(cell)
                length += 1
                c += 1
        else:
            r = row
            while r < grid.height and grid.grid[r][col] is not None:
                cell = grid.grid[r][col]
                if cell == "":
                    pattern.append(".")
                else:
                    pattern.append(cell)
                length += 1
                r += 1

        return "".join(pattern), length

    def _get_final_words(self, grid: CrosswordGrid) -> List[str]:
        """Zwróć wszystkie skończone wyrazy (poziome i pionowe) na siatce.

        Najpierw próbujemy użyć `grid.placed_words` (jeśli dostępne), co jest szybsze
        i niezawodne. Jeśli nie ma tej struktury, robimy pełne skanowanie siatki.
        """
        # Jeśli generator przechowuje słowa w `placed_words`, użyj ich
        try:
            placed = getattr(grid, "placed_words", None)
            if placed and isinstance(placed, list):
                return [w.upper() for w, _, _, _, _ in placed if w and len(w) >= 2]
        except Exception:
            pass

        words: List[str] = []
        # poziomo
        for r in range(grid.height):
            c = 0
            while c < grid.width:
                if grid.grid[r][c] is None:
                    c += 1
                    continue
                # start
                if c == 0 or grid.grid[r][c - 1] is None:
                    buf = []
                    cc = c
                    while cc < grid.width and grid.grid[r][cc] is not None:
                        ch = grid.grid[r][cc]
                        if not ch or ch == "":
                            buf = []
                            break
                        buf.append(ch)
                        cc += 1
                    if len(buf) >= 2:
                        words.append("".join(buf).upper())
                    c = cc
                else:
                    c += 1

        # pionowo
        for c in range(grid.width):
            r = 0
            while r < grid.height:
                if grid.grid[r][c] is None:
                    r += 1
                    continue
                if r == 0 or grid.grid[r - 1][c] is None:
                    buf = []
                    rr = r
                    while rr < grid.height and grid.grid[rr][c] is not None:
                        ch = grid.grid[rr][c]
                        if not ch or ch == "":
                            buf = []
                            break
                        buf.append(ch)
                        rr += 1
                    if len(buf) >= 2:
                        words.append("".join(buf).upper())
                    r = rr
                else:
                    r += 1

        return words

    def _is_word_valid(self, word: str) -> bool:
        """Sprawdź poprawność wyrazu w bazie: najpierw `bin_source`, potem `word_source`."""
        w = word.strip().upper()
        if not w:
            return False
        try:
            if self.bin_source and self.bin_source.loaded:
                words = self.bin_source.get_words_by_length(len(w))
                if w in (x.upper() for x in words):
                    return True
        except Exception:
            pass

        if self.word_source and self.word_source.loaded:
            return self.word_source.is_valid(w)

        return False

    def _is_grid_scrabble_valid(self, grid: CrosswordGrid) -> tuple:
        """Sprawdź, czy wszystkie finalne wyrazy na siatce są poprawne wg słownika.

        Zwraca (bool, list) gdzie lista to nieprawidłowe wyrazy (może być pusta).
        """
        words = self._get_final_words(grid)
        invalid = []
        for w in words:
            if not self._is_word_valid(w):
                invalid.append(w)
        return (len(invalid) == 0, invalid)

    def _save_unused_words(self, used_words: Set[str]) -> None:
        """Zapisz niewykorzystane słowa z wejściowej listy do pliku."""
        if not self.output_dir or not self.word_source:
            return

        source_words = [w.upper() for w in self.word_source.get_all_words()]
        unused = [w for w in source_words if w not in used_words]
        path = os.path.join(self.output_dir, "niewykorzystane_słowa.txt")
        with open(path, "w", encoding="utf-8") as f:
            for word in unused:
                f.write(word + "\n")
        print(f"[Orchestrator] Niewykorzystane słowa ({len(unused)}): {path}")

    def _generate_clue_via_api(self, word: str) -> str:
        """Spróbuj wygenerować krótką definicję/podpowiedź dla `word` korzystając z zewnętrznego API.

        Funkcja czyta klucz z `API_klucz/deepseek.txt` w katalogu `base_dir`.
        Jeśli nie ma klucza lub wystąpi błąd - zwraca pusty string.
        """
        try:
            key_path = os.path.join(self.base_dir, "API_klucz", "deepseek.txt")
            if not os.path.exists(key_path):
                return ""

            with open(key_path, "r", encoding="utf-8") as kf:
                api_key = kf.read().strip()
            if not api_key:
                return ""

            # Przygotuj prosty prompt (bardziej precyzyjny)
            prompt = (
                f"Podaj krótką (maks. jedno zdanie) definicję słowa '{word}' po polsku. "
                "Nie podawaj przykładów użycia ani dodatkowych komentarzy. Jeśli to imię własne, napisz 'imię własne'."
            )

            # Domyślny endpoint Deepseek (może wymagać dostosowania)
            endpoint = "https://api.deepseek.ai/generate"

            # Wczytaj cache jeśli jeszcze nie
            word_key = word.strip().upper()
            if not self._api_cache_loaded:
                try:
                    if os.path.exists(self._api_cache_path):
                        with open(self._api_cache_path, "r", encoding="utf-8") as cf:
                            self._api_cache = json.load(cf)
                except Exception:
                    self._api_cache = {}
                self._api_cache_loaded = True

            # Jeśli jest w cache - zwróć natychmiast
            cached = self._api_cache.get(word_key)
            if cached:
                return cached

            # Jeżeli tryb dry-run i brak cache - nie wykonuj żądania
            if getattr(self, "_api_dry_run", False) and not cached:
                return ""

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload: Dict[str, Any] = {"prompt": prompt, "max_tokens": 60}

            max_retries = 3
            backoff_base = 0.5
            resp_data: Any = None
            for attempt in range(max_retries):
                try:
                    resp = requests.post(
                        endpoint, json=payload, headers=headers, timeout=6
                    )
                    if resp.status_code == 200:
                        resp_data = resp.json()
                        break
                    else:
                        # krótkie opóźnienie przy błędzie serwera
                        time.sleep(backoff_base * (2**attempt))
                except requests.RequestException:
                    time.sleep(backoff_base * (2**attempt))

            if not resp_data:
                return ""

            text = ""
            if isinstance(resp_data, dict):
                text = resp_data.get("text") or resp_data.get("result") or ""
                if (
                    not text
                    and "choices" in resp_data
                    and isinstance(resp_data["choices"], list)
                ):
                    c = resp_data["choices"][0]
                    text = c.get("text") or c.get("message", {}).get("content", "")

            text = (text or "").strip()

            # Zapisz do cache jeśli mamy wynik
            if text:
                try:
                    self._api_cache[word_key] = text
                    with open(self._api_cache_path, "w", encoding="utf-8") as cf:
                        json.dump(self._api_cache, cf, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            return text
        except Exception as e:
            print(f"[Orchestrator] Błąd API generowania podpowiedzi: {e}")
            return ""

    def _has_good_intersections(self, grid: CrosswordGrid) -> bool:
        """Sprawdź, czy wyrazy dobrze się przecinają (nie są tylko obok siebie).

        Wymagamy aby większość wyrazów przecinała się z innymi wyrazami,
        a nie tylko były umieszczone obok siebie.
        """
        if not hasattr(grid, "placed_words") or not grid.placed_words:
            return True  # Brak infirmacji, zaakceptuj

        # Dla każdego umieszczonego wyrazu, sprawdzenie czy ma mniej niż jedno przecięcie
        intersecting_count = 0
        for word, row, col, direction, _ in grid.placed_words:
            has_intersection = False
            if direction == Direction.HORIZONTAL:
                # Sprawdz pionowe przecięcia
                for c in range(col, col + len(word)):
                    if row > 0 and grid.grid[row - 1][c] not in (None, ""):
                        has_intersection = True
                        break
                    if row < grid.height - 1 and grid.grid[row + 1][c] not in (
                        None,
                        "",
                    ):
                        has_intersection = True
                        break
            else:  # VERTICAL
                # Sprawdz poziome przecięcia
                for r in range(row, row + len(word)):
                    if col > 0 and grid.grid[r][col - 1] not in (None, ""):
                        has_intersection = True
                        break
                    if col < grid.width - 1 and grid.grid[r][col + 1] not in (None, ""):
                        has_intersection = True
                        break

            if has_intersection:
                intersecting_count += 1

        # Co najmniej 70% wyrazów powinno się przecinać
        total_words = len(grid.placed_words)
        if total_words > 0:
            intersection_ratio = intersecting_count / total_words
            return intersection_ratio >= 0.7

        return True

    def _has_duplicate_words(self, grid: CrosswordGrid) -> bool:
        """Sprawdzenie czy są duplikaty wyrazów na siatce.

        Zwraca True jeśli są duplikaty (złe), False jeśli OK.
        """
        if not hasattr(grid, "placed_words") or not grid.placed_words:
            return False  # Brak infirmacji, zaakceptuj

        words_used = []
        for word, _, _, _, _ in grid.placed_words:
            words_used.append(word.upper())

        # Jeśli liczba unikalnych słów jest mniejsza niż całkowita - są duplikaty
        unique_words = set(words_used)
        has_dupes = len(unique_words) < len(words_used)

        return has_dupes
