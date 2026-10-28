# Intérprete Bazilio

Proyecto de Lenguajes y Autómatas I: un intérprete para un lenguaje pequeño de
composición musical. La guía completa está en
`Practica_Guiada_Interprete_Bazilio.txt`; los ejemplos ejecutables están en
`programas/`.

## Requisitos

- Python 3.
- Runtime de ANTLR para Python: `pip install antlr4-python3-runtime==4.13.2`.
- Herramienta ANTLR 4.13 disponible como `antlr4`.
- Para producir PDF, MIDI, WAV y MP3: LilyPond, TiMidity++ con un soundfont y
    ffmpeg. Sin estas herramientas, el intérprete sigue funcionando y puede
    crear el archivo LilyPond con `--solo-ly`.

## Preparación

Desde la raíz del proyecto, genera el lexer, parser y visitor de Python:

```sh
antlr4 -Dlanguage=Python3 -visitor Bazilio.g4
```

Los archivos generados deben permanecer junto a `analizar.py` y `bazilio.py`.

## Uso

```sh
python3 analizar.py programas/hello.bzl
python3 analizar.py --tokens programas/hello.bzl
python3 analizar.py --arbol programas/hello.bzl
python3 bazilio.py programas/e2_aritmetica.bzl
python3 bazilio.py programas/e2_lectura.bzl
python3 bazilio.py programas/hanoi.bzl
python3 bazilio.py programas/hello.bzl --solo-ly
python3 bazilio.py programas/hanoi_musical.bzl Hanoi --solo-ly
```

Los programas que usan `<?>` leen enteros de la entrada estándar. Hanoi solicita
el número de discos. La etapa musical guarda sus archivos junto al `.bzl`.

Los archivos `bazilio_etapa2.py` a `bazilio_etapa6.py` conservan los nombres
usados por la guía y delegan en el intérprete completo de `bazilio.py`; no son
implementaciones históricas independientes de cada etapa.

## Archivos principales

- `Bazilio.g4`: gramática lexer/parser.
- `analizar.py`: validación sintáctica, listado de tokens y árbol.
- `bazilio.py`: intérprete completo, listas, procedimientos y salida musical.
- `programas/`: ejemplos y casos de error de la guía.
