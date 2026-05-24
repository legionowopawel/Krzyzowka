# -*- coding: utf-8 -*-
"""
Test user word guarantee mechanism.

Verify that all planned_words are placed in the final grid (CRITICAL requirement).
User said: "chcę by pojawiały się n a krzyżówce nawet jak przejdziesz do następnego etapu"
(I want them to appear on crossword even when you move to next stage)
"""

from crossword_strategies import StrategyBasedGenerator, StrategyConfig, StartingStrategy
from crossword_grid import CrosswordGrid
from word_source import WordSource

# Prepare test data
word_source = WordSource("baza_wyrazow/baza.txt")

# Sample planned words to guarantee
planned_words = {
    "PIOTRKOWSKI",
    "BIURO",
    "NAPRAWA",
    "DYREKTOR",
    "PRACOWNIK",
}

def test_user_words_guarantee():
    """Test that user words are guaranteed to appear in final grid."""
    
    print("\n" + "="*70)
    print("TEST: User Words Guarantee Mechanism")
    print("="*70)
    print(f"Planned words to guarantee: {planned_words}")
    print()
    
    # Test with standard strategy
    config = StrategyConfig(
        name="Test_User_Words",
        starting_strategy=StartingStrategy.EDGE_FIRST,
        max_iterations=3,
        backtrack_depth=250,
        aggressive_fill=True,
        edge_first=True,
    )
    
    generator = StrategyBasedGenerator(
        config=config,
        word_source=word_source,
        planned_words=planned_words,
    )
    
    # Generate grid
    grid = generator.generate(20, 20)
    
    # Check results
    print(f"Generated grid: {grid.width}x{grid.height}")
    print(f"Words placed: {len(grid.placed_words)}")
    print(f"Density: {grid.get_density():.1%}")
    print()
    
    # Extract user words from placed_words
    placed_words_upper = {w.upper() for w, _, _, _, _ in grid.placed_words}
    
    print("Checking user words in final grid:")
    print("-" * 70)
    
    all_found = True
    for planned_word in planned_words:
        word_upper = planned_word.upper()
        is_present = word_upper in placed_words_upper
        status = "✓ FOUND" if is_present else "✗ MISSING"
        print(f"  {planned_word:20} -> {status}")
        if not is_present:
            all_found = False
    
    print("-" * 70)
    
    if all_found:
        print("\n✓ SUCCESS: All user words present in final grid!")
        print("  The guarantee mechanism is working correctly.")
    else:
        print("\n✗ FAILURE: Some user words are missing from final grid!")
        print("  The guarantee mechanism needs debugging.")
    
    print()
    return all_found


def test_edge_first_with_user_words():
    """Test EDGE_FIRST strategy specifically."""
    
    print("\n" + "="*70)
    print("TEST: EDGE_FIRST Strategy with User Words")
    print("="*70)
    
    test_words = {"KRZYŻÓWKA", "SŁOWO", "PUZZLE", "ZAGADKA"}
    
    print(f"Testing with: {test_words}")
    print()
    
    config = StrategyConfig(
        name="EDGE_FIRST Test",
        starting_strategy=StartingStrategy.EDGE_FIRST,
        max_iterations=5,
        backtrack_depth=350,
        aggressive_fill=True,
        edge_first=True,
    )
    
    generator = StrategyBasedGenerator(
        config=config,
        word_source=word_source,
        planned_words=test_words,
    )
    
    results = []
    for attempt in range(3):
        print(f"Attempt {attempt + 1}/3...")
        grid = generator.generate(18, 18)
        
        placed_words_upper = {w.upper() for w, _, _, _, _ in grid.placed_words}
        found = {w for w in test_words if w.upper() in placed_words_upper}
        
        results.append({
            'density': grid.get_density(),
            'words_count': len(grid.placed_words),
            'user_words_found': len(found),
            'total_user_words': len(test_words),
        })
        
        print(f"  Density: {grid.get_density():.1%}, Words: {len(grid.placed_words)}, "
              f"User words: {len(found)}/{len(test_words)}")
    
    print()
    avg_density = sum(r['density'] for r in results) / len(results)
    avg_user_words = sum(r['user_words_found'] for r in results) / len(results)
    
    print(f"Average density: {avg_density:.1%}")
    print(f"Average user words found: {avg_user_words:.1f}/{len(test_words)}")
    
    print()


if __name__ == "__main__":
    # Run tests
    success = test_user_words_guarantee()
    test_edge_first_with_user_words()
    
    if success:
        print("\n✓ ALL TESTS PASSED")
    else:
        print("\n✗ TESTS FAILED - User word guarantee not working")
