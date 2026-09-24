# project-architecture Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear la skill global `project-architecture` que describe la arquitectura en `ARCHITECTURE.md` y la valida contra `PROJECT_SPEC.md`.

**Architecture:** Una sola skill global genérica (deduce stack del repo); overrides por proyecto solo si un repo lo necesita. No toca `audit-project` ni `spec-driven-qa`.

**Tech Stack:** Markdown + frontmatter YAML (Agent Skills / OpenCode V2). Verificación con `skill` tool y shell.

**Spec:** `docs/superpowers/specs/2026-09-24-project-architecture-design.md`

## Global Constraints

- ID `project-architecture`, dir `~/.config/opencode/skills/project-architecture/SKILL.md`.
- Frontmatter mínimo: `name` + `description` que empieza con `Use when` y solo describe triggers.
- Sin rutas privadas, sin `autoinvoke: false` (es punto de entrada, debe anunciarse).
- Cuerpo corto; triggers ES incluidos.
- No duplica IDs existentes.

## Review Focus

- Repo sin `PROJECT_SPEC.md`: la skill debe trabajar igual generando `ARCHITECTURE.md` y marcando trazabilidad como `NOT_FOUND`, jamás inventando requisitos — test en Task 2.
- Stack no-Python (ej. TS/Go): no debe imponer reglas Python ni comandos `pytest` — test en Task 2.
- Repo gigante: debe pedir alcance/archivos foco en vez de leer todo — cubierto en cuerpo ("delimita alcance primero").
- Solape con `audit-project`: description debe dejar claro que esta mapea componentes, no audita requisitos — test en Task 2.
- `slash`: no se configura nada (default visible); si el TUI no la lista es problema del cliente, fuera de alcance.

---

### Task 1: Crear la skill global

**Files:**
- Create: `C:\Users\vn246\.config\opencode\skills\project-architecture\SKILL.md`
- Test: carga vía `skill` tool con `{"id": "project-architecture"}`

**Interfaces:**
- Consumes: spec de diseño (4 secciones aprobadas).
- Produces: skill ID `project-architecture` anunciada globalmente.

- [ ] **Step 1: Crear el directorio y SKILL.md**

```bash
New-Item -ItemType Directory -Force -Path C:\Users\vn246\.config\opencode\skills\project-architecture
```

Contenido exacto de `SKILL.md`:

```markdown
---
name: project-architecture
description: Use when describing a project's architecture, mapping components to requirements, or validating architecture against PROJECT_SPEC.md. Triggers also on Spanish: describe la arquitectura, arquitectura del proyecto, valida arquitectura contra spec, donde vive.
---

# Project Architecture

Describe la arquitectura y valida su alineación con la especificación.

## Workflow

1. Read `PROJECT_SPEC.md` (repo root) if it exists; otherwise mark traceability `NOT_FOUND`, never invent requirements.
2. Delimit scope first on large repos (ask which areas/flows matter).
3. Inspect code: layers/modules, main flows, external dependencies, contracts (APIs, DB, events).
4. Write/update `ARCHITECTURE.md` at repo root: layers, flows, dependencies, contracts, spec-requirement to component map, decisions, non-goals. Write only with user approval.
5. Report drift both ways: requirement without component, component without requirement, undeclared dependency.
6. Propose a single next step. Read-only first; zero side effects during audit.

## Rules

- `PROJECT_SPEC.md` wins on conflict.
- One step per cycle; proportional changes.
- Never change identity, persistence, public API, or secret-handling as a side-effect cleanup.
- Never log tokens, connection strings, full payloads, or env contents.

## Handoff

- Requirement-level audit → `audit-project` (read-only) or `spec-driven-qa` (audit + implement cycle).
- Code quality within implementation → `boy-scout` + `python-clean-code`.
```

- [ ] **Step 2: Verificar frontmatter y carga**

Run: leer las primeras 5 líneas del archivo y confirmar `name: project-architecture` y `description:` empezando con `Use when`.
Expected: ambas presentes, sin `autoinvoke: false`, sin rutas absolutas privadas en el cuerpo.

- [ ] **Step 3: Cargar vía skill tool con `{"id": "project-architecture"}`**

Expected: carga el cuerpo completo con base directory `C:\Users\vn246\.config\opencode\skills\project-architecture`.

- [ ] **Step 4: Chequeo de solape**

Run: comparar la description contra `audit-project` ("solo informa... jamás implementa") y `spec-driven-qa` ("ciclo que SÍ implementa").
Expected: la nueva habla de componentes/arquitectura, las otras de requisitos; sin confusión de rol.

### Task 2: Validación de escenarios

**Files:**
- Test: ninguno nuevo (verificación por conversación + lectura).

- [ ] **Step 1: Trigger directo**

Prompt de prueba: "describe la arquitectura del proyecto".
Expected: la skill aplica claramente.

- [ ] **Step 2: Shorthand natural**

Prompt de prueba: "¿dónde vive la validación de horómetros?".
Expected: la skill aplica (mapeo componente).

- [ ] **Step 3: Tarea vecina**

Prompt de prueba: "arregla este typo en el README".
Expected: ninguna skill de arquitectura; a lo sumo clean skills si hay código.

- [ ] **Step 4: Repo sin spec / stack no-Python**

Razonar (sin ejecutar): sin `PROJECT_SPEC.md` genera `ARCHITECTURE.md` con trazabilidad `NOT_FOUND`; en repo TS no menciona `pytest` ni reglas Python.
Expected: cuerpo ya lo cubre (paso 1 del workflow + sin comandos hardcodeados).
