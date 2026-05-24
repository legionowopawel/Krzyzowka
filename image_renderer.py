# -*- coding: utf-8 -*-
"""
image_renderer.py — Renderowanie krzyżówki do PNG
Grafika z pełną obsługą kolorów, czcionek i numeracji
"""

from typing import Optional, Tuple, Dict, List
from PIL import Image, ImageDraw, ImageFont
from crossword_grid import CrosswordGrid, Direction


class CrosswordImageRenderer:
    """Renderer krzyżówki do pliku PNG z obsługą kolorów i parametrów."""

    # Predefiniowane kolory (nazwa -> RGB tuple)
    PREDEFINED_COLORS = {
        "przezroczyste": (255, 255, 255),  # Białe (dla komórek pustych)
        "czarne": (0, 0, 0),  # Czarne (dla niedostępnych)
        "żółte": (255, 255, 0),
        "szare": (128, 128, 128),
        "białe": (255, 255, 255),
        "czerwone": (255, 0, 0),
        "zielone": (0, 128, 0),
        "niebieskie": (0, 0, 255),
        "pomarańczowe": (255, 165, 0),
        "różowe": (255, 192, 203),
        "beżowe": (245, 222, 179),
    }

    def __init__(
        self,
        cell_size: int = 40,
        font_size: int = 24,
        font_name: str = "Arial",
        color_empty: Optional[Tuple[int, int, int]] = None,
        color_tile: Optional[Tuple[int, int, int]] = None,
        color_black: Optional[Tuple[int, int, int]] = None,
        color_text: Optional[Tuple[int, int, int]] = None,
        color_clue_num: Optional[Tuple[int, int, int]] = None,
    ):
        """
        Args:
            cell_size: Rozmiar jednej komórki w pikselach
            font_size: Rozmiar czcionki
            font_name: Nazwa czcionki systemowej (domyślnie Arial)
            color_empty: Kolor pustych komórek (RGB tuple lub nazwa)
            color_tile: Kolor komórek z literami (RGB tuple lub nazwa)
            color_black: Kolor czarnych komórek
            color_text: Kolor tekstu (liter)
            color_clue_num: Kolor numerów pytań
        """
        self.cell_size = cell_size
        self.font_size = font_size
        self.font_name = font_name
        self.margin = 40

        # Domyślne kolory (Scrabble style)
        self.color_empty = color_empty or (220, 220, 220)
        self.color_tile = color_tile or (245, 222, 179)
        self.color_black = color_black or (0, 0, 0)
        self.color_text = color_text or (40, 40, 40)
        self.color_clue_num = color_clue_num or (200, 0, 0)
        self.color_border = (0, 0, 0)

        # Spróbuj załadować czcionkę
        self.font_main = self._load_font(font_size, font_name)
        self.font_clue = self._load_font(max(8, font_size // 2), font_name)

    def _load_font(self, size: int, font_name: str) -> ImageFont.FreeTypeFont:
        """Załaduj czcionkę TrueType z systemu."""
        # Mapowanie nazw czcionek na ścieżki Windows
        font_paths = {
            "Arial": "C:\\Windows\\Fonts\\arial.ttf",
            "Calibri": "C:\\Windows\\Fonts\\calibri.ttf",
            "Times": "C:\\Windows\\Fonts\\times.ttf",
            "Courier": "C:\\Windows\\Fonts\\cour.ttf",
            "Verdana": "C:\\Windows\\Fonts\\verdana.ttf",
        }

        candidates = [
            font_paths.get(font_name, f"C:\\Windows\\Fonts\\{font_name.lower()}.ttf"),
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\calibri.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]

        for font_path in candidates:
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                pass

        # Fallback: domyślna czcionka PIL
        return ImageFont.load_default()

    def render(self, grid: CrosswordGrid, filled: bool = True) -> Image.Image:
        """
        Renderuj siatkę krzyżówki do obrazu PIL.
        WAŻNE: Rysuje WSZYSTKIE numery pytań, nie tylko na startach wyrazów.

        Args:
            grid: Siatka krzyżówki
            filled: True = uzupełniona (z literami), False = pusta (do wypełniania)

        Returns:
            Obiekt Image PIL
        """
        width_px = grid.width * self.cell_size + 2 * self.margin
        height_px = grid.height * self.cell_size + 2 * self.margin

        # Stwórz obraz
        img = Image.new('RGB', (width_px, height_px), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Mapowanie numeru pytania -> pozycja (r, c) gdzie po raz pierwszy się pojawił
        clue_num_positions: Dict[int, Tuple[int, int]] = {}

        # Zbierz pozycje wszystkich numerów pytań
        for num, row, col in self._collect_all_clue_positions(grid):
            if num not in clue_num_positions:
                clue_num_positions[num] = (row, col)

        # Rysuj siatkę
        for r in range(grid.height):
            for c in range(grid.width):
                x0 = self.margin + c * self.cell_size
                y0 = self.margin + r * self.cell_size
                x1 = x0 + self.cell_size
                y1 = y0 + self.cell_size

                cell = grid.grid[r][c]

                # Kolor tła komórki
                if cell is None:
                    # Czarna komórka (niedostępna)
                    fill_color = self.color_black
                elif cell == "":
                    # Puste pole do wpisania
                    fill_color = self.color_empty
                else:
                    # Wypełniona komórka z literą
                    fill_color = self.color_tile

                # Rysuj prostokąt
                draw.rectangle(
                    [x0, y0, x1, y1],
                    fill=fill_color,
                    outline=self.color_border,
                    width=2,
                )

                # Jeśli to wersja uzupełniona i jest litera, rysuj ją WYCENTROWANĄ
                if filled and cell and cell != "":
                    cell_center_x = x0 + self.cell_size / 2
                    cell_center_y = y0 + self.cell_size / 2
                    draw.text(
                        (cell_center_x, cell_center_y),
                        cell,
                        fill=self.color_text,
                        font=self.font_main,
                        anchor="mm",
                    )

                # Zbierz wszystkie numery które mają start w tej komórce
                nums_at_this_cell = [
                    num
                    for num, (nr, nc) in clue_num_positions.items()
                    if nr == r and nc == c
                ]

                # Jeśli jest numer pytania i komórka nie jest czarna, rysuj go
                if nums_at_this_cell and cell is not None:
                    num_text = str(min(nums_at_this_cell))
                    draw.text(
                        (x0 + 4, y0 + 2),
                        num_text,
                        fill=self.color_clue_num,
                        font=self.font_clue,
                    )

        return img

    def _collect_all_clue_positions(
        self, grid: CrosswordGrid
    ) -> List[Tuple[int, int, int]]:
        """
        Zbierz WSZYSTKIE pozycje gdzie zaczynają się wyrazy (dla poziomych i pionowych).

        Komórka jest startem wyrazu poziomego gdy:
          - poprzednia komórka to None lub jest poza siatką (lewa krawędź)
          - następna komórka istnieje i nie jest czarna (None)

        Komórka jest startem wyrazu pionowego gdy:
          - górna komórka to None lub jest poza siatką (górna krawędź)
          - dolna komórka istnieje i nie jest czarna (None)

        Returns:
            Lista (num_pytania, row, col)
        """
        positions = []
        collected_nums: set = set()

        for r in range(grid.height):
            for c in range(grid.width):
                cell = grid.grid[r][c]

                # Pomijamy czarne komórki (None) — nie mogą być startami wyrazów
                if cell is None:
                    continue

                # Sprawdź czy to start słowa poziomego:
                # - lewa strona to krawędź siatki lub czarna komórka
                # - prawa strona istnieje i nie jest czarna
                is_h_start = (
                    (c == 0 or grid.grid[r][c - 1] is None)
                    and c < grid.width - 1
                    and grid.grid[r][c + 1] is not None
                )

                # Sprawdź czy to start słowa pionowego:
                # - górna strona to krawędź siatki lub czarna komórka
                # - dolna strona istnieje i nie jest czarna
                is_v_start = (
                    (r == 0 or grid.grid[r - 1][c] is None)
                    and r < grid.height - 1
                    and grid.grid[r + 1][c] is not None
                )

                if is_h_start or is_v_start:
                    clue_num = grid.get_clue_number(r, c)
                    if clue_num and clue_num not in collected_nums:
                        positions.append((clue_num, r, c))
                        collected_nums.add(clue_num)

        return positions

    def render_with_clues(self, grid: CrosswordGrid, filled: bool = True) -> Image.Image:
        """
        Renderuj krzyżówkę wraz z pytaniami poniżej.

        Args:
            grid: Siatka krzyżówki
            filled: True = uzupełniona, False = pusta

        Returns:
            Obraz zawierający siatkę krzyżówki i pytania
        """
        # Renderuj siatkę
        grid_img = self.render(grid, filled=filled)

        # Pobierz pytania
        h_clues, v_clues = grid.get_clues_list()

        # Oblicz wysokość sekcji pytań
        clues_height = max(len(h_clues), len(v_clues)) * 30 + 100

        # Stwórz większy obraz
        total_height = grid_img.height + clues_height
        final_img = Image.new('RGB', (grid_img.width, total_height), color=(255, 255, 255))

        # Wklej siatkę
        final_img.paste(grid_img, (0, 0))

        # Rysuj pytania
        draw = ImageDraw.Draw(final_img)

        # --- Sekcja POZIOMO ---
        y = grid_img.height + 20
        draw.text((20, y), "POZIOMO:", fill=self.color_text, font=self.font_main)
        y += 40

        for num, clue, word in h_clues[:20]:  # Maksymalnie 20 pytań
            text = f"{num}. {clue}"
            draw.text((40, y), text, fill=self.color_text, font=self.font_clue)
            y += 25

        # --- Sekcja PIONOWO ---
        v_x = grid_img.width // 2 + 20
        v_y = grid_img.height + 20
        draw.text((v_x, v_y), "PIONOWO:", fill=self.color_text, font=self.font_main)
        v_y += 40

        for num, clue, word in v_clues[:20]:
            text = f"{num}. {clue}"
            draw.text((v_x + 20, v_y), text, fill=self.color_text, font=self.font_clue)
            v_y += 25

        return final_img
