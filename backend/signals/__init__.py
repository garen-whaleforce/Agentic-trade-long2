# Signals module
from .generator import SignalGenerator, generate_signal
from .gate import DeterministicGate, GateResult

__all__ = [
    "SignalGenerator",
    "generate_signal",
    "DeterministicGate",
    "GateResult",
]
