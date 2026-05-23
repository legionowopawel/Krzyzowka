# Generator Krzyżówek

Projekt generuje klasyczne krzyżówki na podstawie bazy słów i definicji.
Program potrafi utworzyć gotową siatkę z pytaniami, zapisać ją jako plik tekstowy,
HTML, Excel oraz wygenerować grafikę PNG.

## Co robi program

- wczytuje słowa i definicje z pliku źródłowego
- generuje siatkę krzyżówki o zadanych wymiarach
- umieszcza wyrazy tak, aby tworzyły prawidłowy układ krzyżówki
- eksportuje wyniki do plików: HTML, Excel, PNG oraz TXT
- obsługuje tryb graficzny (GUI) i tryb wiersza poleceń (CLI)

## Najważniejsze pliki

- main.py — punkt wejścia programu
- gui_main.py — uruchomienie interfejsu graficznego
- crossword_orchestrator.py — orkiestracja procesu generowania
- crossword_generator.py — logika tworzenia siatki krzyżówki
- word_source.py — wczytywanie i filtrowanie słów
- html_exporter.py, excel_exporter.py, image_renderer.py — eksport wyników

## Uruchomienie

`ash
python main.py
`

lub w trybie CLI:

`ash
python main.py --cli 15 15
`

## Cel projektu

Celem jest szybkie i wygodne generowanie krzyżówek z własnej bazy słów,
które można zapisać i wydrukować w kilku formatach.
