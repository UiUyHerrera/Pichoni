import hashlib
import threading
from urllib.parse import urlsplit, urlunsplit

import requests

API = "https://discord.com/api/v9"
HOST = "https://freeimage.host/api/1/upload"
HOST_CLAVE = "6d207e02198a847aa98d0a2a901485a5"
BLOQUEADOS = ("files.catbox.moe", "litter.catbox.moe")
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
MAX_BYTES = 10 * 1024 * 1024
EXTENSIONES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


class ErrorImagen(Exception):
    pass


class Imagenes:
    def __init__(self, token: str, app_id: str, subidas: dict[str, str]) -> None:
        self.token = token
        self.app_id = app_id
        self.subidas = subidas
        self.cache: dict[tuple[str, str], str] = {}
        self.candado = threading.Lock()

    def resolver(self, url: str, app_id: str | None = None) -> str | None:
        if url.startswith("mp:"):
            return url
        app_id = app_id or self.app_id
        clave_cache = (app_id, url)
        with self.candado:
            if clave_cache in self.cache:
                return self.cache[clave_cache]
        try:
            r = requests.post(
                f"{API}/applications/{app_id}/external-assets",
                headers={"Authorization": self.token},
                json={"urls": [url]},
                timeout=15,
            )
        except requests.RequestException:
            return None
        if r.status_code != 200:
            return None
        try:
            datos = r.json()
        except ValueError:
            return None
        if not isinstance(datos, list) or not datos or not isinstance(datos[0], dict):
            return None
        ruta = datos[0].get("external_asset_path")
        if not isinstance(ruta, str) or not ruta:
            return None
        imagen = "mp:" + ruta
        with self.candado:
            self.cache[clave_cache] = imagen
        return imagen

    def subir(self, nombre: str, contenido: bytes) -> str:
        extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        if extension not in EXTENSIONES:
            raise ErrorImagen("Formato no soportado. Usa PNG, JPG, GIF o WEBP.")
        if len(contenido) > MAX_BYTES:
            raise ErrorImagen("La imagen pesa más de 10 MB.")
        huella = hashlib.sha256(contenido).hexdigest()
        if huella in self.subidas and not self.necesita_rehospedar(self.subidas[huella]):
            return self.subidas[huella]
        try:
            r = requests.post(
                HOST,
                data={"key": HOST_CLAVE, "format": "json"},
                files={"source": (f"imagen{extension}", contenido)},
                timeout=60,
            )
        except requests.RequestException as e:
            raise ErrorImagen("No se pudo subir la imagen. Revisa tu internet.") from e

        try:
            respuesta = r.json()
        except ValueError as e:
            if r.status_code != 200:
                raise ErrorImagen(f"Freeimage.host respondió con HTTP {r.status_code}.") from e
            raise ErrorImagen("Freeimage.host devolvió una respuesta inválida.") from e
        if not isinstance(respuesta, dict):
            raise ErrorImagen("Freeimage.host devolvió una respuesta inválida.")

        codigo = respuesta.get("status_code")
        if r.status_code != 200 or codigo not in (None, 200):
            detalle = self._detalle_error(respuesta, r.status_code, codigo)
            raise ErrorImagen(f"Freeimage.host rechazó la subida: {detalle}")

        imagen = respuesta.get("image")
        url = imagen.get("url", "") if isinstance(imagen, dict) else ""
        url = url.strip() if isinstance(url, str) else ""
        try:
            partes = urlsplit(url)
            hostname = partes.hostname
        except ValueError as e:
            raise ErrorImagen("Freeimage.host devolvió un enlace de imagen inválido.") from e
        if partes.scheme.lower() == "http" and hostname in ("freeimage.host", "www.freeimage.host"):
            url = urlunsplit(("https", partes.netloc, partes.path, partes.query, partes.fragment))
            partes = urlsplit(url)
            hostname = partes.hostname
        if partes.scheme.lower() != "https" or not hostname:
            raise ErrorImagen("Freeimage.host no devolvió un enlace HTTPS válido.")

        self.subidas[huella] = url
        return url

    @staticmethod
    def _detalle_error(respuesta: dict, http_status: int, api_status: object) -> str:
        error = respuesta.get("error")
        if isinstance(error, dict):
            detalle = error.get("message") or error.get("text")
        elif isinstance(error, str):
            detalle = error
        else:
            detalle = None
        detalle = detalle or respuesta.get("status_txt")
        if not isinstance(detalle, str) or not detalle.strip() or detalle.strip().upper() == "OK":
            codigo = api_status if api_status is not None else http_status
            detalle = f"código {codigo}"
        return " ".join(detalle.split())[:180]

    def necesita_rehospedar(self, url: str) -> bool:
        return any(f"//{dominio}/" in url for dominio in BLOQUEADOS)

    def rehospedar(self, url: str) -> str | None:
        try:
            r = requests.get(url, headers=NAVEGADOR, timeout=30)
        except requests.RequestException:
            return None
        if r.status_code != 200 or not r.content:
            return None
        nombre = url.rsplit("/", 1)[-1]
        try:
            return self.subir(nombre, r.content)
        except ErrorImagen:
            return None
