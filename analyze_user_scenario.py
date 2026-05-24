#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Detailed test of the exact scenario from user's report
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from word_source import WordSource
from crossword_grid import CrosswordGrid, Direction

word_source = WordSource("baza_wyrazow/baza.txt")

print("="*70)
print("USER's SCENARIO: Recreating reported errors")
print("="*70 + "\n")

# Test the exact boundary check logic
grid = CrosswordGrid(15, 15)

# The issue: "DDYPLOM instead of DYPLOM" 
# This means D at row 8, col 1 and then DYPLOM at row 8, cols 2-7
# Actually wait, let me reread...

user_grid_line_8 = ". . . E . N A U K A A . C . ."
print("User reports Row 8 as:", user_grid_line_8)
print("Which in the grid table is shown as DDYPLOM...")
print("Let me parse this: . . . E . . D Y P L O M C . .")
print("So: DYPLOM is at cols 7-12")
print("But user says it's DDYPLOM - extra D")
print("This could mean there's a D at col 6 too?\n")

# OR - let me check if the user means the REPORTED word list shows "DDYPLOM"
# when extracting from the grid...

# Simulate this:
grid.place_word("NAUKA", 8, 7, Direction.HORIZONTAL, "test", word_source)
print("[Placed] NAUKA at (8, 7)")

# Now try to place DYPLOM somewhere that would work
# If row 8 cols 7-12 are N-A-U-K-A-A, then DYPLOM can't fit
# But what if it's at a different row?

print("\n[Analysis] The actual problem might be:")
print("1. Words are being placed correctly with boundary checks")
print("2. But when EXTRACTED from the grid, the extraction logic")
print("   is reading adjacent cells incorrectly?")
print("3. OR the user is reading the grid visual output wrong?\n")

# Let me test extraction logic
grid2 = CrosswordGrid(15, 15)
grid2.place_word("DYPLOM", 5, 3, Direction.HORIZONTAL, "test", word_source)
print("[Placed] DYPLOM at (5, 3)")

# Extract using get_word_at - does it work correctly?
extracted_word = grid2.get_word_at(5, 3, Direction.HORIZONTAL)
print(f"[Extracted] get_word_at(5, 3, HORIZONTAL) = '{extracted_word}'")
print(f"Expected: 'DYPLOM'")

if extracted_word != "DYPLOM":
    print(f"ERROR: Got '{extracted_word}' instead of 'DYPLOM'!")
else:
    print("OK: Extraction is correct")

print("\n" + "="*70)
print("Checking if placed_words list is correct")
print("="*70 + "\n")

print(f"placed_words: {grid2.placed_words}")

print("\n" + "="*70)
