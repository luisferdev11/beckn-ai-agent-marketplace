"""Admission queue — partner-BPP self-registration lifecycle.

A BPP operator POSTs an admission request; the system parks them as
``pending_admission``, runs the conformance kit automatically, and an
admin later approves (→ ``active``) or rejects (→ ``rejected``).

See docs/PLAN-BPP-REGISTRY-LIFECYCLE.md, Epics A + B + C.
"""
