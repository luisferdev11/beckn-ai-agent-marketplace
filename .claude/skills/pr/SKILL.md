---
name: pr
description: "Empaqueta tu trabajo, crea un commit con mensaje generado y abre un PR contra develop — con revisión humana en cada paso"
allowed-tools: Bash(git *) Bash(gh *)
---

Eres un asistente que ayuda al desarrollador a subir sus cambios de forma ordenada.
Sigue los pasos en orden y **espera confirmación del desarrollador antes de avanzar** en cada punto marcado con [PAUSA].

## Paso 0 — Verificar rama

Corre `git branch --show-current` y `git status`.

- Si la rama actual es `main` o `develop`: **detente** e indica al desarrollador que debe crear una rama de feature antes de continuar:
  ```
  git checkout -b feat/<nombre-descriptivo>
  ```
- Si hay una rama de feature activa: continúa al Paso 1.

## Paso 1 — ¿Qué implementaste? [PAUSA]

Pregunta al desarrollador:

> "¿Qué implementaste o arreglaste en esta sesión? Descríbelo en tus propias palabras (no necesita ser formal)."

Espera su respuesta antes de continuar. Guarda esa descripción — la usarás para generar el commit message y la descripción del PR.

## Paso 2 — Leer los cambios

Corre en paralelo:
- `git diff HEAD` (cambios no stageados)
- `git diff --cached` (cambios ya stageados)
- `git status --short`

Agrupa los archivos modificados por área del proyecto:

| Área | Carpetas |
|------|----------|
| BAP | `services/bap/` |
| BPP | `services/bpp/` |
| Orchestrator | `services/orchestrator/` |
| Agents | `services/agents/` |
| Infra / Docker | `infra/`, `docker-compose*` |
| Libs / Modelos | `libs/` |
| Schemas | `schemas/` |
| Scripts / Tests | `scripts/` |
| Docs / Config | `*.md`, `CLAUDE.md`, `.claude/` |
| Otros | cualquier otro archivo |

## Paso 3 — Mostrar resumen y pedir confirmación [PAUSA]

Muestra una tabla con todos los archivos modificados, su área y su estado (M modificado / A nuevo / D eliminado):

```
Área          | Archivo                                    | Estado
--------------|--------------------------------------------|-------
BAP           | services/bap/app/handlers/discovery.py     | A (nuevo)
Infra         | infra/docker-compose.yml                   | M
Docs          | README.md                                  | M
```

Marca con ⚠️ los archivos que NO pertenecen al área principal descrita por el desarrollador en el Paso 1.

Pregunta:

> "¿Incluimos todos estos archivos en el commit? Si quieres excluir alguno o tienes algo que explicar sobre los cambios marcados con ⚠️, dímelo ahora."

Espera su respuesta. Ajusta la lista de archivos según lo que indique.

Si hay archivos marcados con ⚠️ que el desarrollador confirma incluir, **guárdalos como "cambios fuera de área"** — los mencionarás en el PR.

## Paso 4 — Generar commit message [PAUSA]

Basándote en la descripción del Paso 1 y los archivos confirmados, genera un commit message siguiendo Conventional Commits:

```
<tipo>(<scope>): <descripción corta en inglés>
```

Tipos válidos: `feat`, `fix`, `refactor`, `docs`, `chore`, `test`
Scope: nombre del área principal (`bap`, `bpp`, `orchestrator`, `agents`, `infra`, `libs`)

Ejemplo:
```
feat(bap): implement discover endpoint and DS routing
```

Muestra el mensaje propuesto y pregunta:

> "¿Usamos este commit message o lo modificamos?"

Espera confirmación antes de continuar.

## Paso 5 — Stagear y commitear

Con la lista de archivos aprobada y el mensaje confirmado:

```bash
git add <archivos aprobados>
git commit -m "<mensaje aprobado>"
```

Muestra el output del commit.

## Paso 6 — Push

Corre:
```bash
git push -u origin HEAD
```

Si el push falla por falta de upstream, usa `git push --set-upstream origin <rama>`.

## Paso 7 — Generar descripción del PR [PAUSA]

Genera una descripción de PR con este formato:

```markdown
## ¿Qué hace este PR?
<resumen en 2-3 bullets basado en la descripción del desarrollador>

## Cambios principales
<lista de archivos clave y qué cambia en cada uno>

## Cómo probar
- [ ] <paso de prueba 1>
- [ ] <paso de prueba 2>

## Notas para el revisor
<si hay cambios fuera de área, agrégalos aquí con una nota explicando el contexto>
```

Si hay archivos "fuera de área" del Paso 3, agrégalos en "Notas para el revisor" con un prefijo ⚠️:

```
⚠️ Este PR incluye cambios en `infra/docker-compose.yml` que están fuera del área principal (BAP).
   El desarrollador indica: "<lo que dijo en el Paso 3>". Se recomienda revisión explícita.
```

Muestra la descripción generada y pregunta:

> "¿La descripción del PR está bien o quieres ajustar algo antes de crearlo?"

Espera su respuesta. Aplica los ajustes que indique.

## Paso 8 — Crear el PR

Con la descripción aprobada, crea el PR apuntando a `develop`:

```bash
gh pr create \
  --base develop \
  --title "<tipo>(<scope>): <descripción corta>" \
  --body "<descripción aprobada>"
```

Muestra la URL del PR creado.

---

ARGUMENTS: $ARGUMENTS
