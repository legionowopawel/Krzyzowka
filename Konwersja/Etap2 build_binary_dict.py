# -*- coding: utf-8 -*-
"""
build_binary_dict.py — Konwersja slowa.db → pliki binarne dla mmap+bisect
=========================================================================
Uruchom RAZ:
    python build_binary_dict.py
    python build_binary_dict.py --db slowa.db --out .

Tworzy dwa pliki obok slowa.db (lub w katalogu --out):
    slowa.bin   (~50 MB)  — posortowane słowa, fixed 16B records → is_valid
    klucze.bin  (~50 MB)  — posortowane klucze anagramów         → fetch kandydatów

Format rekordu slowa.bin (16 bajtów):
    [1B długość][15B słowo uppercase, padded zerami]
    Posortowany leksykograficznie → bisect w 22 porównaniach na 3.25M słów

Format rekordu klucze.bin (32 bajty):
    [16B klucz = posortowane litery słowa, padded zerami]
    [16B słowo uppercase, padded zerami]
    Posortowany po kluczu → zakres anagramów przez bisect_left/bisect_right

Po konwersji SQLite NIE JEST już potrzebna do wyszukiwania.
scrabble_ai.py v8 używa tylko tych dwóch plików.

Czas konwersji: ~30-90 sekund dla 3.25M słów.
"""

import sqlite3
import struct
import os
import sys
import time
import argparse

RECORD_SIZE   = 16   # 1B długość + 15B słowo
KEY_REC_SIZE  = 32   # 16B klucz + 16B słowo
MAX_WORD_LEN  = 15   # Scrabble: plansza 15x15


def encode_word(word: str) -> bytes:
    """Koduje słowo do 16-bajtowego rekordu fixed-width."""
    w = word.upper()[:MAX_WORD_LEN]
    b = w.encode('utf-8', errors='ignore')[:MAX_WORD_LEN]
    length = len(b)
    return bytes([length]) + b.ljust(MAX_WORD_LEN, b'\x00')


def encode_key_record(word: str) -> bytes:
    """Koduje parę (klucz, słowo) do 32-bajtowego rekordu."""
    w = word.upper()[:MAX_WORD_LEN]
    b = w.encode('utf-8', errors='ignore')[:MAX_WORD_LEN]
    key_b = b''.join(sorted(b))[:MAX_WORD_LEN]   # posortowane bajty = klucz anagramu
    rec_key  = key_b.ljust(MAX_WORD_LEN, b'\x00')
    rec_word = b.ljust(MAX_WORD_LEN,     b'\x00')
    return bytes([len(key_b)]) + rec_key[1:] + bytes([len(b)]) + rec_word[1:]


# Uwaga: powyższy format jest trochę skomplikowany — uprośćmy:
# klucze.bin rekord = 16B klucz (padded) + 16B słowo (padded) = 32B łącznie
def encode_key_rec_simple(word_bytes: bytes, key_bytes: bytes) -> bytes:
    """Prosty 32-bajtowy rekord: 16B klucz + 16B słowo (oba padded zerami)."""
    return key_bytes.ljust(16, b'\x00') + word_bytes.ljust(16, b'\x00')


def build(db_path: str, out_dir: str) -> None:
    if not os.path.exists(db_path):
        print(f"BŁĄD: Nie znaleziono '{db_path}'")
        sys.exit(1)

    words_path  = os.path.join(out_dir, 'slowa.bin')
    keys_path   = os.path.join(out_dir, 'klucze.bin')

    print(f"Źródło:   {db_path}  ({os.path.getsize(db_path)/1024/1024:.1f} MB)")
    print(f"Cel:      {words_path}")
    print(f"          {keys_path}")
    print("=" * 60)

    # ── Krok 1: Wczytaj wszystkie słowa z SQLite ───────────────────────────
    print("[1/4] Wczytuję słowa z SQLite...")
    t0 = time.monotonic()

    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA mmap_size=268435456;")
    conn.execute("PRAGMA cache_size=-65536;")
    cur = conn.cursor()
    cur.execute(
        "SELECT word FROM dictionary WHERE length(word) BETWEEN 2 AND 15"
    )

    words_raw = []
    skipped   = 0
    while True:
        chunk = cur.fetchmany(50_000)
        if not chunk:
            break
        for (w,) in chunk:
            try:
                wb = w.upper().encode('utf-8', errors='ignore')
                if 2 <= len(wb) <= 15:
                    words_raw.append(wb)
                else:
                    skipped += 1
            except Exception:
                skipped += 1

    conn.close()
    elapsed = time.monotonic() - t0
    print(f"      Wczytano: {len(words_raw):,} słów  (pominięto: {skipped:,})  [{elapsed:.1f}s]")

    # ── Krok 2: Sortuj słowa (do slowa.bin) ───────────────────────────────
    print("[2/4] Sortuję słowa...")
    t0 = time.monotonic()
    words_raw.sort()
    # Usuń duplikaty
    words_unique = []
    prev = None
    for w in words_raw:
        if w != prev:
            words_unique.append(w)
            prev = w
    elapsed = time.monotonic() - t0
    print(f"      Po sortowaniu: {len(words_unique):,} unikalnych słów  [{elapsed:.1f}s]")

    # ── Krok 3: Zapisz slowa.bin ──────────────────────────────────────────
    print(f"[3/4] Zapisuję {words_path}...")
    t0 = time.monotonic()

    # Nagłówek: 8 bajtów = liczba rekordów (uint64 little-endian)
    n = len(words_unique)
    with open(words_path, 'wb') as f:
        f.write(struct.pack('<Q', n))   # 8B nagłówek
        for wb in words_unique:
            length = len(wb)
            f.write(bytes([length]) + wb.ljust(MAX_WORD_LEN, b'\x00'))

    size_mb = os.path.getsize(words_path) / 1024 / 1024
    elapsed = time.monotonic() - t0
    print(f"      Zapisano: {size_mb:.1f} MB  [{elapsed:.1f}s]")

    # ── Krok 4: Zbuduj i zapisz klucze.bin ────────────────────────────────
    print(f"[4/4] Buduję i zapisuję {keys_path}...")
    t0 = time.monotonic()

    # Rekord klucze.bin: 32 bajty = 16B klucz (posortowane bajty słowa) + 16B słowo
    # Posortowany po (klucz, słowo) → bisect_left/right po samym kluczu
    key_records = []
    for wb in words_unique:
        key_b = bytes(sorted(wb))[:MAX_WORD_LEN]   # klucz = posortowane bajty
        # Rekord: 16B klucz padded + 16B słowo padded
        rec = key_b.ljust(16, b'\x00') + wb.ljust(16, b'\x00')
        key_records.append(rec)

    key_records.sort()   # sortuj po (klucz, słowo)

    with open(keys_path, 'wb') as f:
        f.write(struct.pack('<Q', len(key_records)))   # 8B nagłówek
        for rec in key_records:
            f.write(rec)

    size_mb = os.path.getsize(keys_path) / 1024 / 1024
    elapsed = time.monotonic() - t0
    print(f"      Zapisano: {size_mb:.1f} MB  [{elapsed:.1f}s]")

    # ── Podsumowanie ──────────────────────────────────────────────────────
    total_mb = (os.path.getsize(words_path) + os.path.getsize(keys_path)) / 1024 / 1024
    print()
    print("=" * 60)
    print(f"GOTOWE!  Łączny rozmiar plików: {total_mb:.1f} MB")
    print(f"  {words_path}")
    print(f"  {keys_path}")
    print()
    print("Możesz teraz usunąć slowa.db — nie jest już potrzebna do gry.")
    print("Skopiuj oba pliki .bin obok scrabble.py i scrabble_ai.py")
    print("=" * 60)

    # ── Szybki test poprawności ────────────────────────────────────────────
    print("\nTest poprawności...")
    _self_test(words_path, keys_path, words_unique[:5])


def _self_test(words_path: str, keys_path: str, sample_words: list) -> None:
    """Sprawdza czy bisect działa poprawnie na wygenerowanych plikach."""
    import mmap

    with open(words_path, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    n = struct.unpack_from('<Q', mm, 0)[0]
    base = 8   # po nagłówku

    def word_at(i: int) -> bytes:
        off = base + i * RECORD_SIZE
        length = mm[off]
        return mm[off+1: off+1+length]

    def is_valid(word: str) -> bool:
        wb = word.upper().encode('utf-8', errors='ignore')[:MAX_WORD_LEN]
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) // 2
            mw = word_at(mid)
            if mw < wb:   lo = mid + 1
            elif mw > wb: hi = mid
            else:         return True
        return False

    ok = 0
    for wb in sample_words:
        word = wb.decode('utf-8', errors='ignore')
        if is_valid(word):
            ok += 1
        else:
            print(f"  BŁĄD: '{word}' nie znalezione!")

    mm.close()
    print(f"  Weryfikacja: {ok}/{len(sample_words)} słów znalezionych poprawnie ✓")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Konwertuj slowa.db → pliki binarne dla mmap+bisect"
    )
    parser.add_argument("--db",  default="slowa.db", help="Ścieżka do slowa.db")
    parser.add_argument("--out", default=".",        help="Katalog wyjściowy (domyślnie: .)")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    build(args.db, args.out)
