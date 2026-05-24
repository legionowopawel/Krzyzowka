# -*- coding: utf-8 -*-
"""
crossword_grid.py — Struktura danych i logika siatki krzyżówki
"""

from typing import List, Dict, Optional, Set, Tuple
from enum import Enum
import copy


class Direction(Enum):
    """Kierunek słowa w krzyżówce."""
    HORIZONTAL = "H"
    VERTICAL = "V"


class CrosswordGrid:
    """
    Siatka krzyżówki o wymiarach n×m.
    Każda komórka może być:
      - None (niedostępna, czarna)
      - "" (pusta, dostępna do wypełnienia)
      - litera (już wypełniona)
    """

    def __init__(self, width: int, height: int):
        """
        Inicjalizuje pustą siatkę.
        
        Args:
            width: Liczba kolumn
            height: Liczba wierszy
        """
        self.width = width
        self.height = height

        # Siatka: grid[row][col] = None | "" | litera
        self.grid: List[List[Optional[str]]] = [
            ["" for _ in range(width)] for _ in range(height)
        ]

        # Wygenerowane słowa:
        # [(word, row, col, direction, clue_number), ...]
        self.placed_words: List[Tuple[str, int, int, Direction, int]] = []

        # Mapowanie: (row, col) -> clue_number
        self.clue_numbers: Dict[Tuple[int, int], int] = {}

        # Licznik pytań do przydzielenia
        self.next_clue_number = 1

    def copy(self) -> 'CrosswordGrid':
        """Głębokie kopie siatki."""
        g = CrosswordGrid(self.width, self.height)
        g.grid = [row[:] for row in self.grid]
        g.placed_words = copy.deepcopy(self.placed_words)
        g.clue_numbers = copy.deepcopy(self.clue_numbers)
        g.next_clue_number = self.next_clue_number
        return g

    def can_place_word(
        self,
        word: str,
        row: int,
        col: int,
        direction: Direction,
        valid_words_set: Optional[Set[str]] = None,
    ) -> bool:
        """
        Sprawdź czy można umieścić słowo w danym miejscu.

        Reguły:
        - Słowo musi się zmieścić w planszy
        - Nie może przechodzić przez czarne komórki (None)
        - Każda litera musi pasować: albo komórka pusta (""), albo ta sama litera
        - Słowo prostopadłe (cross-word) powstałe przez nowe litery musi istnieć
          w valid_words_set (jeśli podano) — lub musi mieć długość 1 (brak słowa)
        - Musi mieć co najmniej jedno przecięcie z istniejącymi słowami
          (chyba że to pierwsze słowo — grid jest pusty)
        - Nie może być "luźne" — każde umieszczone słowo (po pierwszym) musi
          przecinać się z co najmniej jednym istniejącym słowem przez wspólną literę

        Returns:
            True jeśli słowo się zmieści i nie koliduje
        """

        if not word:
            return False

        # Sprawdzenie czy słowo się zmieści
        if direction == Direction.HORIZONTAL:
            if col + len(word) > self.width:
                return False

            # Sprawdzenie granicy PRZED słowem
            if col > 0:
                before = self.grid[row][col - 1]
                if before and before != "":
                    return False

            # Sprawdzenie granicy ZA słowem
            end_col = col + len(word)
            if end_col < self.width:
                after = self.grid[row][end_col]
                if after and after != "":
                    return False

            # Sprawdź każdą komórkę słowa
            # true_intersections  — komórki gdzie słowo trafia w ISTNIEJĄCĄ literę (twarde przecięcie)
            # cross_intersections — komórki gdzie pusta komórka sąsiaduje pionowo z literami (miękkie)
            true_intersections = 0
            cross_intersections = 0
            for i, letter in enumerate(word):
                c = col + i
                r = row
                cell = self.grid[r][c]

                if cell is None:
                    return False

                if cell == "":
                    # Komórka pusta — sprawdź czy nie tworzy niedozwolonego cross-worda pionowego
                    above = self.grid[r - 1][c] if r > 0 else None
                    below = self.grid[r + 1][c] if r < self.height - 1 else None
                    has_above = above and above != ""
                    has_below = below and below != ""

                    if has_above or has_below:
                        if valid_words_set is not None:
                            cross_word = self._get_cross_word_horizontal(r, c, letter)
                            if len(cross_word) >= 2 and cross_word.upper() not in valid_words_set:
                                return False
                        # Miękkie przecięcie: sąsiedztwo pionowe, ale nie wspólna litera
                        cross_intersections += 1
                else:
                    # Komórka zawiera literę — musi być zgodna (TWARDE przecięcie)
                    if cell != letter:
                        return False
                    true_intersections += 1

            # Jeśli siatka nie jest pusta, wymagamy co najmniej 1 połączenia z istniejącymi słowami
            # (twarde LUB miękkie — musi być jakakolwiek relacja z siatką)
            if self.get_filled_count() > 0 and true_intersections == 0 and cross_intersections == 0:
                return False

            return True

        else:  # VERTICAL
            if row + len(word) > self.height:
                return False

            if row > 0:
                before = self.grid[row - 1][col]
                if before and before != "":
                    return False

            end_row = row + len(word)
            if end_row < self.height:
                after = self.grid[end_row][col]
                if after and after != "":
                    return False

            true_intersections = 0
            cross_intersections = 0
            for i, letter in enumerate(word):
                r = row + i
                c = col
                cell = self.grid[r][c]

                if cell is None:
                    return False

                if cell == "":
                    # Sprawdź czy są sąsiedzi poziomi
                    left = self.grid[r][c - 1] if c > 0 else None
                    right = self.grid[r][c + 1] if c < self.width - 1 else None
                    has_left = left and left != ""
                    has_right = right and right != ""

                    if has_left or has_right:
                        if valid_words_set is not None:
                            cross_word = self._get_cross_word_vertical(r, c, letter)
                            if len(cross_word) >= 2 and cross_word.upper() not in valid_words_set:
                                return False
                        cross_intersections += 1
                else:
                    if cell != letter:
                        return False
                    true_intersections += 1

            if self.get_filled_count() > 0 and true_intersections == 0 and cross_intersections == 0:
                return False

            return True

    def _get_cross_word_horizontal(self, row: int, col: int, new_letter: str) -> str:
        """Zbierz słowo pionowe w kolumnie col, gdy w (row,col) będzie new_letter."""
        # Idź w górę
        letters = []
        r = row - 1
        while r >= 0 and self.grid[r][col] and self.grid[r][col] != "":
            letters.append(self.grid[r][col])
            r -= 1
        letters.reverse()
        letters.append(new_letter)
        # Idź w dół
        r = row + 1
        while r < self.height and self.grid[r][col] and self.grid[r][col] != "":
            letters.append(self.grid[r][col])
            r += 1
        return "".join(letters)

    def _get_cross_word_vertical(self, row: int, col: int, new_letter: str) -> str:
        """Zbierz słowo poziome w wierszu row, gdy w (row,col) będzie new_letter."""
        # Idź w lewo
        letters = []
        c = col - 1
        while c >= 0 and self.grid[row][c] and self.grid[row][c] != "":
            letters.append(self.grid[row][c])
            c -= 1
        letters.reverse()
        letters.append(new_letter)
        # Idź w prawo
        c = col + 1
        while c < self.width and self.grid[row][c] and self.grid[row][c] != "":
            letters.append(self.grid[row][c])
            c += 1
        return "".join(letters)

    def place_word(
        self,
        word: str,
        row: int,
        col: int,
        direction: Direction,
        clue: str,
        word_source=None,
    ) -> bool:
        """
        Umieść słowo w siatce i przypisz numer pytania.
        Waliduje cross-words (słowa prostopadłe).

        Args:
            word_source: Opcjonalnie - do walidacji słów powstałych z przecięć

        Returns:
            True jeśli się udało
        """
        # Zbuduj zbiór poprawnych słów (baza użytkownika + bin)
        valid_words_set: Optional[Set[str]] = None
        if word_source is not None:
            valid_words_set = set(w.upper() for w in word_source.get_all_words())

        if not self.can_place_word(word, row, col, direction, valid_words_set):
            return False

        # Przypisz numer pytania jeśli pole nie ma jeszcze numeru
        clue_num = self.clue_numbers.get((row, col))
        if clue_num is None:
            clue_num = self.next_clue_number
            self.clue_numbers[(row, col)] = clue_num
            self.next_clue_number += 1

        # Umieść litery
        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                self.grid[row][col + i] = letter
        else:
            for i, letter in enumerate(word):
                self.grid[row + i][col] = letter

        # Zarejestruj słowo
        if clue_num is not None:
            self.placed_words.append((word, row, col, direction, clue))

        return True

    def get_clue_number(self, row: int, col: int) -> Optional[int]:
        """Pobierz numer pytania dla danej komórki."""
        return self.clue_numbers.get((row, col))

    def _get_perpendicular_words(
        self, word: str, row: int, col: int, direction: Direction
    ) -> List[str]:
        """
        Zwróć słowa, które powstają w wyniku przecięcia tego słowa.
        Te słowa muszą istnieć w bazie!
        """
        perpendicular_words = []

        if direction == Direction.HORIZONTAL:
            # Słowo poziome - szukaj nowych słów pionowych
            for i, letter in enumerate(word):
                c = col + i
                # Idź do górnego krańca słowa pionowego
                start_row = row
                while (
                    start_row > 0
                    and self.grid[start_row - 1][c]
                    and self.grid[start_row - 1][c] != ""
                ):
                    start_row -= 1

                # Zbierz słowo pionowe
                v_word = ""
                r = start_row
                while r < self.height and self.grid[r][c] and self.grid[r][c] != "":
                    v_word += self.grid[r][c]
                    r += 1

                # Jeśli to nowe słowo (zawiera naszą literę i ma > 1 litera)
                if len(v_word) > 1 and start_row <= row < start_row + len(v_word):
                    if v_word not in perpendicular_words:
                        perpendicular_words.append(v_word)
        else:
            # Słowo pionowe - szukaj nowych słów poziomych
            for i, letter in enumerate(word):
                r = row + i
                # Idź do lewego krańca słowa poziomego
                start_col = col
                while (
                    start_col > 0
                    and self.grid[r][start_col - 1]
                    and self.grid[r][start_col - 1] != ""
                ):
                    start_col -= 1

                # Zbierz słowo poziome
                h_word = ""
                c = start_col
                while c < self.width and self.grid[r][c] and self.grid[r][c] != "":
                    h_word += self.grid[r][c]
                    c += 1

                # Jeśli to nowe słowo (zawiera naszą literę i ma > 1 litera)
                if len(h_word) > 1 and start_col <= col < start_col + len(h_word):
                    if h_word not in perpendicular_words:
                        perpendicular_words.append(h_word)

        return perpendicular_words

    def get_word_at(
        self,
        row: int,
        col: int,
        direction: Direction
    ) -> Optional[str]:
        """Pobierz słowo zaczynające się w danym miejscu i kierunku."""
        word = ""

        if direction == Direction.HORIZONTAL:
            c = col
            while c < self.width and self.grid[row][c]:
                word += self.grid[row][c]
                c += 1
        else:
            r = row
            while r < self.height and self.grid[r][col]:
                word += self.grid[r][col]
                r += 1

        return word if len(word) > 1 else None

    def get_empty_cells(self) -> List[Tuple[int, int]]:
        """Zwróć listę pustych komórek (potencjalne miejsca do wypełnienia)."""
        cells = []
        for r in range(self.height):
            for c in range(self.width):
                if self.grid[r][c] == "":
                    cells.append((r, c))
        return cells

    def get_filled_count(self) -> int:
        """Ile komórek jest wypełnionych?"""
        return sum(
            1 for r in range(self.height)
            for c in range(self.width)
            if self.grid[r][c] and self.grid[r][c] != ""
        )

    def refresh_clues(self, word_source=None) -> None:
        """
        Odtwórz numery pytań i listę umieszczonych słów z siatki.

        NAPRAWA: Nie przypisuje już numeru każdej literze oddzielnie,
        ale całym słowom.
        """
        self.placed_words = []
        self.clue_numbers = {}
        self.next_clue_number = 1

        # Śledzenie cual słowa już przetworzone
        processed_words = set()

        for row in range(self.height):
            for col in range(self.width):
                cell = self.grid[row][col]
                if cell is None or cell == "":
                    continue

                # Poziomo: sprawdzenie czy to POCZĄTEK słowa
                if col == 0 or self.grid[row][col - 1] is None:
                    # Zbierz słowo poziome
                    horiz_word = ""
                    c = col
                    while c < self.width and self.grid[row][c] not in (None, ""):
                        horiz_word += self.grid[row][c]
                        c += 1

                    # Tylko jeśli słowo ma >1 litery I to pierwszy raz je widzimy
                    word_key_h = (row, col, Direction.HORIZONTAL, horiz_word)
                    if len(horiz_word) > 1 and word_key_h not in processed_words:
                        processed_words.add(word_key_h)

                        definition = None
                        if word_source is not None:
                            try:
                                definition = word_source.get_word(horiz_word)
                            except Exception:
                                definition = None
                        if definition is None:
                            definition = horiz_word

                        clue_num = self.next_clue_number
                        self.clue_numbers[(row, col)] = clue_num
                        self.next_clue_number += 1
                        self.placed_words.append(
                            (horiz_word, row, col, Direction.HORIZONTAL, definition)
                        )

                # Pionowo: sprawdzenie czy to POCZĄTEK słowa
                if row == 0 or self.grid[row - 1][col] is None:
                    # Zbierz słowo pionowe
                    vert_word = ""
                    r = row
                    while r < self.height and self.grid[r][col] not in (None, ""):
                        vert_word += self.grid[r][col]
                        r += 1

                    # Tylko jeśli słowo ma >1 litery I to pierwszy raz je widzimy
                    word_key_v = (row, col, Direction.VERTICAL, vert_word)
                    if len(vert_word) > 1 and word_key_v not in processed_words:
                        processed_words.add(word_key_v)

                        definition = None
                        if word_source is not None:
                            try:
                                definition = word_source.get_word(vert_word)
                            except Exception:
                                definition = None
                        if definition is None:
                            definition = vert_word

                        clue_num = self.next_clue_number
                        self.clue_numbers[(row, col)] = clue_num
                        self.next_clue_number += 1
                        self.placed_words.append(
                            (vert_word, row, col, Direction.VERTICAL, definition)
                        )

    def get_density(self) -> float:
        """Procent wypełnionej powierzchni."""
        total = self.width * self.height
        filled = self.get_filled_count()
        return (filled / total * 100) if total > 0 else 0

    def to_string(self) -> str:
        """Zwróć tekstową reprezentację siatki."""
        lines = []
        for row in self.grid:
            line = " ".join(
                c if c == "" else c if isinstance(c, str) else "█"
                for c in row
            )
            lines.append(line)
        return "\n".join(lines)

    def get_clues_list(self) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str]]]:
        """
        Zwróć listy pytań dla pozomych i pionowych słów.

        Returns:
            (clues_horizontal, clues_vertical)
            gdzie każde to lista (numer_pytania, tekst_pytania, word)
        """
        h_clues_dict = {}  # {clue_num: (clue, word)}
        v_clues_dict = {}  # {clue_num: (clue, word)}

        for word, row, col, direction, clue in self.placed_words:
            clue_num = self.clue_numbers.get((row, col))
            if clue_num:
                if direction == Direction.HORIZONTAL:
                    # Jeśli tego numeru jeszcze nie ma, dodaj (unika duplikatów)
                    if clue_num not in h_clues_dict:
                        h_clues_dict[clue_num] = (clue, word)
                else:
                    if clue_num not in v_clues_dict:
                        v_clues_dict[clue_num] = (clue, word)

        # Konwertuj do listy i sortuj po numerze
        h_clues = [(num, clue, word) for num, (clue, word) in h_clues_dict.items()]
        v_clues = [(num, clue, word) for num, (clue, word) in v_clues_dict.items()]

        return h_clues, v_clues
