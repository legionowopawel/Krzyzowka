# -*- coding: utf-8 -*-
"""
build_binary_dict.py — Konwersja słownika TXT → pliki binarne mmap+bisect
=========================================================================
Uruchom RAZ:
    python build_binary_dict.py
    python build_binary_dict.py --txt slowa.txt --out .

Wejście:  slowa.txt  — jeden wyraz na linię (kodowanie UTF-8)
Wyjście:
    slowa.bin   (~50 MB)  — posortowane słowa uppercase, fixed 16B/rekord
    klucze.bin  (~50 MB)  — posortowane (klucz_anagramu + słowo), fixed 32B/rekord

Format slowa.bin:
    8B nagłówek (uint64 = liczba rekordów)
    Każdy rekord 16B: [1B długość][15B słowo uppercase, padded 0x00]
    Posortowany leksykograficznie → bisect w 22 krokach na 3.25M słów

Format klucze.bin:
    8B nagłówek (uint64 = liczba rekordów)
    Każdy rekord 32B: [16B klucz padded][16B słowo padded]
    Klucz = bajty słowa posortowane rosnąco (anagram-key)
    Posortowany po (klucz, słowo) → zakres anagramów przez bisect_left/right

Po konwersji slowa.txt nie jest już potrzebny do gry.
"""

import struct
import os
import sys
import time
import argparse

MAX_WORD_LEN = 15
HEADER       = 8
REC_W        = 16
REC_K        = 32


def build(txt_path: str, out_dir: str) -> None:
    if not os.path.exists(txt_path):
        print(f"BŁĄD: Nie znaleziono '{txt_path}'")
        sys.exit(1)

    words_path = os.path.join(out_dir, 'slowa.bin')
    keys_path  = os.path.join(out_dir, 'klucze.bin')
    txt_mb     = os.path.getsize(txt_path) / 1024 / 1024

    print(f"Źródło:  {txt_path}  ({txt_mb:.1f} MB)")
    print(f"Cel:     {words_path}")
    print(f"         {keys_path}")
    print("=" * 60)

    # ── Krok 1: Wczytaj i filtruj ─────────────────────────────────────────
    print("[1/4] Wczytuję plik TXT...")
    t0 = time.monotonic()

    words_raw = []
    skipped   = 0

    with open(txt_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            word = line.strip().upper()
            if not word:
                continue
            try:
                wb = word.encode('utf-8', errors='ignore')
            except Exception:
                skipped += 1
                continue
            if 2 <= len(wb) <= MAX_WORD_LEN:
                words_raw.append(wb)
            else:
                skipped += 1

    elapsed = time.monotonic() - t0
    print(f"      Wczytano:  {len(words_raw):,} słów  "
          f"(pominięto: {skipped:,} — za krótkie/długie)  [{elapsed:.1f}s]")

    # ── Krok 2: Sortuj i usuń duplikaty ───────────────────────────────────
    print("[2/4] Sortuję i usuwam duplikaty...")
    t0 = time.monotonic()

    words_raw.sort()
    unique = []
    prev   = None
    for wb in words_raw:
        if wb != prev:
            unique.append(wb)
            prev = wb

    elapsed = time.monotonic() - t0
    print(f"      Unikalnych: {len(unique):,} słów  [{elapsed:.1f}s]")
    del words_raw

    # ── Krok 3: Zapisz slowa.bin ──────────────────────────────────────────
    print(f"[3/4] Zapisuję {words_path}...")
    t0 = time.monotonic()

    with open(words_path, 'wb') as f:
        f.write(struct.pack('<Q', len(unique)))
        for wb in unique:
            f.write(bytes([len(wb)]) + wb.ljust(MAX_WORD_LEN, b'\x00'))

    size_mb = os.path.getsize(words_path) / 1024 / 1024
    elapsed = time.monotonic() - t0
    print(f"      Zapisano: {size_mb:.1f} MB  [{elapsed:.1f}s]")

    # ── Krok 4: Zbuduj i zapisz klucze.bin ────────────────────────────────
    print(f"[4/4] Buduję klucze anagramów i zapisuję {keys_path}...")
    t0 = time.monotonic()

    key_records = []
    for wb in unique:
        key_b  = bytes(sorted(wb)).ljust(16, b'\x00')
        word_b = wb.ljust(16, b'\x00')
        key_records.append(key_b + word_b)

    key_records.sort()

    with open(keys_path, 'wb') as f:
        f.write(struct.pack('<Q', len(key_records)))
        for rec in key_records:
            f.write(rec)

    size_mb = os.path.getsize(keys_path) / 1024 / 1024
    elapsed = time.monotonic() - t0
    print(f"      Zapisano: {size_mb:.1f} MB  [{elapsed:.1f}s]")

    # ── Podsumowanie ──────────────────────────────────────────────────────
    total_mb = (os.path.getsize(words_path) + os.path.getsize(keys_path)) / 1024 / 1024
    print()
    print("=" * 60)
    print(f"GOTOWE!  Łączny rozmiar: {total_mb:.1f} MB")
    print(f"  {words_path}")
    print(f"  {keys_path}")
    print()
    print("Skopiuj oba pliki .bin obok scrabble.py i scrabble_ai.py")
    print("slowa.txt i slowa.db nie są już potrzebne do gry.")
    print("=" * 60)

    print("\nTest poprawności...")
    _self_test(words_path, unique[:5])


def _self_test(words_path: str, sample: list) -> None:
    import mmap
    with open(words_path, 'rb') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    n = struct.unpack_from('<Q', mm, 0)[0]

    def word_at(i):
        off = HEADER + i * REC_W
        return mm[off+1: off+1+mm[off]]

    def is_valid(wb):
        lo, hi = 0, n
        while lo < hi:
            mid = (lo + hi) >> 1
            mw  = word_at(mid)
            if   mw < wb: lo = mid + 1
            elif mw > wb: hi = mid
            else:         return True
        return False

    mm.close()
    ok = 0
    for wb in sample:
        # Ponownie otwórz — po close() mm jest nieaktywny
        with open(words_path, 'rb') as f:
            mm2 = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        n2 = struct.unpack_from('<Q', mm2, 0)[0]
        def word_at2(i):
            off = HEADER + i * REC_W
            return mm2[off+1: off+1+mm2[off]]
        lo, hi = 0, n2
        found = False
        while lo < hi:
            mid = (lo + hi) >> 1
            mw  = word_at2(mid)
            if   mw < wb: lo = mid + 1
            elif mw > wb: hi = mid
            else:         found = True; break
        mm2.close()
        word_str = wb.decode('utf-8', errors='ignore')
        print(f"  '{word_str}' → {'OK ✓' if found else 'BŁĄD!'}")
        if found:
            ok += 1

    print(f"  Wynik: {ok}/{len(sample)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Konwertuj słownik TXT → binarne pliki mmap+bisect dla Scrabble AI"
    )
    parser.add_argument("--txt", default="slowa.txt",
                        help="Ścieżka do pliku TXT (domyślnie: slowa.txt)")
    parser.add_argument("--out", default=".",
                        help="Katalog wyjściowy (domyślnie: bieżący)")
    args = parser.parse_args()
    os.makedirs(args.out, exist_ok=True)
    build(args.txt, args.out)
