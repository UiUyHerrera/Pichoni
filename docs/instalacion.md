# Instalar y actualizar Pichoni

El instalador para Windows se genera como `Pichoni-Setup-<version>.exe`. Instala
la app en `%LOCALAPPDATA%\Programs\Pichoni`, crea un acceso en el menú Inicio y
conserva los perfiles y el token guardados en `%APPDATA%\EstadoDiscord`.

La instalación estándar comprueba si hay una nueva versión al iniciar. Si hay una
actualización publicada, descarga el instalador oficial, verifica su SHA-256 y la
instala en silencio; al terminar, Pichoni se abre de nuevo. Si no hay conexión o
falla la verificación/instalación, la versión actual sigue funcionando y puedes
usar **Ajustes > Actualizaciones** para abrir el release oficial. Las versiones
portables no se actualizan automáticamente.

El botón de cerrar y `Alt+F4` salen completamente de Pichoni y quitan su actividad;
minimizar la ventana la mantiene activa en la bandeja del sistema.

Para publicar una actualización, crea y sube un tag con formato `vMAJOR.MINOR.PATCH`
(por ejemplo, `v1.0.1`). La acción de GitHub compila el ejecutable y el instalador
con el logo y los adjunta a la versión publicada.
