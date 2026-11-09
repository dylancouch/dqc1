# =============================================================================
# @file     ibm_backend.py
# @brief    Dynamic IBM Quantum backend selection with preferred-list and fallback.
#
# @license  MIT License — see LICENSE file for details.
# =============================================================================
"""
IBM Quantum backend selection helper.

Usage:
    from ibm_backend import select_backend
    from qiskit_ibm_runtime import QiskitRuntimeService

    service = QiskitRuntimeService(channel="ibm_quantum_platform")
    backend = select_backend(service)
    print(f"Using backend: {backend.name}")
"""

from qiskit_ibm_runtime import QiskitRuntimeService

# Preferred backends in priority order. The first one found to be
# operational will be selected. If none are available, falls back
# to least_busy() among all operational real-hardware backends.
PREFERRED_BACKENDS = [
    "ibm_fez",
    "ibm_torino",
    "ibm_marrakesh",
    "ibm_kingston",
]


def select_backend(service: QiskitRuntimeService):
    """Return the best available IBM Quantum backend.

    Tries PREFERRED_BACKENDS in order, returning the first that is
    currently operational. Falls back to least_busy() if none of the
    preferred backends are available.
    """
    available = {b.name: b for b in service.backends(operational=True)}

    for name in PREFERRED_BACKENDS:
        if name in available:
            print(f"[backend] Selected preferred backend: {name}")
            return available[name]

    # Fallback: least busy real-hardware backend
    backend = service.least_busy(operational=True, simulator=False)
    print(f"[backend] No preferred backend available. Falling back to least busy: {backend.name}")
    return backend


if __name__ == "__main__":
    service = QiskitRuntimeService(channel="ibm_quantum_platform")
    backend = select_backend(service)
    # .status().pending_jobs removed — deprecated in qiskit-ibm-runtime ≥0.20
    print(f"Backend:        {backend.name}")
    print(f"Qubits:         {backend.num_qubits}")
