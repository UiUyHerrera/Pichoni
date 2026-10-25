import json
import os
import shutil
import sys
import time
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_ID = "383226320970055681"
TIPOS = {"jugando": 0, "transmitiendo": 1, "escuchando": 2, "viendo": 3, "compitiendo": 5}
PUNTOS = ("online", "idle", "dnd", "invisible")
MIN_ROTACION_SEGUNDOS = 15
MIN_ROTACION_MINUTOS = 1
MAX_TIEMPO_MINUTOS = 444 * 525_600


def limite_tiempo_minutos(ahora: float | None = None) -> int:
    return min(MAX_TIEMPO_MINUTOS, max(1, int((ahora if ahora is not None else time.time()) // 60)))


def carpeta_datos() -> Path:
    base = Path(os.environ.get("APPDATA") or Path.home())
    carpeta = base / "EstadoDiscord"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def carpeta_programa() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def nuevo_id() -> str:
    return uuid.uuid4().hex[:10]


def perfil_vacio(titulo: str = "Nuevo perfil", tipo: str = "jugando") -> dict[str, Any]:
    return {
        "id": nuevo_id(),
        "titulo": titulo,
        "tipo": tipo,
        "nombre": "",
        "detalles": [""],
        "texto": [""],
        "rotar_cada": 30,
        "url": "",
        "imagen": {"url": "", "texto": ""},
        "imagen_chica": {"url": "", "texto": ""},
        "botones": [{"texto": "", "url": ""}, {"texto": "", "url": ""}],
        "tiempo": {"modo": "ninguno", "minutos": 30, "total": 60},
    }


def config_vacia() -> dict[str, Any]:
    return {
        "version": 1,
        "punto": "online",
        "personalizado": {"texto": "", "emoji": ""},
        "perfil_activo": None,
        "perfiles_extra": [],
        "rotar_perfiles": {"activo": False, "ids": [], "minutos": 10},
        "iniciar_con_windows": False,
        "tema": "pichoni",
        "app_id": APP_ID,
        "subidas": {},
        "perfiles": [],
    }


def _texto(valor: Any, largo: int = 128) -> str:
    return str(valor).strip()[:largo] if isinstance(valor, (str, int, float)) else ""


def _lista(valor: Any) -> list[str]:
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list):
        return [""]
    textos = [_texto(v) for v in valor][:20]
    return textos or [""]


def _entero(valor: Any, minimo: int, maximo: int, defecto: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return defecto
    return max(minimo, min(maximo, numero))


def normalizar_perfil(crudo: Any) -> dict[str, Any]:
    base = perfil_vacio()
    if not isinstance(crudo, dict):
        return base
    perfil = deepcopy(base)
    perfil["id"] = _texto(crudo.get("id"), 32) or base["id"]
    perfil["titulo"] = _texto(crudo.get("titulo"), 40) or "Sin título"
    perfil["tipo"] = crudo.get("tipo") if crudo.get("tipo") in TIPOS else "jugando"
    perfil["nombre"] = _texto(crudo.get("nombre"))
    perfil["detalles"] = _lista(crudo.get("detalles"))
    perfil["texto"] = _lista(crudo.get("texto"))
    perfil["rotar_cada"] = _entero(crudo.get("rotar_cada"), MIN_ROTACION_SEGUNDOS, 3600, 30)
    perfil["url"] = _texto(crudo.get("url"), 512)
    for clave in ("imagen", "imagen_chica"):
        valor = crudo.get(clave) if isinstance(crudo.get(clave), dict) else {}
        perfil[clave] = {"url": _texto(valor.get("url"), 1024), "texto": _texto(valor.get("texto"))}
    botones = crudo.get("botones") if isinstance(crudo.get("botones"), list) else []
    perfil["botones"] = [
        {"texto": _texto(b.get("texto"), 32), "url": _texto(b.get("url"), 512)} if isinstance(b, dict) else {"texto": "", "url": ""}
        for b in (botones + [{}, {}])[:2]
    ]
    tiempo = crudo.get("tiempo") if isinstance(crudo.get("tiempo"), dict) else {}
    modo = tiempo.get("modo") if tiempo.get("modo") in ("ninguno", "transcurrido", "fingido", "progreso", "regresiva") else "ninguno"
    if perfil["tipo"] == "transmitiendo":
        modo = "ninguno"
    perfil["tiempo"] = {
        "modo": modo,
        "minutos": _entero(
            tiempo.get("minutos"),
            1,
            limite_tiempo_minutos() if modo in ("fingido", "progreso") else MAX_TIEMPO_MINUTOS,
            30,
        ),
        "total": _entero(tiempo.get("total"), 1, MAX_TIEMPO_MINUTOS, 60),
    }
    return perfil


def normalizar(crudo: Any) -> dict[str, Any]:
    config = config_vacia()
    if not isinstance(crudo, dict):
        return config
    config["punto"] = crudo.get("punto") if crudo.get("punto") in PUNTOS else "online"
    personalizado = crudo.get("personalizado") if isinstance(crudo.get("personalizado"), dict) else {}
    config["personalizado"] = {"texto": _texto(personalizado.get("texto")), "emoji": _texto(personalizado.get("emoji"), 16)}
    config["perfiles"] = [normalizar_perfil(p) for p in crudo.get("perfiles", []) if isinstance(p, dict)][:50]
    ids = [p["id"] for p in config["perfiles"]]
    config["perfil_activo"] = crudo.get("perfil_activo") if crudo.get("perfil_activo") in ids else None
    extra = crudo.get("perfiles_extra") if isinstance(crudo.get("perfiles_extra"), list) else []
    config["perfiles_extra"] = list(dict.fromkeys(i for i in extra if i in ids))
    rotar = crudo.get("rotar_perfiles") if isinstance(crudo.get("rotar_perfiles"), dict) else {}
    config["rotar_perfiles"] = {
        "activo": bool(rotar.get("activo")),
        "ids": [i for i in rotar.get("ids", []) if i in ids] if isinstance(rotar.get("ids"), list) else [],
        "minutos": _entero(rotar.get("minutos"), MIN_ROTACION_MINUTOS, 1440, 10),
    }
    config["iniciar_con_windows"] = bool(crudo.get("iniciar_con_windows"))
    config["tema"] = crudo.get("tema") if crudo.get("tema") in ("pichoni", "discord", "claro") else "pichoni"
    config["app_id"] = _texto(crudo.get("app_id"), 24) if str(crudo.get("app_id", "")).isdigit() else APP_ID
    subidas = crudo.get("subidas")
    config["subidas"] = {k: v for k, v in subidas.items() if isinstance(k, str) and isinstance(v, str)} if isinstance(subidas, dict) else {}
    return config


def migrar_estados(viejo: dict[str, Any]) -> dict[str, Any]:
    config = config_vacia()
    config["punto"] = viejo.get("punto", "online")
    if str(viejo.get("app_id", "")).isdigit():
        config["app_id"] = viejo["app_id"]
    for tipo in ("transmitiendo", "jugando", "escuchando"):
        datos = viejo.get(tipo)
        if not isinstance(datos, dict):
            continue
        perfil = perfil_vacio(tipo.capitalize(), tipo)
        perfil["nombre"] = datos.get("nombre", "")
        perfil["detalles"] = [datos.get("detalles", "")]
        perfil["texto"] = [datos.get("texto", "")]
        perfil["url"] = datos.get("url", "")
        perfil["imagen"] = {"url": datos.get("foto", ""), "texto": datos.get("foto_texto", "")}
        config["perfiles"].append(perfil)
        if viejo.get("tipo") == tipo:
            config["perfil_activo"] = perfil["id"]
    return normalizar(config)


class Almacen:
    def __init__(self, carpeta: Path | None = None) -> None:
        self.carpeta = carpeta or carpeta_datos()
        self.archivo = self.carpeta / "config.json"
        self.archivo_token = self.carpeta / "token.txt"

    def cargar(self) -> dict[str, Any]:
        if self.archivo.exists():
            try:
                return normalizar(json.loads(self.archivo.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                shutil.copy(self.archivo, self.archivo.with_suffix(".roto.json"))
        viejo = carpeta_programa() / "estados.json"
        if viejo.exists():
            try:
                config = migrar_estados(json.loads(viejo.read_text(encoding="utf-8")))
                self.guardar(config)
                return config
            except (OSError, json.JSONDecodeError):
                pass
        config = config_vacia()
        ejemplo = perfil_vacio("Mi stream", "transmitiendo")
        ejemplo["nombre"] = "Minecraft"
        ejemplo["url"] = "https://twitch.tv/"
        config["perfiles"].append(ejemplo)
        return config

    def guardar(self, config: dict[str, Any]) -> None:
        temporal = self.archivo.with_suffix(".tmp")
        temporal.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        temporal.replace(self.archivo)

    def leer_token(self) -> str:
        if os.environ.get("DISCORD_TOKEN"):
            return os.environ["DISCORD_TOKEN"].strip()
        if self.archivo_token.exists():
            return self.archivo_token.read_text(encoding="utf-8").strip()
        local = carpeta_programa() / "token.txt"
        if local.exists():
            token = local.read_text(encoding="utf-8").strip()
            if token:
                self.guardar_token(token)
            return token
        return ""

    def guardar_token(self, token: str) -> None:
        self.archivo_token.write_text(token.strip(), encoding="utf-8")
