# Bazilo Web

Formulario local titulado “Tu secuencia, hecha música” para escribir una secuencia Bazilio y generar archivos reutilizando el intérprete de la raíz. Los enlaces de descarga aparecen bajo el botón de generación.

## Requisitos

- Python 3.
- `antlr4-python3-runtime==4.13.2` instalado en el mismo Python con que se inicia el servidor.
- Archivos generados por ANTLR en la raíz (`BazilioLexer.py`, `BazilioParser.py` y `BazilioVisitor.py`).
- Para obtener PDF, MIDI, WAV y MP3: LilyPond, TiMidity++ con un soundfont configurado y ffmpeg.

## Iniciar

Desde la raíz del repositorio:

```sh
python3 bazilo/server.py
```

El servidor imprime una URL local, por ejemplo `http://127.0.0.1:43571`; abre
la URL que indique tu terminal. Se selecciona un puerto libre automáticamente.
Detén el servidor con `Ctrl+C`.

## Desplegar en Railway

El proyecto incluye un `Dockerfile` en la raíz para instalar Python, ANTLR,
LilyPond, TiMidity++, un soundfont y ffmpeg. Railway detecta ese archivo
automáticamente al desplegar el repositorio.

1. Sube este proyecto a un repositorio de GitHub. No subas los entornos
   virtuales ni las carpetas `bazilo/bazilo-*` generadas durante pruebas.
2. En Railway, crea un proyecto nuevo y selecciona **Deploy from GitHub Repo**.
3. Selecciona el repositorio y espera a que termine el build de Docker.
4. En el servicio, abre **Settings > Networking > Generate Domain**.
5. Abre el dominio generado. Railway proporciona automáticamente la variable
   `PORT`; el servidor ya está preparado para escuchar en ese puerto.

Cada generación usa almacenamiento temporal del contenedor. Los enlaces de
descarga expiran y los archivos pueden desaparecer si Railway reinicia o
vuelve a desplegar el servicio, por lo que no deben usarse como almacenamiento
permanente.

En la casilla pega una expresión de reproducción Bazilio, por ejemplo
`(:) {E E F G G F E D C C D E E D D}`. Se aceptan notas de A a G, con octava
opcional (de 0 a 8); el intérprete valida además el rango real del piano. Se
permiten hasta 512 notas por solicitud.

Cada solicitud se procesa en una carpeta temporal local y los archivos resultantes se entregan como descargas. El servicio solo escucha en `127.0.0.1`; no está pensado para exponerse a una red pública.

Antes de ofrecer enlaces, el servidor valida la estructura del LilyPond, PDF,
MIDI y WAV, y decodifica el WAV y MP3 completos con ffmpeg. Cada descarga usa
su tamaño esperado y SHA-256; el navegador verifica ambos antes de mostrarla.
Los enlaces temporales expiran al cabo de 30 minutos. Con el servidor encendido,
se puede comprobar una generación y sus descargas con:

```sh
python3 bazilo/integrity_check.py http://127.0.0.1:PUERTO
```

Reemplaza `PUERTO` por el que se anunció al iniciar el servidor.
