"""
Discovery Service config — loads the registered BPPs from YAML.

The YAML file lists every BPP that should receive a fan-out when a
discover lands at this service. Format:

    bpps:
      - subscriber_id: bpp.example.com
        receiver_url: http://onix-bpp:8082/bpp/receiver
        name: General Tecla Industries
      - subscriber_id: bpp-serg.example.com
        receiver_url: http://onix-bpp-serg:8083/bpp/receiver
        name: Serg Ops
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import yaml


DEFAULT_CONFIG_PATH = "/app/config/bpps.yaml"


@dataclass(frozen=True)
class BppEntry:
    subscriber_id: str
    receiver_url: str
    name: str


def load_bpps(path: str | None = None) -> list[BppEntry]:
    config_path = path or os.getenv("DISCOVERY_CONFIG_PATH", DEFAULT_CONFIG_PATH)
    if not os.path.exists(config_path):
        return []

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    bpps_raw = data.get("bpps") or []
    return [
        BppEntry(
            subscriber_id=entry["subscriber_id"],
            receiver_url=entry["receiver_url"].rstrip("/"),
            name=entry.get("name", entry["subscriber_id"]),
        )
        for entry in bpps_raw
    ]
