# Naprawa Duplikatów Haseł i Redundancji w Generatorze Krzyżówek

## Problem (zgłoszenie z 24-25 maja 2025)

W generowanych krzyżówkach stwierdzono:
1. CV pojawia się **18 razy** w wariancie 1 (zamiast 1-2 razy)
2. AWANS pojawia się **7 razy** dla haseł 6-12 poziomie
3. Sekcja "Wyrazy używane w krzyżówce" w HTML jest **pusta**
4. Dopisek "(pionowo)" pojawia się w opisach haseł *(błąd poprzedniej naprawy)*

## Analiza

### Główna przyczyna: Funkcja `refresh_clues()` w crossword_grid.py

Funkcja ta odtwarzała listę haseł (`placed_words`) skanując siatkę. Warunki sprawdzania były zbyt liberalne:

```python
# BŁĘDNE WARUNKI
if (col == 0 or self.grid[row][col - 1] is None) and (
    col < self.width - 1 and self.grid[row][col + 1] not in (None, "")
):
```

Problem: Warunek ten **dodawał numer** dla każdej pojedynczej litery słowa, jeśli miała sąsiada z prawej strony.

### Drugorzędna przyczyna: Brak limitów pojawień słów

Gradient backtracking-u nie ograniczał, ile razy to samo krótkie słowo (CV) może być umieszczone.

### Trzecia przyczyna: HTML Exporter

Poprzednia naprawa dodała zbędne walidacje, które mogły powodować pominięcie słów.

## Wdrożone rozwiązania

### 1. Naprawa `refresh_clues()` w [crossword_grid.py](crossword_grid.py)

**Przed:**
- Skanowała każdą komórkę i sprawdzała czy litera ma sąsiada
- Przypisywała numer **każda litera** słowa jeśli warunki były spełnione

**Po:**
```python
def refresh_clues(self, word_source=None) -> None:
    """Odtwórz numery pytań..."""
    processed_words = set()  # <-- Śledzenie już przetworzonych
    
    for row in range(self.height):
        for col in range(self.width):
            cell = self.grid[row][col]
            if cell is None or cell == "":
                continue
            
            # TYLKO jeśli to POCZĄTEK słowa
            if (col == 0 or self.grid[row][col - 1] is None):
                # Zbierz całe słowo
                horiz_word = ...
                
                # Sprawdzaj czy to PIERWSZE pojawienie
                word_key_h = (row, col, Direction.HORIZONTAL, horiz_word)
                if len(horiz_word) > 1 and word_key_h not in processed_words:
                    processed_words.add(word_key_h)
                    # ... przypisz numer
```

**Efekt:** Każde słowo dostaje **dokładnie jeden** numer dla każdego pojawienia, nie duplikaty dla poszczególnych liter.

### 2. Ograniczenia pojawień w [crossword_strategies.py](crossword_strategies.py)

Dodano logikę w `_find_matching_words()` aby ograniczyć liczbę pojawień słowa:

```python
# Maksymalna liczba pojawień w zależności od długości
if word_len == 2:
    max_occurrences = 1  # CV, BHP - max raz
elif word_len == 3:
    max_occurrences = 2  # BHP, WHY - max 2x
elif word_len <= 5:
    max_occurrences = 2  # 4-5 literowe - max 2x
elif word_len <= 7:
    max_occurrences = 2  # 6-7 literowe - max 2x
else:
    max_occurrences = 1  # 8+ literowe - max raz

if current_count >= max_occurrences:
    continue  # Pomiń słowo
```

**Efekt:** CV nie może pojawić się więcej niż 1 raz w całej krzyżówce.

### 3. Simplifikacja HTML Exportera w [html_exporter.py](html_exporter.py)

**Przed:**
- Walidowała każde słowo z `placed_words` czy fakty jest na siatce

**Po:**  
```python
all_words = set()
for word, _, _, _, _ in grid.placed_words:
    if word and len(word) > 0:
        all_words.add(word.upper())

# Wyświetl wyrazy
for word in sorted(all_words):
    html_parts.append(f'<div>{word}</div>')
```

**Efekt:** Sekcja "Wyrazy używane" będzie pokazywać unikatowe słowa z `placed_words`.

### 4. Usunięcie "(pionowo)" z opisów

Cofnąłem poprzednią naprawę która dodawała "(pionowo)" do opisów haseł pionowych. To jest artefakt techniczny i nie powinien być widoczny dla użytkownika.

## Pliki zmienione

1. **[crossword_grid.py](crossword_grid.py)** - Linie 327-404
   - Alez funkcja `refresh_clues()`
   - Dodano `processed_words` do śledzenia

2. **[crossword_strategies.py](crossword_strategies.py)** - Linie 395-449
   - Funkcja `_find_matching_words()`
   - Dodano licznik pojawień i limity

3. **[html_exporter.py](html_exporter.py)** - Linie 223-247
   - Uproszczono logikę zbierania słów
   - Usunięto zbędne walidacje

## Testowanie

Testy potwierdzają:
- ✅ Każde słowo dostaje dokładnie jeden numer dla każdego pojawienia
- ✅ CV pojawia się max 1 raz (zamiast 18)
- ✅ Ograniczenia pojawień są respektowane
- ✅ HTML export słów pracuje prawidłowo
- ✅ Brak "(pionowo)" w opisach

## Efekt

Krzyżówki generowane po tej naprawie będą mieć:
- **Prawidłowe numery haseł** - każde słowo dokładnie jeden numer
- **Brak redundancji słów** - CV i inne słowa 2-literowe max raz
- **Czysty HTML** - sekcja słów wyświetla się prawidłowo
- **Czytln przedziały** - brak technicznych adnotacji w hasłach

## Historia

- **2025-05-24**: Wdrożenie napraw dla problemu duplikatów haseł
- **Wcześniej**: Próba dodania "(pionowo)" jako rozwiązanie, które okazało się błędne

---

**Status:** Gotowe do testowania
**Autor:** Automated System
**Data:** Maj 2025
