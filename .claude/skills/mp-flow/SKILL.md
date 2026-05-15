---
name: mp-flow
description: "Ejecuta flujo Beckn completo contra el proyecto real (BAP-AI + BPP-AI), no contra sandbox"
disable-model-invocation: true
allowed-tools: Bash(curl *) Bash(python3 *) Bash(docker *)
---

Ejecuta un flujo Beckn contra **nuestros servicios propios** (bap-ai, bpp-ai).

## Instrucciones

1. Verifica que los servicios esten corriendo (`curl -s http://localhost:3001/health`)
2. Interpreta argumentos:
   - Sin argumentos o "full": select + init + confirm + status
   - "select": solo select
   - "status": solo status (requiere transaction_id como segundo arg)
   - "smoke": corre el smoke_test.py completo
   - Cualquier accion individual: ejecutala sola
3. Usa la **API del BAP** (no llamadas directas a ONIX):
   - `POST http://localhost:3001/api/contracts/select` con `{"agent_id": "...", "offer_id": "..."}`
   - `POST http://localhost:3001/api/contracts/init` con `{"transaction_id": "..."}`
   - `POST http://localhost:3001/api/contracts/confirm` con `{"transaction_id": "..."}`
   - `POST http://localhost:3001/api/contracts/status` con `{"transaction_id": "..."}`
4. Despues de cada paso:
   - Muestra la respuesta de la API del BAP (incluye ACK de ONIX)
   - Espera a que el callback llegue: `curl -s http://localhost:3001/api/callbacks/ultimo`
   - Muestra datos clave del callback
5. Al final, muestra resumen con todos los callbacks

## Agentes disponibles en el catalogo

Consulta `curl -s http://localhost:3002/api/catalog` para ver la lista actual. Defaults:
- `agent-summarizer-001` / `offer-summarizer-basic` — Legal Document Summarizer (INR 6.00)
- `agent-code-reviewer-001` / `offer-code-review-basic` — Code Review Assistant (INR 10.00)
- `agent-data-extractor-001` / `offer-data-extractor-basic` — Invoice Data Extractor (INR 4.00)

## Endpoints utiles

- Callbacks: `GET http://localhost:3001/api/callbacks`
- Ultimo callback: `GET http://localhost:3001/api/callbacks/ultimo`
- Count: `GET http://localhost:3001/api/callbacks/count`
- Transacciones: `GET http://localhost:3001/api/transactions`
- Contratos BPP: `GET http://localhost:3002/api/contracts`
- Catalogo BPP: `GET http://localhost:3002/api/catalog`

## Formato de salida

```
=== PASO N: ACTION ===
Enviado a: BAP API /api/contracts/{action}
ONIX ACK: ACK
Callback: on_{action}
Datos clave: [precio, status, resultado del agente, etc.]
```

## Smoke test

Si el argumento es "smoke", ejecuta:
```
python3 /home/pillofon/Documents/infosys/Agent-Beckn-Marketplace/beckn-ai-agent-marketplace/scripts/smoke_test.py
```

ARGUMENTS: $ARGUMENTS
