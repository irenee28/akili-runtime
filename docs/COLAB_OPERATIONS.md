# Colab operations

## 1. Recover existing evidence first

Run `tools/colab/Akili_Drive_Evidence_Collector_v1_Standalone_Colab.ipynb`.

It scans the existing Drive runs without changing them, separates publication candidates from development evidence, excludes weights by default, scans for common secret formats, and creates a GitHub-ready ZIP with checksums.

## 2. MuJoCo three-seed rerun

Run `notebooks/publication/Akili_MuJoCo_v0_2_Three_Seed_Publication_Rerun_Colab.ipynb` only when the collector cannot recover three immutable successful seeds.

## 3. LLM three-seed rerun

Run `notebooks/publication/Akili_LLM_Skill_Runtime_v0_1_Three_Seed_Publication_Rerun_Colab.ipynb` only when the original clean evidence cannot be recovered. Use a Colab GPU.

## 4. Official Mammoth baselines

Run `benchmarks/split_cifar100/Akili_Mammoth_DERPP_Baseline_Suite_v1_Standalone_Colab.ipynb`.

Start in smoke mode. After ER, DER++, and ER-ACE complete, set `AKILI_DERPP_MODE=publication` and run seeds 1,2,3.

This runner records the exact Mammoth commit and refuses to proceed without the existing CIFAR-100 cache. It does not intentionally download the dataset.

## Scientific boundary

The Mammoth suite freezes official baseline evidence. It does not yet implement DER++ + Akili admission, DER++ + Akili lifecycle, or full managed forgetting.

Agent Evolution v0.4.2 stays private until a real run passes all binding checks.
