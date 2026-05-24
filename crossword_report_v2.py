# -*- coding: utf-8 -*-
"""
crossword_report_v2.py — Prosty parser krzyżówki HTML do JSONa
Wyodrębnia siatkę i wyrazy bez skomplikowanych regexów.
"""

import json
import re
from bs4 import BeautifulSoup
from pathlib import Path


class SimpleReportGenerator:
    """Generuje raport JSON dla krzyżówki."""
    
    def __init__(self, html_path: str):
        self.html_path = html_path
        self.grid = []
        self.width = 0
        self.height = 0
        self.words = []
        self.errors = []
    
    def parse_html(self) -> bool:
        """Parsuj HTML i wyodrębnij siatkę."""
        try:
            with open(self.html_path, 'r', encoding='utf-8') as f:
                html = f.read()
        except Exception as e:
            print(f"BŁĄD: {e}")
            return False
        
        # Użyj BeautifulSoup do parsowania
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except:
            print("BŁĄD: BeautifulSoup niedostępny, używam regex...")
            return self._parse_html_regex(html)
        
        # Znajdź wszystkie grid-row
        grid_div = soup.find('div', {'class': 'grid'})
        if not grid_div:
            print("BŁĄD: Nie znaleziono grid")
            return False
        
        grid_rows = grid_div.find_all('div', {'class': 'grid-row'})
        self.height = len(grid_rows)
        print(f"Znaleziono {self.height} wierszy")
        
        # Parsuj każdy wiersz
        for row_idx, row_div in enumerate(grid_rows):
            row_data = []
            cells = row_div.find_all('div', {'class': 'cell'})
            
            if not cells and row_idx == 0:
                print("OSTRZEŻENIE: Wiersz 0 bez cell'i")
                return False
            
            for col_idx, cell in enumerate(cells):
                cell_obj = {
                    'row': row_idx,
                    'col': col_idx,
                    'type': 'empty',
                    'letter': None,
                    'clue_num': None
                }
                
                # Sprawdzenie klasy
                cell_class = cell.get('class', [])
                if 'black' in cell_class:
                    cell_obj['type'] = 'black'
                    row_data.append(cell_obj)
                    continue
                
                # Wyodrębnij zawartość
                cell_text = cell.get_text().strip()
                
                if not cell_text:
                    cell_obj['type'] = 'empty'
                else:
                    # Jest tekst (litera lub litera+cyfra)
                    # Sprawdź czy jest span z cyfrą
                    span = cell.find('span', {'class': 'cell-clue'})
                    if span:
                        try:
                            cell_obj['clue_num'] = int(span.get_text().strip())
                        except:
                            pass
                    
                    # Wyodrębnij samą literę
                    # Usuń span i weź tylko litery
                    text_without_span = cell_text
                    for s in cell.find_all('span'):
                        text_without_span = text_without_span.replace(s.get_text(), '')
                    
                    text_without_span = text_without_span.strip()
                    
                    # Szukaj litery
                    for char in text_without_span:
                        if char.isalpha():
                            cell_obj['letter'] = char.upper()
                            cell_obj['type'] = 'letter'
                            break
                
                row_data.append(cell_obj)
            
            if row_data:
                if not self.width:
                    self.width = len(row_data)
                self.grid.append(row_data)
        
        if not self.grid:
            print("BŁĄD: Siatka jest pusta")
            return False
        
        print(f"Wymiary siatki: {self.width}x{self.height}")
        return True
    
    def extract_words(self):
        """Wyodrębnij wyrazy."""
        
        # Poziomo
        for row in self.grid:
            col = 0
            while col < len(row):
                if row[col]['letter']:
                    word_start = col
                    word = ""
                    clue_num = row[col]['clue_num']
                    
                    while col < len(row) and row[col]['letter']:
                        word += row[col]['letter']
                        col += 1
                    
                    if len(word) >= 2:
                        self.words.append({
                            'word': word,
                            'row': row[word_start]['row'],
                            'col': word_start,
                            'direction': '→ HORIZONTAL',
                            'length': len(word),
                            'clue_num': clue_num
                        })
                else:
                    col += 1
        
        # Pionowo
        for col in range(self.width):
            row = 0
            while row < len(self.grid):
                if self.grid[row][col]['letter']:
                    word_start = row
                    word = ""
                    clue_num = self.grid[row][col]['clue_num']
                    
                    while row < len(self.grid) and self.grid[row][col]['letter']:
                        word += self.grid[row][col]['letter']
                        row += 1
                    
                    if len(word) >= 2:
                        self.words.append({
                            'word': word,
                            'row': word_start,
                            'col': col,
                            'direction': '↓ VERTICAL',
                            'length': len(word),
                            'clue_num': clue_num
                        })
                else:
                    row += 1
        
        print(f"Wyodrębniono {len(self.words)} wyrazów")
    
    def validate(self):
        """Waliduj krzyżówkę."""
        h_words = [w for w in self.words if 'HORIZONTAL' in w['direction']]
        v_words = [w for w in self.words if 'VERTICAL' in w['direction']]
        
        # Sprawdzenie przecięć
        for hw in h_words:
            intersections_list = []
            
            for i in range(hw['length']):
                h_row = hw['row']
                h_col = hw['col'] + i
                h_letter = self.grid[h_row][h_col]['letter']
                
                found_intersection = False
                for vw in v_words:
                    v_col = vw['col']
                    v_row = vw['row']
                    
                    if v_col == h_col and v_row <= h_row < v_row + vw['length']:
                        v_idx = h_row - v_row
                        v_letter = vw['word'][v_idx]
                        
                        if h_letter != v_letter:
                            self.errors.append({
                                'type': 'MISMATCH',
                                'msg': f"NIEZGODNOŚĆ: '{hw['word']}'[{i}]={h_letter} != '{vw['word']}'[{v_idx}]={v_letter}",
                                'pos': (h_row, h_col)
                            })
                        else:
                            intersections_list.append({'word': vw['word'], 'letter': h_letter})
                            found_intersection = True
            
            if not intersections_list and len(h_words) > 1 and len(v_words) > 0:
                self.errors.append({
                    'type': 'NO_INTERSECT',
                    'msg': f"BRAK PRZECIĘCIA: '{hw['word']}' ({hw['row']},{hw['col']}) →",
                    'pos': (hw['row'], hw['col'])
                })
        
        print(f"Znaleziono {len(self.errors)} błędów")
    
    def save_json(self, output_path: str) -> bool:
        """Zapisz raport JSON."""
        report = {
            'metadata': {
                'file': Path(self.html_path).name,
                'grid_size': f"{self.width}x{self.height}",
                'total_cells': self.width * self.height
            },
            'grid_structure': [],
            'words_in_crossword': self.words,
            'statistics': {
                'total_words': len(self.words),
                'horizontal': len([w for w in self.words if 'HORIZONTAL' in w['direction']]),
                'vertical': len([w for w in self.words if 'VERTICAL' in w['direction']]),
                'total_letters': sum(w['length'] for w in self.words),
                'errors': len(self.errors)
            },
            'validation_results': {
                'valid': len(self.errors) == 0,
                'errors': self.errors
            }
        }
        
        # Dodaj grid
        for row in self.grid:
            report['grid_structure'].append(row)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            print(f"✓ Raport zapisany: {output_path}")
            return True
        except Exception as e:
            print(f"BŁĄD ZAPISU: {e}")
            return False
    
    def process(self, output_path: str) -> bool:
        """Pełny proces."""
        if not self.parse_html():
            return False
        
        self.extract_words()
        self.validate()
        
        return self.save_json(output_path)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Użycie: python crossword_report_v2.py <html> [output.json]")
        sys.exit(1)
    
    html_file = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else "raport.json"
    
    print("=" * 70)
    print("GENERATOR RAPORTU KRZYŻÓWKI v2")
    print("=" * 70)
    
    gen = SimpleReportGenerator(html_file)
    if gen.process(out_file):
        stats = gen.grid and gen.words
        print(f"\nStatus: {'OK - POPRAWNA' if len(gen.errors) == 0 else 'BŁĘDY'}")
        print(f"Summary: {gen.width}x{gen.height}, {len(gen.words)} wyrazów, {len(gen.errors)} błędów")
    else:
        print("BŁĄD: Nie udało się przetworzyć")
        sys.exit(1)
