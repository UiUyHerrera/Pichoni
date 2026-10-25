import io
from unittest.mock import Mock

import pytest
import requests
from PIL import Image, ImageSequence

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


def test_subida_no_necesita_token_de_discord(monkeypatch):
    monkeypatch.setattr(
        "nucleo.imagenes.requests.post",
        lambda *args, **kwargs: respuesta(
            200,
            {"status_code": 200, "image": {"url": "https://cdn.example.test/imagen.png"}},
        ),
    )
    uploader = Imagenes("", "123", {})

    assert uploader.subir("foto.png", b"png-data") == "https://cdn.example.test/imagen.png"


def test_recorte_redimensiona_imagen_estatica_a_encuadre_cuadrado():
    origen = Image.new("RGB", (200, 100), "red")
    origen.paste(Image.new("RGB", (100, 100), "blue"), (100, 0))
    contenido = io.BytesIO()
    origen.save(contenido, format="PNG")

    recortada = Imagenes._recortar(
        ".png",
        contenido.getvalue(),
        {"x": 0.5, "y": 0, "ancho": 0.5, "alto": 1},
    )

    imagen = Image.open(io.BytesIO(recortada))
    assert imagen.size == (512, 512)
    assert imagen.getpixel((256, 256))[:3] == (0, 0, 255)


def test_recorte_conserva_todos_los_fotogramas_y_duracion_del_gif():
    origen = [
        Image.new("RGBA", (200, 100), (255, 0, 0, 255)),
        Image.new("RGBA", (200, 100), (0, 0, 255, 255)),
    ]
    contenido = io.BytesIO()
    origen[0].save(
        contenido,
        format="GIF",
        save_all=True,
        append_images=origen[1:],
        duration=[80, 140],
        loop=0,
    )

    recortada = Imagenes._recortar(
        ".gif",
        contenido.getvalue(),
        {"x": 0.25, "y": 0, "ancho": 0.5, "alto": 1},
    )
    resultado = Image.open(io.BytesIO(recortada))

    assert resultado.size == (512, 512)
    assert resultado.n_frames == 2
    assert [frame.info["duration"] for frame in ImageSequence.Iterator(resultado)] == [80, 140]


def test_recorte_rechaza_una_region_que_no_sea_cuadrada():
    contenido = io.BytesIO()
    Image.new("RGB", (100, 100), "red").save(contenido, format="PNG")

    with pytest.raises(ErrorImagen, match="cuadrado"):
        Imagenes._recortar(
            ".png",
            contenido.getvalue(),
            {"x": 0, "y": 0, "ancho": 0.5, "alto": 0.4},
        )


def test_recorte_rechaza_extension_que_no_coincide_con_el_archivo():
    contenido = io.BytesIO()
    Image.new("RGB", (100, 100), "red").save(contenido, format="PNG")

    with pytest.raises(ErrorImagen, match="extensión"):
        Imagenes._recortar(
            ".jpg",
            contenido.getvalue(),
            {"x": 0, "y": 0, "ancho": 1, "alto": 1},
        )


def test_recorte_rechaza_gif_con_demasiados_fotogramas():
    fotogramas = [Image.new("RGB", (2, 2), (indice % 255, 0, 0)) for indice in range(121)]
    contenido = io.BytesIO()
    fotogramas[0].save(contenido, format="GIF", save_all=True, append_images=fotogramas[1:])

    with pytest.raises(ErrorImagen, match="fotogramas"):
        Imagenes._recortar(
            ".gif",
            contenido.getvalue(),
            {"x": 0, "y": 0, "ancho": 1, "alto": 1},
        )


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
