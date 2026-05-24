#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostyka: Pełne testy graniczne siatki krzyżówki
Sprawdza: DDYPLOM, OPIEKAA, PPORZĄDEK, przecięcia, cross-wordy
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from crossword_grid import CrosswordGrid, Direction

PASS = "✅ PASS"
FAIL = "❌ FAIL"

def check(label, condition, expected=True):
    status = PASS if condition == expected else FAIL
    exp_str = "True" if expected else "False"
    got_str = "True" if condition else "False"
    print(f"  {status}  {label}")
    if condition != expected:
        print(f"        Oczekiwano: {exp_str}, Otrzymano: {got_str}")
    return condition == expected

results = []

print("=" * 70)
print("TESTY GRANICZNE — crossword_grid.can_place_word()")
print("=" * 70)

# --- Blok 1: Granice (boundary checks) ---
print("\n[Blok 1] Sprawdzanie granic (boundary checks)\n")

# Test 1.1: Litera PRZED słowem — musi odrzucić (DDYPLOM case)
g = CrosswordGrid(15, 15)
g.grid[5][2] = 'D'
results.append(check(
    "Litera 'D' przed (5,3) → 'DYPLOM' poziomo (5,3) musi ODRZUCIĆ [DDYPLOM fix]",
    g.can_place_word("DYPLOM", 5, 3, Direction.HORIZONTAL),
    expected=False
))

# Test 1.2: Litera ZA słowem — musi odrzucić (OPIEKAA case)
g2 = CrosswordGrid(15, 15)
g2.grid[6][8] = 'A'
results.append(check(
    "Litera 'A' za (6,8) → 'OPIEKA' poziomo (6,2) kończy na (6,7), musi ODRZUCIĆ [OPIEKAA fix]",
    g2.can_place_word("OPIEKA", 6, 2, Direction.HORIZONTAL),
    expected=False
))

# Test 1.3: Litera nad słowem pionowym — musi odrzucić (PPORZĄDEK case)
g3 = CrosswordGrid(15, 15)
g3.grid[2][4] = 'P'
results.append(check(
    "Litera 'P' nad (2,4) → 'PORZADEK' pionowo (3,4) musi ODRZUCIĆ [PPORZĄDEK fix]",
    g3.can_place_word("PORZADEK", 3, 4, Direction.VERTICAL),
    expected=False
))

# Test 1.4: Litera pod słowem pionowym — musi odrzucić
g4 = CrosswordGrid(15, 15)
g4.grid[12][4] = 'X'
results.append(check(
    "Litera 'X' pod (12,4) → słowo 8-lit. pionowe (4,4) musi ODRZUCIĆ",
    g4.can_place_word("ABCDEFGH", 4, 4, Direction.VERTICAL),
    expected=False
))

# Test 1.5: Czyste granice — musi zaakceptować
g5 = CrosswordGrid(15, 15)
results.append(check(
    "Brak sąsiadów → 'TEST' poziomo (5,3) musi ZAAKCEPTOWAĆ",
    g5.can_place_word("TEST", 5, 3, Direction.HORIZONTAL),
    expected=True
))

# Test 1.6: Słowo wychodzi poza siatkę — musi odrzucić
g6 = CrosswordGrid(10, 10)
results.append(check(
    "Słowo 8-lit. zaczynające na kol. 5 w siatce 10-szer. musi ODRZUCIĆ (5+8=13>10)",
    g6.can_place_word("ABCDEFGH", 5, 5, Direction.HORIZONTAL),
    expected=False
))

# --- Blok 2: Przecięcia ---
print("\n[Blok 2] Wymaganie przecięć\n")

# Test 2.1: Pierwsze słowo nie wymaga przecięcia
g7 = CrosswordGrid(15, 15)
results.append(check(
    "Pierwsze słowo (siatka pusta) → brak wymagania przecięcia",
    g7.can_place_word("KARIERA", 5, 3, Direction.HORIZONTAL),
    expected=True
))

# Test 2.2: Drugie słowo musi mieć przecięcie
g8 = CrosswordGrid(15, 15)
g8.place_word("KARIERA", 5, 3, Direction.HORIZONTAL, "test")
# Słowo poziome w innym wierszu bez żadnego wspólnego punktu → odrzucić
results.append(check(
    "Drugie słowo bez żadnego połączenia z siatką musi ODRZUCIĆ",
    g8.can_place_word("BIURO", 9, 9, Direction.HORIZONTAL),
    expected=False
))

# Test 2.3: Drugie słowo z prawdziwym przecięciem — zaakceptować
g9 = CrosswordGrid(15, 15)
g9.place_word("KARIERA", 5, 3, Direction.HORIZONTAL, "test")
# K(5,3) A(5,4) R(5,5) I(5,6) E(5,7) R(5,8) A(5,9)
# Słowo pionowe przez 'A' na (5,9): jeśli słowo AWANS i A pasuje na (5,9)
# Spróbuj z dowolnym słowem zaczynającym się od A w (3,9) pionowo
# tak żeby A lądowało na (5,9)
# ATAKI: A(3,9) T(4,9) A(5,9) ← przecięcie z KARIERA K.A.R.I.E.R.A, A jest na (5,9)
g9_result = g9.can_place_word("ABA", 5, 9, Direction.VERTICAL)  # A pasuje (5,9)
results.append(check(
    "Słowo pionowe trafiające w literę istniejącego słowa musi ZAAKCEPTOWAĆ",
    g9_result,
    expected=True
))

# --- Blok 3: Cross-word validation ---
print("\n[Blok 3] Walidacja cross-wordów (słów prostopadłych)\n")

# Test 3.1: Umieść KARIERA poziomo, sprawdź prostopadłe
g10 = CrosswordGrid(15, 15)
g10.place_word("KARIERA", 5, 3, Direction.HORIZONTAL, "test")
print(f"  [Setup] KARIERA umieszczona na (5,3) poziomo: K(5,3) A(5,4) R(5,5) I(5,6) E(5,7) R(5,8) A(5,9)")

# Słowo pionowe: ETAT w kol. 7 (E na (3,7), T(4,7), A(5,7)=E z KARIERA — NIEZGODNE)
# E z KARIERA jest na (5,7), więc jeśli chcemy przejść przez to E,
# pionowe słowo musi mieć 'E' na pozycji odpowiadającej wierszowi 5
bad_cross = g10.can_place_word("ATUT", 3, 7, Direction.VERTICAL)
# A(3,7) T(4,7) U(5,7)← powinno być E, U != E → ODRZUCIĆ
results.append(check(
    "Słowo pionowe z niezgodną literą w miejscu przecięcia musi ODRZUCIĆ",
    bad_cross,
    expected=False
))

# Test 3.2: Pionowe słowo z pasującą literą na przecięciu
good_cross = g10.can_place_word("ATELA", 3, 7, Direction.VERTICAL)
# A(3,7) T(4,7) E(5,7)← pasuje do KARIERA R E... czekaj:
# KARIERA: K=3, A=4, R=5, I=6, E=7, R=8, A=9 (kolumny)
# Na (5,7) jest 'E' — słowo pionowe musi mieć 'E' na pozycji i gdzie row+i=5 → i=5-3=2
# ATELA: A(i=0,row=3) T(i=1,row=4) E(i=2,row=5) ← pasuje! L(row=6) A(row=7)
results.append(check(
    "Pionowe 'ATELA' przez 'E' z KARIERA na (3,7) musi ZAAKCEPTOWAĆ",
    good_cross,
    expected=True
))

# --- Blok 4: Wymuszenie zwartości siatki ---
print("\n[Blok 4] Test zagęszczenia (density check)\n")

g11 = CrosswordGrid(15, 15)
g11.place_word("KARIERA", 5, 3, Direction.HORIZONTAL, "test")
g11.place_word("ATELA", 3, 7, Direction.VERTICAL, "test")

density = g11.get_density()
filled = g11.get_filled_count()
total = 15 * 15
results.append(check(
    f"Po 2 słowach: {filled}/{total} komórek wypełnionych ({density:.1f}%) > 0%",
    filled > 0,
    expected=True
))

# --- Podsumowanie ---
print("\n" + "=" * 70)
passed = sum(1 for r in results if r)
total_tests = len(results)
print(f"WYNIK: {passed}/{total_tests} testów zaliczonych")
if passed == total_tests:
    print("✅ Wszystkie testy przeszły!")
else:
    print(f"❌ {total_tests - passed} testów nie przeszło — sprawdź crossword_grid.py")
print("=" * 70)
