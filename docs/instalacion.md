# Instalar y actualizar Pichoni

El instalador para Windows se genera como `Pichoni-Setup-<version>.exe`. Instala
la app en `%LOCALAPPDATA%\Programs\Pichoni`, crea un acceso en el menú Inicio y
conserva los perfiles y el token guardados en `%APPDATA%\EstadoDiscord`.

En una instalación nueva, Pichoni usa Discord RPC local: abre Discord de
escritorio y elige **Continuar sin token**. No hace falta iniciar sesión de nuevo
ni pegar credenciales. RPC muestra una actividad a la vez y permite Jugando,
Escuchando, Viendo y Compitiendo. No puede cambiar el estado global, el estado
personalizado o la actividad Transmitiendo. Los perfiles no compatibles se
ocultan temporalmente y se conservan para el modo avanzado. El modo
avanzado con token se conserva para configuraciones existentes y puede elegirse
desde **Ajustes > Conexión**; cambiar de modo no elimina el token guardado.
En **Ajustes > Apariencia** puedes personalizar por separado el color de acento,
los botones, el fondo, los paneles y tarjetas, la barra lateral y el texto. La
interfaz usa la base Pichoni. La rotación de perfiles y textos está
temporalmente retirada.
Las imágenes elegidas desde el equipo se suben a freeimage.host para obtener un
enlace HTTPS; esto también funciona en el modo RPC sin token. Antes de subir,
puedes arrastrar y acercar la imagen para elegir el encuadre cuadrado. Los GIF
conservan su animación y aplican el mismo encuadre a todos sus fotogramas.

RPC requiere que el Client ID tenga Rich Presence configurado. Discord puede
restringir aplicaciones no aprobadas o limitar sus usuarios de prueba, así que
el acceso para otros usuarios debe verificarse con la aplicación registrada.

La instalación estándar comprueba si hay una nueva versión al iniciar. Si hay una
actualización publicada, descarga el instalador oficial, verifica su SHA-256 y la
instala en silencio; al terminar, Pichoni se abre de nuevo. Si no hay conexión o
falla la verificación/instalación, la versión actual sigue funcionando y puedes
usar **Ajustes > Actualizaciones** para abrir el release oficial. Las versiones
portables no se actualizan automáticamente.

El botón de cerrar y `Alt+F4` ocultan Pichoni en la bandeja y muestran un aviso.
Para cerrarlo por completo, elige **Salir** desde el icono de Pichoni en la bandeja.

Una etiqueta `vMAJOR.MINOR.PATCH` inicia la compilación de una versión estable.
Para pruebas, usa `vMAJOR.MINOR.PATCH-rc.N` (por ejemplo, `v1.0.7-rc.1`); GitHub
la publicará como pre-release sin marcarla como última versión estable. GitHub
Actions compila el ejecutable y el instalador para ambas.
