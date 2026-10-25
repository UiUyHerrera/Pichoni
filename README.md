# Pichoni

Aplicación de escritorio para configurar actividades de Discord Rich Presence
en Windows.

## Uso

Descarga el instalador desde [Releases](https://github.com/UiUyHerrera/Pichoni/releases)
e instala Pichoni. En el primer inicio puedes elegir el modo normal sin token o
el modo avanzado con token. En **Ajustes > Apariencia** puedes personalizar por
separado el color de acento, los botones, el fondo, los paneles y tarjetas, la
barra lateral y el texto. Los colores de la interfaz usan la base Pichoni.
La rotación de perfiles y textos está temporalmente retirada.
El modo recomendado conecta con la aplicación de escritorio de
Discord mediante RPC local: no pide ni guarda un token, pero Discord debe estar abierto. Este modo publica una actividad a la vez y
permite Jugando, Escuchando, Viendo y Compitiendo. No cambia el estado global ni
el estado personalizado; Transmitiendo no está disponible. Los tipos y perfiles
no compatibles se ocultan mientras usas RPC y se conservan para el modo avanzado.

El modo avanzado con token sigue disponible para quienes ya lo usan. Para cambiar
de modo o conectarse con token, abre **Ajustes > Conexión**. Los perfiles y el
token guardado se conservan al cambiar de modo; eliminar el token es una acción
separada.

El modo RPC necesita un Client ID de una aplicación con Rich Presence configurado.
Discord puede limitar el acceso de aplicaciones no aprobadas, por lo que el uso
por otros usuarios depende de la configuración y aprobación de esa aplicación.

## Importante

- En el modo avanzado con token, Pichoni guarda el token como texto en el equipo.
  No lo compartas ni lo incluyas en capturas, archivos o reportes.
- El uso de un token de cuenta personal para automatizar actividades puede
  incumplir las reglas de Discord y poner la cuenta en riesgo.
- Las imágenes locales que se agreguen a perfiles se suben a freeimage.host,
  también en el modo sin token. La app avisa antes de subirlas. Puedes ajustar el
  encuadre cuadrado; los GIF mantienen la animación.
- El botón “Ver” de una actividad Transmitiendo lo controla Discord y necesita
  un enlace válido de Twitch o YouTube.

Al cerrar la ventana, Pichoni queda en segundo plano y muestra un aviso. Para
cerrarlo por completo, elige **Salir** desde el icono de la bandeja del sistema.

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

Una etiqueta `vMAJOR.MINOR.PATCH` inicia la compilación de una versión estable.
Para pruebas, usa `vMAJOR.MINOR.PATCH-rc.N` (por ejemplo, `v1.0.7-rc.1`); GitHub
la publicará como pre-release sin marcarla como última versión estable. GitHub
Actions compila el ejecutable y el instalador para ambas.
