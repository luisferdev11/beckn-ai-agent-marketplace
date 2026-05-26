"""Hardcoded DeDi subscriber records.

Each entry is the verbatim response that ``fabric.nfh.global/registry/dedi``
would return for the corresponding subscriber id, with ``details.url``
rewritten to internal Docker URIs so ONIX-BAP routes inside the network.

When a new participant joins the local network the operator must add an
entry here AND a row to the ``subscribers`` table in postgres-mocknet
(via the Registry CRUD). The two stores are intentionally separate in
MVP — see ``app/dedi/__init__.py``.
"""
from __future__ import annotations

SUBSCRIBERS: dict[str, dict] = {
    "bap.example.com": {
        "message": "ok",
        "data": {
            "namespace": "beckn-one",
            "namespace_id": "76EU7wu5EJGPXGeM4QxyWf8YEU9N1wYnNmGrEUZMK33PJT3uGRQwK4",
            "registry_id": "76EU8REebknSwWigtj7L6uFrAfpqRMRuXrY3jtpEmv7dpXPB9Zxpwb",
            "registry_name": "example-NPs",
            "record_id": "76EU7LZ7gfqj13dWDKR1Uitnim11mCoxWBPdzLxUpAMBPVdANKgyFM",
            "record_name": "example-bap",
            "description": "Subscription details",
            "details": {
                "subscriber_id": "bap.example.com",
                "url": "http://onix-bap:8081/bap/receiver",
                "type": "BAP",
                "domain": "*",
                "countries": ["IND"],
                "signing_public_key": "g/3swjI93IhZ0SScrVZapeLjU+W0AeiSid3LViYZJFo=",
            },
            "meta": {},
            "parent_namespaces": ["beckn.one", "nfh.global"],
            "network_memberships": ["beckn.one/testnet"],
            "state": "live",
            "ttl": 600,
        },
    },
    "bpp.example.com": {
        "message": "ok",
        "data": {
            "namespace": "beckn-one",
            "namespace_id": "76EU7wu5EJGPXGeM4QxyWf8YEU9N1wYnNmGrEUZMK33PJT3uGRQwK4",
            "registry_id": "76EU8REebknSwWigtj7L6uFrAfpqRMRuXrY3jtpEmv7dpXPB9Zxpwb",
            "registry_name": "example-NPs",
            "record_id": "76EU7ofwRCF1aobQkShARrf1PAUsNpHqWUJoynPu9w45YFKmzqaPmy",
            "record_name": "example-bpp",
            "description": "Subscription details",
            "details": {
                "subscriber_id": "bpp.example.com",
                "url": "http://onix-bpp:8082/bpp/receiver",
                "type": "BPP",
                "domain": "*",
                "countries": ["IND"],
                "signing_public_key": "CqVy97DW45bcZPPrWIYGe2ldl9C93NFeVciiAEYsvR0=",
            },
            "meta": {},
            "parent_namespaces": ["beckn.one", "nfh.global"],
            "network_memberships": ["beckn.one/testnet"],
            "state": "live",
            "ttl": 600,
        },
    },
    "bpp-serg.example.com": {
        "message": "ok",
        "data": {
            "namespace": "beckn-one",
            "namespace_id": "76EU7wu5EJGPXGeM4QxyWf8YEU9N1wYnNmGrEUZMK33PJT3uGRQwK4",
            "registry_id": "76EU8REebknSwWigtj7L6uFrAfpqRMRuXrY3jtpEmv7dpXPB9Zxpwb",
            "registry_name": "example-NPs",
            "record_id": "76EU7sergsergsergsergsergsergsergsergsergsergsergsergsr",
            "record_name": "serg-ops-bpp",
            "description": "Subscription details",
            "details": {
                "subscriber_id": "bpp-serg.example.com",
                "url": "http://onix-bpp-serg:8083/bpp/receiver",
                "type": "BPP",
                "domain": "*",
                "countries": ["MEX"],
                "signing_public_key": "bfbdo3TxLzSRutUMSjl+OeDtZgqVDlCuLbR2aDbtPN0=",
            },
            "meta": {},
            "parent_namespaces": ["beckn.one", "nfh.global"],
            "network_memberships": ["beckn.one/testnet"],
            "state": "live",
            "ttl": 600,
        },
    },
}
