import sys
from pathlib import Path

NOMBRE = "Pichoni"
NOMBRE_ANTERIOR = "EstadoDiscord"
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
_mutex: int | None = None


def comando_inicio() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --oculto'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    ejecutable = pythonw if pythonw.exists() else Path(sys.executable)
    app = Path(__file__).resolve().parent.parent / "app.py"
    return f'"{ejecutable}" "{app}" --oculto'


def iniciar_con_windows(activar: bool) -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN, 0, winreg.KEY_SET_VALUE) as clave:
            if activar:
                winreg.SetValueEx(clave, NOMBRE, 0, winreg.REG_SZ, comando_inicio())
            for nombre in (NOMBRE, NOMBRE_ANTERIOR):
                if activar and nombre == NOMBRE:
                    continue
                try:
                    winreg.DeleteValue(clave, nombre)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False


def instancia_unica() -> bool:
    if sys.platform != "win32":
        return True
    import ctypes

    global _mutex
    kernel = ctypes.windll.kernel32
    _mutex = kernel.CreateMutexW(None, False, f"Local\\{NOMBRE}")
    return kernel.GetLastError() != 183
