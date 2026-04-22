# Estrategia de testing

Documento de referencia para todo el equipo del Beckn AI Agent Marketplace.
Lee esto antes de escribir o modificar tests.

---

## Filosofia

**Test-Driven Development (TDD) como default.** El ciclo es:

```
RED        →   GREEN       →   REFACTOR
(escribes      (escribes        (limpias sin
 un test        el minimo        romper el
 que falla)     codigo           test)
                para pasar)
```

Esto garantiza tres cosas:

1. **Escribimos solo el codigo que necesitamos** — nada de features especulativas.
2. **Cada cambio esta cubierto** — si rompes algo, la CI te avisa.
3. **Los tests son documentacion ejecutable** — leer los tests es la forma mas rapida de entender que hace un endpoint.

### Tests RED planeados (xfail)

Cuando un test define un contrato que todavia no existe (endpoint, handler, feature), se marca con:

```python
pytestmark = pytest.mark.xfail(
    reason="discover endpoint not implemented yet — TDD RED phase",
    strict=True,
)
```

`strict=True` es importante: si el test empieza a pasar sin quitar el marker, pytest falla la suite. Asi nos obliga a limpiar el marker cuando se implementa el feature.

Ejemplo: durante varios dias, los tests de `discover` y `cancel` estuvieron en rojo antes de implementar los endpoints. Eso es correcto y deseado — define el contrato antes del codigo.

---

## Arquitectura de 4 capas

Organizamos los tests en cuatro niveles, de adentro hacia afuera:

```
┌─────────────────────────────────────────────────────────────┐
│  4. E2E (tests/e2e/)          — Docker stack real           │
│     HTTP → servicios vivos, sin mocks. Valida integracion   │
│     real con ONIX y red.                                     │
├─────────────────────────────────────────────────────────────┤
│  3. Integration (services/*/tests/integration/)              │
│     FastAPI TestClient → aplicacion completa. ONIX mockeado  │
│     con respx. Valida rutas, payloads salientes, flujos.    │
├─────────────────────────────────────────────────────────────┤
│  2. Contract (services/*/tests/contract/)                    │
│     Valida conformidad con el spec Beckn v2: @context, @type,│
│     campos requeridos (tokensUsed, latencyMs, etc.)         │
├─────────────────────────────────────────────────────────────┤
│  1. Unit (services/*/tests/unit/)                            │
│     Funciones puras. Sin red, sin DB, sin FastAPI. Rapidos. │
└─────────────────────────────────────────────────────────────┘
```

### Que va en cada capa

| Capa | Ejemplo de que testear | No testear aqui |
|------|------------------------|-----------------|
| **Unit** | Pricing con GST, acumulacion del store, `_build_context`, validaciones puras | Rutas HTTP, llamadas externas |
| **Contract** | Que `on_status` incluye `@context`, `@type`, `tokensUsed`, `latencyMs` | Que la ruta responde 200 |
| **Integration** | `POST /api/contracts/select` retorna 200 + payload a ONIX correcto | Que ONIX firme bien (eso es ONIX) |
| **E2E** | `select → init → confirm → status` completo contra Docker | Logica interna de un servicio |

---

## Estructura de directorios

```
beckn-ai-agent-marketplace/
├── tests/
│   ├── TESTING.md                ← este documento
│   └── e2e/
│       └── test_full_flow.py     ← E2E contra Docker stack
│
├── services/bap/tests/
│   ├── conftest.py               ← fixtures compartidas (client, mock_onix, clean_store)
│   ├── factories/
│   │   └── beckn.py              ← builders de payloads Beckn
│   ├── unit/
│   │   ├── test_context.py       ← _build_context, _now_iso
│   │   └── test_store.py         ← acumulacion de callbacks, status transitions
│   ├── contract/
│   │   └── test_beckn_schema.py  ← conformidad con spec Beckn v2
│   └── integration/
│       ├── test_select.py
│       ├── test_init.py
│       ├── test_discover.py
│       └── test_cancel.py
│
└── services/bpp/tests/
    ├── conftest.py               ← fixtures BPP (mock_orchestrator, mock_onix_bpp)
    ├── factories/
    │   └── agents.py             ← builders de payloads de agentes
    ├── unit/
    │   └── test_pricing.py       ← logica de precio + GST
    └── integration/
        ├── test_handle_select.py
        └── test_handle_confirm.py
```

---

## Fixtures compartidas

### BAP (`services/bap/tests/conftest.py`)

| Fixture | Scope | Que hace |
|---------|-------|----------|
| `app` | function | Instancia de FastAPI |
| `client` | function | `httpx.AsyncClient` con `ASGITransport` — no levanta servidor real |
| `clean_store` | function, autouse | Limpia `_callbacks` y `_transactions` antes y despues de cada test. **No necesitas pedirla explicitamente.** |
| `mock_onix` | function | Mockea todos los endpoints ONIX (`select`, `init`, `confirm`, `status`, `cancel`, `discover`, ...). Retorna ACK por defecto. Yields un dict `{action: respx_route}`. |
| `mock_onix_nack` | function | Como `mock_onix` pero retorna NACK — para testear manejo de errores. |

**Uso tipico de `mock_onix`:**

```python
async def test_select_sends_correct_payload(self, client, mock_onix):
    await client.post("/api/contracts/select", json={"agent_id": "x"})

    assert mock_onix["select"].called
    payload = json.loads(mock_onix["select"].calls.last.request.content)
    assert payload["context"]["action"] == "select"
```

### BPP (`services/bpp/tests/conftest.py`)

| Fixture | Scope | Que hace |
|---------|-------|----------|
| `clean_contracts` | function, autouse | Limpia el contract store. Automatico. |
| `mock_orchestrator` | function | Mockea `start_execution` y `get_execution` del orchestrator client. |
| `mock_onix_bpp` | function | Mockea los callbacks salientes del BPP (`on_select`, `on_init`, `on_confirm`, ...). |

---

## Factories

**Regla de oro:** nunca hardcodees payloads Beckn en tests. Usa las factories.

### Por que

1. **Cuando cambia el spec, actualizas un lugar.** Si todos los tests construyen su propio dict, un cambio en Beckn v2 significa tocar 50 tests.
2. **Los tests dicen su intencion, no su formato.** `make_on_select_callback(txn_id)` es mas claro que 30 lineas de JSON embebido.
3. **Parametros por defecto validos.** Las factories producen payloads que el spec valida — no tenemos que pensar en cada campo.

### Ejemplo (BAP)

```python
from tests.factories.beckn import make_on_select_callback

async def test_init_uses_stored_commitments(client, mock_onix):
    txn_id = "txn-001"
    # Simula que ya llego un on_select
    cb = make_on_select_callback(txn_id, agent_id="agent-code-reviewer-001")
    bap_store.store_callback(cb["context"], cb["message"])

    await client.post("/api/contracts/init", json={"transaction_id": txn_id})

    payload = json.loads(mock_onix["init"].calls.last.request.content)
    resources = payload["message"]["contract"]["commitments"][0]["resources"]
    assert resources[0]["id"] == "agent-code-reviewer-001"
```

### Factories disponibles

**BAP** (`services/bap/tests/factories/beckn.py`):
- `make_context(action, txn_id=None, **overrides)` — contexto Beckn v2 base
- `make_select_payload(agent_id, offer_id, quantity, ...)` — body para `/api/contracts/select`
- `make_on_select_callback(txn_id, agent_id, price_value)` — callback de on_select con consideration
- `make_on_confirm_callback(txn_id)` — callback de on_confirm
- `make_on_status_completed_callback(txn_id)` — on_status con performanceAttributes completos

**BPP** (`services/bpp/tests/factories/agents.py`):
- `make_agent()`, `make_offer()` — entidades del catalogo
- `make_select_contract_message()` — mensaje entrante en el webhook /select
- `make_beckn_context()` — contexto para webhooks

---

## Como correr los tests

Desde la raiz del monorepo:

```bash
make test              # BAP + BPP (unit + contract + integration). Sin Docker.
make test-bap          # Solo BAP
make test-bpp          # Solo BPP
make test-e2e          # E2E (requiere docker compose up)
make test-cov          # Con reporte de cobertura
make install-test      # Instalar deps de testing (pytest, respx, etc.)
```

### Por servicio

```bash
cd services/bap && python -m pytest tests/ -v --tb=short

# Solo unit
cd services/bap && python -m pytest tests/unit/ -v

# Un archivo
cd services/bap && python -m pytest tests/integration/test_select.py -v

# Un test
cd services/bap && python -m pytest tests/integration/test_select.py::TestSelectHappyPath::test_returns_200 -v
```

### E2E

Requieren el stack corriendo:

```bash
cd infra && docker compose up -d
# esperar healthy...
cd .. && pytest tests/e2e/ -v -m e2e
```

Los E2E estan marcados con `pytest.mark.e2e` — asi no se ejecutan en la suite normal.

---

## Convenciones

### Naming

```python
class TestSelectHappyPath:
    async def test_returns_200(self, client, mock_onix):
        ...

    async def test_returns_transaction_id(self, client, mock_onix):
        ...

class TestSelectPayloadSentToONIX:
    async def test_payload_context_action_is_select(self, client, mock_onix):
        ...

class TestSelectErrorScenarios:
    async def test_onix_unavailable_returns_error(self, client):
        ...
```

Formato: `Test<Feature><Scenario>` / `test_<what_it_verifies>`. Los tests deben leerse como frases.

### Un test, una afirmacion

Mal:
```python
async def test_select(client, mock_onix):
    r = await client.post(...)
    assert r.status_code == 200
    assert "transactionId" in r.json()
    assert mock_onix["select"].called
    assert r.json()["onix_response"]["message"]["ack"]["status"] == "ACK"
```

Bien — 4 tests separados. Cuando uno falla, sabes exactamente que rompio.

### Nombre de variables de transaccion

Usa `txn-<feature>-<numero>` cuando el test crea uno propio:

```python
txn_id = "txn-init-001"
txn_id = "txn-cancel-005"
```

Asi cuando ves logs, sabes de que test viene.

---

## Como agregar un test nuevo (receta TDD)

### 1. Empiezas con RED

Escribes el test antes del codigo:

```python
# services/bap/tests/integration/test_rate.py
import pytest

pytestmark = pytest.mark.xfail(
    reason="rate endpoint not implemented yet — TDD RED phase",
    strict=True,
)


class TestRateEndpointExists:
    async def test_rate_returns_200(self, client, mock_onix):
        response = await client.post("/api/contracts/rate", json={
            "transaction_id": "txn-rate-001",
            "rating": 5,
        })
        assert response.status_code == 200
```

Corres la suite — el test falla (xfail). 

### 2. GREEN: escribes el minimo codigo

```python
# services/bap/app/routes/api.py
class RateRequest(BaseModel):
    transaction_id: str
    rating: int

@router.post("/contracts/rate")
async def rate(req: RateRequest):
    ctx = _build_context("rate", req.transaction_id)
    payload = {"context": ctx, "message": {...}}
    result = await _send_to_onix("rate", payload)
    return {"transactionId": req.transaction_id, "onix_response": result}
```

Quitas el `pytestmark` xfail. Corres — pasa. 

### 3. REFACTOR: limpias

Extraes helpers, renombras, sin romper el test. Si la suite sigue verde, el refactor fue seguro.

### 4. Agregas mas tests para cubrir edge cases

```python
class TestRatePayloadSentToONIX:
    async def test_payload_includes_rating(self, client, mock_onix):
        await client.post("/api/contracts/rate", json={
            "transaction_id": "txn-rate-002",
            "rating": 4,
        })
        payload = json.loads(mock_onix["rate"].calls.last.request.content)
        assert payload["message"]["rating"]["value"] == 4
```

---

## Que NO testeamos

Evitamos desperdiciar esfuerzo en:

- **Logica de ONIX** — es middleware maduro, su equipo lo testea. Nosotros mockeamos.
- **Validacion de firmas Ed25519** — igual, ONIX.
- **FastAPI internals** — si Pydantic valida un modelo, no testeamos que Pydantic funciona.
- **Llamadas reales a Groq/LLMs en tests** — son lentas, cuestan dinero y son flakeantes. Mockeamos el orchestrator en BPP tests.
- **Docker compose** — lo testeamos implicitamente via E2E, pero no hay un test dedicado.

---

## Tests que pueden romperse y por que

### "respx AllMockedAssertionError"

Estas haciendo una llamada HTTP a una URL no registrada en `mock_onix`. Revisa que el endpoint que estas golpeando este en la lista `_BECKN_ACTIONS` de `conftest.py`.

### "Python 3.9 unsupported operand type(s) for |"

El codigo usa `dict | None` (PEP 604, Python 3.10+). Agrega `from __future__ import annotations` al principio del archivo.

### "Transaction status is ACTIVE but expected CONFIRMED"

Bug historico: el store no actualizaba status si el contract venia vacio. Si vuelve a aparecer, revisa `services/bap/app/store.py` — las transiciones de status deben estar FUERA del `if contract:`.

### Un test aislado pasa pero con la suite falla

Probablemente no estas usando `clean_store` / `clean_contracts` — aunque es `autouse=True`, si tu test crea su propio store o importa estado raro, puede contaminarse. Usa `txn-<feature>-<N>` unicos.

---

## Cobertura

Ahorita (2026-04-22):

| Suite | Tests | Cubre |
|-------|-------|-------|
| BAP unit | 23 | `_build_context`, store accumulation, status transitions |
| BAP contract | 7 | conformidad Beckn v2 (on_select, on_status) |
| BAP integration | 59 | select, init, discover, cancel |
| BPP unit | 14 | pricing con GST, quantity multiplier |
| BPP integration | 11 | handle_select, handle_confirm |
| E2E | 7 | flujo completo Docker |
| **Total** | **121** | |

Objetivo minimo por feature nuevo: **1 unit + 1 integration**. Contract test si toca un payload Beckn. E2E si cambia el flujo.

---

## Referencias

- [CONTRIBUTING.md](../CONTRIBUTING.md) — workflow general del repo
- [CLAUDE.md](../CLAUDE.md) — contexto Beckn v2 para asistentes de IA
- [pytest docs](https://docs.pytest.org/)
- [respx docs](https://lundberg.github.io/respx/) — mock httpx
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
