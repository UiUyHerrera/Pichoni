import hashlib

import pytest
import requests

from nucleo.actualizador import ErrorActualizacion, descargar_instalador
from nucleo.version import REPOSITORIO


class RespuestaFalsa:
    def __init__(self, contenido):
        self.contenido = contenido
        self.headers = {"Content-Length": str(len(contenido))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.contenido


def url_instalador():
    return f"https://github.com/{REPOSITORIO}/releases/download/v1.2.3/Pichoni-Setup-1.2.3.exe"


def test_descarga_verifica_sha256_y_tamano(monkeypatch, tmp_path):
    contenido = b"installer bytes"
    monkeypatch.setattr("nucleo.actualizador.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("nucleo.actualizador.requests.get", lambda *args, **kwargs: RespuestaFalsa(contenido))

    ruta = descargar_instalador(
        url_instalador(),
        "1.2.3",
        len(contenido),
        f"sha256:{hashlib.sha256(contenido).hexdigest()}",
    )

    assert ruta.read_bytes() == contenido
    ruta.unlink()


@pytest.mark.parametrize(
    "url,version,tamano,digest",
    [
        ("http://github.com/release.exe", "1.2.3", 10, "sha256:" + "0" * 64),
        ("https://example.com/release.exe", "1.2.3", 10, "sha256:" + "0" * 64),
        ("https://github.com/[::1]/release.exe", "1.2.3", 10, "sha256:" + "0" * 64),
        (url_instalador(), "1.2.3", 0, "sha256:" + "0" * 64),
        (url_instalador(), "1.2.3", 10, "invalid"),
        (url_instalador(), "../1", 10, "sha256:" + "0" * 64),
    ],
)
def test_descarga_rechaza_metadatos_no_confiables(url, version, tamano, digest):
    with pytest.raises(ErrorActualizacion):
        descargar_instalador(url, version, tamano, digest)


def test_descarga_rechaza_instalador_con_hash_incorrecto(monkeypatch, tmp_path):
    contenido = b"tampered installer"
    monkeypatch.setattr("nucleo.actualizador.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("nucleo.actualizador.requests.get", lambda *args, **kwargs: RespuestaFalsa(contenido))

    with pytest.raises(ErrorActualizacion, match="SHA-256"):
        descargar_instalador(url_instalador(), "1.2.3", len(contenido), "sha256:" + "0" * 64)

    assert list(tmp_path.iterdir()) == []


def test_descarga_expone_fallos_de_red(monkeypatch, tmp_path):
    def fallar(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("nucleo.actualizador.tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("nucleo.actualizador.requests.get", fallar)

    with pytest.raises(ErrorActualizacion, match="No se pudo descargar"):
        descargar_instalador(url_instalador(), "1.2.3", 10, "sha256:" + "0" * 64)
