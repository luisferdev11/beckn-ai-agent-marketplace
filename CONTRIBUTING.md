# Guia de contribucion

## Setup inicial

```bash
git clone <repo-url>
cd beckn-ai-agent-marketplace

# Levantar todo
cd infra && docker compose up --build

# Verificar
curl http://localhost:3001/health  # marketplace (BAP)
curl http://localhost:3002/health  # provider (BPP)
curl http://localhost:3003/health  # orchestrator

# Smoke test
python scripts/smoke_test.py
```

## Ramas

```
main                          ← estable, protegida, solo merges via PR
└── develop                   ← rama de integracion
    ├── feature/beckn-*       ← equipo Beckn/Protocol
    ├── feature/db-*          ← equipo Database
    ├── feature/orch-*        ← equipo Orchestrator
    └── feature/agents-*      ← equipo Agentes IA
```

### Flujo de trabajo

1. Checkout de `develop`: `git checkout develop && git pull`
2. Crea tu rama: `git checkout -b feature/{equipo}-{descripcion}`
3. Trabaja, commitea, pushea
4. Crea PR hacia `develop`
5. Al menos 1 review antes de merge
6. Periodicamente, `develop` se mergea a `main` cuando este estable

### Que carpetas toca cada equipo

| Equipo | Carpetas principales | Archivos compartidos |
|--------|---------------------|---------------------|
| Beckn/Protocol | `services/bap/`, `services/bpp/`, `infra/` | `libs/beckn_models/`, `CLAUDE.md` |
| Database | `services/bap/app/db/`, `services/bpp/app/db/` | `libs/beckn_models/`, `infra/docker-compose.yml` |
| Orchestrator | `services/orchestrator/` | `infra/docker-compose.yml` |
| Agentes IA | `services/agents/` | `infra/docker-compose.yml` |

**Regla:** si necesitas modificar `docker-compose.yml` o `libs/beckn_models/`, coordina con el equipo de Beckn.

## Correr un solo servicio localmente (sin Docker)

```bash
# Instalar modelos compartidos
cd libs/beckn_models && pip install -e .

# Correr tu servicio
cd services/<tu-servicio>
pip install -r requirements.txt
uvicorn app.main:app --port <tu-puerto> --reload
```

Nota: ONIX y Redis siguen necesitando Docker.

## Agregar un nuevo servicio

1. Crea carpeta en `services/<nombre>/`
2. Estructura minima:
   ```
   services/<nombre>/
   ├── app/
   │   ├── __init__.py
   │   └── main.py        # FastAPI app con /health endpoint
   ├── Dockerfile
   └── requirements.txt
   ```
3. Agrega el servicio a `infra/docker-compose.yml`
4. Documenta en el README y CLAUDE.md

## Usar los modelos compartidos

```python
from beckn_models import BecknContext, Contract, Catalog, AIAgentAttributes
from beckn_models.context import ack_response, nack_response
```

Si agregas modelos nuevos, ponlos en `libs/beckn_models/` y actualiza `__init__.py`.

## Skills de Claude Code

Cada equipo puede crear sus propias skills en `.claude/skills/<nombre>/SKILL.md`.
Skills existentes: `/mp-status`, `/mp-flow`, `/mp-logs`.

## Beckn v2 — lo que debes saber

**Lee el CLAUDE.md completo antes de empezar.** Lo mas importante:

- Este proyecto usa Beckn **v2.0.0**, NO v1
- Si tu asistente de IA sugiere `search`, `on_search`, `Order`, o `Gateway` → esta usando v1. Corrigelo.
- Los terminos correctos son: `discover`, `on_discover`, `Contract`, `CDS` (Catalog Discovery Service)
- ONIX maneja toda la criptografia y validacion de protocolo. Nuestros servicios solo envian/reciben JSON por HTTP.

## Contrato de integracion entre servicios

### Provider → Orchestrator (despues de confirm)

```
POST http://orchestrator:3003/execute
{
    "contract_id": "string",
    "agent_id": "string",
    "input": { ... }
}
→ {
    "execution_id": "string",
    "status": "PENDING | RUNNING | COMPLETED | FAILED",
    "result": { ... },
    "metadata": { "latencyMs": int, "tokensConsumed": int, ... }
}
```

### Orchestrator → Agents (cuando se definan)

```
POST http://agents:3004/run/<agent-id>
{
    "input": { ... },
    "config": { ... }
}
→ {
    "result": { ... },
    "metadata": { ... }
}
```

Estos contratos son borradores. Coordinar cambios entre equipos.
