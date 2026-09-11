"""SoS actuarial guest domain (day-one).

Not an iec-proto-c lift. HTTP JSON on the Unit public port. Emits
WorkHandoff JSON only (kind/class/payload_digest + status/id). Transport
is operator/ctl-mediated — no guest→ctl HTTP, no runtime.apply
compute-work. Reserve demo is a UX seed stub (not IFRS17; named iec
baseline remains reserve_ifrs17). Stub fallback until operator/ctl
admits the handoff (or an opt-in lab hook). Default hook stays inert.
Does not close #70.
"""

__version__ = "0.1.0"
