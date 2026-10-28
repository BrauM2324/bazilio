from __future__ import annotations

import hashlib
import json
import sys
import urllib.error
import urllib.request

NOTES = "(:) {E E F G G F E D C C D E E D D}"
BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8765"

request = urllib.request.Request(
    f"{BASE_URL}/api/generar",
    data=json.dumps({"notes": NOTES}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=180) as response:
        payload = json.load(response)
except urllib.error.URLError as error:
    raise SystemExit(f"No se pudo contactar el servidor {BASE_URL}: {error}")

for artifact in payload["files"]:
    with urllib.request.urlopen(BASE_URL + artifact["url"], timeout=60) as response:
        data = response.read()
        declared_length = int(response.headers["Content-Length"])
        declared_hash = response.headers["X-Checksum-SHA256"]
    actual_hash = hashlib.sha256(data).hexdigest()
    if len(data) != artifact["size"] or declared_length != artifact["size"]:
        raise SystemExit(f"{artifact['name']}: tamaño descargado incompleto")
    if actual_hash != artifact["sha256"] or actual_hash != declared_hash:
        raise SystemExit(f"{artifact['name']}: checksum SHA-256 incorrecto")
    print(f"OK {artifact['name']}: {len(data)} bytes, SHA-256 verificado")
