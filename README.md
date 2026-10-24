# Pichoni

Aplicación de escritorio para configurar actividades de Discord Rich Presence
en Windows.

## Uso

Descarga el instalador desde [Releases](https://github.com/UiUyHerrera/Pichoni/releases).
Instala Pichoni, abre la aplicación y sigue las instrucciones de conexión.

## Importante

- Pichoni guarda el token de Discord como texto en el equipo. No lo compartas ni
  lo incluyas en capturas, archivos o reportes.
- El uso de un token de cuenta personal para automatizar actividades puede
  incumplir las reglas de Discord y poner la cuenta en riesgo.
- Las imágenes locales que se agreguen a perfiles se suben a freeimage.host.
- El botón “Ver” de una actividad Transmitiendo lo controla Discord y necesita
  un enlace válido de Twitch o YouTube.

## Ejecutar desde el código

Requiere Python 3.12 y Windows:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Las pruebas se ejecutan con:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

La publicación de una etiqueta `vMAJOR.MINOR.PATCH` inicia la compilación del
ejecutable y del instalador mediante GitHub Actions.
