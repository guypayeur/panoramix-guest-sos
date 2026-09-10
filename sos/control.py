"""Placeholder SoS control stub.

Day-one is thinner than iec-proto-c. No Temporal/Ray/AWS URLs, no L1–L2 port.
"""

from __future__ import annotations


class ControlStub:
    """In-guest control placeholder. HTTP JSON only; engines are not here."""

    def snapshot(self) -> dict:
        return {
            "control": "stub",
            "ready": False,
            "iec_equivalent": False,
        }
