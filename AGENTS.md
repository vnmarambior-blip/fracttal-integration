# AGENTS.md

## Principio principal

Prioriza resolver el objetivo funcional con el menor número de pasos, archivos y cambios posibles.

NO conviertas una tarea concreta en una auditoría, refactor, documentación o reorganización general.

## Fuente de verdad

- `PROJECT_SPEC.md` manda. En conflicto, gana el spec.
- `ARCHITECTURE.md` (cuando exista) para arquitectura.

## Reglas de ejecución

### 1. Resolver antes que documentar

Para cada tarea:

1. Identifica el objetivo concreto.
2. Inspecciona únicamente los archivos necesarios.
3. Ejecuta la prueba mínima que permita validar el objetivo.
4. Corrige si existe un error reproducible.
5. Verifica.
6. Detente.

No crear documentación adicional salvo que sea solicitada explícitamente.

### 2. No crear archivos temporales

NO crear:

* scripts `_tmp`
* scripts `test_*.py` fuera de `tests/`
* archivos `debug_*`
* archivos `check_*`
* archivos `verify_*`
* reportes `.md`
* dumps
* copias de archivos
* backups
* archivos `*_old`
* archivos `*_new`
* archivos `*_fixed`

Si necesitas ejecutar una prueba puntual, usa:

* comandos existentes;
* tests existentes;
* Python inline;
* PowerShell inline;
* herramientas existentes del proyecto.

Si crear un archivo nuevo es realmente necesario, primero indícalo y explica por qué no puede hacerse de otra forma.

### 3. No duplicar funcionalidad

Antes de crear una función, script, test o herramienta:

* busca si ya existe algo equivalente;
* reutilízalo si existe.

NO crear una segunda herramienta que haga esencialmente lo mismo.

### 4. No hacer pasos innecesarios

No ejecutar:

* auditorías generales;
* inventarios completos;
* refactors preventivos;
* reorganizaciones;
* análisis de arquitectura;
* documentación automática;
* limpieza estética;

si no son necesarios para cumplir la tarea actual.

### 5. Alcance estricto

Una tarea debe tener:

* objetivo;
* alcance;
* criterio de éxito.

Trabaja únicamente dentro de ese alcance.

Si durante la ejecución encuentras otro problema no bloqueante:

1. regístralo brevemente;
2. no lo investigues;
3. no lo corrijas;
4. continúa con la tarea actual.

### 6. Detenerse cuando el objetivo esté probado

Cuando el criterio de éxito se cumpla:

DETENTE.

No continúes buscando problemas "por si acaso".

### 7. Antes de modificar

Antes de editar código:

* identifica el archivo;
* identifica la función;
* explica brevemente el cambio;
* verifica que el cambio sea necesario.

No modificar múltiples archivos si uno basta.

### 8. Pruebas

Ejecuta la prueba mínima necesaria.

Preferencia:

1. comando/test específico;
2. test relacionado;
3. suite completa solo cuando el cambio pueda afectar otras áreas.

No ejecutar la suite completa repetidamente durante una corrección puntual.

### 9. Git

No crear commits automáticamente.

No crear ramas automáticamente.

No hacer merge.

No hacer reset.

No eliminar worktrees.

No modificar historial.

Solo modificar Git cuando se solicite explícitamente.

### 10. Producción

Nunca ejecutar operaciones productivas sin autorización explícita.

Para este proyecto:

* PUT/PATCH/DELETE requieren autorización explícita.
* SQL INSERT/UPDATE/DELETE/MERGE requieren autorización explícita.
* Los sync completos requieren autorización explícita.

READ-ONLY significa realmente READ-ONLY.

### 11. Credenciales

Nunca imprimir:

* connection strings;
* tokens;
* passwords;
* API keys;
* OAuth secrets.

Si una credencial existe pero el proceso no la detecta:

diagnosticar primero.

NO reemplazarla.
NO regenerarla.
NO solicitar que se vuelva a crear si ya existe.

### 12. Archivos nuevos

Objetivo: mantener el proyecto pequeño.

Regla:

> Si puedes resolverlo sin crear un archivo, NO crees un archivo.

Antes de crear un archivo nuevo, responde:

* ¿Por qué es necesario?
* ¿Por qué no puedo usar un archivo existente?
* ¿Será parte permanente del producto?

Si no es permanente, usa ejecución inline o una herramienta existente.

### 13. Comunicación

Al finalizar entrega solamente:

## Resultado

Qué se consiguió.

## Evidencia

Comandos/tests ejecutados y resultado.

## Cambios

Archivos modificados.

## Bloqueos

Solo si existe un bloqueo real.

No generar un ensayo ni un reporte extenso.

### 14. SQL Server local

- Connection string en `.env` (`SQL_CONNECTION_STRING`), nunca hardcodeada.
- BD: `FracttalIntegration` en instancia `MSSQLSERVER` (Windows Auth).
- Migraciones P1.1 vía scripts `migrate_*.sql` antes de cualquier test de persistencia.

## Regla de oro

Una tarea concreta debe producir:

**objetivo → mínimo diagnóstico → acción → prueba → resultado → STOP.**

## Related Skills

- **spec-driven-qa** — ciclo gobernado por PROJECT_SPEC.md
- **audit-project** — auditoría read-only contra spec
- **telemetry-audit** — para validar datos OEM→SQL→Fracttal
- **data-quality** — clasificar inconsistencias
- **fracttal-integration** — interactuar con Fracttal API
- **aemp-integration** — parser multi-OEM ISO 15143-3
- **python-clean-code** / **clean-*** — calidad de código
- **boy-scout** — mejoras incrementales