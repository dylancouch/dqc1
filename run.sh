#!/usr/bin/env bash
# =============================================================================
# @file     run.sh
# @brief    Interactive menu to run DQC1.ipynb on local simulator or IBM hardware.
#
# @license  MIT License — see LICENSE file for details.
# =============================================================================
#
# Presents a menu to select the execution backend:
#   [1] Local Simulator  — Statevector sim, fast/free, for testing logic
#   [2] IBM Hardware     — Real QPU via SamplerV2, costs shots, "production"
#
# Then prompts for key config params (feature map, shots, etc.) and executes
# DQC1.ipynb via nbconvert, saving output to a mode-stamped output file.
#
# Usage:
#   bash run.sh
#
# Requirements:
#   - .venv must exist at project root (python -m venv .venv)
#   - IBM credentials saved via QiskitRuntimeService.save_account()
#     (only required when selecting IBM Hardware mode)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# Resolve project root as the directory containing this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTEBOOK="$SCRIPT_DIR/DQC1.ipynb"
# Support Windows Git Bash and POSIX virtual environments.
if [[ -x "$SCRIPT_DIR/.venv/Scripts/python.exe" ]]; then
    ACTIVATE="$SCRIPT_DIR/.venv/Scripts/activate"
    VENV_PY="$SCRIPT_DIR/.venv/Scripts/python.exe"
else
    ACTIVATE="$SCRIPT_DIR/.venv/bin/activate"
    VENV_PY="$SCRIPT_DIR/.venv/bin/python"
fi

# Named Jupyter kernel pointing to the venv's Python interpreter
KERNEL_NAME="dqc1-venv"

# Execution timeout per cell in seconds (IBM queue waits can take minutes)
CELL_TIMEOUT=3600

# ---------------------------------------------------------------------------
# Helper: print a section divider
# ---------------------------------------------------------------------------
divider() {
    echo "============================================================"
}

# ---------------------------------------------------------------------------
# Step 1 — Backend selection menu
# ---------------------------------------------------------------------------
clear
divider
echo " DQC1 — Quantum Kernel Execution"
divider
echo ""
echo "  Select execution backend:"
echo ""
echo "  [1]  Local Simulator   (Statevector — fast, free, no queue)"
echo "  [2]  IBM Hardware      (Real QPU via SamplerV2 — production)"
echo ""
divider

# Loop until the user picks a valid option
while true; do
    read -rp "  Choice [1/2]: " BACKEND_CHOICE
    case "$BACKEND_CHOICE" in
        1)
            # Local statevector simulation — no IBM credentials needed
            USE_IBM_BACKEND=0
            BACKEND_LABEL="Local Simulator"
            OUTPUT="$SCRIPT_DIR/DQC1_local_output.ipynb"
            break
            ;;
        2)
            # Real IBM Quantum hardware — requires saved credentials
            USE_IBM_BACKEND=1
            BACKEND_LABEL="IBM Hardware"
            OUTPUT="$SCRIPT_DIR/DQC1_ibm_output.ipynb"
            break
            ;;
        *)
            echo "  Invalid choice. Enter 1 or 2."
            ;;
    esac
done

echo ""

# ---------------------------------------------------------------------------
# Step 2 — Config params (press Enter to accept the default shown)
# ---------------------------------------------------------------------------
echo "  Configure run parameters (Enter = keep default):"
echo ""

# Feature map: controls the quantum circuit structure used for encoding
read -rp "  Feature map [zz / karimi / zdiag / rxryrz / pauli] (default: zz): " INPUT
FEATURE_MAP="${INPUT:-zz}"

# Circuit depth: number of repeated feature-map layers in the circuit
read -rp "  Layers (default: 3): " INPUT
LAYERS="${INPUT:-3}"

# PCA components: also determines qubit count (one qubit per PCA dimension)
read -rp "  PCA components / qubits (default: 6): " INPUT
PCA_COMPONENTS="${INPUT:-6}"

# Shots per circuit: more shots = lower shot noise but higher cost and time
read -rp "  Shots per circuit (default: 1024): " INPUT
DQC1_KERNEL_SHOTS="${INPUT:-1024}"

# Initial cluster count for the DQC1 unsupervised clustering phase
read -rp "  Initial clusters (default: 6): " INPUT
INIT_CLUSTERS="${INPUT:-6}"

# Sample cap: 0 = full dataset; >0 = use only N training samples (useful for
# quick IBM smoke tests that would otherwise exhaust shot budget on full data)
read -rp "  Max training samples, 0 = full dataset (default: 0): " INPUT
N_SAMPLES="${INPUT:-0}"

# IBM-specific: max circuits bundled into a single SamplerV2 job submission.
# IBM open plan caps at ~300 circuits/job; 100 stays safely under the limit.
if [[ "$USE_IBM_BACKEND" == "1" ]]; then
    read -rp "  Max circuits per IBM job (default: 100): " INPUT
    IBM_MAX_CIRCUITS_PER_JOB="${INPUT:-100}"
else
    # Not used in local mode, but exported so the notebook env is consistent
    IBM_MAX_CIRCUITS_PER_JOB=100
fi

# Skip the entropy-reduction phase and keep K=INIT_CLUSTERS from the init phase
read -rp "  Disable cluster reduction? [1=yes / 0=no] (default: 1): " INPUT
DISABLE_REDUCTION="${INPUT:-1}"

echo ""

# ---------------------------------------------------------------------------
# Step 3 — Verify prerequisites
# ---------------------------------------------------------------------------

# Ensure the notebook file exists before doing anything else
if [[ ! -f "$NOTEBOOK" ]]; then
    echo "[ERROR] Notebook not found: $NOTEBOOK"
    exit 1
fi

# Ensure the venv has been created; guide the user if it hasn't
if [[ ! -f "$ACTIVATE" ]]; then
    echo "[ERROR] venv not found: $ACTIVATE"
    echo "        Run: python -m venv .venv && python -m pip install -r requirements.txt"
    exit 1
fi

# ---------------------------------------------------------------------------
# Step 4 — Activate venv
# ---------------------------------------------------------------------------

# Source the activation script; from here on python/pip are the venv's binaries
source "$ACTIVATE"
echo "[VENV] Activated: $(python --version)"

# ---------------------------------------------------------------------------
# Step 5 — Register venv as a named Jupyter kernel
# ---------------------------------------------------------------------------

# Ensure required packages are installed into the venv and register the kernel
echo "[KERNEL] Installing ipykernel & papermill into venv and registering kernel '$KERNEL_NAME'..."
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install ipykernel papermill -q
# Register kernel using the venv Python so kernel.json points to the venv interpreter
"$VENV_PY" -m ipykernel install --user --name "$KERNEL_NAME" --display-name "DQC1 (.venv)"
echo "[KERNEL] Registered (points to $VENV_PY)."
echo ""

# ---------------------------------------------------------------------------
# Step 6 — Export all env vars for the notebook kernel
# ---------------------------------------------------------------------------

# Discover dataset folders under data/ and prompt in the shell (not in the notebook)
# This avoids notebook input() calls which fail under papermill (no stdin).
DATA_ROOT="$SCRIPT_DIR/data"
DATASET_FOLDERS=()
if [[ -d "$DATA_ROOT" ]]; then
    shopt -s nullglob
    for d in "$DATA_ROOT"/*; do
        if [[ -d "$d" ]]; then
            DATASET_FOLDERS+=("$(basename "$d")")
        fi
    done
    shopt -u nullglob
fi

if [[ -z "${MRI_DATASET:-}" ]]; then
    if [[ ${#DATASET_FOLDERS[@]} -eq 0 ]]; then
        echo "[DATASET] No dataset folders found under data/. Notebook may prompt interactively." 
    elif [[ ${#DATASET_FOLDERS[@]} -eq 1 ]]; then
        MRI_DATASET="${DATASET_FOLDERS[0]}"
        export MRI_DATASET
        echo "[DATASET] Using dataset: $MRI_DATASET"
    else
        echo "Available dataset folders:"
        idx=1
        for name in "${DATASET_FOLDERS[@]}"; do
            printf "  [%d] %s\n" "$idx" "$name"
            idx=$((idx+1))
        done
        read -rp "Select dataset by number or name (default: 1): " SEL
        if [[ -z "$SEL" ]]; then
            SEL=1
        fi
        if [[ "$SEL" =~ ^[0-9]+$ ]] && (( SEL >= 1 && SEL <= ${#DATASET_FOLDERS[@]} )); then
            MRI_DATASET="${DATASET_FOLDERS[$((SEL-1))]}"
        else
            MRI_DATASET="$SEL"
        fi
        export MRI_DATASET
        echo "[DATASET] Selected: $MRI_DATASET"
    fi
fi

export USE_IBM_BACKEND
export FEATURE_MAP
export LAYERS
export PCA_COMPONENTS
export DQC1_KERNEL_SHOTS
export INIT_CLUSTERS
export N_SAMPLES
export IBM_MAX_CIRCUITS_PER_JOB
export DISABLE_REDUCTION
export MRI_DATASET

# ---------------------------------------------------------------------------
# Step 7 — Print run summary before launching
# ---------------------------------------------------------------------------
divider
echo " DQC1 Run Summary"
divider
echo " Backend:           $BACKEND_LABEL  (USE_IBM_BACKEND=$USE_IBM_BACKEND)"
echo " Notebook:          $NOTEBOOK"
echo " Output:            $OUTPUT"
echo " Kernel:            $KERNEL_NAME"
echo " Feature map:       $FEATURE_MAP  (layers=$LAYERS)"
echo " PCA components:    $PCA_COMPONENTS"
echo " Shots:             $DQC1_KERNEL_SHOTS"
echo " Init clusters:     $INIT_CLUSTERS"
echo " Max samples:       $([ "$N_SAMPLES" = "0" ] && echo "full dataset" || echo "$N_SAMPLES")"
echo " Disable reduction: $DISABLE_REDUCTION"
if [[ "$USE_IBM_BACKEND" == "1" ]]; then
echo " Max circuits/job:  $IBM_MAX_CIRCUITS_PER_JOB"
fi
divider
echo ""

# Give the user a moment to review the summary before the terminal clears
sleep 2
clear

# ---------------------------------------------------------------------------
# Step 8 — Execute the notebook
# ---------------------------------------------------------------------------

echo "[RUN] Starting notebook execution..."
echo "[RUN] Backend: $BACKEND_LABEL"
echo "[RUN] Cell timeout: ${CELL_TIMEOUT}s"
echo ""

# Use papermill to execute the notebook. papermill is preferred over nbconvert
# on Windows because nbconvert's kernel subprocess hangs due to the ProactorEventLoop
# not supporting ZMQ's add_reader — a Windows-specific incompatibility that cannot
# be reliably fixed from outside the kernel process.
# papermill handles Windows kernel lifecycle without this issue.
"$VENV_PY" -m papermill \
    "$NOTEBOOK" \
    "$OUTPUT" \
    --kernel "$KERNEL_NAME" \
    --execution-timeout "$CELL_TIMEOUT" \
    --no-progress-bar

echo ""
divider
echo " Execution complete."
echo " Backend:    $BACKEND_LABEL"
echo " Output:     $OUTPUT"
divider
