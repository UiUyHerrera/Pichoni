import hashlib
import threading

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
        self.cache: dict[str, str] = {}
        self.candado = threading.Lock()

    def resolver(self, url: str) -> str | None:
        if url.startswith("mp:"):
            return url
        with self.candado:
            if url in self.cache:
                return self.cache[url]
        try:
            r = requests.post(
                f"{API}/applications/{self.app_id}/external-assets",
                headers={"Authorization": self.token},
                json={"urls": [url]},
                timeout=15,
            )
        except requests.RequestException:
            return None
        if r.status_code != 200:
            return None
        datos = r.json()
        if not datos or "external_asset_path" not in datos[0]:
            return None
        imagen = "mp:" + datos[0]["external_asset_path"]
        with self.candado:
            self.cache[url] = imagen
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
            url = r.json().get("image", {}).get("url", "") if r.status_code == 200 else ""
        except (requests.RequestException, ValueError) as e:
            raise ErrorImagen("No se pudo subir la imagen. Revisa tu internet.") from e
        if not url.startswith("https://"):
            raise ErrorImagen("El servidor de imágenes rechazó la subida.")
        self.subidas[huella] = url
        return url

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
