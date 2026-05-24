#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the planned words constraint implementation
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from word_source import WordSource
from crossword_strategies import MultiStrategyGenerator

# Setup
word_source = WordSource("baza_wyrazow/baza.txt")

# Define planned words (from user's expected list)
planned_words = [
    "ZADANIE",
    "BLISKO",
    "TERAPIA",
    "DOŚWIADCZENIE",
    "MALOWANIE",
    "NARZĘDZIA",
    "LIŚCIE",
    "EKIPA",
    "PATELNIA",
    "AWANS",
    "SZACUNEK",
    "DORADCA",
    "ŚRUBKA",
    "DYPLOM",
    "ETAT"
]

print("="*70)
print("TEST: Planned Words Constraint")
print("="*70 + "\n")

print(f"Planned words ({len(planned_words)}):")
for w in planned_words:
    print(f"  - {w}")

print("\n[Creating generator WITH planned words]")
generator = MultiStrategyGenerator(word_source, planned_words=planned_words)

print(f"Generator.planned_words: {generator.planned_words}")
print(f"Count: {len(generator.planned_words)}")

print("\n[Generating one grid]")
results = generator.generate_all_strategies(width=15, height=15)

if results:
    result = results[0]
    grid = result.grid
    
    print(f"\n[Result] Strategy: {result.strategy_name}")
    print(f"[Result] Words placed: {len(grid.placed_words)}")
    
    placed_words = [w.upper() for w, _, _, _, _ in grid.placed_words]
    placed_set = set(placed_words)
    
    # Check coverage
    planned_set = set(w.upper() for w in planned_words)
    
    covered = placed_set & planned_set
    missing = planned_set - placed_set
    extra = placed_set - planned_set
    
    print(f"\n[Analysis]")
    print(f"  Planned words appeared: {len(covered)}/{len(planned_set)}")
    if covered:
        print(f"    {sorted(covered)}")
    
    if missing:
        print(f"  Missing: {len(missing)} words")
        print(f"    {sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}")
    
    if extra:
        print(f"  Extra (not planned): {len(extra)} words")
        print(f"    {sorted(extra)[:5]}{'...' if len(extra) > 5 else ''}")
    
    print(f"\n✓ Test complete!")
else:
    print("Generation failed!")
