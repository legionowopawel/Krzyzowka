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
        direction: Direction
    ) -> bool:
        """
        Sprawdź czy można umieścić słowo w danym miejscu.
        
        Reguły:
        - Słowo musi się zmieścić w planszy
        - Nie może przechodzić przez czarne komórki (None)
        - Każda litera musi pasować: albo komórka pusta (""), albo ta sama litera
        - Musi mieć co najmniej jedno przecięcie z istniejącymi słowami
          (chyba że to pierwsze słowo)
        
        Returns:
            True jeśli słowo się zmieści i nie koliduje
        """
        if not word:
            return False

        # Sprawdzenie czy słowo się zmieści
        if direction == Direction.HORIZONTAL:
            if col + len(word) > self.width:
                return False

            # Sprawdź każdą komórkę
            can_intersect = False
            for i, letter in enumerate(word):
                c = col + i
                r = row
                cell = self.grid[r][c]

                # Czarna komórka = nie możemy
                if cell is None:
                    return False

                # Komórka pusta = OK, ale sprawdzaj sąsiadów
                if cell == "":
                    # Sprawdź czy nie ma liter z góry/dołu (to byłaby kolizja)
                    # Chyba że to przecięcie planowane
                    continue
                else:
                    # Komórka zawiera literę
                    if cell != letter:
                        # Inna litera = kolizja!
                        return False
                    # Ta sama litera = możliwe przecięcie
                    can_intersect = True

            return True

        else:  # VERTICAL
            if row + len(word) > self.height:
                return False

            can_intersect = False
            for i, letter in enumerate(word):
                r = row + i
                c = col
                cell = self.grid[r][c]

                # Czarna komórka = nie możemy
                if cell is None:
                    return False

                # Komórka pusta = OK
                if cell == "":
                    continue
                else:
                    # Komórka zawiera literę
                    if cell != letter:
                        return False
                    can_intersect = True

            return True

    def place_word(
        self,
        word: str,
        row: int,
        col: int,
        direction: Direction,
        clue: str
    ) -> bool:
        """
        Umieść słowo w siatce i przypisz numer pytania.
        
        Returns:
            True jeśli się udało
        """
        if not self.can_place_word(word, row, col, direction):
            return False

        # Przypisz numer pytania TYLKO jeśli to rzeczywisty start słowa
        # (nie wcześniej wypełnione litery z innego słowa)
        clue_num = None
        if (row, col) not in self.clue_numbers:
            # Sprawdź czy ta pozycja jest już wypełniona (z poprzedniego słowa)
            if not self.grid[row][col]:
                clue_num = self.next_clue_number
                self.clue_numbers[(row, col)] = clue_num
                self.next_clue_number += 1
        else:
            clue_num = self.clue_numbers[(row, col)]

        # Umieść litery
        if direction == Direction.HORIZONTAL:
            for i, letter in enumerate(word):
                self.grid[row][col + i] = letter
        else:
            for i, letter in enumerate(word):
                self.grid[row + i][col] = letter

        # Zarejestruj słowo TYLKO jeśli ma nowy numer pytania
        # (aby uniknąć duplikatów)
        if clue_num is not None:
            self.placed_words.append((word, row, col, direction, clue))

        return True

    def get_clue_number(self, row: int, col: int) -> Optional[int]:
        """Pobierz numer pytania dla danej komórki."""
        return self.clue_numbers.get((row, col))

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
        """Odtwórz numery pytań i listę umieszczonych słów z siatki."""
        self.placed_words = []
        self.clue_numbers = {}
        self.next_clue_number = 1

        for row in range(self.height):
            for col in range(self.width):
                cell = self.grid[row][col]
                if cell is None or cell == "":
                    continue

                # Poziomo
                if (col == 0 or self.grid[row][col - 1] is None) and (
                    col < self.width - 1 and self.grid[row][col + 1] not in (None, "")
                ):
                    horiz_word = ""
                    c = col
                    while c < self.width and self.grid[row][c] not in (None, ""):
                        horiz_word += self.grid[row][c]
                        c += 1

                    if len(horiz_word) > 1:
                        definition = None
                        if word_source is not None:
                            try:
                                definition = word_source.get_word(horiz_word)
                            except Exception:
                                definition = None
                        if definition is None:
                            definition = f"({len(horiz_word)} liter)"

                        clue_num = self.next_clue_number
                        self.clue_numbers[(row, col)] = clue_num
                        self.placed_words.append(
                            (horiz_word, row, col, Direction.HORIZONTAL, definition)
                        )
                        self.next_clue_number += 1

                # Pionowo
                if (row == 0 or self.grid[row - 1][col] is None) and (
                    row < self.height - 1 and self.grid[row + 1][col] not in (None, "")
                ):
                    vert_word = ""
                    r = row
                    while r < self.height and self.grid[r][col] not in (None, ""):
                        vert_word += self.grid[r][col]
                        r += 1

                    if len(vert_word) > 1:
                        definition = None
                        if word_source is not None:
                            try:
                                definition = word_source.get_word(vert_word)
                            except Exception:
                                definition = None
                        if definition is None:
                            definition = f"({len(vert_word)} liter)"

                        clue_num = self.next_clue_number
                        self.clue_numbers[(row, col)] = clue_num
                        self.placed_words.append(
                            (vert_word, row, col, Direction.VERTICAL, definition)
                        )
                        self.next_clue_number += 1

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
            gdzie każde to lista (numer_pytania, tekst_pytania)
        """
        h_clues = []
        v_clues = []

        for word, row, col, direction, clue in self.placed_words:
            clue_num = self.clue_numbers.get((row, col))
            if clue_num:
                if direction == Direction.HORIZONTAL:
                    h_clues.append((clue_num, clue, word))
                else:
                    v_clues.append((clue_num, clue, word))

        # Sortuj po numerze pytania
        h_clues.sort(key=lambda x: x[0])
        v_clues.sort(key=lambda x: x[0])

        return h_clues, v_clues
