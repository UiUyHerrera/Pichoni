# Instalar y actualizar Pichoni

El instalador para Windows se genera como `Pichoni-Setup-<version>.exe`. Instala
la app en `%LOCALAPPDATA%\Programs\Pichoni`, crea un acceso en el menú Inicio y
conserva los perfiles y el token guardados en `%APPDATA%\EstadoDiscord`.

Desde **Ajustes > Actualizaciones**, Pichoni consulta si hay una versión nueva y
abre el instalador publicado en el navegador. Si la versión no tiene instalador
adjunto, abre la página de versiones. La app no descarga ni ejecuta actualizaciones
sin confirmación.

Para publicar una actualización, crea y sube un tag con formato `vMAJOR.MINOR.PATCH`
(por ejemplo, `v1.0.1`). La acción de GitHub compila el ejecutable y el instalador
con el logo y los adjunta a la versión publicada.
