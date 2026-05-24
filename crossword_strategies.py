# -*- coding: utf-8 -*-
"""
crossword_strategies.py — Wielostrategiczny generator krzyżówek

Implementuje różne podejścia do umieszczania wyrazów:
1. CENTERED     - Wyraz środek w środku, pionowo go przecinają
2. TOP_LEFT     - Wyraz startowy w górnym lewym rogu
3. TOP_CENTER   - Wyraz startowy na górze pośrodku
4. SPIRAL       - Łączy wyrazy w spiralę od środka
5. RANDOM       - Losowe pozycje startowe
6. DENSE        - Maksymalizuje gęstość (backtracking agresywny)
7. EDGE_FIRST   - NOWA: najdłuższe wyrazy od krawędzi, krzyżowanie ku środkowi,
                  maksymalne zagęszczenie siatki (minimalizacja pustych pól)

Każda strategia próbuje umieścić wyrazy przestrzegając reguł Scrabble:
- Wyrazy muszą się przecinać
- Wszystkie przecięcia muszą tworzyć poprawne słowa
- Brak pustych pól w samym tekście (mogą być na brzegach)

Cel EDGE_FIRST:
  „Strategia minimalizacji pustych pól i maksymalizacji przeplotu haseł."
  - najdłuższe wyrazy trafiają na górne krawędzie i boki,
  - do nich krzyżowane są pozostałe od najdłuższych,
  - wolne pola wypełniane są resztą słów z bazy,
  - każde pole powinno być sprawdzane w dwóch kierunkach,
  - siatka zwarta, bez długich pustych fragmentów.
"""

import random
from typing import List, Tuple, Optional, Dict, Set, Any
from enum import Enum
from word_source import WordSource
from crossword_grid import CrosswordGrid, Direction


class StartingStrategy(Enum):
    """Strategia umieszczenia wyrazu startowego."""
    CENTERED = "centered"
    TOP_LEFT = "top_left"
    TOP_CENTER = "top_center"
    MIDDLE_LEFT = "middle_left"
    RANDOM = "random"
    EDGE_FIRST = "edge_first"  # NOWA


class StrategyConfig:
    """Konfiguracja dla konkretnej strategii."""

    def __init__(
        self,
        name: str,
        starting_strategy: StartingStrategy,
        max_iterations: int = 100,
        backtrack_depth: int = 25,
        aggressive_fill: bool = False,
        maximize_intersections: bool = True,
        edge_first: bool = False,  # NOWE: strategia od brzegów
    ):
        self.name = name
        self.starting_strategy = starting_strategy
        self.max_iterations = max_iterations
        self.backtrack_depth = backtrack_depth
        self.aggressive_fill = aggressive_fill
        self.maximize_intersections = maximize_intersections
        self.edge_first = edge_first


class StrategyResult:
    """Wynik generowania jedną strategią."""

    def __init__(
        self,
        grid: CrosswordGrid,
        strategy_name: str,
        density: float,
        word_count: int,
        filled_cells: int,
        total_cells: int,
        letter_count: int
    ):
        self.grid = grid
        self.strategy_name = strategy_name
        self.density = density
        self.word_count = word_count
        self.filled_cells = filled_cells
        self.total_cells = total_cells
        self.letter_count = letter_count

        self.empty_percent = round(100 * (total_cells - filled_cells) / total_cells, 1)

    def __repr__(self):
        return (
            f"Strategy: {self.strategy_name} | "
            f"Density: {self.density:.1%} | "
            f"Words: {self.word_count} | "
            f"Empty: {self.empty_percent}% | "
            f"Letters: {self.letter_count}"
        )


class MultiStrategyGenerator:
    """
    Generator krzyżówek używający wielu strategii.

    Każda strategia generuje własną krzyżówkę,
    a następnie zostaje wybrana najlepsza.

    Obsługuje planowane wyrazy (constraint-based generation).
    """

    def __init__(
        self,
        word_source: WordSource,
        planned_words: Optional[List[str]] = None,
        user_whitelist=None,
        gpu_matcher=None,
        edge_first_mode: bool = False,  # NOWE: tryb od brzegów
        edge_first_variants: int = 3,  # NOWE: ile wariantów EDGE_FIRST
    ):
        self.word_source = word_source
        self.planned_words = (
            set(w.upper() for w in planned_words) if planned_words else set()
        )
        self.user_whitelist = user_whitelist or set()
        self.gpu_matcher = gpu_matcher
        self.edge_first_mode = edge_first_mode
        self.edge_first_variants = max(1, edge_first_variants)
        self.strategies = self._create_strategies()

    def _create_strategies(self) -> List[StrategyConfig]:
        """
        Utwórz listę strategii do próby.

        ZMIANA: EDGE_FIRST jest teraz ZAWSZE włączony i ma PRIORYTET (pierwsze miejsca).
        To strategia z największym potencjałem do minimalizacji pustych pól.
        """
        base = [
            # NOWE: EDGE_FIRST — priorytet dla maksymalnego zagęszczenia
            # Warianty (2 różne semi-random pozycje startowe)
        ]

        # Zawsze dodaj EDGE_FIRST warianty (min 2)
        num_edge_first = max(2, self.edge_first_variants)
        for i in range(1, num_edge_first + 1):
            base.append(
                StrategyConfig(
                    f"{i}. EDGE_FIRST v{i} (od brzegów, zagęszczenie)",
                    StartingStrategy.EDGE_FIRST,
                    max_iterations=150,
                    backtrack_depth=450,  # zwiększone dla lepszego wype\u0142nienia
                    aggressive_fill=True,
                    maximize_intersections=True,
                    edge_first=True,
                )
            )

        # Pozostałe strategie (jako backup)
        base.extend(
            [
                StrategyConfig(
                    f"{num_edge_first + 1}. CENTERED (wyrazy od środka)",
                    StartingStrategy.CENTERED,
                    max_iterations=100,
                    backtrack_depth=250,  # zwiększone z 200
                    aggressive_fill=True,
                ),
                StrategyConfig(
                    f"{num_edge_first + 2}. TOP_LEFT (z górnego lewego rogu)",
                    StartingStrategy.TOP_LEFT,
                    max_iterations=100,
                    backtrack_depth=250,  # zwiększone z 180
                    aggressive_fill=True,
                ),
                StrategyConfig(
                    f"{num_edge_first + 3}. TOP_CENTER (top środek)",
                    StartingStrategy.TOP_CENTER,
                    max_iterations=100,
                    backtrack_depth=250,  # zwiększone z 180
                    aggressive_fill=True,
                ),
                StrategyConfig(
                    f"{num_edge_first + 4}. MIDDLE_LEFT (środek lewa krawędź)",
                    StartingStrategy.MIDDLE_LEFT,
                    max_iterations=100,
                    backtrack_depth=250,  # zwiększone z 180
                    aggressive_fill=True,
                ),
                StrategyConfig(
                    f"{num_edge_first + 5}. RANDOM (losowe umieszczenie)",
                    StartingStrategy.RANDOM,
                    max_iterations=100,
                    backtrack_depth=250,  # zwiększone z 180
                    aggressive_fill=True,
                ),
            ]
        )

        return base

    def generate_all_strategies(
        self,
        width: int,
        height: int,
        progress_callback=None,
        sort_by_density: bool = True
    ) -> List[StrategyResult]:
        """
        Wygeneruj krzyżówki używając wszystkich strategii.

        Returns:
            Lista StrategyResult posortowana po gęstości (jeśli sort_by_density=True)
        """
        results = []
        total = len(self.strategies)

        for i, strategy_config in enumerate(self.strategies):
            if progress_callback:
                progress_callback(strategy_config.name, i + 1, total)

            generator = StrategyBasedGenerator(
                self.word_source,
                strategy_config,
                planned_words=self.planned_words,
                user_whitelist=self.user_whitelist,
                gpu_matcher=self.gpu_matcher,
            )
            grid = generator.generate(width, height)

            filled = grid.get_filled_count()
            total_cells = width * height
            density = grid.get_density()
            word_count = len(grid.placed_words)
            letter_count = sum(
                1 for r in grid.grid for cell in r
                if cell and cell not in ["", None]
            )

            result = StrategyResult(
                grid=grid,
                strategy_name=strategy_config.name,
                density=density,
                word_count=word_count,
                filled_cells=filled,
                total_cells=total_cells,
                letter_count=letter_count
            )
            results.append(result)

        if sort_by_density:
            results.sort(key=lambda r: r.density, reverse=True)

        return results


class StrategyBasedGenerator:
    """
    Generator używający konkretnej strategii umieszczania wyrazów.
    """

    def __init__(
        self,
        word_source: WordSource,
        config: StrategyConfig,
        planned_words: Optional[Set[str]] = None,
        user_whitelist=None,
        gpu_matcher=None,
    ):
        self.word_source = word_source
        self.config = config
        self.planned_words = planned_words or set()
        self.user_whitelist = user_whitelist or set()
        self.gpu_matcher = gpu_matcher
        self.best_grid = None
        self.best_density = 0.0

    def generate(self, width: int, height: int) -> CrosswordGrid:
        """
        Wygeneruj krzyżówkę używając konfigurowanej strategii.

        Jeśli to EDGE_FIRST — użyj dedykowanego generatora od brzegów.
        W pozostałych przypadkach — standardowy backtracking.

        KRYTYCZNE: Po wszystkich strategiach, gwarantuj że wszystkie planowe słowa
        użytkownika pojawiają się w ostatecznej siatce.
        """
        if self.config.edge_first:
            return self._generate_edge_first(width, height)

        self.best_grid = None
        self.best_density = 0.0
        self.best_user_word_count = 0

        for attempt in range(self.config.max_iterations):
            grid = CrosswordGrid(width, height)

            if not self._place_seed(grid):
                continue

            self._backtrack(grid, depth=0)

            # NOWE (Priority 2): Spróbuj połączyć izolowane grupy białych pól
            self._force_connectivity(grid, depth=0, max_depth=5)

            self._mark_empty_cells_black(grid)

            density = grid.get_density()
            user_words = (
                sum(
                    1
                    for w, _, _, _, _ in grid.placed_words
                    if w.upper() in self.planned_words
                )
                if self.planned_words
                else len(grid.placed_words)
            )

            is_better = user_words > self.best_user_word_count or (
                user_words == self.best_user_word_count and density > self.best_density
            )
            if is_better:
                self.best_density = density
                self.best_user_word_count = user_words
                self.best_grid = grid.copy()

        result = self.best_grid or CrosswordGrid(width, height)

        # KRYTYCZNE: Gwarantuj user words w ostatecznym wyniku
        self._force_planned_words_in_grid(result)

        return result

    # -----------------------------------------------------------------------
    # EDGE_FIRST — strategia od brzegów
    # -----------------------------------------------------------------------

    def _generate_edge_first(self, width: int, height: int) -> CrosswordGrid:
        """
        Strategia EDGE_FIRST — maksymalne zagęszczenie siatki.

        Algorytm:
        1. Posortuj wyrazy od najdłuższych.
        2. Umieść najdłuższe wyrazy wzdłuż górnej krawędzi (poziomo, wiersz 0)
           i lewej krawędzi (pionowo, kolumna 0).
        3. Do każdego brzegowego wyrazu krzyżuj kolejne wyrazy pionowo/poziomo
           — priorytet dla najdłuższych, które mają przecięcia.
        4. Po zapełnieniu brzegów wykonaj agresywny backtracking wypełniający
           wnętrze siatki — każde wolne pole powinno być zagospodarowane.
        5. Zamieniaj puste pola na czarne TYLKO gdy nie można ich już
           zagospodarować — minimalizacja czarnych pól.

        Cel: siatka zwarta, gęsta, dużo przeplotu, mało pustych pól.

        KRYTYCZNE: Po wszystkim gwarantuj że wszystkie planowe słowa użytkownika
        pojawiają się w ostatecznej siatce.
        """
        self.best_grid = None
        self.best_density = 0.0
        self.best_user_word_count = 0

        for attempt in range(self.config.max_iterations):
            grid = CrosswordGrid(width, height)

            # Krok 1: Przygotuj listę wyrazów posortowanych od najdłuższych
            all_words = self._get_sorted_words_for_edge()

            if not all_words:
                continue

            placed_set: Set[str] = set()

            # Krok 2: Umieszczaj najdłuższe wyrazy na górnej krawędzi (H) i lewej (V)
            self._place_edge_words(grid, all_words, placed_set, width, height)

            # Krok 3: Agresywne wypełnianie wnętrza — backtracking od każdego wolnego pola
            self._aggressive_density_fill(
                grid, placed_set, depth=0, max_depth=self.config.backtrack_depth
            )

            # NOWE (Priority 2): Spróbuj połączyć izolowane grupy białych pól
            self._force_connectivity(grid, depth=0, max_depth=5)

            # Krok 4: Zaznacz naprawdę niedostępne pola na czarno
            self._mark_empty_cells_black_aggressive(grid)

            density = grid.get_density()
            user_words_count = sum(
                1
                for w, _, _, _, _ in grid.placed_words
                if w.upper() in (self.planned_words | self.user_whitelist)
            )

            is_better = user_words_count > self.best_user_word_count or (
                user_words_count == self.best_user_word_count
                and density > self.best_density
            )
            if is_better:
                self.best_density = density
                self.best_user_word_count = user_words_count
                self.best_grid = grid.copy()

        result = self.best_grid or CrosswordGrid(width, height)

        # KRYTYCZNE: Gwarantuj user words w ostatecznym wyniku
        self._force_planned_words_in_grid(result)

        return result

    def _get_sorted_words_for_edge(self) -> List[str]:
        """
        Zwróć wyrazy posortowane od najdłuższych.
        Priorytet: wyrazy użytkownika, potem binarne.
        """
        all_words = self.word_source.get_all_words()

        # Wyrazy użytkownika — priorytet
        user_words = sorted(
            [
                w
                for w in all_words
                if w.upper() in (self.planned_words | self.user_whitelist)
            ],
            key=len,
            reverse=True,
        )
        other_words = sorted(
            [
                w
                for w in all_words
                if w.upper() not in (self.planned_words | self.user_whitelist)
            ],
            key=len,
            reverse=True,
        )
        return user_words + other_words

    def _place_edge_words(
        self,
        grid: CrosswordGrid,
        all_words: List[str],
        placed_set: Set[str],
        width: int,
        height: int,
    ) -> None:
        """
        Umieść najdłuższe wyrazy na krawędziach siatki.

        ZMIANA: Bez separatorów (+1) — wyrazy mogą być tylko przedzielone
        przez przecinające się słowa. To maksymalizuje wykorzystanie krawędzi.
        """
        valid_words_set = self._build_valid_words_set()
        remaining = [w for w in all_words if w.upper() not in placed_set]

        # --- Górna krawędź (wiersz 0): poziomo ---
        col = 0
        for word in list(remaining):
            if col >= width:
                break
            max_len = width - col
            if len(word) > max_len or len(word) < 2:
                continue
            clue = self.word_source.get_word(word) or f"({len(word)} liter)"
            if grid.place_word(word, 0, col, Direction.HORIZONTAL, clue):
                placed_set.add(word.upper())
                remaining = [w for w in remaining if w.upper() not in placed_set]
                col += len(word)  # ZMIANA: bez +1 separatora

        # --- Lewa krawędź (kolumna 0): pionowo ---
        row = 0
        for word in list(remaining):
            if row >= height:
                break
            max_len = height - row
            if len(word) > max_len or len(word) < 2:
                continue
            clue = self.word_source.get_word(word) or f"({len(word)} liter)"
            if grid.place_word(word, row, 0, Direction.VERTICAL, clue):
                placed_set.add(word.upper())
                remaining = [w for w in remaining if w.upper() not in placed_set]
                row += len(word)  # ZMIANA: bez +1 separatora

        # --- Prawa krawędź (kolumna width-1): pionowo ---
        row = 0
        right_col = width - 1
        for word in list(remaining):
            if row >= height:
                break
            max_len = height - row
            if len(word) > max_len or len(word) < 2:
                continue
            clue = self.word_source.get_word(word) or f"({len(word)} liter)"
            if grid.place_word(word, row, right_col, Direction.VERTICAL, clue):
                placed_set.add(word.upper())
                remaining = [w for w in remaining if w.upper() not in placed_set]
                row += len(word)  # ZMIANA: bez +1 separatora

        # --- Dolna krawędź (wiersz height-1): poziomo ---
        col = 0
        bottom_row = height - 1
        for word in list(remaining):
            if col >= width:
                break
            max_len = width - col
            if len(word) > max_len or len(word) < 2:
                continue
            clue = self.word_source.get_word(word) or f"({len(word)} liter)"
            if grid.place_word(word, bottom_row, col, Direction.HORIZONTAL, clue):
                placed_set.add(word.upper())
                remaining = [w for w in remaining if w.upper() not in placed_set]
                col += len(word)  # ZMIANA: bez +1 separatora

    def _aggressive_density_fill(
        self,
        grid: CrosswordGrid,
        placed_set: Set[str],
        depth: int,
        max_depth: int,
    ) -> int:
        """
        Agresywne wypełnianie wnętrza siatki - NOWA LOGIKA

        ZMIANA: Teraz dla KAŻDEJ komórki próbuje umieścić wyrazy zarówno
        POZIOMO JAK I PIONOWO (maksymalny przeplot). Nie przerywa po pierwszym sukcesie.

        Priorytet: komórki z literami w sąsiedztwie (duże _proximity_score).
        Cel: każde pole sprawdzane w obu kierunkach (maksymalny przeplat).

        Returns:
            Liczba nowo umieszczonych wyrazów.
        """
        if depth >= max_depth:
            return 0

        valid_words_set = self._build_valid_words_set()

        # Pobierz wszystkie puste komórki, posortowane wg bliskości liter
        empty_cells = grid.get_empty_cells()
        if not empty_cells:
            return 0

        # Sortuj: najpierw komórki z największym sąsiedztwem liter
        empty_cells.sort(key=lambda pos: self._proximity_score(grid, pos), reverse=True)

        # ZMIANA: zwiększyć limit - sprawdzaj więcej komórek dla lepszego wypełnienia
        check_limit = min(len(empty_cells), 200)  # zwiększone z 80 na 200
        placed_count = 0

        for row, col in empty_cells[:check_limit]:
            # Jeśli ta komórka została już wypełniona, pomiń
            if grid.grid[row][col] != "":
                continue

            # Zbierz kandydatów w OBU kierunkach
            h_words = self._find_matching_words_density(
                grid, row, col, Direction.HORIZONTAL, valid_words_set
            )
            v_words = self._find_matching_words_density(
                grid, row, col, Direction.VERTICAL, valid_words_set
            )

            h_limit = 25 if self.config.aggressive_fill else 12
            v_limit = 25 if self.config.aggressive_fill else 12

            # ZMIANA: spróbuj OBYDWA kierunki niezależnie (nie break na H)
            for word in h_words[:h_limit]:
                if word.upper() in placed_set:
                    continue
                clue = self.word_source.get_word(word) or f"({len(word)} liter)"
                if grid.place_word(
                    word, row, col, Direction.HORIZONTAL, clue, self.word_source
                ):
                    placed_set.add(word.upper())
                    placed_count += 1
                    break  # wystarczy jeden wyraz poziomo

            # ZAWSZE spróbuj pionowo, niezależnie od wyniku poziomego
            # (ale tylko jeśli pole nadal jest puste)
            if grid.grid[row][col] == "":
                for word in v_words[:v_limit]:
                    if word.upper() in placed_set:
                        continue
                    clue = self.word_source.get_word(word) or f"({len(word)} liter)"
                    if grid.place_word(
                        word, row, col, Direction.VERTICAL, clue, self.word_source
                    ):
                        placed_set.add(word.upper())
                        placed_count += 1
                        break  # wystarczy jeden wyraz pionowo

        # Rekurencja — kontynuuj wypełnianie jeśli coś nowego zostało dodane
        if placed_count > 0:
            placed_count += self._aggressive_density_fill(
                grid, placed_set, depth + 1, max_depth
            )

        return placed_count

    def _find_matching_words_density(
        self,
        grid: CrosswordGrid,
        row: int,
        col: int,
        direction: Direction,
        valid_words_set: Set[str],
    ) -> List[str]:
        """
        Znajdź kandydatów do umieszczenia (tryb EDGE_FIRST / density).

        NAPRAWA: Ujednolicony scoring z _find_matching_words — używa
        _word_density_score (faktyczny przyrost gęstości), obniżony user_bonus.
        """
        max_len = (
            grid.width - col if direction == Direction.HORIZONTAL else grid.height - row
        )

        word_usage_count: Dict[str, int] = {}
        for w, _, _, _, _ in grid.placed_words:
            wu = w.upper()
            word_usage_count[wu] = word_usage_count.get(wu, 0) + 1

        all_words = self.word_source.get_all_words()
        available = [w for w in all_words if word_usage_count.get(w.upper(), 0) == 0]

        candidates = []
        for word in available:
            if len(word) < 2 or len(word) > max_len:
                continue
            if not grid.can_place_word(word, row, col, direction, valid_words_set):
                continue

            # Globalny scoring gęstości (spójny z _find_matching_words)
            score = self._word_density_score(grid, word, row, col, direction)

            wu = word.upper()
            if wu in (self.planned_words | self.user_whitelist):
                score += (
                    300  # obniżone z 2000 — priorytet tak, ale nie kosztem gęstości
                )

            candidates.append((word, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [w for w, _ in candidates]

    def _mark_empty_cells_black_aggressive(self, grid: CrosswordGrid) -> None:
        """
        Zaznacz puste pola na czarno TYLKO gdy absolutnie nie mogą być częścią wyrazu.

        Bardziej zachowawcze niż _mark_empty_cells_black — próbuje zachować
        jak najwięcej wolnych pól, aby siatka pozostała gęsta.
        Pole staje się czarne tylko gdy:
        - nie ma żadnego sąsiada z literą (ani poziomo, ani pionowo),
        - i nie jest otoczone przez pola z literami z żadnej strony.
        """
        changed = True
        iterations = 0
        max_iterations = 8  # więcej iteracji = dokładniejsze zagęszczenie

        while changed and iterations < max_iterations:
            changed = False
            iterations += 1

            for r in range(grid.height):
                for c in range(grid.width):
                    cell = grid.grid[r][c]
                    if cell != "":
                        continue

                    # Zachowawcza wersja: pole zostaje białe jeśli MA sąsiada z literą
                    has_letter_neighbor = False
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nr, nc = r + dr, c + dc
                        if 0 <= nr < grid.height and 0 <= nc < grid.width:
                            neighbor = grid.grid[nr][nc]
                            if neighbor and neighbor not in ("", None):
                                has_letter_neighbor = True
                                break

                    # Pole staje się czarne tylko gdy jest całkowicie izolowane
                    if not has_letter_neighbor:
                        can_be_used = self._can_be_part_of_word(grid, r, c)
                        if not can_be_used:
                            grid.grid[r][c] = None
                            changed = True

    def _force_connectivity(
        self,
        grid: CrosswordGrid,
        depth: int = 0,
        max_depth: int = 5,
    ) -> int:
        """
        Spróbuj połączyć izolowane grupy białych pół wyrazami (Priority 2).

        Algorytm:
        1. Znajdź grupy sąsiednich białych pól (bez liter)
        2. Dla każdej grupy sprawdź czy może być słowem poziomym lub pionowym
        3. Próbuj umieścić wyraz
        4. Rekurencja jeśli coś zostało dodane

        Cel: Zmaksymalizować spójność siatki — brak izoli pól, które mogą być połączone.

        Returns:
            Liczba umieszczonych wyrazów
        """
        if depth >= max_depth:
            return 0

        valid_words_set = self._build_valid_words_set()
        placed_count = 0
        word_usage_count: Dict[str, int] = {}

        for w, _, _, _, _ in grid.placed_words:
            wu = w.upper()
            word_usage_count[wu] = word_usage_count.get(wu, 0) + 1

        # Szukaj grup białych pól które mogą być słowami
        visited = set()

        for start_row in range(grid.height):
            for start_col in range(grid.width):
                if (start_row, start_col) in visited:
                    continue

                cell = grid.grid[start_row][start_col]
                if cell != "":
                    continue

                # Spróbuj poziomo — czy to może być słowo?
                col = start_col
                while col > 0 and grid.grid[start_row][col - 1] == "":
                    col -= 1

                h_group = []
                c = col
                while c < grid.width and grid.grid[start_row][c] == "":
                    h_group.append((start_row, c))
                    visited.add((start_row, c))
                    c += 1

                # Jeśli grupa ma 2+ pola, spróbuj umieścić słowo
                if len(h_group) >= 2:
                    word_len = len(h_group)
                    candidates = [
                        w
                        for w in self.word_source.get_all_words()
                        if len(w) == word_len
                        and word_usage_count.get(w.upper(), 0) == 0
                    ]

                    for word in candidates:
                        if grid.can_place_word(
                            word, start_row, col, Direction.HORIZONTAL, valid_words_set
                        ):
                            clue = (
                                self.word_source.get_word(word) or f"({word_len} liter)"
                            )
                            if grid.place_word(
                                word,
                                start_row,
                                col,
                                Direction.HORIZONTAL,
                                clue,
                                self.word_source,
                            ):
                                placed_count += 1
                                word_usage_count[word.upper()] = (
                                    word_usage_count.get(word.upper(), 0) + 1
                                )
                                break

                # Spróbuj pionowo
                row = start_row
                while row > 0 and grid.grid[row - 1][start_col] == "":
                    row -= 1

                v_group = []
                r = row
                while r < grid.height and grid.grid[r][start_col] == "":
                    v_group.append((r, start_col))
                    visited.add((r, start_col))
                    r += 1

                if len(v_group) >= 2:
                    word_len = len(v_group)
                    candidates = [
                        w
                        for w in self.word_source.get_all_words()
                        if len(w) == word_len
                        and word_usage_count.get(w.upper(), 0) == 0
                    ]

                    for word in candidates:
                        if grid.can_place_word(
                            word, row, start_col, Direction.VERTICAL, valid_words_set
                        ):
                            clue = (
                                self.word_source.get_word(word) or f"({word_len} liter)"
                            )
                            if grid.place_word(
                                word,
                                row,
                                start_col,
                                Direction.VERTICAL,
                                clue,
                                self.word_source,
                            ):
                                placed_count += 1
                                word_usage_count[word.upper()] = (
                                    word_usage_count.get(word.upper(), 0) + 1
                                )
                                break

        # Rekurencja — próbuj dopóki coś się zmienia
        if placed_count > 0:
            placed_count += self._force_connectivity(grid, depth + 1, max_depth)

        return placed_count

    def _build_valid_words_set(self) -> Set[str]:
        """Zbiór wszystkich poprawnych słów (do walidacji cross-wordów)."""
        valid: Set[str] = set(w.upper() for w in self.word_source.get_all_words())
        valid.update(self.planned_words)
        valid.update(self.user_whitelist)
        return valid

    # -----------------------------------------------------------------------
    # STANDARDOWY GENERATOR (pozostałe strategie)
    # -----------------------------------------------------------------------

    def _place_seed(self, grid: CrosswordGrid) -> bool:
        """
        Umieść wyraz startowy zgodnie ze strategią.

        NAPRAWA: Seed może być teraz pionowy LUB poziomy.
        Obie orientacje są próbowane; wybieramy tę, która daje
        większy potencjał przecięć (więcej wolnych komórek wokół).
        """
        strategy = self.config.starting_strategy

        max_grid_dim = min(grid.width, grid.height)
        min_seed_len = max(2, min(5, max_grid_dim - 1))
        max_seed_len = max_grid_dim

        seed = self._get_seed_word(min_len=min_seed_len, max_len=max_seed_len)
        if not seed:
            return False

        clue = self.word_source.get_word(seed) or "?"

        # Spróbuj obie orientacje i wybierz lepszą
        candidates = []

        # Pozioma
        row_h, col_h = self._get_seed_position(
            grid, len(seed), strategy, Direction.HORIZONTAL
        )
        if row_h is not None:
            candidates.append((row_h, col_h, Direction.HORIZONTAL))

        # Pionowa (jeśli słowo mieści się w pionie)
        row_v, col_v = self._get_seed_position(
            grid, len(seed), strategy, Direction.VERTICAL
        )
        if row_v is not None:
            candidates.append((row_v, col_v, Direction.VERTICAL))

        if not candidates:
            return False

        # Wybierz orientację dającą największy "potential score" (środek planszy preferowany)
        def _center_score(r, c, d, length):
            """Im bliżej środka i im więcej miejsca na przecięcia, tym lepiej."""
            mid_r, mid_c = grid.height / 2, grid.width / 2
            if d == Direction.HORIZONTAL:
                word_mid_c = c + length / 2
                return -(abs(r - mid_r) + abs(word_mid_c - mid_c))
            else:
                word_mid_r = r + length / 2
                return -(abs(word_mid_r - mid_r) + abs(c - mid_c))

        candidates.sort(
            key=lambda x: _center_score(x[0], x[1], x[2], len(seed)), reverse=True
        )

        for row, col, direction in candidates:
            if grid.place_word(seed, row, col, direction, clue):
                return True

        return False

    def _get_seed_position(
        self,
        grid: CrosswordGrid,
        word_len: int,
        strategy: StartingStrategy,
        direction: Direction = Direction.HORIZONTAL,
    ) -> Tuple[Optional[int], Optional[int]]:
        """Oblicz pozycję wyrazu startowego dla danej orientacji."""
        h, w = grid.height, grid.width

        if direction == Direction.HORIZONTAL:
            if word_len > w:
                return None, None
        else:
            if word_len > h:
                return None, None

        if direction == Direction.HORIZONTAL:
            if strategy == StartingStrategy.CENTERED:
                row = h // 2
                col = max(0, (w - word_len) // 2)
            elif strategy == StartingStrategy.TOP_LEFT:
                row = 0
                col = 0
            elif strategy == StartingStrategy.TOP_CENTER:
                row = 0
                col = max(0, (w - word_len) // 2)
            elif strategy == StartingStrategy.MIDDLE_LEFT:
                row = h // 2
                col = 0
            elif strategy == StartingStrategy.RANDOM:
                max_row = max(0, h - 1)
                row = random.randint(0, max_row)
                max_col = max(0, w - word_len)
                col = random.randint(0, max_col)
            else:
                return None, None

            if col < 0 or col + word_len > w or row < 0 or row >= h:
                return None, None

        else:  # VERTICAL
            if strategy == StartingStrategy.CENTERED:
                row = max(0, (h - word_len) // 2)
                col = w // 2
            elif strategy == StartingStrategy.TOP_LEFT:
                row = 0
                col = 0
            elif strategy == StartingStrategy.TOP_CENTER:
                row = 0
                col = w // 2
            elif strategy == StartingStrategy.MIDDLE_LEFT:
                row = max(0, (h - word_len) // 2)
                col = 0
            elif strategy == StartingStrategy.RANDOM:
                max_row = max(0, h - word_len)
                row = random.randint(0, max_row)
                max_col = max(0, w - 1)
                col = random.randint(0, max_col)
            else:
                return None, None

            if row < 0 or row + word_len > h or col < 0 or col >= w:
                return None, None

        return row, col

    def _get_seed_word(self, min_len: int, max_len: int) -> Optional[str]:
        """Pobierz słowo startowe — priorytet dla najdłuższych z bazy użytkownika."""
        if self.planned_words:
            user_candidates = sorted(
                [w for w in self.planned_words if min_len <= len(w) <= max_len],
                key=lambda w: len(w),
                reverse=True,
            )
            if user_candidates:
                top = user_candidates[:3]
                return random.choice(top)

        candidates = []
        for length in range(max_len, min_len - 1, -1):
            candidates.extend(self.word_source.get_words_by_length(length))

        return random.choice(candidates) if candidates else None

    def _backtrack(self, grid: CrosswordGrid, depth: int) -> int:
        """
        Rekurencyjny backtracking z prawdziwym UNDO (snapshot siatki).

        NAPRAWA:
        - Przed każdym place_word() zapisywany jest snapshot siatki.
        - Jeśli gałąź nie poprawia globalnej gęstości, cofamy (undo przez snapshot).
        - Dla każdej komórki porównujemy obie orientacje i wybieramy lepszą globalnie.
        - Nie przerywamy po pierwszym sukcesie — sprawdzamy wszystkie kandydaty
          z obu kierunków i kontynuujemy z najlepszym wynikiem.
        """
        if depth >= self.config.backtrack_depth:
            return 0

        empty_cells = grid.get_empty_cells()
        if not empty_cells:
            return 0

        empty_cells.sort(
            key=lambda pos: self._proximity_score(grid, pos),
            reverse=True
        )

        check_limit = min(len(empty_cells), 100) if self.config.aggressive_fill else 30
        placed_count = 0

        for row, col in empty_cells[:check_limit]:
            # Zbierz kandydatów z OBU kierunków
            h_words = self._find_matching_words(grid, row, col, Direction.HORIZONTAL)
            v_words = self._find_matching_words(grid, row, col, Direction.VERTICAL)
            h_limit = 25 if self.config.aggressive_fill else 10
            v_limit = 25 if self.config.aggressive_fill else 10

            # Buduj listę (word, direction, score) i wybierz globalnie najlepsze
            all_candidates = []
            for word in h_words[:h_limit]:
                score = self._word_density_score(
                    grid, word, row, col, Direction.HORIZONTAL
                )
                all_candidates.append((word, Direction.HORIZONTAL, score))
            for word in v_words[:v_limit]:
                score = self._word_density_score(
                    grid, word, row, col, Direction.VERTICAL
                )
                all_candidates.append((word, Direction.VERTICAL, score))

            # Sortuj globalnie — najlepszy wynik gęstości / odblokowania planszy pierwszy
            all_candidates.sort(key=lambda x: x[2], reverse=True)

            best_placed = 0
            placed_this_cell = False

            for word, direction, _ in all_candidates:
                definition = self.word_source.get_word(word) or f"({len(word)} liter)"

                # SNAPSHOT przed umieszczeniem (prawdziwy undo)
                snapshot = [row_data[:] for row_data in grid.grid]
                snapshot_words = list(grid.placed_words)
                snapshot_clues = dict(grid.clue_numbers)
                snapshot_next = grid.next_clue_number

                if grid.place_word(
                    word, row, col, direction, definition, self.word_source
                ):
                    new_placed = self._backtrack(grid, depth + 1)
                    total = 1 + new_placed

                    if total > best_placed:
                        best_placed = total
                        placed_this_cell = True
                        # Utrzymaj ten stan (nie cofaj) — jest lepszy
                        # ale wróć do tej pętli żeby sprawdzić dalej
                        # Zrób snapshot aktualnego "najlepszego" stanu
                        best_snapshot = [r[:] for r in grid.grid]
                        best_words = list(grid.placed_words)
                        best_clues = dict(grid.clue_numbers)
                        best_next = grid.next_clue_number

                    # Cofnij tę gałąź i spróbuj następnego kandydata
                    grid.grid = [r[:] for r in snapshot]
                    grid.placed_words = list(snapshot_words)
                    grid.clue_numbers = dict(snapshot_clues)
                    grid.next_clue_number = snapshot_next

            # Przywróć najlepszy znaleziony stan dla tej komórki
            if placed_this_cell:
                grid.grid = best_snapshot
                grid.placed_words = best_words
                grid.clue_numbers = best_clues
                grid.next_clue_number = best_next
                placed_count += best_placed

        return placed_count

    def _word_density_score(
        self, grid: CrosswordGrid, word: str, row: int, col: int, direction: Direction
    ) -> float:
        """
        Globalny wynik gęstości słowa: ile nowych komórek faktycznie wypełnia
        i ile przecięć tworzy. DRASTYCZNIE ZMIENIONY SCORING.

        Priorytet: GĘSTOŚĆ SIATKI > wszystko inne

        Nowy Scoring:
          new_cells      = +20 za każdą NOWĄ literę (było 3) — PRIORYTET!
          intersections  = +15 za każde prawdziwe przecięcie (było 10)
          cross_adj      = +5 za każdą komórkę sąsiadującą prostopadle (było 2)
          length_bonus   = +0.05 * len(word) (zmniejszone)
          user_bonus     = +100 jeśli z bazy użytkownika (było 500 — mniej ważne)
        """
        new_cells = 0
        intersections = 0
        cross_adj = 0

        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                c = col + i
                if c >= grid.width:
                    break
                cell = grid.grid[row][c]
                if cell == "":
                    new_cells += 20  # ZMIANA: 3 → 20 (priorytet gęstości!)
                    # Sprawdź sąsiadów pionowych (miękkie przecięcie)
                    above = grid.grid[row - 1][c] if row > 0 else None
                    below = grid.grid[row + 1][c] if row < grid.height - 1 else None
                    if (above and above not in ("", None)) or (
                        below and below not in ("", None)
                    ):
                        cross_adj += 5  # ZMIANA: 2 → 5
                elif cell == letter:
                    intersections += 15  # ZMIANA: 10 → 15
        else:
            for i, letter in enumerate(word):
                r = row + i
                if r >= grid.height:
                    break
                cell = grid.grid[r][col]
                if cell == "":
                    new_cells += 20  # ZMIANA: 3 → 20
                    left = grid.grid[r][col - 1] if col > 0 else None
                    right = grid.grid[r][col + 1] if col < grid.width - 1 else None
                    if (left and left not in ("", None)) or (
                        right and right not in ("", None)
                    ):
                        cross_adj += 5  # ZMIANA: 2 → 5
                elif cell == letter:
                    intersections += 15  # ZMIANA: 10 → 15

        word_upper = word.upper()
        user_bonus = (
            100 if (self.planned_words and word_upper in self.planned_words) else 0
        )  # ZMIANA: 500 → 100
        length_bonus = 0.05 * len(word)  # ZMIANA: 0.1 → 0.05

        return user_bonus + new_cells + intersections + cross_adj + length_bonus

    def _proximity_score(self, grid: CrosswordGrid, pos: Tuple[int, int]) -> float:
        """Punktacja bliskości (ile liter w pobliżu + bonus za skrzyżowania dwukierunkowe)."""
        row, col = pos
        score = 0

        # Sąsiedzi bezpośredni (4 kierunki) — silniejszy sygnał
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < grid.height and 0 <= nc < grid.width:
                cell = grid.grid[nr][nc]
                if cell and cell not in ("", None):
                    score += 2  # bezpośredni sąsiad = 2 punkty

        # Sąsiedzi ukośni — słabszy sygnał
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nr, nc = row + dr, col + dc
            if 0 <= nr < grid.height and 0 <= nc < grid.width:
                cell = grid.grid[nr][nc]
                if cell and cell not in ("", None):
                    score += 1

        # Bonus: komórka ma sąsiadów zarówno poziomo JAK I pionowo
        # (może tworzyć skrzyżowanie, co zwiększa gęstość)
        has_h = any(
            0 <= col + dc < grid.width and grid.grid[row][col + dc] not in (None, "")
            for dc in [-1, 1]
        )
        has_v = any(
            0 <= row + dr < grid.height and grid.grid[row + dr][col] not in (None, "")
            for dr in [-1, 1]
        )
        if has_h and has_v:
            score += 5  # silny bonus za potencjalne skrzyżowanie

        return score

    def _find_matching_words(
        self,
        grid: CrosswordGrid,
        row: int,
        col: int,
        direction: Direction
    ) -> List[str]:
        """
        Znajdź słowa mogące być umieszczone w danej pozycji.

        NAPRAWA:
        - user_bonus obniżony z 1000 → 300 (by nie tłumił lepszych gęstościowo słów).
        - Scoring oparty na _word_density_score (faktyczny przyrost wypełnienia),
          nie tylko długość i przecięcia.
        - Słowa oceniane symetrycznie (ten sam mechanizm dla H i V).
        - Nie faworyzujemy jednej orientacji przy budowaniu listy.
        """
        valid_words_set: Set[str] = set(
            w.upper() for w in self.word_source.get_all_words()
        )
        if self.planned_words:
            valid_words_set.update(w.upper() for w in self.planned_words)
        if self.user_whitelist:
            valid_words_set.update(self.user_whitelist)

        max_len = (
            grid.width - col if direction == Direction.HORIZONTAL
            else grid.height - row
        )

        word_usage_count: Dict[str, int] = {}
        for word, _, _, _, _ in grid.placed_words:
            word_upper = word.upper()
            word_usage_count[word_upper] = word_usage_count.get(word_upper, 0) + 1

        all_words = self.word_source.get_all_words()

        # Połącz pule (user najpierw jako tiebreaker przez bonus, nie przez kolejność)
        available = [w for w in all_words if word_usage_count.get(w.upper(), 0) == 0]

        candidates = []
        for word in available:
            if len(word) < 2 or len(word) > max_len:
                continue

            if not grid.can_place_word(word, row, col, direction, valid_words_set):
                continue

            # Globalny wynik gęstości — ile nowych pól + ile przecięć + odblokowania
            score = self._word_density_score(grid, word, row, col, direction)

            # Zmniejszony bonus dla słów użytkownika — priorytet tak, ale nie kosztem gęstości
            word_upper = word.upper()
            if self.planned_words and word_upper in self.planned_words:
                score += 300  # obniżone z 1000

            candidates.append((word, score))

        candidates.sort(key=lambda x: x[1], reverse=True)
        return [w for w, _ in candidates]

    def _count_intersections(
        self,
        grid: CrosswordGrid,
        word: str,
        row: int,
        col: int,
        direction: Direction
    ) -> int:
        """Ile liter słowa się przecina z istniejącymi."""
        count = 0

        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                c = col + i
                if c < grid.width:
                    cell = grid.grid[row][c]
                    if cell and cell not in ["", None] and cell == letter:
                        count += 1
        else:
            for i, letter in enumerate(word):
                r = row + i
                if r < grid.height:
                    cell = grid.grid[r][col]
                    if cell and cell not in ["", None] and cell == letter:
                        count += 1

        return count

    def _mark_empty_cells_black(self, grid: CrosswordGrid) -> None:
        """
        Zaznacz puste pola na czarno (None) — ZMIENIONA LOGIKA

        Cel: Minimalizacja czarnych pól — markuj TYLKO pola całkowicie bezużyteczne.

        Pole staje się czarne TYLKO gdy:
        1. Jest całkowicie izolowane (brak sąsiada z literą w żadnym kierunku), LUB
        2. Nie może być częścią żadnego wyrazu (za mała przerwa między literami)

        Bardziej agresywne w utrzymywaniu białych pól dla maksymalnej gęstości.
        """
        max_iterations = 5
        changed = True
        iteration = 0

        while changed and iteration < max_iterations:
            changed = False
            iteration += 1

            for r in range(grid.height):
                for c in range(grid.width):
                    if grid.grid[r][c] != "":
                        continue  # pomiń: już litera, lub None

                    # Sprawdź czy pole ma szansę być częścią wyrazu
                    if not self._can_be_part_of_word(grid, r, c):
                        # Pole jest całkowicie izolowane — markuj na czarno
                        grid.grid[r][c] = None
                        changed = True

    def _can_be_part_of_word(self, grid: CrosswordGrid, row: int, col: int) -> bool:
        """Sprawdź czy puste pole może być częścią wyrazu."""
        h_connected_left = False
        h_connected_right = False

        for c in range(col - 1, -1, -1):
            if grid.grid[row][c] is None:
                break
            if grid.grid[row][c] and grid.grid[row][c] != "":
                h_connected_left = True
                break

        for c in range(col + 1, grid.width):
            if grid.grid[row][c] is None:
                break
            if grid.grid[row][c] and grid.grid[row][c] != "":
                h_connected_right = True
                break

        v_connected_top = False
        v_connected_bottom = False

        for r in range(row - 1, -1, -1):
            if grid.grid[r][col] is None:
                break
            if grid.grid[r][col] and grid.grid[r][col] != "":
                v_connected_top = True
                break

        for r in range(row + 1, grid.height):
            if grid.grid[r][col] is None:
                break
            if grid.grid[r][col] and grid.grid[r][col] != "":
                v_connected_bottom = True
                break

        h_can_be_used = h_connected_left or h_connected_right
        v_can_be_used = v_connected_top or v_connected_bottom

        return h_can_be_used or v_can_be_used

    def _force_planned_words_in_grid(self, grid: CrosswordGrid) -> None:
        """
        KRYTYCZNE: Gwarantuj że wszystkie planowe użytkownika pojawiają się w siatce.

        Jeśli słowo z planned_words nie jest jeszcze na siatce:
        1. Iteruj po wszystkich możliwych pozycjach (H i V)
        2. Próbuj umieścić każde słowo na każdej pozycji
        3. Aktualizuj valid_words_set po każdej próbie

        Użytkownik wymagał: "chcę by pojawiały się n a krzyżówce nawet jak
        przejdziesz do następnego etapu" — słowa muszą BYĆ GWARANTOWANE.
        """
        if not self.planned_words:
            return

        # Zbierz już umieszczone słowa
        placed_words_upper = {w.upper() for w, _, _, _, _ in grid.placed_words}

        # Dla każdego planowanego słowa (od najdłuższych) sprawdź czy jest już na siatce
        for planned_word in sorted(self.planned_words, key=len, reverse=True):
            word_upper = planned_word.upper()

            # Jeśli już na siatce — OK
            if word_upper in placed_words_upper:
                continue

            definition = (
                self.word_source.get_word(planned_word)
                or f"({len(planned_word)} liter)"
            )

            # Zbuduj aktualny zestaw poprawnych słów (obejmuje już umieszczone)
            valid_words_set = self._build_valid_words_set()

            # Spróbuj każdą pozycję H i V
            found = False

            # POZIOMO
            for row in range(grid.height):
                if found:
                    break
                for col in range(grid.width - len(planned_word) + 1):
                    # Sprawdź czy można umieścić
                    if not grid.can_place_word(
                        planned_word, row, col, Direction.HORIZONTAL, valid_words_set
                    ):
                        continue

                    # Próbuj umieścić
                    if grid.place_word(
                        planned_word,
                        row,
                        col,
                        Direction.HORIZONTAL,
                        definition,
                        self.word_source,
                    ):
                        placed_words_upper.add(word_upper)
                        found = True
                        break

            # PIONOWO (tylko jeśli nie znaleziono poziomo)
            if not found:
                for row in range(grid.height - len(planned_word) + 1):
                    if found:
                        break
                    for col in range(grid.width):
                        if not grid.can_place_word(
                            planned_word, row, col, Direction.VERTICAL, valid_words_set
                        ):
                            continue

                        if grid.place_word(
                            planned_word,
                            row,
                            col,
                            Direction.VERTICAL,
                            definition,
                            self.word_source,
                        ):
                            placed_words_upper.add(word_upper)
                            found = True
                            break

    def _compute_placement_score_for_planned_word(
        self, grid: CrosswordGrid, word: str, row: int, col: int, direction: Direction
    ) -> float:
        """Oblicz wynik dla umieszczenia planowego słowa (licze gęstość i połączenia)."""
        score = 0

        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                c = col + i
                cell = grid.grid[row][c]

                # Nowa litera — +20 (priorytet)
                if cell == "":
                    score += 20
                # Przecięcie z istniejącą literą — +15
                elif cell == letter.upper():
                    score += 15
                # Czarne pole nas nie interesuje
        else:
            for i, letter in enumerate(word):
                r = row + i
                cell = grid.grid[r][col]

                if cell == "":
                    score += 20
                elif cell == letter.upper():
                    score += 15

        # Bonus za umieszczenie z już istniejącymi słowami (kolokacja)
        # Więcej przecięć = lepiej
        intersections = 0
        if direction == Direction.HORIZONTAL:
            # Raczej między innymi słowami
            for i in range(len(word)):
                c = col + i
                if grid.grid[row][c] == word[i].upper():
                    intersections += 1
        else:
            for i in range(len(word)):
                r = row + i
                if grid.grid[r][col] == word[i].upper():
                    intersections += 1

        score += intersections * 10
        return score
