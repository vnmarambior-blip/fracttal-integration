# Design: project-architecture skill (2026-09-24)

## 1. Propósito y alcance (aprobado)
- Skill `project-architecture` que deja la arquitectura descrita en `ARCHITECTURE.md` y la valida contra `PROJECT_SPEC.md` para reducir drift y errores.
- Vale para proyecto nuevo (andamiaje + spec esqueleto) y en curso (deduce desde código).
- Triggers: "describe la arquitectura", "arquitectura del proyecto", "¿dónde vive X?", "valida arquitectura contra spec", "nuevo proyecto, deja arquitectura descrita". Silencio en fixes puntuales, installs, docs generales.
- No pisa `audit-project` ni `spec-driven-qa`: esas auditan requisitos; esta mapea componentes contra requisitos.

## 2. Artefactos y workflow (aprobado)
- Artefacto: `ARCHITECTURE.md` en raíz con: capas/módulos, flujos principales, dependencias externas, contratos (APIs, DB, eventos), mapa requisito-spec a componente, decisiones y no-objetivos.
- Workflow:
  1. Leer spec (si existe) + código. Read-only, cero efectos.
  2. Generar/actualizar `ARCHITECTURE.md`.
  3. Matriz de trazabilidad spec contra componentes.
  4. Reportar drift (requisito sin componente, componente sin requisito, dependencia no declarada).
  5. Proponer un único próximo paso. Escribe el md solo con aprobación.
- Conexión spec: valida en ambos sentidos, no genera spec nuevo.

## 3. Reglas y validación (aprobado)
- Reglas: cero efectos en auditoría; un paso por ciclo; no inventar componentes ni requisitos (`NOT_FOUND`, no inferidos); spec manda en conflicto; cambios proporcionales.
- Errores típicos que detecta: capa que salta niveles, dependencia circular, secreto en código, contrato sin dueño, flujo sin auditoría.
- Validación: `ARCHITECTURE.md` existe, cada requisito mapea a componente con evidencia (`ruta:línea`), drift accionable en un paso.

## 4. Instalación y convivencia (aprobado)
- Global genérica en `~/.config/opencode/skills/project-architecture/` (cualquier stack, deduce del repo).
- Override por proyecto solo si el repo necesita mapa propio.
- Frontmatter mínimo `name` + `description` (empieza con `Use when`), cuerpo corto, sin rutas privadas.
- Convive con clean-code + `audit-project` + `spec-driven-qa` sin IDs duplicados.

## No-objetivos
- No implementa features ni migra código; solo describe y valida.
- No sustituye revisión humana de decisiones arquitectónicas.

## Related Skills

- **spec-driven-qa** — ciclo que implementa contra spec; esta skill solo mapea
- **audit-project** — auditoría read-only de requisitos; esta skill mapea arquitectura
- **python-clean-code** — validar calidad en componentes mapeados
