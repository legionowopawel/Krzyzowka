# CRITICAL BUGS ANALYSIS
**Date:** May 26, 2026  
**Status:** Active Investigation  

## Summary
Despite previous fixes for word duplication and density, THREE CRITICAL BUGS still persist:

1. **Malformed Words** (OPIEKAA, DDYPLOM, PPORZĄDEK)
2. **Wrong Words Used** (Random database selection instead of planned clue list)
3. **Boundary Check Failure** (DDYPLOM scenario shows can_place_word returns True when it should return False)

---

## BUG #1: WRONG WORDS USED (ARCHITECTURE PROBLEM)

### Problem Description
The generator is supposed to use words from a **planned clue list** (e.g., from 002.txt with 15 specific words: ZADANIE, BLISKO, TERAPIA, DOŚWIADCZENIE, etc.)

**What actually happens:**
- Generator freely selects ANY word from the 100-word database (baza.txt)
- Result: Only 4 of 15 planned words appear in final grid
- 11 slots filled with random database words (KARIERA, PRACA, INTEGRACJA, etc.)

### Evidence
User report shows:
- **Planned:** ZADANIE, BLISKO, TERAPIA, DOŚWIADCZENIE, MALOWANIE, NARZĘDZIA, LIŚCIE, EKIPA, PATELNIA, AWANS, SZACUNEK, DORADCA, ŚRUBKA, DYPLOM, ETAT (15 words from clue file)
- **Actually used:** Only DOŚWIADCZENIE, ŚRUBKA, DORADCA, AWANS (4 words)
- **Extra words not in plan:** KARIERA, PRACA, INTEGRACJA, SPOTKANIE, CV, CEL, KAWA, GRUPA

### Code Analysis
**File:** `word_source.py`
**File:** `crossword_strategies.py` lines 402-510 (`_find_matching_words` function)  
**File:** `crossword_orchestrator.py` (no planned words mechanism)

**Current logic:**
```python
# crossword_strategies.py line ~418
for word_len in range(2, min(15, max_len + 1)):
    for word in self.word_source.get_words_by_length(word_len):
        # No constraint to check if word is in planned list!
```

**Missing logic:**
- No parameter for "planned_words" or "required_words"
- Generator has NO knowledge of which words MUST be used
- selects purely by availability and scoring

### Fix Strategy
**Option 1** (Recommended): Add planned words constraint to MultiStrategyGenerator
- Accept optional `planned_words: List[str]` parameter
- Modify `_find_matching_words()` to prioritize/filter for planned words
- In orchestrator, load planned words from clue file before generation

**Option 2**: Modify WordSource to support "active" word lists
- Add `set_active_words(words)` method
- Modify `get_words_by_length()` to filter only active words

### Root Cause
**Architectural:** Generator treats all words equally and doesn't distinguish between:
- Words that MUST appear (planned/required)
- Words that CAN appear (optional filler)

---

## BUG #2: BOUNDARY CHECK FAILURE (DDYPLOM CASE)

### Problem Description
When D is placed at (8,1), boundary check allows DYPLOM at (8,2), creating DDYPLOM

### Test Results
```
[Scenario 2] Direct boundary check
  D placed at (8, 1)
  Trying to place DYPLOM at (8, 2)
  Can place? True             << WRONG! Should be False
  Would create: DDYPLOM
```

### Expected Behavior
- Cell (8,1) has 'D'
- Trying to place DYPLOM at (8,2-7)
- **Must reject because:** Cell (8,1) is non-empty and adjacent to (8,2)

### Code Analysis
**File:** `crossword_grid.py` lines 97-108 (horizontal boundary check)

```python
# Line 97-108: Check before position
if col > 0:
    before = self.grid[row][col - 1]
    if before and before != "":
        return False  # Position already has something before it
```

**Problem:** The check ONLY validates the IMMEDIATE preceding cell
- It checks: Is cell at (col-1) empty/None?
- For DYPLOM at (8,2):  checks if (8,1) is empty
- But (8,1) has 'D' from previous placement
- Result: Should reject but doesn't?

**Wait - this should work!** If (8,1) has 'D', then `before != ""` is True, so should return False

**Hypothesis:** The boundary check IS working, but the word isn't being rejected when placed?  OR...

### Deeper Issue
**Possibility 1:** `can_place_word()` passes but `place_word()` creates the malformed word
**Possibility 2:** The grid cell at (8,1) is being stored as empty string "" instead of None/letter
**Possibility 3:** The perpendicular word validation is allowing it to pass

### Required Fix
1. Verify boundary check logic is being called
2. Ensure grid cells store letters correctly (not empty strings)
3. Add unit tests for this exact scenario
4. If still fails, check perpendicular word formation

---

## BUG #3: MALFORMED WORDS (OPIEKAA, PPORZĄDEK)

### Problem Description
Words appear with doubled letters:
- OPIEKAA (should be OPIEKA or separate A)
- DDYPLOM (D + DYPLOM merged)
- PPORZĄDEK (P + PORZĄDEK merged)

### Hypothesis
**Source:** Perpendicular word validation NOT preventing invalid crossing combinations

**Example:** 
- OPIEKA placed horizontally at (6,2-7)
- Boundary check should reject any word at (6,8) because it would merge
- BUT perpendicular word validation might be saying "the crossing is valid"

### Code Analysis
**File:** `crossword_grid.py` lines 263-330 (`_get_perpendicular_words` method)  
**File:** `crossword_grid.py` lines 225-239 (`place_word` validation)

```python
# place_word calls _get_perpendicular_words
perpendicular = self._get_perpendicular_words(word, row, col, direction)
# This checks if perpendicular words are valid, but...
# Does it prevent MERGING with adjacent letters?
```

### Fix Strategy
1. Enhance boundary check to be more aggressive
2. Verify that perpendicular word validation catches attempted merges
3. Add explicit check: adjacent non-empty cell = REJECT

---

## PROPOSED SOLUTIONS (Priority Order)

### Priority 1: Fix Wrong Words Bug (CRITICAL)
**Impact:** Users get completely wrong grids  
**Fix:** Implement word constraint system
- `MultiStrategyGenerator.set_planned_words(words: List[str])`
- Modify `_find_matching_words()` to consider planned status
- Update orchestrator to load and pass planned words

### Priority 2: Fix Boundary Check Edge Case
**Impact:** Malformed words still appear  
**Fix:** 
- Add explicit adjacent cell validation
- Create unit test for DDYPLOM scenario
- Run diagnostic on can_place_word() to verify it's actually rejecting

### Priority 3: Verify Malformed Word Prevention
**Impact:** Grid integrity  
**Fix:**
- Enhanced perpendicular word validation
- Test extraction logic vs. storage logic

---

## TESTING EVIDENCE NEEDED

1. ✅ Boundary checks: PASS on simple cases, UNKNOWN on complex cases
2. ❌ Malformed word prevention: NOT WORKING (user reports show OPIEKAA, DDYPLOM)
3. ❌ Planned words constraint: NO MECHANISM EXISTS
4. ❓ Word extraction: placed_words vs. scanned grid discrepancies

---

## Next Steps
1. Implement planned words constraint (Priority 1)
2. Fix boundary check for DDYPLOM case (Priority 2)
3. Run full test suite with user's expected output
4. Generate and verify output matches planned words list
