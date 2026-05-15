---
name: mp-status
description: "Estado del marketplace (proyecto real): servicios Docker, health checks, callbacks recibidos, contratos activos"
disable-model-invocation: true
allowed-tools: Bash(docker *) Bash(curl *)
---

Muestra el estado de los servicios del **proyecto real** (beckn-ai-agent-marketplace).

## Instrucciones

1. Ejecuta `cd /home/pillofon/Documents/infosys/Agent-Beckn-Marketplace/beckn-ai-agent-marketplace/infra && docker compose ps`
2. Health checks de nuestros servicios:
   - BAP: `curl -s http://localhost:3001/health`
   - BPP: `curl -s http://localhost:3002/health`
   - Orchestrator: `curl -s http://localhost:3003/health`
3. Callbacks recibidos: `curl -s http://localhost:3001/api/callbacks/count`
4. Contratos activos: `curl -s http://localhost:3002/api/contracts`
5. ONIX respondiendo:
   - `curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/bap/caller/ || echo "no responde"`
   - `curl -s -o /dev/null -w "%{http_code}" http://localhost:8082/bpp/caller/ || echo "no responde"`

## Formato de salida

```
Servicio         | Estado    | Puerto | Detalle
-----------------+-----------+--------+--------
redis            | healthy   | 6379   |
onix-bap         | running   | 8081   | responde
onix-bpp         | running   | 8082   | responde
bap-marketplace  | healthy   | 3001   | N callbacks recibidos
bpp-provider     | healthy   | 3002   | N contratos activos
orchestrator     | healthy   | 3003   |
```

Si algun servicio no esta corriendo:
- `cd beckn-ai-agent-marketplace/infra && docker compose up --build`
- Si solo un servicio: `docker compose up --build <servicio> -d`
