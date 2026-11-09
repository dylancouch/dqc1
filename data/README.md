# User-provided datasets

Dataset files are intentionally not included here. Before using a dataset,
confirm that its license and consent terms permit your intended use.

Place the files in a directory under `data/` using this layout:

```text
data/<dataset_name>/
├── features/<dataset_name>_train.bin
└── labels/<dataset_name>_train.meta
```

The feature file format supported by the notebook is a row-major float32
binary array with a 32-value header and 256 features per sample. Labels are
integers, one per line. `.npy` feature arrays are also supported.
