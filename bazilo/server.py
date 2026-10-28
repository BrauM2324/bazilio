from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import subprocess
import tempfile
import threading
import time
from contextlib import redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote
from urllib.parse import urlparse
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from antlr4 import InputStream  
from bazilio import ErrorBazilio, Interprete, generar_salida, parsear  # noqa: E402

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8765"))
MAX_REQUEST_BYTES = 16_384
MAX_NOTES = 512
NOTE_PATTERN = re.compile(r"[A-G](?:[0-8])?\Z")
OUTPUT_LOCK = threading.Lock()
JOB_LOCK = threading.Lock()
JOBS: dict[str, dict[str, Path]] = {}
JOB_TTL_SECONDS = 30 * 60
REQUIRED_EXTENSIONS = {".ly", ".pdf", ".midi", ".wav", ".mp3"}
NOTE_IN_LY_PATTERN = re.compile(r"(?<![A-Za-z])[a-g][,']*4\b")


def parse_notes(value: object) -> list[str]:
    if not isinstance(value, str):
        raise ValueError("La secuencia debe ser texto.")
    value = value.strip()
    if value.startswith("(:)") or "{" in value or "}" in value:
        match = re.fullmatch(r"\(:\)\s*\{([\s\S]*)\}\s*", value)
        if match is None:
            raise ValueError("Usa el formato (: ) {C4 D4 E4} con paréntesis juntos: (:) {C4 D4 E4}.")
        value = match.group(1)
    tokens = value.replace(",", " ").split()
    if not tokens:
        raise ValueError("Escribe al menos una nota, por ejemplo: C4 D4 E4.")
    if len(tokens) > MAX_NOTES:
        raise ValueError(f"El máximo es de {MAX_NOTES} notas por generación.")
    invalid = [token for token in tokens if NOTE_PATTERN.fullmatch(token) is None]
    if invalid:
        raise ValueError(
            "Notas no válidas: " + ", ".join(invalid[:8]) +
            ". Usa notas A-G con octava opcional, por ejemplo C4 o A.")
    return tokens


def build_program(notes: list[str]) -> str:
    sequence = " ".join(notes)
    return f'Main |:\n    (:) {{{sequence}}}\n:|\n'


def _validate_artifacts(paths: list[str], expected_notes: int) -> dict[str, Path]:
    artifacts = {Path(path).suffix: Path(path) for path in paths}
    missing = REQUIRED_EXTENSIONS - artifacts.keys()
    if missing:
        raise ErrorBazilio(
            "La conversión quedó incompleta; faltan: " + ", ".join(sorted(missing)) + ".")

    ly_path = artifacts[".ly"]
    try:
        lilypond_text = ly_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ErrorBazilio(f"El archivo {ly_path.name} no se puede leer completo: {error}")
    if (not lilypond_text.endswith("}\n")
            or "\\score {" not in lilypond_text
            or len(NOTE_IN_LY_PATTERN.findall(lilypond_text)) != expected_notes):
        raise ErrorBazilio(
            f"El archivo {ly_path.name} llegó incompleto o no contiene todas las notas.")

    pdf_data = artifacts[".pdf"].read_bytes()
    if not pdf_data.startswith(b"%PDF-") or b"%%EOF" not in pdf_data[-2048:]:
        raise ErrorBazilio("El PDF generado está incompleto o no tiene una estructura válida.")

    midi_data = artifacts[".midi"].read_bytes()
    if len(midi_data) < 22 or midi_data[:4] != b"MThd":
        raise ErrorBazilio("El MIDI generado está incompleto o no tiene una cabecera válida.")
    header_length = int.from_bytes(midi_data[4:8], "big")
    track_count = int.from_bytes(midi_data[10:12], "big")
    if header_length != 6 or track_count == 0:
        raise ErrorBazilio("El MIDI generado no contiene pistas válidas.")
    offset = 8 + header_length
    tracks = 0
    while offset + 8 <= len(midi_data) and midi_data[offset:offset + 4] == b"MTrk":
        track_length = int.from_bytes(midi_data[offset + 4:offset + 8], "big")
        offset += 8 + track_length
        if offset > len(midi_data):
            raise ErrorBazilio("El MIDI generado tiene una pista truncada.")
        tracks += 1
    if tracks != track_count or offset != len(midi_data):
        raise ErrorBazilio("El MIDI generado está incompleto o contiene pistas dañadas.")

    wav_data = artifacts[".wav"].read_bytes()
    if len(wav_data) < 44 or wav_data[:4] != b"RIFF" or wav_data[8:12] != b"WAVE":
        raise ErrorBazilio("El WAV generado está incompleto o no tiene una cabecera válida.")
    riff_end = 8 + int.from_bytes(wav_data[4:8], "little")
    if riff_end > len(wav_data) or riff_end < 44:
        raise ErrorBazilio("El WAV generado tiene un tamaño RIFF incompleto.")
    offset = 12
    found_format = found_audio = False
    while offset + 8 <= riff_end:
        chunk_id = wav_data[offset:offset + 4]
        chunk_size = int.from_bytes(wav_data[offset + 4:offset + 8], "little")
        chunk_end = offset + 8 + chunk_size
        if chunk_end > riff_end:
            raise ErrorBazilio("El WAV generado contiene un bloque truncado.")
        if chunk_id == b"fmt " and chunk_size >= 16:
            found_format = True
        if chunk_id == b"data" and chunk_size > 0:
            found_audio = True
        offset = chunk_end + (chunk_size & 1)
    if not found_format or not found_audio:
        raise ErrorBazilio("El WAV generado no contiene formato y audio legibles.")

    for extension in (".pdf", ".midi", ".wav", ".mp3"):
        artifact = artifacts[extension]
        if not artifact.is_file() or artifact.stat().st_size == 0:
            raise ErrorBazilio(f"El archivo {artifact.name} está vacío o no se pudo leer.")

    pdfinfo = shutil.which("pdfinfo")
    if pdfinfo:
        check_pdf = subprocess.run(
            [pdfinfo, str(artifacts[".pdf"])], capture_output=True, text=True, timeout=30
        )
        if check_pdf.returncode != 0 or not re.search(r"^Pages:\s+[1-9]", check_pdf.stdout, re.M):
            raise ErrorBazilio("El PDF generado no se puede abrir o no contiene páginas.")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ErrorBazilio("No se encontró ffmpeg para validar la lectura de los audios.")
    for extension in (".wav", ".mp3"):
        check_audio = subprocess.run(
            [ffmpeg, "-v", "error", "-i", str(artifacts[extension]), "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        if check_audio.returncode != 0:
            raise ErrorBazilio(
                f"El archivo {artifacts[extension].name} no se puede decodificar completo.")
    return artifacts


def _remove_expired_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for job_id, files in list(JOBS.items()):
        job_dir = next(iter(files.values())).parent if files else None
        if job_dir is not None and job_dir.stat().st_mtime < cutoff:
            for path in job_dir.iterdir():
                path.unlink(missing_ok=True)
            job_dir.rmdir()
            del JOBS[job_id]


def generate_files(notes: list[str]) -> tuple[str, list[dict[str, object]]]:
    source = build_program(notes)
    tree = parsear(InputStream(source))
    interpreter = Interprete(salida=lambda _message: None)
    interpreter.cargar(tree)
    interpreter.ejecutar()
    if not interpreter.partitura:
        raise ErrorBazilio("La secuencia no produjo notas para la partitura.")

    with OUTPUT_LOCK:
        temp = tempfile.mkdtemp(prefix="bazilo-", dir=WEB_ROOT)
        job_dir = Path(temp)
        try:
            base = str(job_dir / "secuencia")
            captured = io.StringIO()
            with redirect_stdout(captured):
                paths = generar_salida(interpreter.partitura, base)
            artifacts = _validate_artifacts(paths, len(interpreter.partitura))
            job_id = uuid4().hex
            files = []
            with JOB_LOCK:
                _remove_expired_jobs()
                JOBS[job_id] = artifacts
            for file_path in artifacts.values():
                digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
                files.append({
                    "name": file_path.name,
                    "url": f"/api/archivos/{job_id}/{quote(file_path.name)}",
                    "size": file_path.stat().st_size,
                    "sha256": digest,
                })
            return job_id, files
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise


class Handler(BaseHTTPRequestHandler):
    server_version = "BaziloLocal/1.0"

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", (WEB_ROOT / "index.html").read_bytes())
            return
        static_types = {
            "/styles.css": "text/css; charset=utf-8",
            "/app.js": "text/javascript; charset=utf-8",
        }
        if path in static_types:
            asset = WEB_ROOT / path.lstrip("/")
            self._send(200, static_types[path], asset.read_bytes())
            return
        match = re.fullmatch(r"/api/archivos/([a-f0-9]{32})/([A-Za-z0-9_.-]+)", path)
        if match:
            job_id, filename = match.groups()
            with JOB_LOCK:
                artifacts = JOBS.get(job_id)
                artifact = next(
                    (item for item in artifacts.values() if item.name == filename), None
                ) if artifacts else None
            if artifact is None or not artifact.is_file():
                self._send(404, "application/json; charset=utf-8", b'{"error":"Archivo expirado o inexistente"}')
                return
            data = artifact.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            mime_type = {
                ".ly": "text/plain; charset=utf-8",
                ".pdf": "application/pdf",
                ".midi": "audio/midi",
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
            }[artifact.suffix]
            self.send_response(200)
            self.send_header("Content-Type", mime_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Checksum-SHA256", digest)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        if path not in static_types:
            self._send(404, "text/plain; charset=utf-8", b"No encontrado")

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/generar":
            self._send(404, "application/json; charset=utf-8", b'{"error":"No encontrado"}')
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._send(400, "application/json; charset=utf-8", b'{"error":"Solicitud invalida"}')
            return
        if not 0 < content_length <= MAX_REQUEST_BYTES:
            self._send(413, "application/json; charset=utf-8", b'{"error":"Solicitud demasiado grande"}')
            return
        try:
            payload = json.loads(self.rfile.read(content_length))
            notes = parse_notes(payload.get("notes") if isinstance(payload, dict) else None)
            job_id, files = generate_files(notes)
            if not files:
                raise ErrorBazilio(
                    "No se generaron archivos. Revisa LilyPond, TiMidity++ y ffmpeg.")
            response = json.dumps({"job": job_id, "notes": notes, "files": files}).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", response)
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ErrorBazilio) as error:
            response = json.dumps({"error": str(error)}, ensure_ascii=False).encode("utf-8")
            self._send(400, "application/json; charset=utf-8", response)
        except OSError as error:
            response = json.dumps(
                {"error": f"No se pudieron generar los archivos: {error}"},
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(500, "application/json; charset=utf-8", response)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[bazilo] {self.address_string()} - {format % args}")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    port = server.server_address[1]
    print(f"Bazilo disponible en http://{HOST}:{port}")
    print("Pulsa Ctrl+C para detener el servidor.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
