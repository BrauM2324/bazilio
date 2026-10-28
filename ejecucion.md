# Registro de ejecución

Este documento reúne los comandos utilizados para preparar y probar el intérprete Bazilio, organizados en las cuatro tareas realizadas. Los comandos Python usan `/bin/python3`, el intérprete configurado para el proyecto.

## Tarea 1: preparar el entorno y comprobar dependencias

```sh
command -v antlr4
```

Comprobó la disponibilidad de ANTLR. En esta sesión `antlr4` estaba definido como alias para ejecutar el JAR 4.13.2.

```sh
ls -la
```

Revisó el contenido de la raíz antes de generar los archivos del parser.

Se instaló el runtime de Python en la versión indicada por la guía:

```sh
pip install antlr4-python3-runtime==4.13.2
```

Se comprobó la disponibilidad de las herramientas para producir PDF, audio y MP3:

```sh
command -v lilypond
command -v timidity
command -v ffmpeg
```

Las tres herramientas estaban disponibles en el entorno.

## Tarea 2: generar y probar el lexer/parser

```sh
antlr4 -Dlanguage=Python3 -visitor Bazilio.g4
```

Generó los módulos Python del lexer, parser, visitor y listener, además de los archivos de tokens e interpretación de ANTLR.

```sh
/bin/python3 analizar.py programas/hello.bzl programas/euclides.bzl programas/hanoi.bzl programas/hanoi_musical.bzl programas/listas.bzl
```

Verificó que los programas de ejemplo fueran sintácticamente válidos.

```sh
/bin/python3 analizar.py programas/e1_error.bzl
```

Comprobó que un programa inválido se rechazara mostrando la línea y columna del error.

```sh
/bin/python3 analizar.py --tokens programas/hello.bzl
```

Mostró los tokens reconocidos en `hello.bzl`.

```sh
/bin/python3 analizar.py --arbol programas/hello.bzl
```

Mostró el árbol sintáctico de `hello.bzl`.

## Tarea 3: ejecutar las pruebas del intérprete

```sh
/bin/python3 bazilio_etapa2.py programas/e2_aritmetica.bzl
```

Probó asignaciones, operaciones aritméticas y escritura.

```sh
printf '21\n' | /bin/python3 bazilio_etapa2.py programas/e2_lectura.bzl
```

Envió el valor `21` por la entrada estándar para probar lectura y cálculo del doble.

```sh
/bin/python3 bazilio_etapa3.py programas/e3_control.bzl
```

Probó `if`, `else`, `while`, la cuenta regresiva y el cálculo del MCD.

```sh
printf '3\n' | /bin/python3 bazilio_etapa4.py programas/hanoi.bzl
```

Ejecutó las Torres de Hanoi recursivas con tres discos.

```sh
/bin/python3 bazilio_etapa5.py programas/listas.bzl
```

Probó listas, índices, longitud, copia al asignar y paso por referencia a procedimientos.

```sh
/bin/python3 bazilio.py programas/e5_notas.bzl
```

Verificó la conversión de notas musicales a valores enteros.

```sh
/bin/python3 bazilio.py programas/e5_indice.bzl
```

Comprobó el mensaje de error para un índice inexistente.

```sh
/bin/python3 bazilio.py programas/e5_division.bzl
```

Comprobó el manejo de división por cero.

```sh
printf '12\n18\n' | /bin/python3 bazilio.py programas/euclides.bzl
```

Ejecutó Euclides con los valores de entrada `12` y `18`.

```sh
printf '10\n' | /bin/python3 bazilio.py programas/hanoi.bzl | wc -l
```

Contó los movimientos producidos por Hanoi con diez discos; el resultado esperado es 1023.

## Tarea 4: generar y verificar la salida musical

```sh
/bin/python3 bazilio.py programas/hello.bzl --solo-ly
```

Ejecutó Hello Bazilio y generó únicamente el archivo LilyPond, sin llamar a los conversores externos.

```sh
/bin/python3 bazilio.py programas/hanoi_musical.bzl Hanoi --solo-ly
```

Ejecutó el procedimiento musical `Hanoi` y generó su archivo LilyPond.

```sh
/bin/python3 bazilio.py programas/hello.bzl
```

Generó la partitura y los formatos disponibles para Hello Bazilio: `.ly`, PDF, MIDI, WAV y MP3.

```sh
/bin/python3 bazilio.py programas/hanoi_musical.bzl Hanoi
```

Generó la partitura y los formatos disponibles de Hanoi musical.

```sh
wc -l programas/hanoi_musical.ly
```

Contó las líneas del archivo LilyPond de Hanoi musical.

```sh
grep -oE '[a-g][,\x27]*4' programas/hanoi_musical.ly | wc -l
```

Fue el primer intento de conteo; el patrón escapado no reconoció las notas y devolvió `0`.

```sh
sed -n '/\\tempo/,$p' programas/hanoi_musical.ly | grep -oE "[a-g][,']*4" | wc -l
```

Contó correctamente las notas de la partitura: 31.

## Uso del proyecto

Desde la raíz, instala los requisitos Python y genera el parser una vez:

```sh
pip install antlr4-python3-runtime==4.13.2
antlr4 -Dlanguage=Python3 -visitor Bazilio.g4
```

Para revisar la sintaxis, listar tokens o mostrar el árbol:

```sh
/bin/python3 analizar.py programas/hello.bzl
/bin/python3 analizar.py --tokens programas/hello.bzl
/bin/python3 analizar.py --arbol programas/hello.bzl
```

Para ejecutar programas Bazilio:

```sh
/bin/python3 bazilio.py programas/e2_aritmetica.bzl
printf '21\n' | /bin/python3 bazilio.py programas/e2_lectura.bzl
printf '3\n' | /bin/python3 bazilio.py programas/hanoi.bzl
/bin/python3 bazilio.py programas/hello.bzl
/bin/python3 bazilio.py programas/hello.bzl --solo-ly
/bin/python3 bazilio.py programas/hanoi_musical.bzl Hanoi
```

Los programas que contienen `<?>` leen enteros desde la entrada estándar. En Hanoi se debe proporcionar el número de discos. La opción `--solo-ly` genera el archivo `.ly` sin convertirlo; la ejecución musical completa requiere LilyPond, TiMidity++ con un soundfont configurado y ffmpeg. Los archivos generados se guardan junto al programa `.bzl`.
