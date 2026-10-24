import asyncio
import json
import threading
from collections.abc import Callable
from typing import Any

import requests
import websockets

API = "https://discord.com/api/v9"
GATEWAY = "wss://gateway.discord.gg/?v=10&encoding=json"


def obtener_usuario(token: str) -> dict[str, Any] | None:
    try:
        r = requests.get(f"{API}/users/@me", headers={"Authorization": token}, timeout=15)
    except requests.RequestException:
        return None
    return r.json() if r.status_code == 200 else None


def compartir_actividad(token: str, activar: bool | None = None) -> bool | None:
    try:
        if activar is None:
            r = requests.get(f"{API}/users/@me/settings", headers={"Authorization": token}, timeout=15)
        else:
            r = requests.patch(
                f"{API}/users/@me/settings",
                headers={"Authorization": token},
                json={"show_current_game": activar},
                timeout=15,
            )
    except requests.RequestException:
        return None
    return bool(r.json().get("show_current_game")) if r.status_code == 200 else None


class Conexion:
    def __init__(self, token: str, al_conectar: Callable[[], None] | None = None) -> None:
        self.token = token
        self.al_conectar = al_conectar
        self.loop = asyncio.new_event_loop()
        self.ws: Any = None
        self.activities: list[dict[str, Any]] = []
        self.punto = "online"
        self.conectado = False
        self.visibles: list[int] | None = None
        self.token_invalido = False
        self.hilo = threading.Thread(target=self._correr, daemon=True)
        self._parar = False
        self._send_lock = asyncio.Lock()

    def iniciar(self) -> None:
        self.hilo.start()

    def detener(self) -> None:
        self._parar = True
        if self.loop.is_running():
            # A normal close (1000) makes Discord drop the session and its activity right away;
            # just stopping the loop leaves a dead session showing the old activity for a while.
            try:
                asyncio.run_coroutine_threadsafe(self._cerrar(), self.loop).result(timeout=3)
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)

    async def _cerrar(self) -> None:
        if self.ws is not None:
            await self.ws.close(code=1000)

    def ejecutar(self, coro: Any) -> None:
        if self.loop.is_running():
            asyncio.run_coroutine_threadsafe(coro, self.loop)
        else:
            coro.close()

    def actualizar(self, activities: list[dict[str, Any]], punto: str) -> None:
        self.activities = activities
        self.punto = punto
        self.visibles = None
        self.ejecutar(self._enviar())

    def _payload(self) -> dict[str, Any]:
        return {"since": 0, "activities": self.activities, "status": self.punto, "afk": False}

    async def _enviar(self) -> None:
        if self.ws is None:
            return
        try:
            async with self._send_lock:
                await self.ws.send(json.dumps({"op": 3, "d": self._payload()}))
        except websockets.ConnectionClosed:
            pass

    async def _enviar_latido(self, ws: Any, secuencia: dict[str, int | None]) -> bool:
        try:
            async with self._send_lock:
                await ws.send(json.dumps({"op": 1, "d": secuencia["valor"]}))
        except websockets.ConnectionClosed:
            return False
        return True

    async def _latido(self, ws: Any, intervalo: int, secuencia: dict[str, int | None]) -> None:
        while True:
            await asyncio.sleep(intervalo / 1000)
            if not await self._enviar_latido(ws, secuencia):
                return

    async def _sesion(self) -> None:
        async with websockets.connect(GATEWAY, max_size=None) as ws:
            hola = json.loads(await ws.recv())
            secuencia: dict[str, int | None] = {"valor": None}
            latido = asyncio.create_task(self._latido(ws, hola["d"]["heartbeat_interval"], secuencia))
            await ws.send(json.dumps({
                "op": 2,
                "d": {
                    "token": self.token,
                    "capabilities": 509,
                    "properties": {"os": "Windows", "browser": "Chrome", "device": ""},
                    "presence": self._payload(),
                },
            }))
            try:
                async for mensaje in ws:
                    datos = json.loads(mensaje)
                    if datos.get("s") is not None:
                        secuencia["valor"] = datos["s"]
                    evento = datos.get("t")
                    if evento == "READY":
                        self.ws = ws
                        self.conectado = True
                        await self._enviar()
                        if self.al_conectar:
                            self.al_conectar()
                    elif evento == "SESSIONS_REPLACE":
                        todas = next((s for s in datos["d"] if s.get("session_id") == "all"), None)
                        if todas is not None:
                            self.visibles = [a.get("type") for a in todas.get("activities", [])]
                    elif datos.get("op") == 1:
                        await self._enviar_latido(ws, secuencia)
                    elif datos.get("op") in (7, 9):
                        return
            finally:
                self.ws = None
                self.conectado = False
                latido.cancel()
                try:
                    await latido
                except asyncio.CancelledError:
                    pass

    async def _bucle(self) -> None:
        espera = 2
        while not self._parar:
            try:
                await self._sesion()
                espera = 2
            except websockets.ConnectionClosed as e:
                if e.rcvd is not None and e.rcvd.code == 4004:
                    self.token_invalido = True
                    return
            except (OSError, websockets.WebSocketException):
                pass
            await asyncio.sleep(espera)
            espera = min(espera * 2, 60)

    def _correr(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._bucle())
        except RuntimeError:
            pass
