# Frontend Integration — 2026-05-07

## Que se hizo

### 1. BAP Backend — prompt en confirm
- Se agrego `ConfirmRequest` model con campo opcional `prompt` en `services/bap/app/routes/api.py`
- El endpoint `/api/contracts/confirm` ahora inyecta el prompt del usuario en `commitment.resources[0].descriptor.longDesc` antes de enviar a ONIX
- Esto permite que el frontend envie la tarea del usuario al agente en el paso de confirm

### 2. API Client (`services/frontend/src/lib/beckn-api.ts`)
Nuevo modulo con:
- `discover(query)` — POST discover + poll on_discover + parsea catalogo a `DiscoveredAgent[]`
- `selectAgent(agentId, offerId)` — POST select + poll on_select + retorna contrato con pricing
- `initTransaction(txnId)` — POST init + poll on_init + retorna contrato con consideration
- `confirmTransaction(txnId, prompt)` — POST confirm con prompt + poll on_confirm
- `pollStatus(txnId)` — POST status + poll on_status (60s timeout) + retorna performance
- Polling generico: cada 1s hasta 30s (60s para status), filtra por transaction_id
- Tipos TypeScript para todo el modelo de datos Beckn v2

### 3. Search Page (`services/frontend/src/app/search/page.tsx`)
- Reescrita para usar `discover()` real en vez de mock data
- Loading state con skeleton cards mientras espera on_discover
- Error handling visible al usuario
- El contador de agentes en el hero se actualiza con datos reales

### 4. Agent Card (`services/frontend/src/app/search/_components/AgentCard.tsx`)
- Adaptada al tipo `DiscoveredAgent` que viene del catalogo real
- Muestra: nombre, descripcion, skills, modalities, jurisdiction, pricing, SLA, provider
- Iconos asignados automaticamente por nombre del agente

### 5. Agent Modal (`services/frontend/src/app/search/_components/AgentModal.tsx`)
Flujo completo de 8 pasos dentro del drawer:
1. **details** — info del agente desde discover, boton "Select Agent"
2. **selecting** — loading, llama select API + poll on_select
3. **pricing** — muestra pricing breakdown del BPP (consideration.breakup), boton "Proceed to Payment"
4. **buying** — loading, llama init API + poll on_init
5. **payment** — mock bank page con campos de tarjeta pre-llenados (sandbox), boton "Pay"
6. **prompt** — textarea para que el usuario escriba su tarea, boton "Confirm & Run Agent"
7. **confirming** — loading, llama confirm API con prompt
8. **redirecting** — redirige a `/result/{txnId}`

### 6. Result Page (`services/frontend/src/app/result/[txnId]/page.tsx`)
- Reescrita para usar `pollStatus()` real
- Muestra tracker de 5 pasos: Select → Init → Confirm → Execute → Result
- Metadata de ejecucion: status, model, latency, tokens (in/out/total)
- Resultado: texto del agente en un panel con scroll, o JSON formateado si no es texto
- Error handling: muestra mensajes de error del agente (ej: agentes que no funcionan)

### 7. Fix de migracion DB
- Se aplico `002_add_beckn_fields.sql` manualmente al Postgres corriendo (faltaba `beckn_id`, `agentfacts_id`, etc.)
- Se eliminaron agentes duplicados (ids 2, 3, 4)

### 8. Callback Viewer (`scripts/callback-viewer.html`)
- Herramienta de debug: HTML standalone que poll `localhost:3001/api/callbacks` cada 5s
- Renderiza callbacks en formato legible con filtros por action y transaction_id
- Renderizado especial para on_discover (agent cards) y on_status (resultado + metricas)

---

## Problemas conocidos y posibles

### Proxy Next.js en standalone mode
- **Problema:** `next.config.ts` rewrites se resuelven en build time, no runtime. En Docker standalone, el proxy apuntaba a `localhost:3001` dentro del container (no alcanza al BAP).
- **Solucion actual:** El frontend llama directamente a `http://localhost:3001` desde el browser. Esto funciona porque docker-compose mapea el puerto 3001 al host.
- **Limitacion:** Solo funciona en desarrollo local. En produccion necesitaria un reverse proxy (nginx) o un API route de Next.js que haga el proxy en server-side.

### Agentes sin beckn_id (id 1 y 5)
- Los agentes viejos no tienen `beckn_id` ni `label`. La funcion `_agent_to_beckn_resource` del BPP usa `agent["beckn_id"] or str(agent["id"])` como fallback, pero el `label` sale como `None` y el nombre se toma de `agent_name` JSONB.
- El frontend los muestra con nombre generico "AI Agent" porque `label` es null. Considerar limpiar estos agentes o agregarles `beckn_id`/`label`.

### Agentes que no funcionan (ids 1, 6, 7, 8)
- Solo el agente id 5 (Groq Text Generator) ejecuta un LLM real.
- Los demas van a fallar en el orchestrator o retornar error. El frontend deberia mostrar el error gracefully desde el on_status.
- **Pendiente verificar:** que el orchestrator retorne un on_status con `status.code = "FAILED"` para estos agentes en vez de no retornar nada (lo cual causaria timeout en el frontend).

### Polling y timeouts
- Si ONIX o el BPP estan lentos, el polling de 30s podria no ser suficiente.
- Si un callback nunca llega (ej: BPP crashea), el usuario vera un error de timeout. No hay retry automatico.
- El polling de on_status es de 60s para dar tiempo a la ejecucion del agente.

### TypeScript warnings en IDE
- El IDE muestra errores de JSX (`JSX.IntrinsicElements` not found) que son un problema de configuracion de tipos de React, no del codigo. El build de Next.js dentro de Docker compila correctamente.

### Migraciones de BD
- La migracion 002 solo se ejecuta en el `init.sh` de Postgres cuando el volumen se crea por primera vez. Si el volumen ya existia, la migracion no se aplica automaticamente.
- **Solucion:** correr manualmente `docker compose exec postgres psql -U postgres -d beckn_ai_marketplace < infra/db/migrations/002_add_beckn_fields.sql` o recrear el volumen con `docker compose down -v`.

### FilterPanel removido
- El `FilterPanel` del frontend anterior no se usa en la nueva version porque los filtros del mock data (credentials, data_residency) no aplican a los datos reales del catalogo Beckn.
- Si se quiere filtrar en el frontend, se necesitaria un nuevo FilterPanel basado en los campos reales (modalities, jurisdiction, skills, pricing range).

### Session storage para agent info
- El modal guarda info del agente en `sessionStorage` para que la result page la lea. Si el usuario abre el link directamente, solo vera el icono por defecto y "AI Agent" como nombre.
- Considerar agregar un endpoint que retorne la info del agente por transaction_id.
