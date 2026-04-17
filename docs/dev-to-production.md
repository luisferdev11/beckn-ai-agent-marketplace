# De desarrollo a produccion — cambios requeridos

Este documento lista todo lo que funciona diferente en desarrollo vs produccion, por que, y que hacer para migrar.

---

## 1. Credenciales Beckn (identidad en la red)

**Desarrollo:** usamos credenciales pre-registradas del starter kit de Beckn.
- `bapId: bap.example.com`
- `bppId: bpp.example.com`
- Llaves Ed25519 hardcoded en `infra/onix/bap.yaml` y `infra/onix/bpp.yaml`
- Registradas en el testnet `beckn.one/testnet`

**Produccion:** cada participante debe tener identidad propia.

**Que hacer:**
1. Generar par de llaves Ed25519 propio (una para BAP, otra para BPP)
2. Registrar cada subscriber en el DeDi Registry con dominio propio (ej: `marketplace.tudominio.com`)
3. Actualizar `keyManager` en ambos YAMLs de ONIX con las llaves nuevas
4. Actualizar `subscriberId` en los YAMLs
5. Actualizar `networkId` si se usa una red diferente al testnet
6. Separar llaves de firma y encriptacion (en dev se usa la misma para ambas)

**Archivos afectados:** `infra/onix/bap.yaml`, `infra/onix/bpp.yaml`

---

## 2. Extended schema validation (ONIX)

**Desarrollo:** desactivada (`extendedSchema_enabled: "false"`) en los 4 endpoints de ONIX (BAP Caller, BAP Receiver, BPP Caller, BPP Receiver).

**Por que:** ONIX intenta fetchear la URL del `@context` en los objetos `*Attributes` (como `performanceAttributes`, `resourceAttributes`) y validar contra ella. Nuestro `@context` apunta a una URL que no tiene un JSON-LD context document en el formato que ONIX espera. La base validation sigue activa (verifica que `@context` y `@type` existan como strings).

**Produccion:** debe estar activada para garantizar integridad semantica.

**Que hacer:**
1. Crear un JSON-LD context document (no JSON Schema) siguiendo el patron del sandbox de Beckn:
   ```json
   {
     "@context": {
       "@version": 1.1,
       "schema": "https://schema.org/",
       "agent": "https://tudominio.com/vocab/ai-agent#",
       "AIAgentService": "agent:AIAgentService",
       "capabilities": "agent:capabilities",
       "latencyMs": "agent:latencyMs",
       "tokensConsumed": "agent:tokensConsumed",
       "result": "agent:result"
     }
   }
   ```
2. Hospedar el archivo en un dominio publico (ej: `raw.githubusercontent.com` o dominio propio)
3. Agregar el dominio a `extendedSchema_allowedDomains` en los YAMLs de ONIX
4. Actualizar `@context` en `catalog_data.py` y `beckn_actions.py` para apuntar a la URL nueva
5. Cambiar `extendedSchema_enabled` a `"true"` en los 4 endpoints
6. Considerar contribuir el schema al ecosistema Beckn via su proceso de governance

**Archivos afectados:** `infra/onix/bap.yaml`, `infra/onix/bpp.yaml`, `services/bpp/app/catalog_data.py`, `services/bpp/app/handlers/beckn_actions.py`, `schemas/` (nuevo archivo `context.jsonld`)

---

## 3. Persistencia (base de datos)

**Desarrollo:** todo en memoria (diccionarios Python). Se pierde al reiniciar contenedores.
- BAP: callbacks y transacciones en `_callbacks[]` y `_transactions{}` (archivo `services/bap/app/store.py`)
- BPP: contratos en `_contracts{}` (archivo `services/bpp/app/handlers/beckn_actions.py`)

**Produccion:** base de datos persistente.

**Que hacer:**
1. Migrar a SQLite (rapido) o PostgreSQL (escalable)
2. Definir modelos de BD para: contratos, callbacks, transacciones, catalogo de agentes
3. Agregar migraciones (Alembic)
4. Agregar PostgreSQL al `docker-compose.yml`
5. Manejar reconexion y retries
6. Considerar Redis para cache de sesion/estado temporal

**Archivos afectados:** `services/bap/app/store.py`, `services/bpp/app/handlers/beckn_actions.py`, `services/bap/app/db/`, `services/bpp/app/db/`, `infra/docker-compose.yml`

**Equipo responsable:** Database

---

## 4. Catalogo de agentes

**Desarrollo:** hardcoded en `services/bpp/app/catalog_data.py`. 3 agentes mock con datos estaticos.

**Produccion:** catalogo dinamico backed por BD, con API de administracion.

**Que hacer:**
1. Migrar catalogo a BD
2. API CRUD para agregar/editar/eliminar agentes y ofertas
3. Publish automatico al CDS cuando el catalogo cambie
4. Validacion de schema JSON-LD al agregar un agente
5. Versionado de catalogo

**Archivos afectados:** `services/bpp/app/catalog_data.py` (reemplazar), `services/bpp/app/routes/` (nuevas rutas admin)

---

## 5. Publish al CDS (Catalog Discovery Service)

**Desarrollo:** publish manual via `POST /api/catalog/publish`. El catalogo se publica sin `resourceAttributes` porque la extended validation del CDS externo rechaza nuestro `@context`.

**Por que se quitan resourceAttributes en publish:** el CDS en `fabric.nfh.global` tiene su propia validacion de extended schemas. Como no controlamos su config, y nuestra URL de `@context` no sirve un JSON-LD context valido, el CDS rechaza el payload. Nuestro catalogo interno si mantiene los `resourceAttributes` completos.

**Produccion:**
1. Resolver el punto 2 (JSON-LD context document) — con eso el publish incluira resourceAttributes
2. Publish automatico al startup del BPP y cuando el catalogo cambie
3. Manejar el callback `on_publish` para confirmar aceptacion
4. Para recibir `on_publish`, el BPP debe ser accesible desde internet (no hostname Docker interno)

**Archivos afectados:** `services/bpp/app/main.py`, `services/bpp/app/catalog_data.py`

---

## 6. Discovery Service

**Desarrollo:** no existe. El BAP conoce al BPP directamente (`bppId: bpp.example.com` hardcoded en `services/bap/app/config.py`).

**Produccion:** Discovery Service propio o uso del DS del testnet/produccion.

**Que hacer:**
1. Construir DS en `services/discovery/` que indexe catalogos publicados
2. Soportar `POST /beckn/discover` con busqueda por texto y filtros JSONPath
3. Actualizar routing de ONIX-BAP para que `discover` apunte al DS propio
4. O usar el DS externo — requiere que el BAP sea accesible desde internet para recibir `on_discover`

**Archivos afectados:** `services/discovery/` (nuevo), `infra/onix/routing/generic-routing-BAPCaller.yaml`, `infra/docker-compose.yml`

---

## 7. Ejecucion real de agentes

**Desarrollo:** el BPP devuelve resultados mock hardcoded en `on_status`. No llama al orchestrator.

**Produccion:** flujo real: confirm → BPP llama orchestrator → orchestrator ejecuta agente → resultado real.

**Que hacer:**
1. Despues de `confirm`, BPP llama `POST http://orchestrator:3003/execute`
2. Orchestrator ejecuta el agente correspondiente via `POST http://agents:3004/run/{agent_id}`
3. BPP almacena resultado y lo devuelve en `on_status`
4. Manejar ejecuciones asincronas (agentes que tardan) con polling o callbacks
5. Timeouts y retries
6. SLA monitoring (latencia real vs prometida)

**Archivos afectados:** `services/bpp/app/handlers/beckn_actions.py` (handle_confirm, handle_status), `services/orchestrator/`, `services/agents/`

**Equipos responsables:** Orchestrator + Agentes IA + Beckn/Protocol

---

## 8. BAP dinamico (parcialmente resuelto)

**Desarrollo:** init/confirm ahora usan datos del on_select almacenado, pero con fallbacks hardcoded si el callback no ha llegado. El `bppId` esta hardcoded en config — no se puede hablar con multiples BPPs.

**Produccion:**
1. Eliminar fallbacks hardcoded — si no hay on_select, rechazar init
2. Soportar multiples BPPs (bppId dinamico por transaccion, resuelto via discover)
3. Manejar timeouts de callbacks (que pasa si on_select nunca llega)
4. WebSocket o SSE para notificar al frontend cuando llegan callbacks

**Archivos afectados:** `services/bap/app/routes/api.py`, `services/bap/app/config.py`

---

## 9. Seguridad

**Desarrollo:** sin autenticacion, CORS abierto (`allow_origins=["*"]`), sin rate limiting, sin HTTPS.

**Produccion:**
1. Autenticacion en la API del BAP (JWT o API keys para el frontend)
2. Restringir CORS a dominios conocidos
3. Rate limiting
4. HTTPS (TLS termination en reverse proxy o load balancer)
5. No exponer endpoints de debug (`/api/catalog`, `/api/contracts`) al publico
6. Variables de entorno para secrets (no hardcodear en YAMLs)
7. Separar llaves de firma y encriptacion en ONIX
8. Audit logging

**Archivos afectados:** todos los `main.py`, `infra/docker-compose.yml` (agregar reverse proxy), YAMLs de ONIX

---

## 10. Networking

**Desarrollo:** todo corre en red Docker interna (`beckn_network`). BAP/BPP solo accesibles en `localhost`. El CDS externo no puede llamarnos de vuelta (callbacks como `on_publish` no llegan).

**Produccion:**
1. Desplegar en VPS o cloud con IP publica
2. Configurar dominios reales para BAP y BPP
3. Actualizar `bapUri` y `bppUri` en los YAMLs de ONIX con las URLs publicas
4. Configurar firewall — solo exponer puertos necesarios
5. Reverse proxy (nginx/caddy) para TLS y routing

**Archivos afectados:** `infra/onix/bap.yaml`, `infra/onix/bpp.yaml`, `infra/docker-compose.yml`

---

## 11. Observabilidad

**Desarrollo:** logs en stdout, sin metricas, sin alertas.

**Produccion:**
1. Logging estructurado (JSON) con correlation por transactionId
2. Prometheus + Grafana para metricas (latencia, throughput, errores)
3. Health checks mas robustos (verificar conectividad a Redis, ONIX, BD)
4. Alertas (PagerDuty/Slack) cuando un servicio cae o SLA se incumple
5. Tracing distribuido (OpenTelemetry — ONIX tiene plugin `otelSetup` disponible)

---

## Resumen — orden sugerido de migracion

| Prioridad | Cambio | Bloquea |
|-----------|--------|---------|
| 1 | Persistencia (BD) | Todo lo demas depende de no perder datos |
| 2 | Ejecucion real de agentes | Sin esto no hay producto |
| 3 | JSON-LD context document + extended validation | Necesario para publish completo al CDS |
| 4 | Credenciales propias + networking publico | Necesario para recibir callbacks externos |
| 5 | Discovery Service | Necesario para marketplace abierto |
| 6 | Seguridad | Necesario antes de exponer al publico |
| 7 | Observabilidad | Necesario para operar en produccion |
| 8 | BAP dinamico completo | Mejora de UX, no bloqueante |
