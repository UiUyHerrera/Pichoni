import threading
import time
from collections.abc import Callable
from copy import deepcopy
from typing import Any

from pypresence import ActivityType, Presence, PyPresenceException


TIPOS_RPC = {0, 2, 3, 5}


class ConexionRPC:
    def __init__(self, app_id: str, al_conectar: Callable[[], None] | None = None) -> None:
        self.app_id = app_id
        self.al_conectar = al_conectar
        self.actividades: list[dict[str, Any]] = []
        self.punto = "online"
        self.conectado = False
        self.actividades_omitidas = 0
        self.error: str | None = None
        self._parar = threading.Event()
        self._cambio = threading.Event()
        self._candado = threading.Lock()
        self._hilo = threading.Thread(target=self._correr, daemon=True)

    def iniciar(self) -> None:
        self._hilo.start()

    def detener(self) -> None:
        self._parar.set()
        self._cambio.set()
        if self._hilo.is_alive() and threading.current_thread() is not self._hilo:
            self._hilo.join(timeout=6)

    def actualizar(self, activities: list[dict[str, Any]], punto: str) -> None:
        with self._candado:
            self.actividades = deepcopy(activities)
            self.punto = punto
        self._cambio.set()

    def _actividad_rpc(self) -> dict[str, Any] | None:
        with self._candado:
            actividades = deepcopy(self.actividades)
        seleccionada = next((a for a in actividades if a.get("type") in TIPOS_RPC), None)
        self.actividades_omitidas = len(actividades) - (1 if seleccionada else 0)
        return seleccionada

    def _publicar(self, presencia: Presence) -> None:
        actividad = self._actividad_rpc()
        if actividad is None:
            presencia.clear()
            return

        assets = actividad.get("assets", {})
        timestamps = actividad.get("timestamps", {})
        buttons = actividad.get("buttons", [])
        metadata = actividad.get("metadata", {})
        button_urls = metadata.get("button_urls", [])
        botones = [
            {"label": texto, "url": url}
            for texto, url in zip(buttons[:2], button_urls[:2])
            if isinstance(texto, str) and isinstance(url, str) and url.startswith("https://")
        ]
        large_image = assets.get("large_image")
        small_image = assets.get("small_image")
        presencia.update(
            name=actividad.get("name"),
            activity_type=ActivityType(actividad["type"]),
            details=actividad.get("details"),
            state=actividad.get("state"),
            start=int(timestamps["start"] / 1000) if timestamps.get("start") else None,
            end=int(timestamps["end"] / 1000) if timestamps.get("end") else None,
            large_image=large_image if isinstance(large_image, str) and not large_image.startswith("mp:") else None,
            large_text=assets.get("large_text"),
            small_image=small_image if isinstance(small_image, str) and not small_image.startswith("mp:") else None,
            small_text=assets.get("small_text"),
            buttons=botones or None,
        )

    def _correr(self) -> None:
        espera = 2
        while not self._parar.is_set():
            presencia: Presence | None = None
            try:
                presencia = Presence(self.app_id, connection_timeout=3, response_timeout=5)
                presencia.connect()
                espera = 2
                self.conectado = True
                self.error = None
                if self.al_conectar:
                    self.al_conectar()
                self._publicar(presencia)
                while not self._parar.is_set():
                    self._cambio.wait(10)
                    self._cambio.clear()
                    if self._parar.is_set():
                        break
                    self._publicar(presencia)
            except (PyPresenceException, OSError, ValueError) as error:
                self.error = str(error)
            finally:
                self.conectado = False
                if presencia is not None:
                    if not self._parar.is_set():
                        try:
                            presencia.clear()
                        except (PyPresenceException, OSError):
                            pass
                    try:
                        presencia.close()
                    except (PyPresenceException, OSError, RuntimeError):
                        pass
            if not self._parar.is_set():
                self._parar.wait(espera)
                espera = min(espera * 2, 30)
