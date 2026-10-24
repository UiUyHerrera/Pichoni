import asyncio
import json

import nucleo.gateway as gateway


class WebSocketFalso:
    def __init__(self, mensajes):
        self.mensajes = iter(mensajes)
        self.enviados = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def recv(self):
        return json.dumps({"op": 10, "d": {"heartbeat_interval": 60_000}})

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return json.dumps(next(self.mensajes))
        except StopIteration:
            raise StopAsyncIteration

    async def send(self, mensaje):
        self.enviados.append(json.loads(mensaje))


def test_opcode_1_responde_con_la_ultima_secuencia(monkeypatch):
    ws = WebSocketFalso([
        {"op": 0, "s": 42, "t": "READY", "d": {}},
        {"op": 1, "d": None},
    ])
    monkeypatch.setattr(gateway.websockets, "connect", lambda *args, **kwargs: ws)
    conexion = gateway.Conexion("token")

    asyncio.run(conexion._sesion())

    assert {"op": 1, "d": 42} in ws.enviados


def test_opcode_1_sin_secuencia_envia_null(monkeypatch):
    ws = WebSocketFalso([{"op": 1, "d": None}])
    monkeypatch.setattr(gateway.websockets, "connect", lambda *args, **kwargs: ws)
    conexion = gateway.Conexion("token")

    asyncio.run(conexion._sesion())

    assert {"op": 1, "d": None} in ws.enviados


def test_heartbeat_periodico_usa_la_secuencia_actual(monkeypatch):
    conexion = gateway.Conexion("token")
    ws = WebSocketFalso([])
    secuencia = {"valor": 17}

    class FinHeartbeat(Exception):
        pass

    llamadas = 0

    async def dormir(_):
        nonlocal llamadas
        if llamadas:
            raise FinHeartbeat
        llamadas += 1

    monkeypatch.setattr(gateway.asyncio, "sleep", dormir)

    async def probar():
        try:
            await conexion._latido(ws, 60_000, secuencia)
        except FinHeartbeat:
            pass

    asyncio.run(probar())

    assert ws.enviados == [{"op": 1, "d": 17}]
