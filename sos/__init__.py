"""SoS actuarial guest domain (day-one).

Not an iec-proto-c lift. HTTP JSON on the Unit public port. Opaque work
handoff is kind/class/payload_digest (runtime/compute_work.py on
panoramix-runtime main, #70 Slice B). Ctl exports GET /handoff and
/payload; operator/ctl admits to runtime compute (mesh compute-job → sos).
Reserve digest keys match runtime.reserve.digest_for (docs/reserve.md /
PR #84). Local reserve demo is a UX seed stub only (not IFRS17 math; named
iec baseline remains reserve_ifrs17). Guest never calls runtime.apply.
Compute engines stay in panoramix-runtime bindings. Does not close #70.
"""

__version__ = "0.1.0"
