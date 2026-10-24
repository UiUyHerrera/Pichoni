from unittest.mock import Mock

import pytest
import requests

from nucleo.imagenes import ErrorImagen, Imagenes


def imagenes() -> Imagenes:
    return Imagenes("token", "123", {})


def respuesta(status_code: int, payload: dict) -> Mock:
    resultado = Mock()
    resultado.status_code = status_code
    resultado.json.return_value = payload
    return resultado


def test_subida_convierte_el_enlace_http_documentado_a_https(monkeypatch):
    monkeypatch.setattr(
        "nucleo.imagenes.requests.post",
        lambda *args, **kwargs: respuesta(
            200,
            {
                "status_code": 200,
                "status_txt": "OK",
                "image": {"url": "http://freeimage.host/images/2026/10/imagen.png"},
            },
        ),
    )
    servicio = imagenes()

    url = servicio.subir("foto.png", b"png-data")

    assert url == "https://freeimage.host/images/2026/10/imagen.png"
    assert servicio.subidas


def test_subida_conserva_enlace_https_devuelto_por_el_servidor(monkeypatch):
    monkeypatch.setattr(
        "nucleo.imagenes.requests.post",
        lambda *args, **kwargs: respuesta(
            200,
            {"status_code": 200, "image": {"url": "https://cdn.example.test/imagen.png"}},
        ),
    )

    assert imagenes().subir("foto.png", b"png-data") == "https://cdn.example.test/imagen.png"


def test_subida_rechaza_enlaces_http_de_otros_dominios(monkeypatch):
    monkeypatch.setattr(
        "nucleo.imagenes.requests.post",
        lambda *args, **kwargs: respuesta(
            200,
            {"status_code": 200, "image": {"url": "http://cdn.example.test/imagen.png"}},
        ),
    )

    with pytest.raises(ErrorImagen, match="HTTPS válido"):
        imagenes().subir("foto.png", b"png-data")


def test_subida_rechaza_respuesta_exitosa_sin_url_de_imagen(monkeypatch):
    monkeypatch.setattr(
        "nucleo.imagenes.requests.post",
        lambda *args, **kwargs: respuesta(200, {"status_code": 200, "image": {}}),
    )

    with pytest.raises(ErrorImagen, match="HTTPS válido"):
        imagenes().subir("foto.png", b"png-data")


def test_subida_muestra_motivo_de_rechazo_del_servidor(monkeypatch):
    monkeypatch.setattr(
        "nucleo.imagenes.requests.post",
        lambda *args, **kwargs: respuesta(
            200,
            {
                "status_code": 403,
                "status_txt": "FAIL",
                "error": {"message": "Invalid API key"},
            },
        ),
    )

    with pytest.raises(ErrorImagen, match="Invalid API key"):
        imagenes().subir("foto.png", b"png-data")


def test_subida_informa_un_error_http_sin_json(monkeypatch):
    resultado = respuesta(503, {})
    resultado.json.side_effect = ValueError("not JSON")
    monkeypatch.setattr("nucleo.imagenes.requests.post", lambda *args, **kwargs: resultado)

    with pytest.raises(ErrorImagen, match="HTTP 503"):
        imagenes().subir("foto.png", b"png-data")


def test_subida_informa_fallos_de_conexion(monkeypatch):
    def fallar(*args, **kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr("nucleo.imagenes.requests.post", fallar)

    with pytest.raises(ErrorImagen, match="Revisa tu internet"):
        imagenes().subir("foto.png", b"png-data")


@pytest.mark.parametrize("payload", [{"error": "unexpected"}, ["invalid"], [{}]])
def test_resolver_omite_respuestas_discord_malformadas(monkeypatch, payload):
    resultado = respuesta(200, payload)
    monkeypatch.setattr("nucleo.imagenes.requests.post", lambda *args, **kwargs: resultado)

    assert imagenes().resolver("https://example.test/image.png") is None


def test_resolver_omite_json_invalido(monkeypatch):
    resultado = respuesta(200, {})
    resultado.json.side_effect = ValueError("not JSON")
    monkeypatch.setattr("nucleo.imagenes.requests.post", lambda *args, **kwargs: resultado)

    assert imagenes().resolver("https://example.test/image.png") is None
