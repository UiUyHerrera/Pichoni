import base64
import json
import os
import shutil
import subprocess
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
from nucleo.actualizador import ErrorActualizacion, descargar_instalador
from nucleo.config import TIPOS, Almacen, normalizar
from nucleo.gateway import Conexion, compartir_actividad, obtener_usuario
from nucleo.imagenes import ErrorImagen, Imagenes
from nucleo.rotacion import Motor, buscar
from nucleo.rpc import ConexionRPC
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
        self.conexion: Conexion | ConexionRPC | None = None
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
        if self.config["modo_conexion"] == "rpc":
            return self.conectar_rpc()
        return self.conectar_token()

    def conectar_token(self) -> bool:
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

    def conectar_rpc(self) -> bool:
        if self.conexion:
            self.conexion.detener()
        self.token_invalido = False
        self.usuario = None
        self.compartir = None
        self.imagenes = Imagenes("", self.config["app_id"], self.config["subidas"])
        self.conexion = ConexionRPC(self.config["app_id"], self.aplicar)
        with self.candado:
            self.motor.activar(self.config["perfil_activo"], time.time())
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

        config_actividad = config
        if config["modo_conexion"] == "rpc":
            config_actividad = deepcopy(config)
            config_actividad["perfiles_extra"] = []
            config_actividad["personalizado"] = {"texto": "", "emoji": ""}
            resolver = lambda url: url if url.startswith("https://") and not url.startswith("mp:") else None
            actividades = motor.actividades(config_actividad, resolver)
        elif imagenes is None:
            actividades = []
        else:
            resolver = lambda url: imagenes.resolver(url, app_id=config["app_id"])
            actividades = motor.actividades(config_actividad, resolver)

        with self.candado:
            motor_actual = (
                self.motor.perfil_id,
                self.motor.indice,
                self.motor.inicio,
            )
            motor_capturado = (
                motor.perfil_id,
                motor.indice,
                motor.inicio,
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
                config_ciclo = self.config
                if self.config["modo_conexion"] == "rpc":
                    config_ciclo = deepcopy(self.config)
                    config_ciclo["perfiles_extra"] = []
                    config_ciclo["personalizado"] = {"texto": "", "emoji": ""}
                antes = self.config["perfil_activo"]
                cambio = self.motor.paso(config_ciclo, time.time())
                if config_ciclo is not self.config:
                    self.config["perfil_activo"] = config_ciclo["perfil_activo"]
                if self.config["perfil_activo"] != antes:
                    self.guardar_config()
            if cambio or self.pendiente:
                self.aplicar()

    def estado(self) -> dict[str, Any]:
        visible = None
        conexion = self.conexion
        with self.candado:
            perfil = buscar(self.config, self.motor.perfil_id)
            if isinstance(conexion, Conexion) and perfil and conexion.visibles is not None:
                visible = TIPOS[perfil["tipo"]] in conexion.visibles
            config = deepcopy(self.config)
            indice = self.motor.indice
            inicio = self.motor.inicio
            revision = self.revision
            actividades_omitidas = (
                conexion.actividades_omitidas
                if isinstance(conexion, ConexionRPC)
                else self.motor.actividades_omitidas
            )
            token_invalido = self.token_invalido or (
                isinstance(conexion, Conexion) and conexion.token_invalido
            )
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
            "modo_conexion": config["modo_conexion"],
            "error_conexion": conexion.error if isinstance(conexion, ConexionRPC) else None,
            "visible": visible,
            "compartir": self.compartir,
            "tiene_token": bool(self.token) and not token_invalido,
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
        self._actualizacion_candado = threading.Lock()
        self._actualizacion_iniciada = False

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
                asset
                for asset in assets
                if isinstance(asset, dict)
                and asset.get("name") == f"Pichoni-Setup-{version}.exe"
            ),
            None,
        )
        return {
            "estado": "disponible" if es_version_nueva(version) else "actualizada",
            "actual": VERSION,
            "disponible": version,
            "url": instalador.get("browser_download_url", PAGINA_VERSIONES) if instalador else PAGINA_VERSIONES,
            "digest": instalador.get("digest") if instalador else None,
            "tamano": instalador.get("size") if instalador else None,
        }

    def iniciar_actualizacion_automatica(self) -> dict[str, str]:
        instalacion = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / "Pichoni"
        if not getattr(sys, "frozen", False) or Path(sys.executable).resolve().parent != instalacion.resolve():
            return {"estado": "no_aplica"}
        with self._actualizacion_candado:
            if self._actualizacion_iniciada:
                return {"estado": "buscando"}
            self._actualizacion_iniciada = True
        threading.Thread(target=self._actualizar_automaticamente, daemon=True).start()
        return {"estado": "buscando"}

    def _actualizar_automaticamente(self) -> None:
        actualizacion = self.comprobar_actualizacion()
        if actualizacion.get("estado") != "disponible":
            return
        version = actualizacion.get("disponible")
        digest = actualizacion.get("digest")
        tamano = actualizacion.get("tamano")
        url = actualizacion.get("url")
        if not all(isinstance(valor, str) for valor in (version, digest, url)) or not isinstance(tamano, int):
            self._notificar_actualizacion("No se pudo verificar la actualización. Revisa Ajustes > Actualizaciones.")
            return
        try:
            instalador = descargar_instalador(url, version, tamano, digest)
            subprocess.Popen(
                [
                    str(instalador),
                    "/VERYSILENT",
                    "/SUPPRESSMSGBOXES",
                    "/NORESTART",
                    "/SP-",
                ],
                close_fds=True,
                creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        except (ErrorActualizacion, OSError, subprocess.SubprocessError):
            self._notificar_actualizacion("No se pudo instalar automáticamente. Puedes actualizar desde Ajustes.")
            return
        self._notificar_actualizacion(f"Instalando Pichoni {version}…")
        time.sleep(1)
        if self._bandeja:
            self._bandeja.salir()

    def _notificar_actualizacion(self, mensaje: str) -> None:
        if self._ventana:
            self._ventana.evaluate_js(
                "window.notificarActualizacionAutomatica && "
                f"window.notificarActualizacionAutomatica({json.dumps(mensaje)})"
            )

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
            anterior_app_id = s.config["app_id"]
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
            if s.imagenes:
                s.imagenes.subidas = config["subidas"]
            s.guardar_config()
            if config["perfil_activo"] != s.motor.perfil_id:
                s.motor.activar(config["perfil_activo"], time.time())
            reiniciar_rpc = config["modo_conexion"] == "rpc" and config["app_id"] != anterior_app_id
        if reiniciar_rpc:
            s.conectar_rpc()
        else:
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
        self._s.config["modo_conexion"] = "token"
        self._s.config["inicio_completado"] = True
        self._s.guardar_config()
        self._s.conectar()
        return self._s.estado()

    def cambiar_modo_conexion(self, modo: str) -> dict[str, Any]:
        s = self._s
        if modo not in ("rpc", "token"):
            return {"error": "Modo de conexión no válido."}
        with s.candado:
            s.config["inicio_completado"] = True
            if s.config["modo_conexion"] == modo:
                s.guardar_config()
                return s.estado()
            anterior = s.conexion
            s.config["modo_conexion"] = modo
            s.guardar_config()
            s.conexion = None
            s.imagenes = None
            s.usuario = None
            s.compartir = None
        if anterior:
            anterior.detener()
        if modo == "rpc":
            s.conectar_rpc()
        elif s.token:
            s.conectar_token()
        return s.estado()

    def borrar_token(self) -> dict[str, Any]:
        s = self._s
        try:
            s.almacen.archivo_token.unlink(missing_ok=True)
        except OSError as error:
            return {"error": f"No se pudo eliminar el token guardado: {error}"}
        if s.conexion:
            s.conexion.detener()
        s.conexion = None
        s.imagenes = None
        s.usuario = None
        s.token = ""
        s.compartir = None
        s.config["modo_conexion"] = "rpc"
        s.guardar_config()
        s.conectar_rpc()
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
        elif self._ventana:
            self._ventana.destroy()

    def activar_compartir(self) -> dict[str, Any]:
        resultado = compartir_actividad(self._s.token, True)
        if resultado:
            self._s.compartir = True
            self._s.aplicar()
        return {"ok": bool(resultado)}

    def _subir(self, nombre: str, contenido: bytes, recorte: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._s.imagenes is None:
            return {"error": "Conéctate primero."}
        try:
            url = self._s.imagenes.subir(nombre, contenido, recorte)
        except ErrorImagen as e:
            return {"error": str(e)}
        with self._s.candado:
            self._s.config["subidas"] = self._s.imagenes.subidas
            self._s.guardar_config()
        return {"url": url}

    def subir_archivo(
        self, nombre: str, datos: str, recorte: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            contenido = base64.b64decode(datos.split(",", 1)[-1], validate=True)
        except ValueError:
            return {"error": "No se pudo leer la imagen."}
        return self._subir(nombre, contenido, recorte)

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
            if ruta.stat().st_size > 10 * 1024 * 1024:
                return {"error": "La imagen pesa más de 10 MB."}
            contenido = ruta.read_bytes()
        except OSError:
            return {"error": "No se pudo abrir el archivo."}
        tipo = {".jpg": "jpeg", ".jpeg": "jpeg"}.get(ruta.suffix.lower(), ruta.suffix.lstrip(".").lower())
        return {
            "nombre": ruta.name,
            "datos": f"data:image/{tipo};base64,{base64.b64encode(contenido).decode('ascii')}",
        }


class Bandeja:
    def __init__(self, ventana: Any, servicio: Servicio) -> None:
        self.ventana = ventana
        self.servicio = servicio
        self.saliendo = False
        self._salida_candado = threading.Lock()
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
        if self.icono.HAS_NOTIFICATION:
            self.icono.remove_notification()
        self.ventana.show()
        self.ventana.restore()
        threading.Timer(0.12, self.animar_apertura).start()

    def animar_apertura(self) -> None:
        self.ventana.evaluate_js(
            "window.iniciarAnimacionApertura && window.iniciarAnimacionApertura()"
        )

    def quitar(self, *_: Any) -> None:
        with self.servicio.candado:
            self.servicio.config["perfil_activo"] = None
            self.servicio.guardar_config()
        self.servicio.motor.activar(None, time.time())
        self.servicio.aplicar()

    def salir(self, *_: Any) -> None:
        with self._salida_candado:
            if self.saliendo:
                return
            self.saliendo = True
        self.icono.stop()
        if self.servicio.conexion:
            self.servicio.conexion.detener()
        self.ventana.destroy()

    def ocultar(self) -> bool:
        if self.saliendo:
            return True
        self.ventana.hide()
        if self.icono.HAS_NOTIFICATION:
            self.icono.notify(
                "Pichoni sigue funcionando en segundo plano. Para cerrarlo por completo, elige Salir desde el icono de la bandeja.",
                "Pichoni",
            )
        return False

    def al_cerrar(self) -> bool:
        return self.ocultar()


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
