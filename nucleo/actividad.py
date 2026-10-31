import re
from collections.abc import Callable
from typing import Any

from .config import MOSTRAR, TIPOS

Resolver = Callable[[str], str | None]
MAX_ACTIVIDADES = 5


def textos_validos(lista: list[str]) -> list[str]:
    return [t for t in lista if t.strip()]


def elegir(lista: list[str], indice: int) -> str:
    validos = textos_validos(lista)
    return validos[indice % len(validos)] if validos else ""


def rota(perfil: dict[str, Any]) -> bool:
    return len(textos_validos(perfil["detalles"])) > 1 or len(textos_validos(perfil["texto"])) > 1


STREAM_DOMINIOS = re.compile(r"^https?://(www\.|m\.)?(twitch\.tv|youtube\.com|youtu\.be)/\S+", re.IGNORECASE)


def url_valida(url: str) -> bool:
    return url.startswith("https://") or url.startswith("http://")


def url_stream(url: str) -> bool:
    return bool(STREAM_DOMINIOS.match(url))


def construir(perfil: dict[str, Any], indice: int, inicio_ms: int, app_id: str, resolver: Resolver) -> dict[str, Any]:
    tipo = TIPOS[perfil["tipo"]]
    actividad: dict[str, Any] = {"name": perfil["nombre"] or perfil["titulo"] or "Discord", "type": tipo}
    detalles = elegir(perfil["detalles"], indice)
    texto = elegir(perfil["texto"], indice)
    if detalles:
        actividad["details"] = detalles
        if url_valida(perfil["detalles_url"]):
            actividad["details_url"] = perfil["detalles_url"]
    if texto:
        actividad["state"] = texto
        if url_valida(perfil["texto_url"]):
            actividad["state_url"] = perfil["texto_url"]
    if perfil["mostrar"] != "nombre":
        actividad["status_display_type"] = MOSTRAR[perfil["mostrar"]]
    if perfil["grupo"]["maximo"]:
        actividad["party"] = {"id": perfil["id"], "size": [max(1, perfil["grupo"]["actual"]), perfil["grupo"]["maximo"]]}
    if tipo == 1:
        if url_stream(perfil["url"]):
            actividad["url"] = perfil["url"]

    assets: dict[str, str] = {}
    for clave, destino in (("imagen", "large"), ("imagen_chica", "small")):
        datos = perfil[clave]
        if not datos["url"]:
            continue
        imagen = resolver(datos["url"])
        if imagen:
            assets[f"{destino}_image"] = imagen
            if datos["texto"]:
                assets[f"{destino}_text"] = datos["texto"]
            if url_valida(datos["link"]):
                assets[f"{destino}_url"] = datos["link"]
    if assets:
        actividad["assets"] = assets

    botones = [b for b in perfil["botones"] if b["texto"] and url_valida(b["url"])]
    if botones:
        actividad["buttons"] = [b["texto"] for b in botones]
        actividad["metadata"] = {"button_urls": [b["url"] for b in botones]}

    # Discord shows only one activity per application, so the ID goes only where buttons need it
    # and on streams, which the profile drops without it; images (mp:external) display fine without it.
    if botones or tipo == 1:
        actividad["application_id"] = app_id

    modo = perfil["tiempo"]["modo"] if perfil["tipo"] != "transmitiendo" else "ninguno"
    if modo == "transcurrido":
        actividad["timestamps"] = {"start": inicio_ms}
    elif modo == "fingido":
        actividad["timestamps"] = {"start": max(0, inicio_ms - perfil["tiempo"]["minutos"] * 60_000)}
    elif modo == "progreso":
        inicio = max(0, inicio_ms - perfil["tiempo"]["minutos"] * 60_000)
        total = max(perfil["tiempo"]["total"], perfil["tiempo"]["minutos"] + 1)
        actividad["timestamps"] = {"start": inicio, "end": inicio + total * 60_000}
    elif modo == "regresiva":
        actividad["timestamps"] = {"end": inicio_ms + perfil["tiempo"]["minutos"] * 60_000}
    return actividad


def personalizado(datos: dict[str, str]) -> dict[str, Any] | None:
    if not datos["texto"] and not datos["emoji"]:
        return None
    actividad: dict[str, Any] = {"name": "Custom Status", "type": 4}
    if datos["texto"]:
        actividad["state"] = datos["texto"]
    if datos["emoji"]:
        actividad["emoji"] = {"name": datos["emoji"]}
    return actividad
