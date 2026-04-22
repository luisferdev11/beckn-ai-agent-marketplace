# BAP tests

**Antes de escribir tests, lee [`tests/TESTING.md`](../../../tests/TESTING.md) en la raiz del monorepo.**
Ahi esta la estrategia completa: filosofia TDD, capas, fixtures, factories y convenciones.

## Estructura

```
tests/
├── conftest.py            ← fixtures: client, mock_onix, clean_store
├── factories/
│   └── beckn.py           ← builders de payloads Beckn v2
├── unit/                  ← funciones puras (context, store)
├── contract/              ← conformidad con spec Beckn v2
└── integration/           ← endpoints HTTP + ONIX mockeado
```

## Correr

```bash
# desde services/bap/
python -m pytest tests/ -v --tb=short

# desde la raiz
make test-bap
```

## Que cubre

- **Unit** (`unit/`): `_build_context`, `_now_iso`, acumulacion del store, transiciones de status.
- **Contract** (`contract/`): que los payloads emitidos cumplen spec Beckn v2 (@context, @type, tokensUsed, etc).
- **Integration** (`integration/`): select, init, discover, cancel contra FastAPI, con ONIX mockeado via respx.

## Recetas rapidas

**Nuevo test de endpoint:**
```python
async def test_mi_endpoint(self, client, mock_onix):
    response = await client.post("/api/contracts/mi-accion", json={...})
    assert response.status_code == 200
    assert mock_onix["mi-accion"].called
```

**Simular un callback previo (para init/confirm/cancel):**
```python
from tests.factories.beckn import make_on_select_callback
from app import store as bap_store

cb = make_on_select_callback("txn-001")
bap_store.store_callback(cb["context"], cb["message"])
```
