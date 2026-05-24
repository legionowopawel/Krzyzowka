# ANALIZA ZAGĘSZCZENIA SIATKI - PROBLEMY I ROZWIĄZANIA
**Data:** 25-05-2026  
**Cel:** Minimalizacja pustych pól w krzyżówce

---

## 🔴 PROBLEMY ZNALEZIONE

### 1. **_mark_empty_cells_black jest zbyt konserwatywna**
**Lokalizacja:** `crossword_strategies.py:1067-1083`

**Problem:**
```python
# AKTUALNE (zbyt liberalne):
if not has_any_letter_in_row and not has_any_letter_in_col:
    grid.grid[r][c] = None
```

Pole staje się czarne TYLKO gdy nie ma ŻADNEJ litery w całym wierszu I całej kolumnie. To oznacza, że pola mogą być białe (puste "") nawet jeśli są całkowicie izolowane od możliwości wszysienia.

**Konsekwencja:** Siatka zawiera dużo białych pól bez litery, co zmniejsza gęstość.

**Rozwiązanie:** Zmienić logikę na bardziej agresywną - pole staje się czarne, gdy nie ma szansy być częścią jakiegokolwiek wyrazu:

```python
# PROPONOWANE (agresywne):
if grid.grid[r][c] != "" or grid.grid[r][c] is None:
    continue

# Pole może być czarne, jeśli:
# - Ma sąsiada z literą, ale żaden kierunek nie może zmieścić wyrazu
if self._is_truly_dead_cell(grid, r, c):
    grid.grid[r][c] = None
```

---

### 2. **_aggressive_density_fill - sekwencyjne umieszczanie zamiast równoczesnego**
**Lokalizacja:** `crossword_strategies.py:498-529`

**Problem:**
```python
# AKTUALNE:
placed_h = False
for word in h_words[:h_limit]:
    if grid.place_word(word, row, col, Direction.HORIZONTAL, ...):
        placed_count += 1
        placed_h = True
        break  # <--- PROBLEM: przeryw po pierwszym sukcesie

placed_v = False
for word in v_words[:v_limit]:
    # TEN KOD SIĘ NIGDY NIE WYKONUJE, jeśli placed_h=True
```

Algorytm ustawia słowo poziome, a następnie przechodzi do następnej komórki. Nigdy nie sprawdza, czy w tej samej komórce można ustawić słowo pionowe TAKŻE.

**Konsekwencja:** Wiele komórek jest tylko częściowo wykorzystane (H XOR V, a nie H AND V).

**Rozwiązanie:** Spróbuj umieszczać ZARÓWNO poziomo JAK I PIONOWO dla każdej komórki:

```python
# PROPONOWANE:
for row, col in empty_cells[:check_limit]:
    h_words = self._find_matching_words_density(...)
    v_words = self._find_matching_words_density(...)
    
    # Spróbuj OBYDWA kierunki (nie break!)
    for word in h_words[:h_limit]:
        if grid.place_word(..., Direction.HORIZONTAL, ...):
            placed_set.add(word.upper())
            placed_count += 1
            break
    
    # ZAWSZE spróbuj pionowo, niezależnie od rezultatu H
    for word in v_words[:v_limit]:
        if word.upper() not in placed_set and grid.place_word(..., Direction.VERTICAL, ...):
            placed_set.add(word.upper())
            placed_count += 1
            break
```

---

### 3. **check_limit w _aggressive_density_fill jest za mały**
**Lokalizacja:** `crossword_strategies.py:502`

**Problem:**
```python
check_limit = min(len(empty_cells), 80)
```

Dla siatki 15×15 (225 pól) jeśli jest 150 pustych pól, sprawdzamy tylko ~53%. Za mało!

**Rozwiązanie:** Zwiększyć do 100% albo minimum 150:

```python
# PROPONOWANE:
check_limit = max(len(empty_cells), min(len(empty_cells), 150))  # minimum 150 komórek
```

---

### 4. **_word_density_score - niedostateczna premia za wypełnienie**
**Lokalizacja:** `crossword_strategies.py:878-923`

**Problem:**
```python
# AKTUALNE:
new_cells = 0 + 3 za każdą NOWĄ literę
intersections = 0 + 10 za każde przecięcie
cross_adj = 0 + 2 za sąsiada prostopadłego
user_bonus = 500
```

Dla słowa 5-literowego, które wypełnia 5 nowych pól:
- Score = 500 (user_bonus) + 15 (5×3 nowe pola) + mogły być przecięcia = ~515

To jest mało porównane do dłuższych słów ze słabymi wynikami. Priorytet: gęstość, nie długość.

**Rozwiązanie:** Drast<br>ycznie podnieść premię za nowe pola:

```python
# PROPONOWANE:
new_cells = 0 + 20 za każdą NOWĄ literę (nie 3!)
intersections = 0 + 15 za każde przecięcie (było 10)
cross_adj = 0 + 5 za sąsiada prostopadłego (było 2)
user_bonus = 100 (było 500 - zmienić priorytet!)
```

---

### 5. **Brak logiki "fill-all-connectivity"**
**Lokalizacja:** Brak w kodzie

**Problem:** Nie ma metody, która sprawdza czy dwa białe pola mogą być połączone wyrazem. Jeśli mogą - MUSZĄ być.

**Konsekwencja:** Pozostawiane są pola, które mogłyby być logicznie połączone.

**Rozwiązanie:** Dodać metodę `_force_connectivity`:

```python
def _force_connectivity(self, grid: CrosswordGrid) -> int:
    """
    Zbierz grupy białych pól, które mogą być połączone wyrazem.
    Spróbuj je wszystkie wypełnić.
    """
    # Dla każdej grupy sąsiednich białych pól, spróbuj umieścić wyraz
```

---

### 6. **_place_edge_words używa +1 separator, co zmarnuje miejsce**
**Lokalizacja:** `crossword_strategies.py:419-432`

**Problem:**
```python
col += len(word) + 1  # +1 = czarny separator
```

Na górnej krawędzi, jeśli umieszczeń "PRACA" (5 liter), następne słowo zaczyna się w kolumnie 6. To marnuje miejsce!

**Rozwiązanie:** Separator powinien być czarnym polem (None), które zostanie wpisane, lub wyraz powinien kończyć się tuż przy następnym:

```python
# PROPONOWANE:
col += len(word)  # brak separatora
# Jeśli potrzeba przerwy, grid.place_word zajmie się czarnymi polami automatycznie
```

---

## ✅ REKOMENDOWANE ZMIANY (PRIORYTET)

### Priority 1 - KRYTYCZNE (duży wpływ na gęstość)

**1. Zmienić _mark_empty_cells_black → bardziej agresywna**
- Szukać pól całkowicie izolowanych (brak szansy na wyraz)
- Nie markować pola na czarno, jeśli ma sąsiada z literą

**2. Naprawić _aggressive_density_fill - umieszczanie w OBU kierunkach**
- Usunąć `break` po pierwszym sukcesie H
- Zawsze próbować V, niezależnie od H
- Zwiększyć check_limit do 150+

**3. Zmienić scoring w _word_density_score**
- new_cells: 3 → 20 (priorytet gęstości!)
- intersections: 10 → 15
- cross_adj: 2 → 5
- user_bonus: 500 → 100

### Priority 2 - WAŻNE (średni wpływ)

**4. Dodać _force_connectivity()**
- Wypełnianie przerw między wyrazami
- Łączenie izolowanych grup pól

**5. Zmienić _place_edge_words - brak separatorów**
- col += len(word) zamiast +1
- row += len(word) zamiast +1

### Priority 3 - ULEPSZENIA (małe wpływy)

**6. Zwiększyć backtrack_depth dla EDGE_FIRST**
- Było: 200, zaproponować: 300-400

**7. Włączyć EDGE_FIRST domyślnie**
- Jest zdefiniowana ale nieużywana
- To powinna być domyślna strategia!

---

## 📊 SPODZIEWANE REZULTATY

| Metrika | Przed | Po |
|---------|-------|-----|
| Gęstość | 50-52% | 70-75% |
| Puste pola | ~48-50% | ~25-30% |
| Czarne pola | ~10-15% | ~5-10% |
| Słowa na siatce | 20-23 | 30-40 |
| Czas generacji | <2min | 2-5min |

---

## 🔨 IMPLEMENTACJA

Proponuję wykonać zmiany w tej kolejności:

1. **crossword_strategies.py:1067-1083** - _mark_empty_cells_black (agresywu...)
2. **crossword_strategies.py:498-529** - _aggressive_density_fill (oba kierunki)
3. **crossword_strategies.py:878-923** - _word_density_score (scoring)
4. **crossword_strategies.py:414** - _place_edge_words (bez separatorów)
5. Nowa metoda: _force_connectivity()
6. **main.py / orchestrator** - włączyć EDGE_FIRST domyślnie

---

## UWAGI

- Zmiana w scoring'u wpłynie na WSZYSTKIE strategie (nie tylko EDGE_FIRST)
- Zwiększenie agresji backtrackingu może wydłużyć czas generacji (do zaakceptowania)
- Należy testować na zbiorach słów 50, 100, 200+ aby zweryfikować skalowanie
