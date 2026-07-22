# Reproducing Akili

## 1. Runtime contract

```bash
python -m pip install -e .
python examples/minimal_lifecycle.py
python -m unittest discover -s tests -v
```

Expected result: the example prints a registry with `translator@v1` active, `translator@v2` rolled back, and a valid audit chain.

## 2. CPU MuJoCo notebook

Open:

```text
notebooks/robotics/Akili_Robotics_v0_2_MuJoCo_Standalone.ipynb
```

Recommended environment:

- Python 3.10–3.12
- CPU is sufficient
- `torch`, `numpy`, `mujoco`, `imageio`, `pillow`, `matplotlib`

Configuration is controlled through environment variables. Important variables include:

```text
AKILI_ARM_SEED
AKILI_ARM_OUT
AKILI_ARM_RESUME
```

Run every cell from the top. Do not modify activation thresholds after viewing evaluation results.

## 3. GPU LLM notebook

Open:

```text
notebooks/llm/Akili_Skill_Runtime_v0_1_Standalone_Colab.ipynb
```

Use a Colab GPU. The public base model is downloaded from Hugging Face. A missing `HF_TOKEN` warning is harmless for public models unless rate limiting occurs.

## 4. Import immutable Drive evidence

Export one or more completed run directories as a zip, then execute:

```bash
python tools/import_drive_evidence.py /path/to/drive_runs.zip \
  --destination results/publication/imported
python tools/release_audit.py
python tools/make_checksums.py results/publication
```

The importer never changes source artifact contents. It rejects obvious tokens and records SHA-256 checksums.

## 5. Split CIFAR-100 publication track

The planned frozen protocol is in:

```text
benchmarks/split_cifar100/README.md
```

Development notebooks are included for transparency, but their numbers must not be presented as the final matched DER++ comparison.

## 6. Colab operations

See [`docs/COLAB_OPERATIONS.md`](docs/COLAB_OPERATIONS.md). Always run the evidence collector before repeating an experiment.
