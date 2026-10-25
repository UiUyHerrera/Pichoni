import hashlib
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .version import REPOSITORIO

MAX_TAMANO_INSTALADOR = 100 * 1024 * 1024


class ErrorActualizacion(Exception):
    pass


def descargar_instalador(url: str, version: str, tamano: int, digest: str) -> Path:
    if not isinstance(version, str) or re.fullmatch(r"\d+\.\d+\.\d+", version) is None:
        raise ErrorActualizacion("La versión publicada no es válida.")
    nombre = f"Pichoni-Setup-{version}.exe"
    esperado = f"/{REPOSITORIO}/releases/download/v{version}/{nombre}"
    try:
        partes = urlsplit(url)
        hostname = partes.hostname
    except ValueError as error:
        raise ErrorActualizacion("El enlace del instalador no es válido.") from error
    if (
        partes.scheme != "https"
        or hostname != "github.com"
        or partes.path != esperado
        or partes.query
        or partes.fragment
    ):
        raise ErrorActualizacion("El enlace del instalador no pertenece al release oficial.")
    if not isinstance(tamano, int) or isinstance(tamano, bool) or not 0 < tamano <= MAX_TAMANO_INSTALADOR:
        raise ErrorActualizacion("El tamaño del instalador no es válido.")
    coincidencia = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", digest) if isinstance(digest, str) else None
    if coincidencia is None:
        raise ErrorActualizacion("El release no incluye un SHA-256 válido.")

    destino = Path(tempfile.gettempdir()) / nombre
    descriptor, temporal_nombre = tempfile.mkstemp(prefix="Pichoni-Update-", suffix=".exe.part")
    temporal = Path(temporal_nombre)
    descargados = 0
    huella = hashlib.sha256()
    completo = False
    try:
        with requests.get(url, stream=True, timeout=(10, 30)) as respuesta:
            respuesta.raise_for_status()
            longitud = respuesta.headers.get("Content-Length")
            if longitud is not None and int(longitud) != tamano:
                raise ErrorActualizacion("El tamaño descargado no coincide con el release.")
            with os.fdopen(descriptor, "wb") as archivo:
                descriptor = -1
                for bloque in respuesta.iter_content(chunk_size=1024 * 1024):
                    if not bloque:
                        continue
                    descargados += len(bloque)
                    if descargados > tamano:
                        raise ErrorActualizacion("El instalador descargado excede el tamaño esperado.")
                    huella.update(bloque)
                    archivo.write(bloque)
        if descargados != tamano or huella.hexdigest().lower() != coincidencia.group(1).lower():
            raise ErrorActualizacion("La verificación SHA-256 del instalador falló.")
        os.replace(temporal, destino)
        completo = True
        return destino
    except (requests.RequestException, OSError, ValueError) as error:
        raise ErrorActualizacion("No se pudo descargar y verificar el instalador.") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if not completo:
            temporal.unlink(missing_ok=True)
