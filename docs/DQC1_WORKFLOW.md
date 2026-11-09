# DQC1 Project Workflow

## Purpose

Takes MRI brain tumor feature data as input, runs DQC1 projected-fidelity
clustering on IBM Quantum hardware, returns the resulting cluster assignments
to the local machine, and reports clustering performance metrics against
ground-truth labels.

---

## Execution Flow

### Step 1 — Load MRI Data (local, Cell 9)

- Loads feature vectors from `<dataset>_train.bin`
- Loads ground-truth class labels from `<dataset>_train.meta`
- `.bin` files carry a 32-float32 header that is skipped; feature dimension is 256

### Step 2 — Preprocess (local, Cell 9)

- `StandardScaler` fit on the training feature vectors
- PCA reduction to `PCA_COMPONENTS` dimensions (default 6) — fit on training data only, reused for test to prevent data leakage
- PCA dimension equals qubit count: 6 components → 6-qubit quantum circuits

### Step 3 — Quantum Kernel Computation

Two execution paths controlled by `USE_IBM_BACKEND`:

#### Local path (`USE_IBM_BACKEND=0`, Cell 3)

- `build_dqc1_kernel_matrix()` precomputes `Statevector.from_instruction(U(x))` for all N samples
- Builds Gram matrix via BLAS: `G = S @ S†`, then `K = |G|²`
- Exact, noiseless, fast

#### IBM Cloud path (`USE_IBM_BACKEND=1`, Cell 4 → `ibm_kernel.py`)

- Authenticates via `QiskitRuntimeService(channel="ibm_quantum_platform")`
- Selects backend via `select_backend()` in `ibm_backend.py`
- Builds `U_i @ U_j†` circuit for every upper-triangle pair (i, j)
- Transpiles for target backend at `optimization_level=1`
- Batches circuits into jobs of ≤100 (IBM open plan limit ~300)
- Submits each batch via `SamplerV2`; `job.result()` blocks until complete
- Extracts `K(i,j) = P(measure |0...0>)` from shot counts in the `c` classical register
- Returns the same (N, N) symmetric matrix as the local path

**Kernel value:**
```
K(i,j) = |<0| U_i @ U_j† |0>|²
        ≈ P(measure |0...0> on U_i @ U_j† applied to |0...0>)   ← IBM hardware
```

### Step 4 — DQC1 Clustering (local, Cell 9)

- `DQC1EntropyCluster.fit_full()` uses the kernel matrix K for entropy-based (ΔH) cluster assignment
- Init phase: K random seeds grown to minimum cluster size, remaining samples assigned by ΔH
- Reduction phase: disabled by default (`DISABLE_REDUCTION=1`) to preserve K from init
- All clustering logic runs locally; only the kernel circuits ran on IBM hardware

### Step 5 — Performance Metrics vs. Ground Truth (local, Cell 9)

Cluster assignments are compared against the loaded ground-truth labels using:

| Metric            | What it measures                                      |
| ----------------- | ----------------------------------------------------- |
| ARI               | Adjusted Rand Index — pairwise label agreement        |
| NMI               | Normalized Mutual Information                         |
| V-Measure         | Harmonic mean of homogeneity and completeness         |
| Fowlkes-Mallows   | Geometric mean of pairwise precision and recall       |
| Pairwise P/R      | Precision and recall over same-cluster pairs          |
| B-Cubed P/R/F     | Per-item precision and recall aggregated to F-score   |
| Silhouette        | Intra- vs. inter-cluster distance ratio               |
| Davies-Bouldin    | Average similarity between each cluster and its worst |
| Calinski-Harabasz | Ratio of between-cluster to within-cluster dispersion |

---

## Notebook Cell Map

| Cell | Purpose                                                                          |
| ---- | -------------------------------------------------------------------------------- |
| 0    | Markdown header                                                                  |
| 1    | Logging setup (`dlog()` — stdout + timestamped log file)                         |
| 2    | Config, imports, feature maps, `dqc1_kernel_value`, `DQC1EntropyCluster`         |
| 3    | `build_dqc1_kernel_matrix()` — local BLAS/Statevector path                       |
| 4    | IBM CLOUD SECTION — authenticates, selects backend, overrides kernel builder     |
| 5    | Runtime estimation (FakeTorino transpile check + wall-time estimates)          |
| 6    | LOCAL EXECUTION RESUMES marker                                                   |
| 7    | DQC1 purity circuit functions (used when `DISABLE_REDUCTION=0`)                  |
| 8    | Cluster reduction override (`DQC1EntropyCluster._reduce`)         |
| 9    | MRI data load, preprocessing helpers, metrics, `evaluate_mri()`                 |
| 10   | Execute pipeline — calls `evaluate_mri()`                                        |
