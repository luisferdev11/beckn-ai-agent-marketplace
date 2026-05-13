# BPP tests

**Antes de escribir tests, lee [`tests/TESTING.md`](../../../tests/TESTING.md) en la raiz del monorepo.**
Ahi esta la estrategia completa: filosofia TDD, capas, fixtures, factories y convenciones.

## Estructura

```
tests/
├── conftest.py            ← fixtures: client, mock_orchestrator, mock_onix_bpp, clean_contracts
├── factories/
│   └── agents.py          ← builders de catalog/contract messages
├── unit/                  ← pricing, GST, logica de catalogo
└── integration/           ← handlers: handle_select, handle_confirm
```

## Correr

```bash
# desde services/bpp/
python -m pytest tests/ -v --tb=short

# desde la raiz
make test-bpp
```

## Que cubre

- **Unit** (`unit/`): pricing por agente, GST al 18%, quantity multiplier, agentes desconocidos.
- **Integration** (`integration/`): `handle_select` y `handle_confirm` via POST al webhook. Orchestrator mockeado.

## Fixtures clave

| Fixture | Que hace |
|---------|----------|
| `clean_contracts` | Limpia `_contracts` antes/despues de cada test (autouse). |
| `mock_orchestrator` | Mockea `start_execution` y `get_execution`. Retorna resultado COMPLETED con tokens y latencia. |
| `mock_onix_bpp` | Intercepta callbacks `on_*` salientes del BPP. |

## Recetas rapidas

**Test de handler:**
```python
async def test_confirm_activates_contract(client, mock_orchestrator, mock_onix_bpp):
    # envia select primero para que haya contrato
    await client.post("/api/webhook/select", json=make_select_contract_message())
    # luego confirm
    response = await client.post("/api/webhook/confirm", json={...})
    assert response.status_code == 200
    mock_start, _ = mock_orchestrator
    assert mock_start.called  # orchestrator recibio la ejecucion
```
