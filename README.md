# DQC1: Quantum Clustering on MRI Feature Data

This project runs DQC1 projected-fidelity clustering over MRI feature vectors. It supports a local simulator and IBM Quantum hardware. Dataset files and executed notebook outputs are not included.

## How it works

1. Load feature vectors and labels from a user-provided dataset.
2. Scale features and optionally reduce them with PCA.
3. Compute a projected-fidelity kernel locally or through IBM Quantum Runtime.
4. Assign clusters and compare them with the supplied labels.

The kernel estimates `|<0| U_i U_j† |0>|²`; on IBM hardware this is estimated from measurement shots.

## Setup

Clone this repository using the clone URL on its GitHub page. Then, from the project directory:

```bash
python -m venv .venv
```

Activate the environment and install the dependencies:

```bash
# Linux or macOS
source .venv/bin/activate
python -m pip install -r requirements.txt

# Windows PowerShell
.venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
```

Python 3.11 or newer is recommended.

## Dataset

Dataset files are not redistributed by this project. Confirm that you have permission to use the data and place it under `data/<dataset_name>/`. The supported layout and formats are documented in [data/README.md](data/README.md).

## Run

Start the interactive runner:

```bash
bash run.sh
```

Choose the local simulator or IBM hardware, then provide the requested settings. The runner writes an executed notebook to `DQC1_local_output.ipynb` or `DQC1_ibm_output.ipynb`. Those files may contain local paths or service run metadata and are excluded from version control.

IBM hardware runs require a configured IBM Quantum Runtime account. Configure credentials through IBM's supported account setup; never add credential files or tokens to this repository.

## Main files

- `DQC1.ipynb` — preprocessing, kernel, clustering, and evaluation workflow.
- `ibm_kernel.py` — IBM Quantum Runtime kernel implementation.
- `ibm_backend.py` — backend selection.
- `run.sh` — interactive runner.
- `docs/` — workflow and dependency notes.

## License

MIT. The license applies to this project's code. It does not grant rights to any user-provided datasets or third-party assets.
