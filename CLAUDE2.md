# CLAUDE2.md — Portal de Autenticacion y Sistema Hibrido de Credenciales

Este archivo documenta todo lo implementado en la rama `feat-portal` que NO esta cubierto en `CLAUDE.md`.

## Branch: feat-portal (basada en feat-orch-v0.1)

---

## 1. Sistema de Autenticacion y Roles

### Tablas nuevas

**users** (`infra/db/migrations/003_users_and_stats.sql`)
```sql
users (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email               VARCHAR(255) UNIQUE NOT NULL,
  password_hash       VARCHAR(255) NOT NULL,        -- bcrypt, 12 salt rounds
  role                VARCHAR(20) DEFAULT 'consumer', -- 'consumer' | 'publisher' | 'admin'
  subscription_status VARCHAR(20) DEFAULT 'free',     -- 'free' | 'active' | 'cancelled'
  provider_id         INTEGER REFERENCES providers(id) ON DELETE SET NULL,
  created_at, updated_at TIMESTAMPTZ
)
```

**agent_stats** (misma migracion)
```sql
agent_stats (
  id             SERIAL PRIMARY KEY,
  agent_id       INTEGER NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  total_queries  INTEGER DEFAULT 0,
  unique_users   INTEGER DEFAULT 0,
  last_used_at   TIMESTAMPTZ,
  week_queries   INTEGER DEFAULT 0,
  recorded_at    DATE DEFAULT CURRENT_DATE
)
```

### Usuarios seed
| Email | Password | Rol |
|-------|----------|-----|
| baructest@gmail.com | Marketplace2026! | admin |
| generico@gmail.com | Marketplace2026! | consumer |

### JWT
- Libreria: `jose` (Edge-compatible, NO jsonwebtoken)
- Secret: env var `JWT_SECRET`
- Expira en 24h
- Payload: `{ id, email, role, subscription_status, provider_id }`
- Se almacena en cookie httpOnly `token` + localStorage

### Middleware (`src/middleware.ts`)
- Usa `jose` para verificar JWT en Edge Runtime
- Rutas publicas: `/`, `/login`, `/register`, `/api/auth/*`, `/api/providers`, `/api/categories`, `/api/health`
- Proteccion por rol: `/dashboard/publisher` (publisher+admin), `/dashboard/admin` (admin), `/api/admin/*`, `/api/publisher/*`
- Usuarios no autenticados: redirect a `/login` (paginas) o 401 (API)

---

## 2. Arquitectura del Frontend (feat-portal)

### Stack de auth
- Passwords: bcrypt (bcryptjs), 12 salt rounds
- JWT: jose (sign + verify, AES-256-GCM compatible con Edge)
- DB: pg (PostgreSQL client directo, pool en `src/lib/db.ts`)

### Rutas nuevas

| Ruta | Tipo | Descripcion |
|------|------|-------------|
| `/` | Landing | CTAs Sign In / Create Account (solo no autenticados) |
| `/login` | Page | Formulario email + password |
| `/register` | Page | Multi-paso: rol → credenciales → compania → pago mock → done |
| `/dashboard` | Router | Redirect segun rol (consumer/publisher/admin) |
| `/dashboard/consumer` | Page | Replica exacta de /search con hero, auth header, boton Register Agent |
| `/dashboard/publisher` | Page | Mi compania + tabla agentes + stats + registro de agentes |
| `/dashboard/admin` | Page | Tabs: Users, Companies, Agents con acciones CRUD |
| `/upgrade` | Page | Flujo upgrade consumer→publisher: compania + pago mock |
| `/403` | Page | Acceso denegado |
| `/search` | Redirect | Redirige a `/dashboard` |

### API Routes del frontend (Next.js App Router)

| Endpoint | Metodo | Auth | Descripcion |
|----------|--------|------|-------------|
| `/api/auth/register` | POST | No | Registro con creacion de provider opcional |
| `/api/auth/login` | POST | No | Login, retorna JWT + cookie |
| `/api/auth/me` | GET | Si | Perfil del usuario autenticado |
| `/api/auth/check-email` | POST | No | Verifica si email existe |
| `/api/auth/upgrade` | POST | Si | Upgrade consumer → publisher |
| `/api/providers` | GET | No | Lista providers activos (para buscador) |
| `/api/categories` | GET | No | Lista categorias activas |
| `/api/publisher/agents` | GET/POST | Publisher | CRUD agentes del publisher |
| `/api/publisher/stats` | GET | Publisher | Estadisticas de agentes |
| `/api/admin/users` | GET/PUT | Admin | Gestionar usuarios |
| `/api/admin/providers` | GET/PUT | Admin | Gestionar providers |
| `/api/admin/agents` | GET/PUT | Admin | Gestionar agentes |

### Componentes nuevos

```
src/app/_components/
  auth/
    LoginForm.tsx              — Formulario de login
    RegisterForm.tsx           — Registro multi-paso (4 steps)
    CompanySearchForm.tsx      — Buscar/crear compania provider
    PaymentMockForm.tsx        — Pago simulado $29/mes
    PasswordStrengthIndicator.tsx — Barra + checklist de requisitos
  dashboard/
    CompanyProfileCard.tsx     — Card con datos del provider
    AgentStatsCard.tsx         — Grid de metricas por agente
    RegisterAgentForm.tsx      — Formulario adaptativo (managed/external)
  shared/
    SessionDropdown.tsx        — Avatar + email + dropdown logout
```

---

## 3. Sistema Hibrido de Credenciales (Opcion C)

### Concepto
Cada provider elige su modo de integracion al crear la compania:
- **Managed**: Nosotros corremos el agente. Publisher da su API key (encriptada en BD).
- **External**: Publisher hostea su propio endpoint. Nosotros lo llamamos directamente.

### Migracion (`infra/db/migrations/004_provider_mode_and_credentials.sql`)
```sql
ALTER TABLE providers ADD COLUMN integration_mode VARCHAR(20) DEFAULT 'managed';
  -- CHECK: 'managed' | 'external'

ALTER TABLE agents ADD COLUMN credentials JSONB DEFAULT '{}';
  -- Managed: {"api_key": "<encrypted_base64>"}
  -- External o sin key: {}
```

### Encriptacion: AES-256-GCM
- **Key**: env var `CREDENTIALS_ENCRYPTION_KEY` (32 bytes, 64 hex chars)
- **Formato**: `base64(iv_12bytes + ciphertext + authTag_16bytes)`
- **Encrypt** (Node.js): `services/frontend/src/lib/crypto.ts`
- **Decrypt** (Python): `services/bpp/app/crypto.py` (usa `cryptography` lib)
- Misma key compartida entre frontend y BPP via env var

### Flujo de credenciales en ejecucion

```
1. Publisher registra agente con API key
   → Frontend encrypt(api_key) → agents.credentials = {"api_key": "<encrypted>"}

2. BAP confirma contrato → BPP handle_confirm
   → _dispatch_to_orchestrator() lee agent.credentials de BD
   → decrypt(encrypted_key) → plaintext
   → Payload al orchestrator incluye "credentials": {"api_key": "gsk_..."}

3. Orchestrator recibe ExecuteRequest con credentials
   → executor.dispatch() pasa credentials a _call_agent()
   → _call_agent() inyecta {"_credentials": {...}} en el payload JSON

4. Agents service recibe POST /task
   → main.py extrae body.pop("_credentials")
   → Pasa credentials al handler: run_task(payload, credentials=credentials)

5. Handler (code_review, text_generation)
   → _get_llm(api_key=credentials.get("api_key") if credentials else None)
   → Fallback: os.environ.get("GROQ_API_KEY")
   → Si ninguno existe: error
```

### Backward compatibility
- Agentes seeded (IDs 1,5,6,7,8): `credentials = {}`, usan GROQ_API_KEY del .env
- Providers existentes: `integration_mode = 'managed'` por default
- `_get_llm()` fallback chain: request key → env var → error

### Formulario adaptativo
El `RegisterAgentForm` recibe `integrationMode` como prop:
- **Managed**: muestra campo "LLM API Key" (required, type=password), endpoint locked a `http://agents:3004`
- **External**: muestra campo "Agent Endpoint URL" (required), sin campo API key

---

## 4. Archivos modificados fuera del frontend

| Archivo | Cambio |
|---------|--------|
| `services/bpp/requirements.txt` | + cryptography>=42.0 |
| `services/bpp/app/crypto.py` | NUEVO: decrypt AES-256-GCM |
| `services/bpp/app/handlers/beckn_actions.py` | decrypt credentials, pasar al orchestrator |
| `services/orchestrator/app/models.py` | + credentials Optional en ExecuteRequest y ExecutionRecord |
| `services/orchestrator/app/main.py` | Thread credentials al crear ExecutionRecord |
| `services/orchestrator/app/executor.py` | _call_agent inyecta _credentials en payload |
| `services/agents/ai_agents/main.py` | Extrae _credentials del body, pasa a handler |
| `services/agents/ai_agents/code_review/agent.py` | _get_llm(api_key=None) con fallback, run_task acepta credentials |
| `services/agents/ai_agents/text_generation/agent.py` | Identico al code_review |
| `infra/.env` | + CREDENTIALS_ENCRYPTION_KEY |
| `infra/docker-compose.yml` | + CREDENTIALS_ENCRYPTION_KEY en bpp y frontend, + DB vars en frontend, + GOOGLE_API_KEY en agents |

---

## 5. Variables de entorno nuevas

| Variable | Servicios | Descripcion |
|----------|-----------|-------------|
| `JWT_SECRET` | frontend | Secret para firmar/verificar JWT |
| `CREDENTIALS_ENCRYPTION_KEY` | frontend, bpp | 32 bytes hex para AES-256-GCM |
| `DB_HOST/PORT/NAME/USER/PASSWORD` | frontend | Conexion a PostgreSQL (ya existia en bap/bpp) |

---

## 6. Callback Viewer

`scripts/callback-viewer.html` — se agrego sort descendente por ID para que los callbacks mas recientes aparezcan primero:
```js
allCallbacks = (await res.json()).sort((a, b) => b.id - a.id);
```

---

## 7. Datos de prueba en BD

Se agregaron tags `[TEST]` a todos los agentes y providers existentes:
- agent_name y label: prefijo `[TEST]`
- provider organization.name: prefijo `[TEST]`
- Agentes 1 y 5 (creados manualmente sin beckn_id): completados con beckn_id, agentfacts_id, agent_urn, label
