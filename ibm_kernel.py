# =============================================================================
# @file     ibm_kernel.py
# @brief    IBM Quantum SamplerV2 drop-in replacement for build_dqc1_kernel_matrix().
#
# @license  MIT License — see LICENSE file for details.
# =============================================================================
"""
IBM Quantum kernel computation for DQC1 projected-fidelity kernel.

Drop-in replacement for build_dqc1_kernel_matrix() that runs circuit
execution on IBM Quantum hardware via SamplerV2 instead of local
Statevector simulation.

Usage in notebook:
    import os
    os.environ["USE_IBM_BACKEND"] = "1"   # toggle on
    from ibm_kernel import build_ibm_kernel_matrix

    K = build_ibm_kernel_matrix(
        X_np,
        feature_map_fn=get_feature_map_circuit,
        feature_map=FEATURE_MAP,
        layers=LAYERS,
        shots=DQC1_KERNEL_SHOTS,
    )

Kernel value definition (real hardware):
    K(i,j) = P(measure |0...0> on circuit U_i @ U_j†)
    This is the shot-based estimate of |<0|U_i U_j†|0>|^2.
"""

import os
import time
import numpy as np
from typing import Callable, List, Optional

from qiskit import QuantumCircuit, transpile
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2

from ibm_backend import select_backend

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

USE_IBM_BACKEND = bool(int(os.environ.get("USE_IBM_BACKEND", "0")))

# IBM open plan allows ~300 circuits per job; use 100 to stay safely under limit
MAX_CIRCUITS_PER_JOB = int(os.environ.get("IBM_MAX_CIRCUITS_PER_JOB", "100"))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_kernel_circuit(xi: np.ndarray, xj: np.ndarray,
                          feature_map_fn: Callable,
                          feature_map: str, layers: int) -> QuantumCircuit:
    """Build U_i @ U_j† circuit with measurements for kernel estimation."""
    U_i = feature_map_fn(xi, feature_map, layers)
    U_j = feature_map_fn(xj, feature_map, layers)

    n = U_i.num_qubits
    qc = QuantumCircuit(n, n)
    qc.compose(U_i, inplace=True)
    qc.compose(U_j.inverse(), inplace=True)
    qc.measure(range(n), range(n))
    return qc


def _zero_bitstring(n_qubits: int) -> str:
    """Return the all-zeros bitstring for n_qubits (Qiskit little-endian)."""
    return "0" * n_qubits


def _extract_zero_prob(pub_result, n_qubits: int, shots: int) -> float:
    """Extract P(|0...0>) from a SamplerV2 PubResult."""
    zero_key = _zero_bitstring(n_qubits)
    try:
        counts = pub_result.data.c.get_counts()  # classical register named 'c' by QuantumCircuit(n, n)
        zero_count = counts.get(zero_key, 0)
        return float(zero_count) / shots
    except Exception as e:
        print(f"[ibm_kernel] Warning: could not extract counts: {e}")
        return 0.0


def _submit_batch(circuits: List[QuantumCircuit], backend, shots: int) -> List[float]:
    """Transpile a batch of circuits and submit as one SamplerV2 job.
    Returns list of |0...0> probabilities, one per circuit."""
    if not circuits:
        return []

    n_qubits = circuits[0].num_qubits
    print(f"[ibm_kernel] Transpiling {len(circuits)} circuits for {backend.name}…")
    t0 = time.time()
    transpiled = transpile(circuits, backend=backend, optimization_level=1)
    print(f"[ibm_kernel] Transpile done in {time.time() - t0:.1f}s")

    sampler = SamplerV2(backend)
    # SamplerV2 PUB format: (circuit, parameter_values, shots)
    # parameter_values=None because feature values are bound during circuit construction
    pubs = [(qc, None, shots) for qc in transpiled]

    print(f"[ibm_kernel] Submitting job ({len(pubs)} circuits, {shots} shots each)…")
    t1 = time.time()
    job = sampler.run(pubs)
    result = job.result()
    print(f"[ibm_kernel] Job completed in {time.time() - t1:.1f}s  (job id: {job.job_id()})")

    probs = []
    for i, pub_result in enumerate(result):
        p = _extract_zero_prob(pub_result, n_qubits, shots)
        probs.append(float(np.clip(p, 0.0, 1.0)))
    return probs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_ibm_kernel_matrix(
    X_np: np.ndarray,
    feature_map_fn: Callable,
    feature_map: str,
    layers: int,
    shots: int = 1024,
    service: Optional[QiskitRuntimeService] = None,
    backend=None,
) -> np.ndarray:
    """Build DQC1 projected-fidelity kernel matrix using IBM Quantum hardware.

    Replaces build_dqc1_kernel_matrix() for cloud execution.
    Builds U_i @ U_j† circuits for all upper-triangle pairs, batches them
    into jobs of MAX_CIRCUITS_PER_JOB, submits via SamplerV2, and estimates
    K(i,j) = P(measure |0...0>).

    Args:
        X_np:           (N, d) array of PCA-reduced, scaled feature vectors
        feature_map_fn: get_feature_map_circuit from the notebook
        feature_map:    feature map kind string (e.g. "zz")
        layers:         number of feature map layers
        shots:          measurement shots per circuit
        service:        optional pre-authenticated QiskitRuntimeService;
                        if None, a new one is created
        backend:        optional pre-selected IBMBackend; if provided, service
                        is ignored and no second backend selection is performed

    Returns:
        K: (N, N) symmetric kernel matrix with diagonal = 1.0
    """
    X_np = np.asarray(X_np, float)
    N = len(X_np)

    # Resolve backend: use the one passed in, or select via service
    if backend is None:
        # No pre-selected backend supplied; select the best available one now
        if service is None:
            print("[ibm_kernel] Connecting to IBM Quantum…")
            service = QiskitRuntimeService(channel="ibm_cloud")
        backend = select_backend(service)
    print(f"[ibm_kernel] Using backend: {backend.name} ({backend.num_qubits} qubits)")

    # Build upper-triangle pair list and circuits
    pairs = [(i, j) for i in range(N) for j in range(i + 1, N)]
    n_pairs = len(pairs)
    print(f"[ibm_kernel] Building {n_pairs} kernel circuits for {N} samples…")

    circuits = []
    for i, j in pairs:
        qc = _build_kernel_circuit(X_np[i], X_np[j],
                                   feature_map_fn, feature_map, layers)
        circuits.append(qc)

    # Split into batches and submit
    all_probs = []
    n_batches = (n_pairs + MAX_CIRCUITS_PER_JOB - 1) // MAX_CIRCUITS_PER_JOB
    print(f"[ibm_kernel] Submitting {n_batches} batch(es) "
          f"(max {MAX_CIRCUITS_PER_JOB} circuits each)…")

    for b in range(n_batches):
        start = b * MAX_CIRCUITS_PER_JOB
        end = min(start + MAX_CIRCUITS_PER_JOB, n_pairs)
        print(f"[ibm_kernel] Batch {b + 1}/{n_batches}: circuits {start}–{end - 1}")
        batch_probs = _submit_batch(circuits[start:end], backend, shots)
        all_probs.extend(batch_probs)

    # Fill symmetric kernel matrix
    K = np.zeros((N, N), dtype=float)
    np.fill_diagonal(K, 1.0)
    for idx, (i, j) in enumerate(pairs):
        K[i, j] = K[j, i] = all_probs[idx]

    print(f"[ibm_kernel] Kernel matrix complete. "
          f"Min={K.min():.4f}, Max={K.max():.4f}, Mean={K.mean():.4f}")
    return K
