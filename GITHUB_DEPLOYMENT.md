# Ejecución diaria gratuita desde GitHub

Este proyecto se ejecuta diariamente con GitHub Actions. No necesita que este
computador esté encendido.

## Control remoto

En el repositorio privado, abre **Actions** y selecciona **Sincronización diaria
MyDevelon**.

- Para detener las próximas ejecuciones: menú `...` -> **Disable workflow**.
- Para reanudarlo: **Enable workflow**.
- Para detener una ejecución que ya está en curso: abre esa ejecución y usa
  **Cancel workflow**.
- Para probarlo cuando quieras: **Run workflow**.

## Secretos obligatorios

En **Settings -> Secrets and variables -> Actions**, agrega estos secretos:

| Nombre | Valor |
| --- | --- |
| `FRACTTAL_CLIENT_ID` | Cliente OAuth de Fracttal |
| `FRACTTAL_CLIENT_SECRET` | Secreto OAuth de Fracttal |
| `MYDEVELON_CLIENT_ID` | Cliente de MyDevelon |
| `MYDEVELON_CLIENT_SECRET` | Secreto de MyDevelon |
| `SQL_CONNECTION_STRING` | Conexión a SQL Server accesible desde GitHub |
| `SYNC_DRY_RUN` | `true` para simulación; `false` para permitir escrituras autorizadas |

GitHub no puede acceder a `localhost` de este PC. Antes de activar el flujo,
SQL Server debe estar alojado en internet o conectado mediante un servicio
seguro. No expongas SQL Server directamente sin restringir red, usuario y
contraseña.

## Antes de producción

1. Sube el repositorio como privado a tu propia cuenta de GitHub.
2. Configura los secretos, inicialmente con `SYNC_DRY_RUN=true`.
3. Ejecuta **Run workflow** y revisa su registro.
4. Confirma que los resultados esperados aparecen en la tabla de auditoría.
5. Solo entonces cambia `SYNC_DRY_RUN` a `false`.
