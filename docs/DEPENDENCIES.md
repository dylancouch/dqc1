# Dependencies

Install the packages in `requirements.txt` into a Python 3.11 or newer virtual environment. The notebook uses NumPy, scikit-learn, Qiskit, and Qiskit Aer. `run.sh` uses Jupyter IPykernel and Papermill to execute the notebook.

IBM Quantum Runtime is needed only for hardware execution. Configure the account using IBM's supported credential flow; keep credentials outside this repository.

PyTorch is optional. The notebook disables its tensor path when PyTorch is unavailable. Dataset files are not included; see [the dataset notes](../data/README.md).
