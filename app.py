import base64
import shutil
import sys
import threading
import time
import webbrowser
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pystray
import requests
import webview
from PIL import Image

from nucleo import sistema
from nucleo.config import TIPOS, Almacen, normalizar
from nucleo.gateway import Conexion, compartir_actividad, obtener_usuario
from nucleo.imagenes import ErrorImagen, Imagenes
from nucleo.rotacion import Motor, buscar
from nucleo.version import PAGINA_VERSIONES, REPOSITORIO, VERSION, es_version_nueva


def recurso(nombre: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "ui" / nombre


def avatar(usuario: dict[str, Any]) -> str:
    if usuario.get("avatar"):
        return f"https://cdn.discordapp.com/avatars/{usuario['id']}/{usuario['avatar']}.png?size=128"
    return "https://cdn.discordapp.com/embed/avatars/0.png"


class Servicio:
    def __init__(self) -> None:
        self.almacen = Almacen()
        self.config = self.almacen.cargar()
        self.candado = threading.RLock()
        self.motor = Motor()
        self.conexion: Conexion | None = None
        self.imagenes: Imagenes | None = None
        self.aplicar_candado = threading.Lock()
        self.usuario: dict[str, Any] | None = None
        self.compartir: bool | None = None
        self.token = self.almacen.leer_token()
        self.token_invalido = False
        self.ultimo_envio = 0.0
        self.pendiente = False
        self.revision = 0
        self.reemplazos: dict[str, str] = {}

    def conectar(self) -> bool:
        if not self.token:
            return False
        usuario = obtener_usuario(self.token)
        if usuario is None:
            self.token_invalido = True
            return False
        self.token_invalido = False
        self.usuario = usuario
        if self.conexion:
            self.conexion.detener()
        self.imagenes = Imagenes(self.token, self.config["app_id"], self.config["subidas"])
        self.conexion = Conexion(self.token, self._al_conectar)
        with self.candado:
            self.motor.activar(self.config["perfil_activo"], time.time())
            self.conexion.activities = []
            self.conexion.punto = self.config["punto"]
            self.ultimo_envio = 0.0
        self.conexion.iniciar()
        self.aplicar()
        return True

    def _al_conectar(self) -> None:
        threading.Thread(target=self._revisar_compartir, daemon=True).start()
        threading.Thread(target=self._rehospedar, daemon=True).start()

    def _rehospedar(self) -> None:
        imagenes = self.imagenes
        if imagenes is None:
            return
        with self.candado:
            urls = {
                p[clave]["url"]
                for p in self.config["perfiles"]
                for clave in ("imagen", "imagen_chica")
                if imagenes.necesita_rehospedar(p[clave]["url"])
            }
        nuevas = {url: imagenes.rehospedar(url) for url in urls}
        nuevas = {vieja: nueva for vieja, nueva in nuevas.items() if nueva}
        if not nuevas:
            return
        with self.candado:
            self.reemplazos.update(nuevas)
            for p in self.config["perfiles"]:
                for clave in ("imagen", "imagen_chica"):
                    if p[clave]["url"] in nuevas:
                        p[clave]["url"] = nuevas[p[clave]["url"]]
            self.guardar_config()
            self.revision += 1
        self.aplicar()

    def _revisar_compartir(self) -> None:
        self.compartir = compartir_actividad(self.token)

    def aplicar(self) -> None:
        with self.aplicar_candado:
            self._aplicar()

    def _aplicar(self) -> None:
        with self.candado:
            if self.conexion is None:
                return
            if time.time() - self.ultimo_envio < 2:
                self.pendiente = True
                return
            conexion = self.conexion
            config = deepcopy(self.config)
            motor = deepcopy(self.motor)
            imagenes = self.imagenes

        if imagenes is None:
            actividades = []
        else:
            resolver = lambda url: imagenes.resolver(url, app_id=config["app_id"])
            actividades = motor.actividades(config, resolver)

        with self.candado:
            motor_actual = (
                self.motor.perfil_id,
                self.motor.indice,
                self.motor.inicio,
                self.motor.ultimo_texto,
                self.motor.ultimo_perfil,
            )
            motor_capturado = (
                motor.perfil_id,
                motor.indice,
                motor.inicio,
                motor.ultimo_texto,
                motor.ultimo_perfil,
            )
            if (
                self.conexion is not conexion
                or self.imagenes is not imagenes
                or self.config != config
                or motor_actual != motor_capturado
            ):
                self.pendiente = True
                return
            self.motor.actividades_omitidas = motor.actividades_omitidas
            self.pendiente = False
            self.ultimo_envio = time.time()
            conexion.actualizar(actividades, config["punto"])

    def guardar_config(self) -> None:
        self.almacen.guardar(self.config)

    def ciclo(self) -> None:
        while True:
            time.sleep(1)
            with self.candado:
                antes = self.config["perfil_activo"]
                cambio = self.motor.paso(self.config, time.time())
                if self.config["perfil_activo"] != antes:
                    self.guardar_config()
            if cambio or self.pendiente:
                self.aplicar()

    def estado(self) -> dict[str, Any]:
        visible = None
        conexion = self.conexion
        with self.candado:
            perfil = buscar(self.config, self.motor.perfil_id)
            if conexion and perfil and conexion.visibles is not None:
                visible = TIPOS[perfil["tipo"]] in conexion.visibles
            config = deepcopy(self.config)
            indice = self.motor.indice
            inicio = self.motor.inicio
            revision = self.revision
            actividades_omitidas = self.motor.actividades_omitidas
        config.pop("subidas", None)
        usuario = None
        if self.usuario:
            nombre = self.usuario.get("global_name") or ""
            usuario = {
                "nombre": nombre if any(c.isalnum() for c in nombre) else self.usuario["username"],
                "tag": self.usuario["username"],
                "avatar": avatar(self.usuario),
            }
        return {
            "usuario": usuario,
            "config": config,
            "conectado": bool(conexion and conexion.conectado),
            "visible": visible,
            "compartir": self.compartir,
            "tiene_token": bool(self.token) and not self.token_invalido and not (conexion and conexion.token_invalido),
            "indice": indice,
            "inicio": inicio,
            "revision": revision,
            "actividades_omitidas": actividades_omitidas,
        }


class Api:
    def __init__(self, servicio: Servicio) -> None:
        self._s = servicio
        self._ventana: Any = None
        self._bandeja: Any = None
        self._maximizada = False

    def estado(self) -> dict[str, Any]:
        return self._s.estado()

    def comprobar_actualizacion(self) -> dict[str, Any]:
        try:
            respuesta = requests.get(
                f"https://api.github.com/repos/{REPOSITORIO}/releases/latest",
                headers={"Accept": "application/vnd.github+json"},
                timeout=8,
            )
        except requests.RequestException:
            return {"estado": "error"}

        if respuesta.status_code == 404:
            return {"estado": "sin_versiones", "actual": VERSION, "url": PAGINA_VERSIONES}
        if respuesta.status_code != 200:
            return {"estado": "error"}

        try:
            release = respuesta.json()
            version = release.get("tag_name", "").removeprefix("v")
        except (ValueError, AttributeError):
            return {"estado": "error"}
        if not version:
            return {"estado": "error"}
        assets = release.get("assets", [])
        if not isinstance(assets, list):
            return {"estado": "error"}
        instalador = next(
            (
                asset.get("browser_download_url")
                for asset in assets
                if isinstance(asset, dict)
                and isinstance(asset.get("name"), str)
                and asset["name"].startswith("Pichoni-Setup-")
                and asset["name"].endswith(".exe")
                and isinstance(asset.get("browser_download_url"), str)
            ),
            PAGINA_VERSIONES,
        )
        return {
            "estado": "disponible" if es_version_nueva(version) else "actualizada",
            "actual": VERSION,
            "disponible": version,
            "url": instalador,
        }

    def abrir_pagina_descargas(self, url: str | None = None) -> bool:
        destino = PAGINA_VERSIONES
        if url:
            parsed = urlparse(url)
            if (
                parsed.scheme == "https"
                and parsed.hostname == "github.com"
                and parsed.path.startswith(f"/{REPOSITORIO}/releases/")
            ):
                destino = url
        return webbrowser.open(destino)

    def guardar(self, nueva: dict[str, Any]) -> dict[str, Any]:
        s = self._s
        with s.candado:
            subidas = s.config["subidas"]
            config = normalizar({**nueva, "subidas": subidas})
            for p in config["perfiles"]:
                for clave in ("imagen", "imagen_chica"):
                    p[clave]["url"] = s.reemplazos.get(p[clave]["url"], p[clave]["url"])
            if config["iniciar_con_windows"] != s.config["iniciar_con_windows"]:
                if not sistema.iniciar_con_windows(config["iniciar_con_windows"]):
                    config["iniciar_con_windows"] = s.config["iniciar_con_windows"]
            if config["app_id"] != s.config["app_id"] and s.imagenes:
                s.imagenes.app_id = config["app_id"]
                s.imagenes.cache.clear()
            s.config = config
            s.guardar_config()
            if config["perfil_activo"] != s.motor.perfil_id:
                s.motor.activar(config["perfil_activo"], time.time())
        s.aplicar()
        return s.estado()

    def guardar_token(self, token: str) -> dict[str, Any]:
        token = token.strip().strip('"')
        if not token:
            return {"error": "Pega tu token."}
        if obtener_usuario(token) is None:
            return {"error": "Ese token no funciona. Revisa que esté completo."}
        self._s.almacen.guardar_token(token)
        self._s.token = token
        self._s.conectar()
        return self._s.estado()

    def borrar_token(self) -> dict[str, Any]:
        s = self._s
        if s.conexion:
            s.conexion.detener()
        s.conexion = None
        s.imagenes = None
        s.usuario = None
        s.token = ""
        s.compartir = None
        try:
            s.almacen.archivo_token.unlink(missing_ok=True)
        except OSError:
            pass
        return s.estado()

    def minimizar(self) -> None:
        if self._ventana:
            self._ventana.minimize()

    def maximizar(self) -> bool:
        if self._ventana is None:
            return False
        if self._maximizada:
            self._ventana.restore()
        else:
            self._ventana.maximize()
        self._maximizada = not self._maximizada
        return self._maximizada

    def cerrar(self) -> None:
        if self._bandeja:
            self._bandeja.ocultar()

    def activar_compartir(self) -> dict[str, Any]:
        resultado = compartir_actividad(self._s.token, True)
        if resultado:
            self._s.compartir = True
            self._s.aplicar()
        return {"ok": bool(resultado)}

    def _subir(self, nombre: str, contenido: bytes) -> dict[str, Any]:
        if self._s.imagenes is None:
            return {"error": "Conéctate primero."}
        try:
            url = self._s.imagenes.subir(nombre, contenido)
        except ErrorImagen as e:
            return {"error": str(e)}
        with self._s.candado:
            self._s.guardar_config()
        return {"url": url}

    def subir_archivo(self, nombre: str, datos: str) -> dict[str, Any]:
        try:
            contenido = base64.b64decode(datos.split(",", 1)[-1], validate=True)
        except ValueError:
            return {"error": "No se pudo leer la imagen."}
        return self._subir(nombre, contenido)

    def elegir_archivo(self) -> dict[str, Any]:
        if self._ventana is None:
            return {"error": "Ventana no lista."}
        rutas = self._ventana.create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=("Imágenes (*.png;*.jpg;*.jpeg;*.gif;*.webp)",),
        )
        if not rutas:
            return {"cancelado": True}
        ruta = Path(rutas[0])
        try:
            contenido = ruta.read_bytes()
        except OSError:
            return {"error": "No se pudo abrir el archivo."}
        return self._subir(ruta.name, contenido)


class Bandeja:
    def __init__(self, ventana: Any, servicio: Servicio) -> None:
        self.ventana = ventana
        self.servicio = servicio
        self.saliendo = False
        self.avisado = False
        menu = pystray.Menu(
            pystray.MenuItem("Abrir", self.abrir, default=True),
            pystray.MenuItem("Quitar actividad", self.quitar),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir", self.salir),
        )
        self.icono = pystray.Icon("Pichoni", Image.open(recurso("icono.png")), "Pichoni", menu)

    def iniciar(self) -> None:
        self.icono.run_detached()

    def abrir(self, *_: Any) -> None:
        self.ventana.show()
        self.ventana.restore()
        threading.Timer(0.12, self.animar_apertura).start()

    def animar_apertura(self) -> None:
        self.ventana.evaluate_js(
            "window.iniciarAnimacionApertura && window.iniciarAnimacionApertura()"
        )

    def ocultar(self) -> None:
        if not self.saliendo:
            self.ventana.hide()

    def quitar(self, *_: Any) -> None:
        with self.servicio.candado:
            self.servicio.config["perfil_activo"] = None
            self.servicio.config["rotar_perfiles"]["activo"] = False
            self.servicio.guardar_config()
        self.servicio.motor.activar(None, time.time())
        self.servicio.aplicar()

    def salir(self, *_: Any) -> None:
        self.saliendo = True
        self.icono.stop()
        if self.servicio.conexion:
            self.servicio.conexion.detener()
        self.ventana.destroy()

    def al_cerrar(self) -> bool:
        if self.saliendo:
            return True
        self.ventana.evaluate_js(
            "window.iniciarAnimacionCierre && window.iniciarAnimacionCierre()"
        )
        threading.Timer(0.85, self.ocultar).start()
        if not self.avisado:
            self.avisado = True
            try:
                self.icono.notify("Sigue activo en la bandeja. Clic derecho en el ícono para salir.", "Pichoni")
            except NotImplementedError:
                pass
        return False


def main() -> None:
    if not sistema.instancia_unica():
        return
    oculto = "--oculto" in sys.argv
    servicio = Servicio()
    api = Api(servicio)
    ventana = webview.create_window(
        "Pichoni",
        str(recurso("index.html")),
        js_api=api,
        width=1120,
        height=760,
        min_size=(860, 600),
        hidden=oculto,
        frameless=True,
        easy_drag=False,
        background_color="#0B0B0D",
    )
    api._ventana = ventana
    bandeja = Bandeja(ventana, servicio)
    api._bandeja = bandeja
    ventana.events.closing += bandeja.al_cerrar

    def arrancar() -> None:
        bandeja.iniciar()
        servicio.conectar()
        threading.Thread(target=servicio.ciclo, daemon=True).start()

    web = servicio.almacen.carpeta / "web"
    # WebView2 caches the UI files over HTTP; drop that cache so app updates always load.
    for cache in ("Cache", "Code Cache"):
        shutil.rmtree(web / "EBWebView" / "Default" / cache, ignore_errors=True)
    webview.start(arrancar, gui="edgechromium", private_mode=False, storage_path=str(web))


if __name__ == "__main__":
    main()
