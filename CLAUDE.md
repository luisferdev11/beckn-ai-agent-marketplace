# Beckn AI Agent Marketplace

## IMPORTANTE: Beckn v2, NO v1

Este proyecto usa **Beckn Protocol v2.0.0 exclusivamente**. La mayoria del contenido en internet sobre Beckn es de v1 — **NO aplica aqui**. Diferencias criticas:

| Concepto | v1 (NO USAR) | v2 (CORRECTO) |
|----------|-------------|---------------|
| Busqueda | `search` / `on_search` | `discover` / `on_discover` |
| Transaccion | `Order` | `Contract` |
| Catalogo | Gateway broadcast en vivo | `catalog/publish` al CDS, `discover` al DS |
| Payload | JSON plano | **JSON-LD** con `@context` y `@type` |
| SDK | SDKs por lenguaje | **No hay SDK**. ONIX reemplaza al SDK |
| Registry | Custom | DeDi (directorio descentralizado) |
| Acciones | `search, select, init, confirm, track, cancel, update, rating, support, on_*` | `discover, select, init, confirm, status, track, cancel, update, rate, support, on_*` + `catalog/publish, catalog/on_publish` |

**Si ves `search`, `on_search`, `Order`, o `Gateway` en documentacion o en respuestas de IA, es v1 — no lo uses.**

Spec oficial v2: `../protocol-specifications-v2/api/v2.0.0/beckn.yaml` (OpenAPI 3.1.1)

## Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              RED BECKN                                   │
│                                                                         │
│   DeDi Registry (fabric.nfh.global)    CDS (fabric.nfh.global)          │
│   - Identidades + llaves publicas      - Catalog Service (publish)      │
│   - Endpoints de participantes         - Discovery Service (discover)   │
│                                                                         │
└────────────┬──────────────────────────────────┬─────────────────────────┘
             │                                  │
        verifica firmas                   publica/busca
             │                                  │
┌────────────┴──────────────────────────────────┴─────────────────────────┐
│                         NUESTRO SISTEMA                                  │
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐               │
│  │  ONIX-BAP    │◄──►│  ONIX-BPP    │    │    Redis     │               │
│  │  :8081       │    │  :8082       │    │    :6379     │               │
│  │  firma,valida│    │  firma,valida│    │    cache     │               │
│  └──────┬───────┘    └──────┬───────┘    └─────────────┘               │
│         │                   │                                           │
│  ┌──────▼───────┐    ┌──────▼───────┐                                  │
│  │BAP-MARKET-   │    │ BPP-PROVIDER │                                   │
│  │ (BAP)        │    │  (BPP)       │                                   │
│  │ :3001        │    │  :3002       │                                   │
│  │              │    │              │                                   │
│  │ Lado compra- │    │ Catalogo de  │                                   │
│  │ dor. Recibe  │    │ agentes IA.  │                                   │
│  │ callbacks,   │    │ Maneja con-  │                                   │
│  │ expone API   │    │ tratos, dele-│                                   │
│  │ al frontend  │    │ ga ejecucion │                                   │
│  └──────────────┘    └──────┬───────┘                                  │
│                             │                                           │
│                      ┌──────▼───────┐                                   │
│                      │ORCHESTRATOR  │                                   │
│                      │ :3003        │                                   │
│                      │ Recibe tarea,│                                   │
│                      │ elige agente,│                                   │
│                      │ ejecuta      │                                   │
│                      └──────┬───────┘                                   │
│                             │                                           │
│                      ┌──────▼───────┐                                   │
│                      │  AGENTS      │                                   │
│                      │  :3004 (fut.)│                                   │
│                      │  Agentes IA  │                                   │
│                      │  reales      │                                   │
│                      └──────────────┘                                   │
│                                                                         │
│  ┌──────────────┐                                                      │
│  │  FRONTEND    │  React + Next.js  :3000                              │
│  │  :3000       │  Consume API REST del BAP                            │
│  │  Consume API │  services/frontend/                                  │
│  │  del BAP     │                                                      │
│  └──────┬───────┘                                                      │
│         │ fetch / SSE                                                  │
│  ┌──────▼───────┐                                                      │
│  │BAP-MARKET-   │                                                      │
│  │ (BAP) :3001  │                                                      │
│  └──────────────┘                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

## Flujo de una transaccion Beckn v2

```
1. publish     Provider publica catalogo de agentes → CDS
2. discover    Marketplace busca agentes en DS      → on_discover
3. select      Marketplace elige un agente          → on_select (con precio)
4. init        Marketplace da datos de pago         → on_init
5. confirm     Marketplace confirma contrato        → on_confirm (provider ejecuta agente)
6. status      Marketplace consulta resultado       → on_status (resultado del agente)
7. rate        Marketplace califica al agente       → on_rate
```

Cada paso: **ACK sincrono + callback on_* asincrono**.

## Stack

- **Protocolo:** Beckn v2.0.0
- **Middleware:** ONIX adapter (Go, imagen Docker `fidedocker/onix-adapter`)
- **Backend:** Python 3.12 + FastAPI
- **Modelos compartidos:** Pydantic v2 (`libs/beckn_models/`)
- **Agentes IA:** Python (LangChain / CrewAI) — equipo separado
- **Frontend:** React + Next.js (`services/frontend/`, puerto 3000)
- **Infra:** Redis, Docker Compose. PostgreSQL en siguiente iteracion.

## Estructura del proyecto

```
beckn-ai-agent-marketplace/
├── services/                     # Microservicios (cada uno con Dockerfile)
│   ├── bap/                      # MARKETPLACE — lado comprador (BAP) :3001
│   ├── bpp/                      # PROVIDER — lado proveedor (BPP) :3002
│   ├── orchestrator/             # ORCHESTRATOR — ejecuta agentes IA :3003
│   ├── agents/                   # AGENTS — agentes IA individuales :3004
│   ├── frontend/                 # FRONTEND — React + Next.js :3000
│   ├── mock-network/             # Mock local de DeDi + CDS (solo dev) :8090
│   └── discovery/                # DISCOVERY SERVICE (futuro)
├── libs/
│   └── beckn_models/             # Modelos Pydantic compartidos
├── schemas/                      # Schemas del dominio AI (AgentFacts + execution result)
├── infra/
│   ├── docker-compose.yml        # Un solo `docker compose up --build`
│   └── onix/                     # Configs ONIX (routing, llaves, plugins)
├── scripts/                      # Smoke tests y utilidades
├── docs/                         # Documentacion tecnica
└── .claude/skills/               # Skills de Claude Code para el equipo
```

## Equipos y responsabilidades

| Equipo | Carpeta | Servicio Docker | Puerto | Responsabilidad |
|--------|---------|-----------------|--------|-----------------|
| **Beckn/Protocol** | `services/bap/`, `services/bpp/`, `infra/` | `bap-marketplace`, `bpp-provider` | 3001, 3002 | Integracion Beckn v2, catalogo, contratos, API |
| **Database** | `services/bap/app/db/`, `services/bpp/app/db/`, `libs/` | — | — | Persistencia (SQLite→Postgres), migraciones |
| **Orchestrator** | `services/orchestrator/` | `orchestrator` | 3003 | Orquestacion de agentes, colas, timeouts |
| **Agentes IA** | `services/agents/` | `agents` | 3004 | Agentes reales (summarizer, code reviewer, etc.) |
| **Frontend** | `services/frontend/` | `frontend` | 3000 | UI React + Next.js, consume API del BAP |

## Convenciones de codigo

- **Comunicacion en espanol** (codigo y docs en ingles, comunicacion en espanol)
- Cada servicio es independiente con su propio `Dockerfile` y `requirements.txt`
- Modelos compartidos via `libs/beckn_models/` — instalar con `pip install -e ../../libs/beckn_models`
- Docker-first: preferimos correr en Docker, no en local
- Variables de entorno para configuracion (no hardcodear URLs)
- Nombres de servicios en `docker-compose.yml` deben ser descriptivos

## Como ONIX interactua con nuestros servicios

ONIX es un proxy que se sienta entre nuestros servicios y la red Beckn:

**Cuando el marketplace (BAP) envia una accion (ej: select):**
1. Nuestro BAP hace `POST http://onix-bap:8081/bap/caller/select`
2. ONIX-BAP firma el mensaje con Ed25519, valida schema, resuelve ruta via DeDi
3. ONIX-BAP envia al ONIX-BPP del destino
4. ONIX-BPP verifica firma, valida schema, reenvia a nuestro BPP (`http://bpp-provider:3002/api/webhook/select`)

**Cuando el provider (BPP) responde (ej: on_select):**
1. Nuestro BPP hace `POST http://onix-bpp:8082/bpp/caller/on_select`
2. ONIX-BPP firma, valida, envia al ONIX-BAP
3. ONIX-BAP verifica, reenvia a nuestro BAP (`http://bap-marketplace:3001/api/bap-webhook/on_select`)

## Credenciales actuales (testnet)

Usamos credenciales pre-registradas del starter kit:
- BAP: `bap.example.com` (llave Ed25519 en `infra/onix/bap.yaml`)
- BPP: `bpp.example.com` (llave Ed25519 en `infra/onix/bpp.yaml`)
- Registry (prod): `fabric.nfh.global/registry/dedi` (DeDi, beckn.one/testnet)
- CDS (prod): `fabric.nfh.global/beckn/catalog` (Catalog Discovery Service)
- Registry (dev local): `http://mock-network:8090/registry/dedi` (mock, sin internet)
- CDS (dev local): `http://mock-network:8090/beckn/catalog` (mock, sin internet)

## Estado actual (Iter 0 — en progreso)

### Funcionando
- Flujo completo discover → select → init → confirm → status con callbacks
- Ambiente local 100% offline: `mock-network` simula DeDi registry y CDS (`services/mock-network/`)
- Catalogo de 3 agentes IA mock (summarizer, code reviewer, data extractor)
- Pricing real (base + 18% GST)
- Smoke test automatizado (`python scripts/smoke_test.py`)
- Docker compose con 7 servicios (incluye mock-network)
- Orchestrator conectado al BPP (fire & forget en confirm, polling en status)
- `performanceAttributes` en `on_status` con datos reales: latencia, tokens, resultado del agente
- `resourceAttributes` de los 3 agentes migrado a schema **AgentFacts** (NANDA compatible, `schemas/agentfacts-v1.json`)

### Pendiente
- [ ] Persistencia en BD (in-memory actualmente — se pierde al reiniciar)
- [ ] BAP dinamico (init/confirm deben usar datos del on_select almacenado)
- [ ] Hospedar schema JSON-LD en URL publica (`raw.githubusercontent.com`) y re-habilitar `extendedSchema_enabled: true` en `infra/onix/bpp.yaml` BPP Caller
- [ ] Publish de nuestro catalogo al CDS real (dev local: ya funciona via mock-network)
- [ ] Discovery Service propio para produccion (dev local: discover va directo al BPP via mock-network)
- [ ] Conectar agentes reales al orchestrator (actualmente reciben requests pero usan LLM real via Groq)

## Testing

**El proyecto usa TDD.** Antes de implementar un feature, escribe el test que define su contrato.
Para features planeados pero no implementados, marca con `pytest.mark.xfail(strict=True)`.

**4 capas de tests:**
- `services/*/tests/unit/` — funciones puras
- `services/*/tests/contract/` — conformidad con spec Beckn v2
- `services/*/tests/integration/` — endpoints HTTP + ONIX mockeado (respx)
- `tests/e2e/` — stack Docker completo

**Reglas:**
- Nunca hardcodear payloads Beckn en tests — usar factories (`tests/factories/`)
- ONIX siempre mockeado excepto en E2E
- Fixtures autouse `clean_store` / `clean_contracts` ya limpian state entre tests
- Correr: `make test` (BAP+BPP sin Docker), `make test-e2e` (con Docker)

**Documento completo:** `tests/TESTING.md`

## Skills de Claude Code

### Flujo de trabajo del equipo
- `/pr` — Empaqueta tus cambios, genera commit message y abre PR contra develop con revisión humana en cada paso

### Proyecto real
- `/mp-status` — Estado de los servicios del marketplace
- `/mp-flow [full|select|smoke]` — Ejecuta flujo Beckn
- `/mp-logs [bap|bpp|onix|services|errors]` — Logs filtrados

### Sandbox de referencia
- `/beckn-status` — Estado del sandbox
- `/beckn-flow` — Flujo contra sandbox
- `/beckn-logs` — Logs del sandbox
