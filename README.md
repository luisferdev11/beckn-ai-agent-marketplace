# Beckn AI Agent Marketplace

Marketplace abierto y descentralizado de agentes de IA usando [Beckn Protocol v2.0.0](https://github.com/beckn/protocol-specifications-v2).

> **Analogia:** lo que ONDC hizo para el comercio electronico en India, este proyecto lo hace para agentes de IA.

## Quick start

```bash
cd infra
docker compose up --build
```

Verifica:
```bash
curl http://localhost:3001/health   # marketplace (BAP)
curl http://localhost:3002/health   # provider (BPP)
curl http://localhost:3003/health   # orchestrator
python scripts/smoke_test.py       # flujo completo
```

## Arquitectura

```
┌────────────┐     ┌────────────┐     ┌────────────┐     ┌────────────┐
│ Frontend   │────►│bap-market- │────►│ onix-bap   │◄───►│ onix-bpp   │
│ (futuro)   │     │ BAP :3001  │     │    :8081   │     │    :8082   │
└────────────┘     └────────────┘     └────────────┘     └─────┬──────┘
                                                               │
                                                         ┌─────▼──────┐
                                                         │bpp-provider│
                                                         │  BPP :3002 │
                                                         └─────┬──────┘
                                                               │
                                                        ┌──────▼──────┐
                                                        │orchestrator │
                                                        │    :3003    │
                                                        └──────┬──────┘
                                                               │
                                                        ┌──────▼──────┐
                                                        │   agents    │
                                                        │ :3004 (fut.)│
                                                        └─────────────┘
```

**Flujo:** Usuario busca agente → marketplace (BAP) envia `select` → ONIX firma y enruta → provider (BPP) responde con precio → usuario confirma → provider delega ejecucion al orchestrator → agente IA ejecuta → resultado vuelve por la misma cadena.

## Servicios

| Servicio | Puerto | Que hace | Equipo |
|----------|--------|----------|--------|
| `redis` | 6379 | Cache para ONIX (registry lookups) | Infra |
| `onix-bap` | 8081 | Middleware Beckn lado comprador (firma, valida, enruta) | Infra (no se modifica) |
| `onix-bpp` | 8082 | Middleware Beckn lado proveedor (firma, valida, enruta) | Infra (no se modifica) |
| `bap-marketplace` | 3001 | BAP — backend comprador. Recibe callbacks, expone API REST | Beckn/Protocol |
| `bpp-provider` | 3002 | BPP — backend proveedor. Catalogo de agentes, contratos, pricing | Beckn/Protocol + DB |
| `orchestrator` | 3003 | Orquesta ejecucion de agentes IA | Orchestrator |
| `agents` | 3004 | Agentes IA individuales (futuro) | Agentes IA |

## Estructura del proyecto

```
beckn-ai-agent-marketplace/
├── services/
│   ├── bap/                  # marketplace — backend comprador (BAP)
│   ├── bpp/                  # provider — backend proveedor (BPP)
│   ├── orchestrator/         # orchestrator — ejecuta agentes
│   ├── agents/               # agents — agentes IA individuales
│   └── discovery/            # discovery service (Iter 1)
├── libs/
│   └── beckn_models/         # Modelos Pydantic compartidos (Beckn v2 + AI agents)
├── schemas/
│   └── ai-agents-v1.json     # JSON-LD schema para agentes IA
├── infra/
│   ├── docker-compose.yml    # Orquesta todos los servicios
│   └── onix/                 # Configs ONIX (routing, llaves, plugins)
├── scripts/
│   └── smoke_test.py         # Verifica flujo completo
├── docs/                     # Documentacion tecnica
├── .claude/skills/           # Skills de Claude Code para el equipo
├── CLAUDE.md                 # Instrucciones para asistentes de IA
├── CONTRIBUTING.md           # Guia de contribucion y ramas
└── README.md
```

## Para cada equipo

### Si eres del equipo de Database
Tu trabajo: agregar persistencia real (SQLite/Postgres) a marketplace y provider.
1. Ve a `services/bap/app/db/` y `services/bpp/app/db/`
2. Actualmente todo esta in-memory — contratos se pierden al reiniciar
3. Los modelos Pydantic en `libs/beckn_models/` definen la estructura de datos
4. Coordina con el equipo Beckn al modificar modelos compartidos

### Si eres del equipo de Orchestrator
Tu trabajo: reemplazar el placeholder con orquestacion real de agentes.
1. Ve a `services/orchestrator/` — lee el README ahi
2. El provider te llama en `POST /execute` despues de un `confirm`
3. Tu devuelves `status`, `result`, `metadata`
4. No necesitas saber nada de Beckn — solo tu contrato HTTP con el provider

### Si eres del equipo de Agentes IA
Tu trabajo: construir agentes reales (summarizer, code reviewer, etc.)
1. Ve a `services/agents/` — lee el README ahi
2. El orchestrator te llama en `POST /run/<agent-id>`
3. Tu devuelves `result` y `metadata`
4. No necesitas saber nada de Beckn ni del orchestrator — solo tu contrato HTTP
5. Para agregar un nuevo agente al catalogo, coordina con el equipo Beckn (`services/bpp/app/catalog_data.py`)

### Si eres del equipo de Beckn/Protocol
Tu trabajo: integracion Beckn v2, catalogo, discovery, contratos.
1. `services/bap/` — marketplace (BAP)
2. `services/bpp/` — provider (BPP)
3. `infra/` — ONIX configs, docker-compose
4. Pendientes: publish al CDS, discovery service, BAP dinamico

## Desarrollo local (sin Docker)

```bash
# Instalar modelos compartidos
cd libs/beckn_models && pip install -e .

# Correr un servicio
cd services/<tu-servicio>
pip install -r requirements.txt
uvicorn app.main:app --port <puerto> --reload
```

ONIX y Redis solo corren en Docker — no son compilables desde fuente.

## Decisiones tecnicas

| Decision | Eleccion | Razon |
|----------|----------|-------|
| Monorepo | Si | Modelos compartidos, docker-compose unico, equipo chico |
| Lenguaje | Python (FastAPI) | Ecosistema IA es Python-first. TS posible en futuro |
| Beckn middleware | ONIX (Go, Docker) | Oficial Beckn v2. No reimplementamos crypto |
| Credenciales | Starter kit (testnet) | `bap.example.com` / `bpp.example.com`. Propias en Iter 2 |
| Discovery Service | Skipped (Iter 0) | BAP habla directo al BPP conocido. DS en Iter 1 |
| Persistencia | In-memory (Iter 0) | Equipo DB trabajando en SQLite/Postgres |

## Beckn v2 — aviso importante

**Este proyecto usa Beckn v2.0.0. La mayoria del contenido en internet es v1 — NO aplica.**

Si tu asistente de IA sugiere `search`, `on_search`, `Order`, o `Gateway` → corrigelo. Los terminos correctos son `discover`, `on_discover`, `Contract`, `CDS`.

Lee `CLAUDE.md` para la tabla completa de diferencias v1 vs v2.
