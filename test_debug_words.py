# -*- coding: utf-8 -*-
"""
Simple debug test for user words guarantee.
"""

from crossword_strategies import StrategyBasedGenerator, StrategyConfig, StartingStrategy
from crossword_grid import CrosswordGrid, Direction
from word_source import WordSource

word_source = WordSource("baza_wyrazow/baza.txt")

def test_simple():
    """Very simple test - just try to place user words."""
    
    # Create a grid directly and try to place words
    grid = CrosswordGrid(20, 20)
    
    # Place a first word manually to create structure
    grid.place_word("KRZYŻÓWKA", 5, 5, Direction.HORIZONTAL, "Test puzzle", word_source)
    
    print(f"Grid state after first word:")
    print(f"  Words: {len(grid.placed_words)}")
    print(f"  Placed: {[w for w, _, _, _, _ in grid.placed_words]}")
    print()
    
    # Now try to place user words at various positions
    test_words = ["BIURO", "NAPRAWA", "TEST"]
    
    print("Trying to place additional words:")
    for word in test_words:
        print(f"\n  Word: {word}")
        placed = False
        
        # Try H
        for row in range(grid.height - len(word) + 1):
            for col in range(grid.width - len(word) + 1):
                valid_set = set(word.upper() for word in word_source.get_all_words()) | {w.upper() for w, _, _, _, _ in grid.placed_words}
                
                if grid.can_place_word(word, row, col, Direction.HORIZONTAL, valid_set):
                    if grid.place_word(word, row, col, Direction.HORIZONTAL, "Test", word_source):
                        print(f"    ✓ Placed at ({row}, {col}) HORIZONTAL")
                        placed = True
                        break
            if placed:
                break
        
        # Try V if not placed
        if not placed:
            for row in range(grid.height - len(word) + 1):
                for col in range(grid.width):
                    valid_set = set(word.upper() for word in word_source.get_all_words()) | {w.upper() for w, _, _, _, _ in grid.placed_words}
                    
                    if grid.can_place_word(word, row, col, Direction.VERTICAL, valid_set):
                        if grid.place_word(word, row, col, Direction.VERTICAL, "Test", word_source):
                            print(f"    ✓ Placed at ({row}, {col}) VERTICAL")
                            placed = True
                            break
                if placed:
                    break
        
        if not placed:
            print(f"    ✗ Could not place")
    
    print()
    print(f"Final grid state:")
    print(f"  Words placed: {len(grid.placed_words)}")
    print(f"  Words: {[w for w, _, _, _, _ in grid.placed_words]}")


if __name__ == "__main__":
    test_simple()
