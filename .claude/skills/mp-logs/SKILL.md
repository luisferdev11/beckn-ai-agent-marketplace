---
name: mp-logs
description: "Logs filtrados del proyecto real: ONIX adapters, BAP-AI, BPP-AI, Orchestrator"
disable-model-invocation: true
allowed-tools: Bash(docker *)
---

Muestra logs del **proyecto real** (beckn-ai-agent-marketplace).

## Instrucciones

1. Interpreta argumentos:
   - "bap": logs de onix-bap (protocolo) Y bap-ai (nuestro servicio)
   - "bpp": logs de onix-bpp (protocolo) Y bpp-ai (nuestro servicio)
   - "onix": solo logs de ambos adaptadores ONIX
   - "services": solo logs de bap-ai + bpp-ai + orchestrator
   - "errors": solo errores de todos
   - "orchestrator": solo logs del orchestrator
   - Sin argumentos: logs de bap-ai y bpp-ai (nuestros servicios)
   - Un transaction ID (UUID): filtra por ese ID en todos los servicios

2. Nombres de contenedores del proyecto real:
   - `infra-onix-bap-1`
   - `infra-onix-bpp-1`
   - `infra-bap-ai-1`
   - `infra-bpp-ai-1`
   - `infra-orchestrator-1`
   - `infra-redis-1`

3. Obtener los ultimos 50 logs del servicio indicado
4. Para ONIX: filtrar lineas relevantes (firma, routing, schema validation, errores)
5. Para nuestros servicios: mostrar todo excepto health checks
6. Presentar de forma legible con timestamps

## Formato de salida

```
[HH:MM:SS] servicio      | evento
[07:15:16] bpp-ai        | ← select received [txn=64f13c0e]
[07:15:16] bpp-ai        | select: contract contract-64f1 created with 1 commitments
[07:15:16] bpp-ai        | callback on_select sent → HTTP 200
[07:15:16] onix-bpp      | Firma generada para on_select
[07:15:16] onix-bap      | Firma verificada. Reenviado a bap-ai
[07:15:16] bap-ai        | ← on_select received [txn=64f13c0e]
```

ARGUMENTS: $ARGUMENTS
