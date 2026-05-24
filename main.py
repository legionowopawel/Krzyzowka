# -*- coding: utf-8 -*-
"""
main.py — Entry point dla generatora krzyżówek
Uruchom:  
  python main.py [--gui]                                    # GUI (domyślnie)
  python main.py --cli <width> <height> [word_file]        # CLI, standard
  python main.py --cli-multi <width> <height> [word_file]  # CLI, 6 strategii
"""

import sys
import os

# Dodaj katalog Krzyzowka do ścieżki
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main_gui():
    """Uruchom GUI."""
    from gui_main import main
    main()


def main_cli(
    width: int,
    height: int,
    word_file: str = None,
    multi_strategy: bool = False,
    use_api: bool = False,
    use_api_dry_run: bool = False,
    time_limit: float = 3.0,
    max_attempts: int = 5,
    target_variants: int = 3,
) -> int:
    """Uruchom CLI (bez interfejsu graficznego)."""
    from crossword_orchestrator import CrosswordOrchestrator

    orchestrator = CrosswordOrchestrator(
        os.path.dirname(os.path.abspath(__file__))
    )

    # Pobierz nazwę pliku źródłowego
    source_filename = os.path.basename(word_file) if word_file else "dane.txt"

    # Wykonaj
    success = orchestrator.generate_and_export(
        width,
        height,
        source_filename,
        word_file,
        num_variants=target_variants,
        multi_strategy=multi_strategy,
        progress_callback=None,
        use_api=use_api,
        use_api_dry_run=use_api_dry_run,
        time_limit=time_limit,
        max_attempts=max_attempts,
        target_valid_variants=target_variants,
    )

    if success:
        mode = "MULTI-STRATEGY (6 strategii)" if multi_strategy else "STANDARDOWY"
        print(f"\n[OK] Krzyżówka wygenerowana pomyślnie! (Tryb: {mode})")
        print(f"Wyniki w: {orchestrator.output_dir}")
        return 0
    else:
        print("\n[ERROR] Błąd podczas generowania krzyżówki")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        # Tryb CLI standardowy
        if len(sys.argv) < 4:
            print("Użycie: python main.py --cli <width> <height> [word_file]")
            print("Przykład: python main.py --cli 15 15")
            print("          python main.py --cli 15 15 /path/to/words.txt")
            sys.exit(1)

        width = int(sys.argv[2])
        height = int(sys.argv[3])
        word_file = sys.argv[4] if len(sys.argv) > 4 else None
        use_api = "--use-api" in sys.argv
        use_api_dry_run = "--api-dry-run" in sys.argv

        # opcjonalne parametry
        def _get_arg(name, cast, default):
            if name in sys.argv:
                try:
                    idx = sys.argv.index(name)
                    return cast(sys.argv[idx + 1])
                except Exception:
                    return default
            return default

        time_limit = _get_arg("--time-limit", float, 3.0)
        max_attempts = _get_arg("--max-attempts", int, 5)
        target_variants = _get_arg("--target-variants", int, 3)

        sys.exit(
            main_cli(
                width,
                height,
                word_file,
                multi_strategy=False,
                use_api=use_api,
                use_api_dry_run=use_api_dry_run,
                time_limit=time_limit,
                max_attempts=max_attempts,
                target_variants=target_variants,
            )
        )

    elif len(sys.argv) > 1 and sys.argv[1] == "--cli-multi":
        # Tryb CLI multi-strategy (6 strategii)
        if len(sys.argv) < 4:
            print("Użycie: python main.py --cli-multi <width> <height> [word_file]")
            print("Generuje krzyżówki 6 różnymi strategiami:")
            print("  1. CENTERED - wyrazy od środka")
            print("  2. TOP_LEFT - z górnego lewego rogu")
            print("  3. TOP_CENTER - od góry pośrodku")
            print("  4. MIDDLE_LEFT - ze środka lewej krawędzi")
            print("  5. DENSE_MODE - maksymalna gęstość")
            print("  6. RANDOM - losowe umieszczenie")
            sys.exit(1)

        width = int(sys.argv[2])
        height = int(sys.argv[3])
        word_file = sys.argv[4] if len(sys.argv) > 4 else None
        use_api = "--use-api" in sys.argv
        use_api_dry_run = "--api-dry-run" in sys.argv

        def _get_arg(name, cast, default):
            if name in sys.argv:
                try:
                    idx = sys.argv.index(name)
                    return cast(sys.argv[idx + 1])
                except Exception:
                    return default
            return default

        time_limit = _get_arg("--time-limit", float, 3.0)
        max_attempts = _get_arg("--max-attempts", int, 5)
        target_variants = _get_arg("--target-variants", int, 3)

        sys.exit(
            main_cli(
                width,
                height,
                word_file,
                multi_strategy=True,
                use_api=use_api,
                use_api_dry_run=use_api_dry_run,
                time_limit=time_limit,
                max_attempts=max_attempts,
                target_variants=target_variants,
            )
        )

    else:
        # Tryb GUI (domyślnie)
        main_gui()
