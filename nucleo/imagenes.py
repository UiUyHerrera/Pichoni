import io
import hashlib
import math
import threading
from urllib.parse import urlsplit, urlunsplit

import requests
from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

API = "https://discord.com/api/v9"
HOST = "https://freeimage.host/api/1/upload"
HOST_CLAVE = "6d207e02198a847aa98d0a2a901485a5"
BLOQUEADOS = ("files.catbox.moe", "litter.catbox.moe")
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}
MAX_BYTES = 10 * 1024 * 1024
EXTENSIONES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TAMANO_ASSET = 512
MAX_DIMENSION = 8192
MAX_FOTOGRAMAS_GIF = 120


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

    def subir(self, nombre: str, contenido: bytes, recorte: dict | None = None) -> str:
        extension = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
        if extension not in EXTENSIONES:
            raise ErrorImagen("Formato no soportado. Usa PNG, JPG, GIF o WEBP.")
        if len(contenido) > MAX_BYTES:
            raise ErrorImagen("La imagen pesa más de 10 MB.")
        if recorte is not None:
            contenido = self._recortar(extension, contenido, recorte)
            if len(contenido) > MAX_BYTES:
                raise ErrorImagen("La imagen editada pesa más de 10 MB.")
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
    def _recortar(extension: str, contenido: bytes, recorte: dict) -> bytes:
        try:
            x = float(recorte["x"])
            y = float(recorte["y"])
            ancho = float(recorte["ancho"])
            alto = float(recorte["alto"])
        except (KeyError, TypeError, ValueError) as error:
            raise ErrorImagen("No se pudo aplicar el encuadre de la imagen.") from error
        if (
            not all(math.isfinite(valor) for valor in (x, y, ancho, alto))
            or x < 0 or y < 0 or ancho <= 0 or alto <= 0
            or x + ancho > 1.0001 or y + alto > 1.0001
        ):
            raise ErrorImagen("El encuadre de la imagen no es válido.")
        try:
            original = Image.open(io.BytesIO(contenido))
            formato_esperado = {
                ".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".gif": "GIF", ".webp": "WEBP"
            }[extension]
            if original.format != formato_esperado:
                raise ErrorImagen("La extensión del archivo no coincide con el formato de la imagen.")
            if original.width > MAX_DIMENSION or original.height > MAX_DIMENSION:
                raise ErrorImagen("La imagen es demasiado grande para encuadrarla (máximo 8192 × 8192).")
            if original.format == "GIF" and getattr(original, "n_frames", 1) > MAX_FOTOGRAMAS_GIF:
                raise ErrorImagen(f"El GIF tiene demasiados fotogramas (máximo {MAX_FOTOGRAMAS_GIF}).")
            if original.width * original.height * getattr(original, "n_frames", 1) > 100_000_000:
                raise ErrorImagen("La imagen animada es demasiado grande para encuadrarla.")

            ancho_px = round(ancho * original.width)
            alto_px = round(alto * original.height)
            if abs(ancho_px - alto_px) > max(2, round(max(ancho_px, alto_px) * 0.005)):
                raise ErrorImagen("El encuadre de la imagen debe ser cuadrado.")
            lado = max(1, min(ancho_px, alto_px))
            left = round(x * original.width)
            top = round(y * original.height)
            left = min(left, original.width - lado)
            top = min(top, original.height - lado)
            caja = (left, top, left + lado, top + lado)

            if original.format == "GIF":
                fotogramas = []
                duraciones = []
                for fotograma in ImageSequence.Iterator(original):
                    fotograma = fotograma.convert("RGBA").crop(caja)
                    fotogramas.append(fotograma.resize(
                        (TAMANO_ASSET, TAMANO_ASSET), Image.Resampling.LANCZOS
                    ))
                    duraciones.append(fotograma.info.get("duration", original.info.get("duration", 100)))
                salida = io.BytesIO()
                fotogramas[0].save(
                    salida,
                    format="GIF",
                    save_all=True,
                    append_images=fotogramas[1:],
                    duration=duraciones,
                    loop=original.info.get("loop", 0),
                    disposal=2,
                    optimize=True,
                )
                return salida.getvalue()

            imagen = ImageOps.exif_transpose(original)
            ancho_px = round(ancho * imagen.width)
            alto_px = round(alto * imagen.height)
            if abs(ancho_px - alto_px) > max(2, round(max(ancho_px, alto_px) * 0.005)):
                raise ErrorImagen("El encuadre de la imagen debe ser cuadrado.")
            lado = max(1, min(ancho_px, alto_px))
            left = round(x * imagen.width)
            top = round(y * imagen.height)
            left = min(left, imagen.width - lado)
            top = min(top, imagen.height - lado)
            imagen = imagen.crop((left, top, left + lado, top + lado)).resize(
                (TAMANO_ASSET, TAMANO_ASSET), Image.Resampling.LANCZOS
            )
            if extension in (".jpg", ".jpeg"):
                imagen = imagen.convert("RGB")
            elif extension == ".png":
                imagen = imagen.convert("RGBA")
            salida = io.BytesIO()
            imagen.save(salida, format=formato_esperado)
            return salida.getvalue()
        except ErrorImagen:
            raise
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
            UnidentifiedImageError,
        ) as error:
            raise ErrorImagen("No se pudo procesar esta imagen.") from error

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
