#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test to compare placed_words vs. extracted words
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from word_source import WordSource
from crossword_strategies import MultiStrategyGenerator

word_source = WordSource("baza_wyrazow/baza.txt")

print("="*70)
print("TESTING: placed_words vs extracted_words")
print("="*70 + "\n")

generator = MultiStrategyGenerator(word_source)
results = generator.generate_all_strategies(width=15, height=15)

if not results:
    print("Generation failed!")
    sys.exit(1)

# Get the best one
result = results[0]
grid = result.grid

if not grid:
    print("No grid generated!")
    sys.exit(1)

print(f"[Grid] Placed words count: {len(grid.placed_words)}\n")

print("[PLACED_WORDS]:")
print("-" * 70)
placed_set = set()
for word, row, col, direction, clue in grid.placed_words:
    placed_set.add(word.upper())
    direction_str = "H" if direction.value == "H" else "V"
    print(f"  {word:20} at ({row:2},{col:2}) {direction_str}")

print(f"\nTotal in placed_words: {len(placed_set)} unique words\n")

# Extract words by scanning grid
print("[EXTRACTED_WORDS from grid]:")
print("-" * 70)

extracted_words = []

# Horizontal
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
                word = "".join(buf).upper()
                extracted_words.append(word)
                print(f"  H({r:2},{c:2}): {word}")
            c = cc
        else:
            c += 1

# Vertical
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
                word = "".join(buf).upper()
                extracted_words.append(word)
                print(f"  V({r:2},{c:2}): {word}")
            r = rr
        else:
            r += 1

extracted_set = set(extracted_words)
print(f"\nTotal extracted: {len(extracted_set)} unique words\n")

print("[DISCREPANCIES]:")
print("-" * 70)

only_in_placed = placed_set - extracted_set
only_in_extracted = extracted_set - placed_set

if only_in_placed:
    print(f"In placed_words but NOT extracted: {sorted(only_in_placed)}")
else:
    print("✓ No words missing from extraction")

if only_in_extracted:
    print(f"In extracted but NOT placed_words: {sorted(only_in_extracted)}")
else:
    print("✓ No extra words in extraction")

# Look for malformed
print("\n[MALFORMED WORDS?]:")
print("-" * 70)
malformed_keywords = ["AA", "DD", "PP", "EE", "SS", "LL", "KK", "ZZ", "NN"]

malformed = [w for w in extracted_set if any(p in w for p in malformed_keywords)]
if malformed:
    print(f"Found in extracted: {sorted(malformed)}")
else:
    print("None found in extracted words")

malformed_placed = [w for w in placed_set if any(p in w for p in malformed_keywords)]
if malformed_placed:
    print(f"Found in placed_words: {sorted(malformed_placed)}")
else:
    print("None found in placed_words")
