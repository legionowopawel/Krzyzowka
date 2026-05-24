import sqlite3

def convert_to_db():
    conn = sqlite3.connect('slowa.db')
    c = conn.cursor()
    # Tworzymy tabelę z indeksem, co daje błyskawiczne wyszukiwanie
    c.execute('CREATE TABLE IF NOT EXISTS dictionary (word TEXT PRIMARY KEY)')
    
    print("Konwertowanie słownika do bazy danych... Może to chwilę potrwać (tylko raz).")
    with open('slowa.txt', 'r', encoding='utf-8-sig') as f:
        words = [(line.strip().upper(),) for line in f]
    
    c.executemany('INSERT OR IGNORE INTO dictionary VALUES (?)', words)
    conn.commit()
    conn.close()
    print("Gotowe! Powstał plik slowa.db.")

if __name__ == "__main__":
    convert_to_db()