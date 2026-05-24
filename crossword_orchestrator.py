# -*- coding: utf-8 -*-
"""
crossword_orchestrator.py — Orkiestracja generowania i eksportu krzyżówek
ZMIANY v3:
  - DeepSeek: poprawny endpoint OpenAI-compatible + tylko wyrazy BEZ opisu
  - GPU: NumPy wektoryzacja + CuPy fallback dla dopasowywania wzorców
  - Warianty zapisywane do pliku (nie trzymane w RAM) — obsługa 10000+
  - PNG → JPG 70% kompresja do katalogu tmp_preview/
  - Wyrazy użytkownika: biała lista (zawsze dozwolone, priorytet przed .bin)
  - faza1.txt: dopisywanie "wyrazy niewykorzystane z bazy użytkownika"
  - Raport JSON rozszerzony o błędy i szczegóły
"""

import os
import gc
import json
import datetime
import time
import requests
from pathlib import Path
from typing import Optional, List, Callable, Set, Dict, Any, Tuple

# GPU — próbuj CuPy (CUDA), fallback do NumPy
try:
    import cupy as np_gpu
    GPU_BACKEND = "cupy"
except ImportError:
    import numpy as np_gpu
    GPU_BACKEND = "numpy"

import numpy as np  # zawsze numpy dla pomocniczych operacji

# CUDA / PyTorch detection (dla info w GUI)
try:
    import torch
    CUDA_AVAILABLE = torch.cuda.is_available()
except ImportError:
    CUDA_AVAILABLE = False

from word_source import WordSource, BinaryWordSource
from crossword_grid import CrosswordGrid, Direction
from crossword_strategies import MultiStrategyGenerator, StrategyResult
from image_renderer import CrosswordImageRenderer
from excel_exporter import ExcelExporter
from html_exporter import HTMLExporter


# ---------------------------------------------------------------------------
# GPU-accelerated word pattern matching
# ---------------------------------------------------------------------------

class GPUWordMatcher:
    """Wektoryzowane dopasowywanie wzorców słów (NumPy/CuPy)."""

    def __init__(self, words: List[str]):
        self.backend = GPU_BACKEND
        self._build_index(words)

    def _build_index(self, words: List[str]):
        """Buduj indeks słów jako macierz kodów ASCII."""
        if not words:
            self._by_len: Dict[int, Any] = {}
            self._word_lists: Dict[int, List[str]] = {}
            return

        # Grupuj słowa po długości — każda grupa to osobna macierz
        from collections import defaultdict
        groups: Dict[int, List[str]] = defaultdict(list)
        for w in words:
            groups[len(w)].append(w.upper())

        self._by_len = {}
        self._word_lists = {}
        for length, wlist in groups.items():
            # Macierz (N, length) kodów znakowych
            arr = np.array([[ord(c) for c in w] for w in wlist], dtype=np.int16)
            try:
                self._by_len[length] = np_gpu.array(arr)
            except Exception:
                self._by_len[length] = arr
            self._word_lists[length] = wlist

    def find_matching(self, pattern: str, max_results: int = 200) -> List[str]:
        """Znajdź słowa pasujące do wzorca (. = dowolna litera)."""
        L = len(pattern)
        if L not in self._by_len:
            return []

        mat = self._by_len[L]   # (N, L)
        wlist = self._word_lists[L]

        # Zbuduj maskę stałych pozycji
        fixed_positions = [(i, ord(c)) for i, c in enumerate(pattern) if c != '.']
        if not fixed_positions:
            return wlist[:max_results]

        try:
            mask = np_gpu.ones(len(wlist), dtype=bool)
            for pos, code in fixed_positions:
                mask &= (mat[:, pos] == code)
            # Przenieś maskę z GPU do CPU jeśli CuPy
            if GPU_BACKEND == "cupy":
                indices = np_gpu.asnumpy(np_gpu.where(mask)[0])
            else:
                indices = np.where(mask)[0]
            return [wlist[i] for i in indices[:max_results]]
        except Exception:
            # Fallback CPU
            results = []
            for w in wlist:
                ok = all(w[p] == chr(c) for p, c in fixed_positions)
                if ok:
                    results.append(w)
                    if len(results) >= max_results:
                        break
            return results


# ---------------------------------------------------------------------------
# VariantFileStore — zapis wariantów do pliku zamiast trzymania w RAM
# ---------------------------------------------------------------------------

class VariantFileStore:
    """Zapisuje metadane wariantów do pliku JSONL (jeden wariant = jedna linia)."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._count = 0
        # Wyczyść jeśli istnieje
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('')

    def append(self, variant_data: dict):
        with open(self.filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(variant_data, ensure_ascii=False) + '\n')
        self._count += 1

    def count(self) -> int:
        return self._count

    def read_all(self) -> List[dict]:
        variants = []
        if not os.path.exists(self.filepath):
            return variants
        with open(self.filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        variants.append(json.loads(line))
                    except Exception:
                        pass
        return variants

    def find_best(self, key_func) -> Optional[dict]:
        best = None
        best_score = None
        for v in self.read_all():
            score = key_func(v)
            if best_score is None or score > best_score:
                best_score = score
                best = v
        return best


# ---------------------------------------------------------------------------
# CrosswordOrchestrator
# ---------------------------------------------------------------------------

class CrosswordOrchestrator:
    """Zarządza całym procesem generowania i eksportu krzyżówek."""

    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.word_source: Optional[WordSource] = None
        self.bin_source: Optional[BinaryWordSource] = None
        self.gpu_matcher: Optional[GPUWordMatcher] = None
        self.output_dir: Optional[str] = None
        self.planned_words: List[str] = []
        self.use_api_enabled: bool = False
        self._api_cache: Dict[str, str] = {}
        self._api_cache_loaded: bool = False
        self._api_cache_path: str = os.path.join(self.base_dir, "api_cache.json")
        self._api_dry_run: bool = False
        self._api_log_path: Optional[str] = None

        # GPU info
        self.use_cuda: bool = CUDA_AVAILABLE
        self.gpu_backend: str = GPU_BACKEND
        self.gpu_device: str = f"GPU (CUDA/{GPU_BACKEND})" if self.use_cuda else f"CPU ({GPU_BACKEND})"

        # Kolory i czcionka dla renderera
        self.renderer_color_empty: Optional[tuple] = None
        self.renderer_color_tile: Optional[tuple] = None
        self.renderer_color_black: Optional[tuple] = None
        self.renderer_color_text: Optional[tuple] = None
        self.renderer_color_clue_num: Optional[tuple] = None
        self.renderer_font_name: str = "Arial"

        # Śledzenie wariantów
        self._variant_store: Optional[VariantFileStore] = None
        self._generation_start_time: Optional[datetime.datetime] = None
        self._generation_errors: List[dict] = []  # Błędy do raportu JSON

        # Białą lista wyrazów użytkownika (zawsze dozwolone)
        self._user_whitelist: Set[str] = set()

    # -----------------------------------------------------------------------
    # SETUP
    # -----------------------------------------------------------------------

    def setup_word_source(self, word_file: Optional[str] = None) -> bool:
        try:
            if word_file is None:
                project_dir = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.join(project_dir, "baza_wyrazow", "baza.txt")
                word_file = candidate if os.path.exists(candidate) else os.path.join(project_dir, "dane.txt")

            self.word_source = WordSource(word_file)
            if not self.word_source.loaded:
                return False

            # Zbuduj białą listę wyrazów użytkownika
            self._user_whitelist = set(w.upper() for w in self.word_source.get_all_words())

            # Zbuduj GPU matcher dla wszystkich słów
            all_words = self.word_source.get_all_words()
            print(f"[Orchestrator] Buduję indeks GPU ({GPU_BACKEND}) dla {len(all_words)} słów...")
            self.gpu_matcher = GPUWordMatcher(all_words)
            print(f"[Orchestrator] Indeks GPU gotowy. Backend: {GPU_BACKEND}")
            print(f"[Orchestrator] Źródło słów: OK ({len(all_words)} słów)")
            return True
        except Exception as e:
            self._log_error("setup_word_source", str(e))
            print(f"[Orchestrator] BŁĄD ładowania źródła: {e}")
            return False

    def load_planned_words(self, clue_file: Optional[str] = None) -> bool:
        if clue_file is None:
            for candidate in ["002.txt", "clues.txt", "pytania.txt"]:
                p = os.path.join(self.output_dir or ".", candidate)
                if os.path.exists(p):
                    clue_file = p
                    break
            if not clue_file:
                self.planned_words = []
                return True

        try:
            self.planned_words = []
            if os.path.exists(clue_file):
                with open(clue_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            word = line.split('-')[0].strip().upper()
                            if word:
                                self.planned_words.append(word)
            if self.planned_words:
                print(f"[Orchestrator] Zaplanowane wyrazy: {len(self.planned_words)} słów")
            return True
        except Exception as e:
            self._log_error("load_planned_words", str(e))
            self.planned_words = []
            return False

    def setup_bin_source(self, bin_file: Optional[str] = None) -> bool:
        if bin_file is None:
            bin_file = os.path.join(self.base_dir, "baza_wyrazow", "slowa.bin")
        if not os.path.exists(bin_file):
            print(f"[Orchestrator] Uwaga: Brak slowa.bin: {bin_file}")
            self.bin_source = None
            return False
        try:
            self.bin_source = BinaryWordSource(bin_file)
            if not self.bin_source.loaded:
                self.bin_source = None
                return False
            # Rozszerz GPU matcher o słowa z bin
            bin_words = self.bin_source.get_all_words()
            all_combined = list(self._user_whitelist) + bin_words
            print(f"[Orchestrator] Buduję rozszerzony indeks GPU ({len(all_combined)} słów)...")
            self.gpu_matcher = GPUWordMatcher(all_combined)
            print(f"[Orchestrator] Binarna baza słów: OK ({len(bin_words)} słów)")
            return True
        except Exception as e:
            self._log_error("setup_bin_source", str(e))
            self.bin_source = None
            return False

    def create_output_directory(self, source_filename: str) -> bool:
        try:
            now = datetime.datetime.now()
            date_time = now.strftime("%Y%m%d_%H%M%S")
            clean_name = Path(source_filename).stem
            output_name = f"WYNIKI_{date_time}_{clean_name}"
            backup_dir = os.path.join(self.base_dir, "backup")
            os.makedirs(backup_dir, exist_ok=True)
            self.output_dir = os.path.join(backup_dir, output_name)
            os.makedirs(self.output_dir, exist_ok=True)

            # Katalog tmp_preview dla JPG
            self.tmp_preview_dir = os.path.join(self.output_dir, "tmp_preview")
            os.makedirs(self.tmp_preview_dir, exist_ok=True)

            self._api_log_path = os.path.join(self.output_dir, "api_deepseek.log")

            # Inicjuj store wariantów
            variants_jsonl = os.path.join(self.output_dir, "variants_store.jsonl")
            self._variant_store = VariantFileStore(variants_jsonl)
            self._generation_errors = []

            print(f"[Orchestrator] Katalog wyjściowy: {self.output_dir}")
            print(f"[Orchestrator] Podglądy JPG: {self.tmp_preview_dir}")
            return True
        except Exception as e:
            self._log_error("create_output_directory", str(e))
            print(f"[Orchestrator] BŁĄD tworzenia katalogu: {e}")
            return False

    # -----------------------------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------------------------

    def _log_error(self, context: str, message: str, extra: dict = None):
        """Zapisz błąd do listy błędów (do raportu JSON)."""
        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "context": context,
            "message": message,
        }
        if extra:
            entry.update(extra)
        self._generation_errors.append(entry)

    def _add_variant_info(self, variant_num: int, strategy_name: str,
                          empty_percent: float, letter_count: int,
                          word_count: int, dimensions: tuple,
                          user_words_used: int = 0,
                          unused_user_words: List[str] = None) -> None:
        if self._variant_store is None:
            return
        data = {
            "variant_num": variant_num,
            "strategy": strategy_name,
            "empty_percent": round(empty_percent, 1),
            "letter_count": letter_count,
            "word_count": word_count,
            "grid_size": {"width": dimensions[0], "height": dimensions[1]},
            "user_words_used": user_words_used,
            "unused_user_words_count": len(unused_user_words) if unused_user_words else 0,
            "unused_user_words": unused_user_words or [],
        }
        self._variant_store.append(data)

    def _save_report(self) -> bool:
        if not self.output_dir:
            return False
        try:
            variants = self._variant_store.read_all() if self._variant_store else []
            duration = None
            if self._generation_start_time:
                duration = (datetime.datetime.now() - self._generation_start_time).total_seconds()

            report = {
                "generated": datetime.datetime.now().isoformat(),
                "duration_seconds": duration,
                "gpu_backend": GPU_BACKEND,
                "cuda_available": CUDA_AVAILABLE,
                "total_variants": len(variants),
                "variants": variants,
                "word_source_file": self.word_source.filepath if self.word_source else "unknown",
                "total_words_available": len(self.word_source.get_all_words()) if self.word_source else 0,
                "user_whitelist_size": len(self._user_whitelist),
                "errors": self._generation_errors,
                "error_count": len(self._generation_errors),
                "error_categories": self._categorize_errors(),
            }

            report_path = os.path.join(self.output_dir, "raport.json")
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"[Orchestrator] Raport zapisany: {report_path}")
            return True
        except Exception as e:
            print(f"[Orchestrator] BŁĄD zapisu raportu: {e}")
            return False

    def _categorize_errors(self) -> dict:
        cats: Dict[str, int] = {}
        for e in self._generation_errors:
            ctx = e.get("context", "unknown")
            cats[ctx] = cats.get(ctx, 0) + 1
        return cats

    # -----------------------------------------------------------------------
    # MAIN ENTRY POINT
    # -----------------------------------------------------------------------

    def generate_and_export(self, width: int, height: int,
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
                            progressive_mode: bool = False,
                            progressive_phases: int = 3,
                            max_total_variants: int = 100,
                            edge_first_mode: bool = False,
                            edge_first_variants: int = 3,
                            ) -> bool:
        if not self.setup_word_source(word_file):
            print("[Orchestrator] BŁĄD: Nie mogę załadować słów")
            return False
        if not self.create_output_directory(source_filename):
            print("[Orchestrator] BŁĄD: Nie mogę utworzyć katalogu")
            return False

        self._generation_start_time = datetime.datetime.now()
        self.use_api_enabled = bool(use_api)
        self._api_dry_run = bool(use_api_dry_run)

        if edge_first_mode:
            return self._generate_edge_first(width, height, num_variants,
                                             progress_callback,
                                             edge_first_variants=edge_first_variants,
                                             use_extra=use_extra,
                                             max_total_variants=max_total_variants)
        elif progressive_mode:
            return self._generate_progressive(width, height, num_variants,
                                              progressive_phases, progress_callback,
                                              use_extra=use_extra,
                                              max_total_variants=max_total_variants)
        elif multi_strategy:
            return self._generate_multi_strategy(width, height, num_variants,
                                                 progress_callback, use_extra=use_extra,
                                                 max_total_variants=max_total_variants)
        else:
            if target_valid_variants is None:
                target_valid_variants = num_variants
            return self._generate_single_strategy(width, height, num_variants,
                                                  progress_callback,
                                                  time_limit=time_limit,
                                                  max_attempts=max_attempts,
                                                  target_valid_variants=target_valid_variants,
                                                  use_extra=use_extra,
                                                  min_word_length=min_word_length,
                                                  max_total_variants=max_total_variants)

    # -----------------------------------------------------------------------
    # EDGE FIRST — od brzegów
    # -----------------------------------------------------------------------

    def _generate_edge_first(self, width, height, num_variants,
                              progress_callback=None,
                              edge_first_variants: int = 3,
                              use_extra: bool = False,
                              max_total_variants: int = 100) -> bool:
        """
        Tryb EDGE_FIRST — oddzielny katalog EdgeFirst/.

        Generuje N wariantów strategią od brzegów i zapisuje je w osobnym
        podkatalogu EdgeFirst/ wewnątrz katalogu wyjściowego.
        Cel: maksymalne zagęszczenie siatki, minimalizacja pustych pól.
        """
        msg = (f"[Orchestrator] Tryb EDGE_FIRST (od brzegów): "
               f"{edge_first_variants} wariantów, {width}x{height}")
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self.load_planned_words()

        edge_dir = os.path.join(self.output_dir, "EdgeFirst")
        os.makedirs(edge_dir, exist_ok=True)

        from crossword_strategies import MultiStrategyGenerator  # noqa: already imported at top

        multi_gen = MultiStrategyGenerator(
            self.word_source,
            planned_words=self.planned_words,
            user_whitelist=self._user_whitelist,
            gpu_matcher=self.gpu_matcher,
            edge_first_mode=True,
            edge_first_variants=edge_first_variants,
        )

        def strategy_progress(strategy_name, current, total):
            m = f"  [{current}/{total}] EDGE_FIRST: {strategy_name}..."
            print(m)
            if progress_callback:
                progress_callback(m)

        results = multi_gen.generate_all_strategies(
            width, height,
            progress_callback=strategy_progress,
            sort_by_density=True,
        )

        if not results:
            msg = "[Orchestrator] EDGE_FIRST: Brak wyników"
            print(msg)
            if progress_callback:
                progress_callback(msg)
            return False

        # Wybierz najlepsze warianty EDGE_FIRST (prefiks "7.")
        edge_results = [r for r in results if "EDGE_FIRST" in r.strategy_name]
        if not edge_results:
            edge_results = results  # fallback: wszystkie

        used_words: Set[str] = set()
        for i, result in enumerate(edge_results[:max(1, num_variants)], 1):
            variant_num = 1000 + i  # numeracja oddzielna żeby nie kolidować
            self._export_variant_to_directory(
                result.grid, edge_dir, i,
                result.strategy_name,
                result.empty_percent,
                result.letter_count,
                width, height,
            )
            for w, _, _, _, _ in result.grid.placed_words:
                used_words.add(w.upper())

            msg = (f"  [EDGE_FIRST {i}] {result.strategy_name} | "
                   f"Puste: {result.empty_percent}% | Wyrazy: {result.word_count}")
            print(msg)
            if progress_callback:
                progress_callback(msg)

            gc.collect()

        unused = self._get_unused_user_words(used_words)
        msg = (f"[Orchestrator] EDGE_FIRST gotowe! Wyniki w: {edge_dir} | "
               f"Niewykorzystanych: {len(unused)}")
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self._save_report()
        return True

    # -----------------------------------------------------------------------
    # SINGLE STRATEGY
    # -----------------------------------------------------------------------

    def _generate_single_strategy(self, width: int, height: int, num_variants: int,
                                  progress_callback=None, time_limit=60.0,
                                  max_attempts=5, target_valid_variants=None,
                                  use_extra=False, min_word_length=2,
                                  max_total_variants=100) -> bool:
        msg = f"[Orchestrator] Generuję {num_variants} wariantów ({width}x{height}), max_total={max_total_variants}..."
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self.load_planned_words()

        multi_gen = MultiStrategyGenerator(self.word_source,
                                           planned_words=self.planned_words,
                                           user_whitelist=self._user_whitelist,
                                           gpu_matcher=self.gpu_matcher)

        def strategy_progress(strategy_name, current, total):
            m = f"  [{current}/{total}] {strategy_name}..."
            if progress_callback:
                progress_callback(m)

        results = multi_gen.generate_all_strategies(width, height,
                                                    progress_callback=strategy_progress,
                                                    sort_by_density=use_extra)
        if not results:
            msg = "[Orchestrator] BŁĄD: Nie wygenerowano żadnych wyników"
            self._log_error("generate_single_strategy", msg)
            print(msg)
            if progress_callback:
                progress_callback(msg)
            return False

        user_words_set = self._user_whitelist

        def result_score(r: StrategyResult):
            user_count = sum(1 for w, _, _, _, _ in r.grid.placed_words
                             if w.upper() in user_words_set)
            return (user_count, r.density)

        results_ranked = sorted(results, key=result_score, reverse=True)

        used_words: Set[str] = set()
        exported = 0
        for result in results_ranked:
            if exported >= num_variants:
                break
            exported += 1
            self._export_multi_strategy_variant(result.grid, exported,
                                                result.strategy_name,
                                                result.empty_percent,
                                                result.letter_count,
                                                width, height)
            for w, _, _, _, _ in result.grid.placed_words:
                used_words.add(w.upper())

            gc.collect()  # Zwolnij pamięć po eksporcie wariantu

            msg = f"  [OK] Wariant {exported}/{num_variants} GOTOWY! ({len(result.grid.placed_words)} wyrazów)"
            print(msg)
            if progress_callback:
                progress_callback(msg)

        msg = f"[Orchestrator] Wygenerowano {exported}/{num_variants} wariantów"
        print(msg)
        if progress_callback:
            progress_callback(msg)

        unused = self._get_unused_user_words(used_words)
        self._save_unused_words(used_words)
        self._save_report()
        print(f"[Orchestrator] Gotowe! Wyniki w: {self.output_dir}")
        return True

    # -----------------------------------------------------------------------
    # MULTI STRATEGY
    # -----------------------------------------------------------------------

    def _generate_multi_strategy(self, width, height, num_variants,
                                 progress_callback=None, use_extra=False,
                                 max_total_variants=100) -> bool:
        msg = f"[Orchestrator] Multi-strategy ({width}x{height}), max_total={max_total_variants}..."
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self.load_planned_words()
        multi_gen = MultiStrategyGenerator(self.word_source,
                                           planned_words=self.planned_words,
                                           user_whitelist=self._user_whitelist,
                                           gpu_matcher=self.gpu_matcher)

        def strategy_progress(strategy_name, current, total):
            m = f"  [{current}/{total}] Generuję: {strategy_name}..."
            print(m)
            if progress_callback:
                progress_callback(m)

        results = multi_gen.generate_all_strategies(width, height,
                                                    progress_callback=strategy_progress,
                                                    sort_by_density=use_extra)
        print(f"[Orchestrator] Wyniki generowania:")
        for i, r in enumerate(results, 1):
            print(f"  {i}. {r}")

        selected = results[:num_variants]
        if len(selected) < num_variants:
            selected = results

        used_words: Set[str] = set()
        for i, result in enumerate(selected, 1):
            self._export_multi_strategy_variant(result.grid, i,
                                                result.strategy_name,
                                                result.empty_percent,
                                                result.letter_count,
                                                width, height)
            for w, _, _, _, _ in result.grid.placed_words:
                used_words.add(w.upper())
            gc.collect()

        self._save_unused_words(used_words)
        self._save_report()
        print(f"[Orchestrator] Gotowe! Wyniki w: {self.output_dir}")
        return True

    # -----------------------------------------------------------------------
    # PROGRESSIVE
    # -----------------------------------------------------------------------

    def _generate_progressive(self, width, height, num_variants, phases,
                              progress_callback=None, use_extra=False,
                              max_total_variants=100) -> bool:
        msg = f"[Orchestrator] Tryb PROGRESYWNY: {phases} faz, max_total={max_total_variants}"
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self.load_planned_words()
        multi_gen = MultiStrategyGenerator(self.word_source,
                                           planned_words=self.planned_words,
                                           user_whitelist=self._user_whitelist,
                                           gpu_matcher=self.gpu_matcher)

        def strategy_progress(strategy_name, current, total):
            m = f"  [{current}/{total}] Generuję: {strategy_name}..."
            if progress_callback:
                progress_callback(m)

        results = multi_gen.generate_all_strategies(width, height,
                                                    progress_callback=strategy_progress,
                                                    sort_by_density=use_extra)
        if not results:
            msg = "[Orchestrator] BŁĄD: Brak wyników dla fazy 1"
            self._log_error("generate_progressive_phase1", msg)
            print(msg)
            if progress_callback:
                progress_callback(msg)
            return False

        best_grid = results[0].grid
        best_strategy = results[0].strategy_name
        msg = f"[Orchestrator] Faza 1: Gotowa! Strategia: {best_strategy}"
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self._export_variant(best_grid, 1, width, height, file_prefix="faza1")
        gc.collect()

        current_grid = best_grid
        for phase_num in range(2, phases + 1):
            phase_dir_name = f"Dalsze_uzupelnianie{phase_num - 1}"
            phase_dir = os.path.join(self.output_dir, phase_dir_name)
            os.makedirs(phase_dir, exist_ok=True)

            msg = f"[Orchestrator] Faza {phase_num}: Uzupełnianie w {phase_dir_name}/"
            print(msg)
            if progress_callback:
                progress_callback(msg)

            multi_gen_phase = MultiStrategyGenerator(
                self.word_source, planned_words=self.planned_words,
                user_whitelist=self._user_whitelist,
                gpu_matcher=self.gpu_matcher)
            results_phase = multi_gen_phase.generate_all_strategies(
                width, height, progress_callback=strategy_progress, sort_by_density=True)

            if not results_phase:
                msg = f"[Orchestrator] Faza {phase_num}: Brak wyników — pomijam"
                self._log_error(f"generate_progressive_phase{phase_num}", msg)
                print(msg)
                if progress_callback:
                    progress_callback(msg)
                continue

            current_grid = results_phase[0].grid
            self._export_variant_to_directory(current_grid, phase_dir, phase_num,
                                              f"Faza {phase_num}: {results_phase[0].strategy_name}",
                                              results_phase[0].empty_percent,
                                              results_phase[0].letter_count,
                                              width, height)
            gc.collect()
            msg = f"[Orchestrator] Faza {phase_num}: Wyniki w {phase_dir_name}/"
            print(msg)
            if progress_callback:
                progress_callback(msg)

        msg = f"[Orchestrator] Wszystkie fazy gotowe! Wyniki w: {self.output_dir}"
        print(msg)
        if progress_callback:
            progress_callback(msg)

        self._save_report()
        return True

    # -----------------------------------------------------------------------
    # EXPORT
    # -----------------------------------------------------------------------

    def _export_multi_strategy_variant(self, grid: CrosswordGrid, variant_num: int,
                                       strategy_name: str, empty_percent: float,
                                       letter_count: int, width: int, height: int) -> None:
        valid, invalid_words = self._is_grid_scrabble_valid(grid)
        if not valid:
            msg = f"Wariant {variant_num}: pominięty (nieprawidłowe wyrazy: {invalid_words[:5]})"
            self._log_error("export_variant_validation", msg,
                            {"variant": variant_num, "invalid_words": invalid_words})
            print(f"  {msg}")
            return

        variant_dir = os.path.join(self.output_dir, f"variant_{variant_num}")
        os.makedirs(variant_dir, exist_ok=True)

        empty_percent_int = int(round(empty_percent))
        empty_marker = f"_{empty_percent_int:02d}_"
        letter_marker = f"_{letter_count:03d}"
        variant_prefix = f"{variant_num:03d}"

        print(f"  Wariant {variant_num}: {strategy_name} | Puste: {empty_percent:.1f}% | Litery: {letter_count}")

        word_count = len(grid.placed_words) if hasattr(grid, 'placed_words') else 0

        # Statystyki słów użytkownika
        used_user_words = [w for w, _, _, _, _ in grid.placed_words
                          if w.upper() in self._user_whitelist]
        used_other_words = [w for w, _, _, _, _ in grid.placed_words
                           if w.upper() not in self._user_whitelist]
        unused_user = self._get_unused_user_words(set(w.upper() for w in used_user_words))

        self._add_variant_info(variant_num, strategy_name, empty_percent, letter_count,
                               word_count, (width, height),
                               user_words_used=len(used_user_words),
                               unused_user_words=unused_user)

        renderer = CrosswordImageRenderer(
            cell_size=40, font_name=self.renderer_font_name,
            color_empty=self.renderer_color_empty, color_tile=self.renderer_color_tile,
            color_black=self.renderer_color_black, color_text=self.renderer_color_text,
            color_clue_num=self.renderer_color_clue_num,
        )

        # PNG → JPG 70% do tmp_preview
        img_filled = renderer.render(grid, filled=True)
        png_filled_name = f"{variant_prefix}{empty_marker}{letter_marker}_completed.png"
        png_filled_path = os.path.join(variant_dir, png_filled_name)
        img_filled.save(png_filled_path, "PNG")
        self._save_jpg_preview(img_filled, f"{variant_prefix}_completed", variant_num)
        del img_filled

        img_blank = renderer.render(grid, filled=False)
        png_blank_name = f"{variant_prefix}{empty_marker}{letter_marker}_blank.png"
        png_blank_path = os.path.join(variant_dir, png_blank_name)
        img_blank.save(png_blank_path, "PNG")
        self._save_jpg_preview(img_blank, f"{variant_prefix}_blank", variant_num)
        del img_blank

        # TXT
        txt_name = f"{variant_prefix}{empty_marker}{letter_marker}.txt"
        txt_path = os.path.join(variant_dir, txt_name)
        self._save_clues_txt(grid, txt_path, highlight_words=self._user_whitelist)

        # Dopisz do faza1.txt jeśli wariant 1
        if variant_num == 1:
            self._append_to_phase_report(txt_path, unused_user)

        # XLSX
        xlsx_name = f"krizowka{empty_marker}{letter_marker}.xlsx"
        exporter = ExcelExporter()
        exporter.export(grid, os.path.join(variant_dir, xlsx_name))

        # HTML
        html_name = f"krizowka{empty_marker}{letter_marker}.html"
        HTMLExporter.export(grid, os.path.join(variant_dir, html_name))

        # Raport wariantu JSON (rozszerzony)
        variant_report = {
            "variant_num": variant_num,
            "strategy": strategy_name,
            "empty_percent": round(empty_percent, 1),
            "letter_count": letter_count,
            "word_count": word_count,
            "grid_size": {"width": width, "height": height},
            "user_words_used": len(used_user_words),
            "user_words_list": sorted(used_user_words),
            "bin_words_used": len(used_other_words),
            "bin_words_list": sorted(used_other_words),
            "unused_user_words": unused_user,
            "unused_user_words_count": len(unused_user),
            "validation": {"valid": True, "invalid_words": []},
            "errors": [],
            "words": [
                {
                    "word": w,
                    "row": r, "col": c,
                    "direction": d.value,
                    "clue": cl,
                    "from_user_base": w.upper() in self._user_whitelist,
                }
                for w, r, c, d, cl in grid.placed_words
            ],
        }
        with open(os.path.join(variant_dir, "raport_wariantu.json"), 'w', encoding='utf-8') as f:
            json.dump(variant_report, f, ensure_ascii=False, indent=2)

        print(f"    [OK] variant_{variant_num}/ zapisany | użytkownika: {len(used_user_words)}, bin: {len(used_other_words)}")

    def _save_jpg_preview(self, img, name_prefix: str, variant_num: int):
        """Zapisz obraz jako JPG 70% do katalogu tmp_preview."""
        try:
            jpg_name = f"v{variant_num:03d}_{name_prefix}.jpg"
            jpg_path = os.path.join(self.tmp_preview_dir, jpg_name)
            # PIL JPEG wymaga RGB
            if img.mode in ('RGBA', 'P'):
                img_rgb = img.convert('RGB')
            else:
                img_rgb = img
            img_rgb.save(jpg_path, "JPEG", quality=70, optimize=True)
            print(f"    [JPG] {jpg_path}")
        except Exception as e:
            self._log_error("save_jpg_preview", str(e), {"name": name_prefix})
            print(f"    [JPG] BŁĄD: {e}")

    def _append_to_phase_report(self, txt_path: str, unused_user_words: List[str]):
        """Dopisz do pliku faza1.txt sekcję o niewykorzystanych wyrazach użytkownika."""
        try:
            faza_path = os.path.join(self.output_dir, "faza1.txt")
            lines = []
            # Jeśli plik txt istnieje, kopiuj go jako bazę
            if os.path.exists(txt_path):
                with open(txt_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()

            # Dopisz sekcję
            lines.append("\n")
            lines.append("=" * 60 + "\n")
            lines.append("WYRAZY NIEWYKORZYSTANE Z BAZY UŻYTKOWNIKA:\n")
            lines.append("=" * 60 + "\n")
            if unused_user_words:
                for w in sorted(unused_user_words):
                    lines.append(f"  • {w}\n")
                lines.append(f"\nRazem niewykorzystanych: {len(unused_user_words)}\n")
            else:
                lines.append("  (wszystkie wyrazy użytkownika zostały wykorzystane!)\n")

            lines.append(f"\nData generowania: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            lines.append(f"Backend GPU: {GPU_BACKEND}\n")

            with open(faza_path, 'a', encoding='utf-8') as f:
                f.writelines(lines)

            print(f"    [faza1.txt] Dopisano {len(unused_user_words)} niewykorzystanych wyrazów")
        except Exception as e:
            self._log_error("append_to_phase_report", str(e))
            print(f"    [faza1.txt] BŁĄD: {e}")

    def _get_unused_user_words(self, used_words_set: Set[str]) -> List[str]:
        """Zwróć listę wyrazów użytkownika które NIE zostały użyte."""
        return sorted([w for w in self._user_whitelist if w not in used_words_set])

    # -----------------------------------------------------------------------
    # DEEPSEEK API — poprawiony endpoint
    # -----------------------------------------------------------------------

    def _needs_api_clue(self, clue: str, word: str) -> bool:
        """Wyślij do DeepSeek TYLKO wyrazy bez opisu (pusty clue lub clue == word)."""
        if not clue or clue.strip() == "":
            return True
        if clue.strip().upper() == word.strip().upper():
            return True
        # Wyrazy z bazy użytkownika które MAJĄ własny opis — NIE wysyłaj
        if word.upper() in self._user_whitelist:
            user_clue = self.word_source.get_word(word) if self.word_source else None
            if user_clue and user_clue.strip() and user_clue.strip().upper() != word.upper():
                return False  # Ma własny opis — nie używaj DeepSeek
        return True

    def _generate_clue_via_api(self, word: str) -> str:
        """Generuj podpowiedź przez DeepSeek API (OpenAI-compatible endpoint)."""
        try:
            key_path = os.path.join(self.base_dir, "API_klucz", "deepseek.txt")
            if not os.path.exists(key_path):
                self._log_api_call(word, "NO_KEY_FILE")
                return ""

            with open(key_path, 'r', encoding='utf-8') as kf:
                api_key = kf.read().strip()
            if not api_key:
                self._log_api_call(word, "EMPTY_KEY")
                return ""

            word_key = word.strip().upper()

            # Cache
            if not self._api_cache_loaded:
                try:
                    if os.path.exists(self._api_cache_path):
                        with open(self._api_cache_path, 'r', encoding='utf-8') as cf:
                            self._api_cache = json.load(cf)
                except Exception:
                    self._api_cache = {}
                self._api_cache_loaded = True

            if word_key in self._api_cache:
                self._log_api_call(word, "CACHED", result=self._api_cache[word_key])
                return self._api_cache[word_key]

            if self._api_dry_run:
                self._log_api_call(word, "DRY_RUN_SKIP")
                return ""

            # Poprawny endpoint OpenAI-compatible DeepSeek
            endpoint = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            # Dowcipna podpowiedź krzyżówkowa
            prompt = (
                f"Jesteś autorem krzyżówek z poczuciem humoru. "
                f"Napisz jedną krótką, dowcipną podpowiedź krzyżówkową do słowa '{word}' po polsku. "
                f"Podpowiedź ma nakierowywać na odpowiedź ale nie podawać jej wprost. "
                f"Może być żartobliwa lub ironiczna. Tylko jedno zdanie, bez cudzysłowów."
            )
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 80,
                "temperature": 0.8,
            }

            max_retries = 3
            resp_data = None
            last_error = None

            for attempt in range(max_retries):
                try:
                    self._log_api_call(word, f"ATTEMPT_{attempt+1}")
                    resp = requests.post(endpoint, json=payload, headers=headers, timeout=10)
                    if resp.status_code == 200:
                        resp_data = resp.json()
                        break
                    else:
                        last_error = f"HTTP_{resp.status_code}"
                        self._log_api_call(word, f"HTTP_ERROR_{resp.status_code}")
                        time.sleep(0.5 * (2 ** attempt))
                except requests.RequestException as e:
                    last_error = str(e)
                    self._log_api_call(word, "REQUEST_ERROR", error=str(e))
                    time.sleep(0.5 * (2 ** attempt))

            if not resp_data:
                self._log_api_call(word, "NO_RESPONSE", error=last_error or "Unknown")
                return ""

            text = ""
            if isinstance(resp_data, dict) and "choices" in resp_data:
                choices = resp_data["choices"]
                if choices and isinstance(choices, list):
                    msg_obj = choices[0].get("message", {})
                    text = msg_obj.get("content", "").strip()

            if text:
                self._api_cache[word_key] = text
                try:
                    with open(self._api_cache_path, 'w', encoding='utf-8') as cf:
                        json.dump(self._api_cache, cf, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                self._log_api_call(word, "SUCCESS", result=text)
            else:
                self._log_api_call(word, "NO_TEXT_IN_RESPONSE")

            return text
        except Exception as e:
            self._log_error("generate_clue_via_api", str(e), {"word": word})
            self._log_api_call(word, "EXCEPTION", error=str(e))
            return ""

    # -----------------------------------------------------------------------
    # CLUES TXT
    # -----------------------------------------------------------------------

    def _save_clues_txt(self, grid: CrosswordGrid, filepath: str,
                        highlight_words: Optional[Set[str]] = None) -> None:
        try:
            h_clues, v_clues = grid.get_clues_list()

            h_clues_unique = {}
            for num, clue, word in h_clues:
                if num not in h_clues_unique:
                    h_clues_unique[num] = (clue, word)

            v_clues_unique = {}
            for num, clue, word in v_clues:
                if num not in v_clues_unique:
                    v_clues_unique[num] = (clue, word)

            lines = ["KRZYŻÓWKA - PYTANIA", "=" * 60, "", "POZIOMO:", "-" * 60]
            highlight = highlight_words or set()
            used_words = set()

            for num in sorted(h_clues_unique.keys()):
                clue, word = h_clues_unique[num]
                used_words.add(word.upper())

                # Wyrazy użytkownika z własnym opisem — zachowaj opis bez zmian
                if word.upper() in self._user_whitelist and self.word_source:
                    user_clue = self.word_source.get_word(word)
                    if user_clue and user_clue.strip() and user_clue.strip().upper() != word.upper():
                        clue = user_clue  # Zawsze użyj opisu użytkownika
                    elif self._needs_api_clue(clue, word) and self.use_api_enabled:
                        try:
                            generated = self._generate_clue_via_api(word)
                            if generated:
                                clue = generated
                        except Exception:
                            pass
                elif self._needs_api_clue(clue, word) and self.use_api_enabled:
                    try:
                        generated = self._generate_clue_via_api(word)
                        if generated:
                            clue = generated
                    except Exception:
                        pass

                if self._needs_api_clue(clue, word):
                    clue = word

                marker = "*" if word.upper() in highlight else ""
                lines.append(f"{num:2d}. {marker}{clue}{marker} ({len(word)} liter)")

            lines.extend(["", "PIONOWO:", "-" * 60])

            if v_clues_unique:
                for num in sorted(v_clues_unique.keys()):
                    clue, word = v_clues_unique[num]
                    used_words.add(word.upper())

                    if word.upper() in self._user_whitelist and self.word_source:
                        user_clue = self.word_source.get_word(word)
                        if user_clue and user_clue.strip() and user_clue.strip().upper() != word.upper():
                            clue = user_clue
                        elif self._needs_api_clue(clue, word) and self.use_api_enabled:
                            try:
                                generated = self._generate_clue_via_api(word)
                                if generated:
                                    clue = generated
                            except Exception:
                                pass
                    elif self._needs_api_clue(clue, word) and self.use_api_enabled:
                        try:
                            generated = self._generate_clue_via_api(word)
                            if generated:
                                clue = generated
                        except Exception:
                            pass

                    if self._needs_api_clue(clue, word):
                        clue = word

                    marker = "*" if word.upper() in highlight else ""
                    lines.append(f"{num:2d}. {marker}{clue}{marker} ({len(word)} liter)")
            else:
                lines.append("(brak)")

            lines.extend(["", "=" * 60, "WYRAZY UŻYTE W KRZYŻÓWCE (alfabetycznie):", "=" * 60])
            for word in sorted(used_words):
                source_tag = "[U]" if word in self._user_whitelist else "[B]"
                lines.append(f"  {source_tag} {word}")

            lines.extend(["", "LEGENDA: [U]=baza użytkownika, [B]=baza binarna (.bin)"])

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("\n".join(lines))
        except Exception as e:
            self._log_error("save_clues_txt", str(e))
            print(f"[Orchestrator] BŁĄD zapisu TXT: {e}")

    # -----------------------------------------------------------------------
    # EXPORT HELPERS (stare sygnatury — zachowane dla kompatybilności)
    # -----------------------------------------------------------------------

    def _export_variant(self, grid, variant_num, width, height, file_prefix=None) -> None:
        valid, invalid_words = self._is_grid_scrabble_valid(grid)
        if not valid:
            self._log_error("export_variant", f"Nieprawidłowe wyrazy: {invalid_words}",
                            {"variant": variant_num})
            print(f"  Eksport pominięty dla wariantu {variant_num}: {invalid_words}")
            return

        total_cells = width * height
        empty_cells = sum(1 for row in grid.grid for cell in row if cell is None)
        empty_percent = (empty_cells / total_cells * 100) if total_cells > 0 else 0
        letter_count = sum(1 for row in grid.grid for cell in row if cell and cell != "")
        word_count = len(grid.placed_words) if hasattr(grid, 'placed_words') else 0
        strategy_name = file_prefix if file_prefix else f"Variant {variant_num}"
        unused_user = self._get_unused_user_words(
            set(w.upper() for w, _, _, _, _ in grid.placed_words))
        self._add_variant_info(variant_num, strategy_name, empty_percent, letter_count,
                               word_count, (width, height), unused_user_words=unused_user)

        variant_prefix = file_prefix if file_prefix else f"{variant_num:03d}"

        renderer = CrosswordImageRenderer(cell_size=40, font_name=self.renderer_font_name,
                                          color_empty=self.renderer_color_empty,
                                          color_tile=self.renderer_color_tile,
                                          color_black=self.renderer_color_black,
                                          color_text=self.renderer_color_text,
                                          color_clue_num=self.renderer_color_clue_num)

        img_filled = renderer.render(grid, filled=True)
        png_filled_path = os.path.join(self.output_dir, f"{variant_prefix}_completed.png")
        img_filled.save(png_filled_path, "PNG")
        self._save_jpg_preview(img_filled, f"{variant_prefix}_completed", variant_num)
        del img_filled

        img_blank = renderer.render(grid, filled=False)
        png_blank_path = os.path.join(self.output_dir, f"{variant_prefix}_blank.png")
        img_blank.save(png_blank_path, "PNG")
        self._save_jpg_preview(img_blank, f"{variant_prefix}_blank", variant_num)
        del img_blank

        txt_path = os.path.join(self.output_dir, f"{variant_prefix}.txt")
        self._save_clues_txt(grid, txt_path, highlight_words=self._user_whitelist)
        self._append_to_phase_report(txt_path, unused_user)

        if variant_num == 1:
            xlsx_path = os.path.join(self.output_dir,
                                     f"krizowka_{variant_prefix}.xlsx" if file_prefix else "krizowka.xlsx")
            ExcelExporter().export(grid, xlsx_path)
            html_path = os.path.join(self.output_dir,
                                     f"krizowka_{variant_prefix}.html" if file_prefix else "krizowka.html")
            HTMLExporter.export(grid, html_path)

    def _export_variant_to_directory(self, grid, target_dir, variant_num,
                                     strategy_name, empty_percent, letter_count,
                                     width, height) -> None:
        valid, invalid_words = self._is_grid_scrabble_valid(grid)
        if not valid:
            self._log_error("export_to_dir", f"Nieprawidłowe wyrazy: {invalid_words}",
                            {"variant": variant_num, "dir": target_dir})
            print(f"  [{target_dir}] Eksport pominięty: {invalid_words}")
            return

        variant_prefix = f"{variant_num:03d}"
        renderer = CrosswordImageRenderer(cell_size=40, font_name=self.renderer_font_name,
                                          color_empty=self.renderer_color_empty,
                                          color_tile=self.renderer_color_tile,
                                          color_black=self.renderer_color_black,
                                          color_text=self.renderer_color_text,
                                          color_clue_num=self.renderer_color_clue_num)

        img_filled = renderer.render(grid, filled=True)
        png_filled_path = os.path.join(target_dir, f"{variant_prefix}_completed.png")
        img_filled.save(png_filled_path, "PNG")
        self._save_jpg_preview(img_filled, f"phase{variant_num}_completed", variant_num)
        del img_filled

        img_blank = renderer.render(grid, filled=False)
        png_blank_path = os.path.join(target_dir, f"{variant_prefix}_blank.png")
        img_blank.save(png_blank_path, "PNG")
        self._save_jpg_preview(img_blank, f"phase{variant_num}_blank", variant_num)
        del img_blank

        txt_path = os.path.join(target_dir, f"{variant_prefix}.txt")
        self._save_clues_txt(grid, txt_path, highlight_words=self._user_whitelist)

        unused_user = self._get_unused_user_words(
            set(w.upper() for w, _, _, _, _ in grid.placed_words))
        self._append_to_phase_report(txt_path, unused_user)

        if variant_num == 1:
            ExcelExporter().export(grid, os.path.join(target_dir, "krizowka.xlsx"))
            HTMLExporter.export(grid, os.path.join(target_dir, "krizowka.html"))

        print(f"  [{target_dir}] Gotowe!")

    # -----------------------------------------------------------------------
    # VALIDATION
    # -----------------------------------------------------------------------

    def _is_word_valid(self, word: str) -> bool:
        w = word.strip().upper()
        if not w or len(w) < 2:
            return False
        # Biała lista użytkownika — zawsze dozwolone
        if w in self._user_whitelist:
            return True
        # Binarna baza
        if self.bin_source and self.bin_source.loaded:
            words_of_len = self.bin_source.get_words_by_length(len(w))
            if w in (wrd.upper() for wrd in words_of_len):
                return True
        return False

    def _is_grid_scrabble_valid(self, grid: CrosswordGrid) -> tuple:
        words = self._get_final_words(grid)
        invalid = [w for w in words if not self._is_word_valid(w)]
        return (len(invalid) == 0, invalid)

    def _get_final_words(self, grid: CrosswordGrid) -> List[str]:
        try:
            placed = getattr(grid, 'placed_words', None)
            if placed and isinstance(placed, list):
                return [w.upper() for w, _, _, _, _ in placed if w and len(w) >= 2]
        except Exception:
            pass
        words = []
        for r in range(grid.height):
            c = 0
            while c < grid.width:
                if grid.grid[r][c] is None:
                    c += 1
                    continue
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

    def _save_unused_words(self, used_words: Set[str]) -> None:
        if not self.output_dir or not self.word_source:
            return
        source_words = [w.upper() for w in self.word_source.get_all_words()]
        unused = [w for w in source_words if w not in used_words]
        path = os.path.join(self.output_dir, "niewykorzystane_słowa.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f"# Niewykorzystane wyrazy z bazy użytkownika: {len(unused)}\n")
            f.write(f"# Łącznie w bazie: {len(source_words)}\n")
            f.write(f"# Data: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for word in unused:
                f.write(word + "\n")
        print(f"[Orchestrator] Niewykorzystane słowa ({len(unused)}): {path}")

    def _log_api_call(self, word: str, status: str, result: str = "", error: str = "") -> None:
        if not self._api_log_path:
            return
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] WORD: {word} | STATUS: {status}"
            if result:
                log_line += f" | RESULT: {result}"
            if error:
                log_line += f" | ERROR: {error}"
            with open(self._api_log_path, 'a', encoding='utf-8') as f:
                f.write(log_line + "\n")
        except Exception:
            pass

    def _has_good_intersections(self, grid: CrosswordGrid) -> bool:
        """
        Sprawdź czy siatka ma wystarczającą liczbę skrzyżowań między słowami.
        
        Ulepszona wersja: liczy faktyczne przecięcia słów (litera wspólna dla dwóch słów
        w różnych kierunkach), nie tylko sąsiedztwo komórek.
        Wymaga, żeby co najmniej 70% słów miało minimum 1 prawdziwe przecięcie.
        """
        if not hasattr(grid, 'placed_words') or not grid.placed_words:
            return True

        # Zbuduj mapę: (row, col) -> lista słów przechodzących przez tę komórkę
        cell_to_words: Dict[Tuple[int, int], List[int]] = {}
        for idx, (word, row, col, direction, _) in enumerate(grid.placed_words):
            if direction == Direction.HORIZONTAL:
                for i in range(len(word)):
                    pos = (row, col + i)
                    cell_to_words.setdefault(pos, []).append(idx)
            else:
                for i in range(len(word)):
                    pos = (row + i, col)
                    cell_to_words.setdefault(pos, []).append(idx)

        # Dla każdego słowa sprawdź czy ma co najmniej 1 wspólną komórkę z innym słowem
        # o INNYM kierunku (prawdziwe skrzyżowanie)
        intersecting_count = 0
        for idx, (word, row, col, direction, _) in enumerate(grid.placed_words):
            has_true_intersection = False
            if direction == Direction.HORIZONTAL:
                for i in range(len(word)):
                    pos = (row, col + i)
                    for other_idx in cell_to_words.get(pos, []):
                        if other_idx != idx:
                            other_dir = grid.placed_words[other_idx][3]
                            if other_dir == Direction.VERTICAL:
                                has_true_intersection = True
                                break
                    if has_true_intersection:
                        break
            else:
                for i in range(len(word)):
                    pos = (row + i, col)
                    for other_idx in cell_to_words.get(pos, []):
                        if other_idx != idx:
                            other_dir = grid.placed_words[other_idx][3]
                            if other_dir == Direction.HORIZONTAL:
                                has_true_intersection = True
                                break
                    if has_true_intersection:
                        break
            if has_true_intersection:
                intersecting_count += 1

        total_words = len(grid.placed_words)
        # Wymagaj min. 70% słów z prawdziwymi skrzyżowaniami
        return (intersecting_count / total_words >= 0.7) if total_words > 0 else True

    def _has_duplicate_words(self, grid: CrosswordGrid) -> bool:
        if not hasattr(grid, 'placed_words') or not grid.placed_words:
            return False
        words_used = [w.upper() for w, _, _, _, _ in grid.placed_words]
        return len(set(words_used)) < len(words_used)
