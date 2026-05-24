#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostyka: Pełna analiza błędów OPIEKAA, DDYPLOM, PPORZĄDEK
oraz analiza gęstości siatki
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from crossword_grid import CrosswordGrid, Direction

PASS = "✅"
FAIL = "❌"

def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

def extract_row(grid, row, col_start, col_end):
    result = ""
    for c in range(col_start, col_end + 1):
        cell = grid.grid[row][c]
        if cell and cell != "":
            result += cell
        else:
            result += "_"
    return result

def extract_col(grid, col, row_start, row_end):
    result = ""
    for r in range(row_start, row_end + 1):
        cell = grid.grid[r][col]
        if cell and cell != "":
            result += cell
        else:
            result += "_"
    return result


section("SCENARIUSZ 1: Błąd OPIEKAA (litera ZA słowem)")

g1 = CrosswordGrid(15, 15)
g1.grid[6][8] = 'A'  # litera za końcem OPIEKA
print(f"\n[Setup] Komórka (6,8) = 'A' (symulacja litery za słowem)")

result = g1.can_place_word("OPIEKA", 6, 2, Direction.HORIZONTAL)
status = PASS if not result else FAIL
print(f"{status} can_place_word('OPIEKA', 6, 2, H) = {result}")
print(f"   Oczekiwane: False (OPIEKA kończy na kol.7, potem 'A' na kol.8 → OPIEKAA)")

if not result:
    print(f"{PASS} Błąd OPIEKAA WYELIMINOWANY — boundary check działa!")
else:
    print(f"{FAIL} BŁĄD NADAL ISTNIEJE — boundary check po słowie nie wykrywa kolizji!")

# Wariant: umieść OPIEKA, potem sprawdź czy możemy dodać A za nim
g1b = CrosswordGrid(15, 15)
g1b.place_word("OPIEKA", 6, 2, Direction.HORIZONTAL, "test")
print(f"\n[Wariant] Po umieszczeniu OPIEKA(6,2): kol.2-7")
print(f"  Komórka (6,8) = {repr(g1b.grid[6][8])} (powinno być puste '')")
can_place_after = g1b.can_place_word("AWANS", 6, 8, Direction.HORIZONTAL)
status2 = PASS if not can_place_after else FAIL
print(f"{status2} can_place_word('AWANS', 6, 8, H) = {can_place_after}")
print(f"   Oczekiwane: False (AWANS zaczynałby tuż za OPIEKA → OPIEKAAWANS)")


section("SCENARIUSZ 2: Błąd DDYPLOM (litera PRZED słowem)")

g2 = CrosswordGrid(15, 15)
g2.grid[8][1] = 'D'
print(f"\n[Setup] Komórka (8,1) = 'D' (symulacja litery przed słowem)")

result2 = g2.can_place_word("DYPLOM", 8, 2, Direction.HORIZONTAL)
status3 = PASS if not result2 else FAIL
print(f"{status3} can_place_word('DYPLOM', 8, 2, H) = {result2}")
print(f"   Oczekiwane: False ('D' na kol.1 + DYPLOM od kol.2 → DDYPLOM)")

if not result2:
    print(f"{PASS} Błąd DDYPLOM WYELIMINOWANY — boundary check przed słowem działa!")
else:
    print(f"{FAIL} BŁĄD NADAL ISTNIEJE — boundary check przed słowem nie wykrywa!")


section("SCENARIUSZ 3: Błąd PPORZĄDEK (litera NAD słowem pionowym)")

g3 = CrosswordGrid(15, 15)
g3.grid[2][5] = 'P'
print(f"\n[Setup] Komórka (2,5) = 'P' (litera nad słowem pionowym)")

result3 = g3.can_place_word("PORZADEK", 3, 5, Direction.VERTICAL)
status4 = PASS if not result3 else FAIL
print(f"{status4} can_place_word('PORZADEK', 3, 5, V) = {result3}")
print(f"   Oczekiwane: False ('P' w wierszu 2 + PORZADEK od wiersza 3 → PPORZADEK)")

if not result3:
    print(f"{PASS} Błąd PPORZĄDEK WYELIMINOWANY!")
else:
    print(f"{FAIL} BŁĄD NADAL ISTNIEJE — boundary check nad słowem pionowym!")


section("ANALIZA GĘSTOŚCI: Siatka po kilku słowach")

g4 = CrosswordGrid(15, 15)
words_to_place = [
    ("KARIERA", 0, 0, Direction.HORIZONTAL),
    ("ATELA",   0, 2, Direction.VERTICAL),   # A(0,2) T(1,2) E(2,2) L(3,2) A(4,2)
    ("EKO",     2, 2, Direction.HORIZONTAL), # E(2,2) K(2,3) O(2,4) — E skrzyżowane z ATELA
    ("ODA",     2, 4, Direction.VERTICAL),   # O(2,4) D(3,4) A(4,4) — O skrzyżowane z EKO
]

placed = 0
for word, r, c, d in words_to_place:
    ok = g4.place_word(word, r, c, d, "test")
    if ok:
        placed += 1
        print(f"  ✓ Umieszczono: {word:10} @ ({r},{c}) {'H' if d == Direction.HORIZONTAL else 'V'}")
    else:
        print(f"  ✗ Nie można:   {word:10} @ ({r},{c}) {'H' if d == Direction.HORIZONTAL else 'V'}")

print(f"\nUmieszczone słowa: {placed}/{len(words_to_place)}")
density = g4.get_density()
filled = g4.get_filled_count()
print(f"Gęstość siatki: {filled}/{15*15} = {density:.1f}%")

print(f"\n--- Siatka (pierwsze 8 wierszy) ---")
for r in range(8):
    row_str = ""
    for c in range(15):
        cell = g4.grid[r][c]
        if cell is None:
            row_str += "█"
        elif cell == "":
            row_str += "·"
        else:
            row_str += cell
    print(f"  {r}: {row_str}")


section("PODSUMOWANIE NAPRAW")

all_fixed = (not result) and (not result2) and (not result3)
if all_fixed:
    print(f"\n{PASS} Wszystkie 3 błędy malformed words zostały WYELIMINOWANE!")
    print(f"   - OPIEKAA: boundary check po słowie działa")
    print(f"   - DDYPLOM: boundary check przed słowem działa")
    print(f"   - PPORZĄDEK: boundary check nad słowem pionowym działa")
else:
    print(f"\n{FAIL} Nadal istnieją błędy — sprawdź can_place_word() w crossword_grid.py")
    if result:
        print(f"   - OPIEKAA: NIE NAPRAWIONE")
    if result2:
        print(f"   - DDYPLOM: NIE NAPRAWIONE")
    if result3:
        print(f"   - PPORZĄDEK: NIE NAPRAWIONE")

print()
