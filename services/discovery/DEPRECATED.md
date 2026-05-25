# Discovery Service — DEPRECATED

This service is no longer in the runtime path as of Pieza 2 of the
discover v2 redesign. The CDS at `services/mock-network/` (endpoint
`POST /beckn/discover`) replaces the fan-out flow this service used to
drive.

What used to happen:

    BAP → ONIX-BAP → discovery:3007 → fan-out to every registered BPP

What happens now:

    BAP → ONIX-BAP → mock-network:8090/beckn/discover → indexed query

The ONIX routing change lives in `infra/onix/generic-routing-BAPCaller.yaml`.

This directory is kept for reference until we remove the container from
the compose file in a follow-up cleanup PR. The code is read-only.
