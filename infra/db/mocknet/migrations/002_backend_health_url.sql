-- 002_backend_health_url.sql — Add an explicit backend health URL.
--
-- `endpoint_url` is the ONIX receiver URL (what other Beckn nodes POST
-- against) — semantically correct but unhelpful for liveness probing
-- because ONIX does not expose /health. `backend_health_url` lets the
-- liveness probe (services/mock-network/app/registry/liveness.py) hit
-- the participant's own backend service directly.
--
-- Optional: when NULL the probe falls back to deriving from
-- `endpoint_url` (best-effort, see liveness._derive_probe_url).

ALTER TABLE subscribers ADD COLUMN backend_health_url TEXT;

UPDATE subscribers
SET backend_health_url = 'http://bap-marketplace:3001'
WHERE subscriber_id = 'bap.example.com';

UPDATE subscribers
SET backend_health_url = 'http://bpp-provider:3002'
WHERE subscriber_id = 'bpp.example.com';

UPDATE subscribers
SET backend_health_url = 'http://bpp-serg:3005'
WHERE subscriber_id = 'bpp-serg.example.com';
