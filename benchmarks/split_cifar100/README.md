# Frozen Split CIFAR-100 publication protocol

DER++ is a **continual-learning method/baseline**, not a benchmark. This track uses Split CIFAR-100 class-incremental learning as the benchmark and evaluates DER++ both as a baseline and as a possible learning engine under Akili governance.

## Dataset and stream

- CIFAR-100
- 10 sequential tasks
- 10 new classes per task
- class-incremental evaluation
- seeds: 1, 2, 3
- fixed class order and sample order per seed
- official test set inaccessible to training, model selection and threshold setting

## Fixed resource budget

Initial publication budget:

- replay capacity: 400 examples for replay methods
- same backbone and initialization
- same acquisition epochs and optimizer family
- same training-example exposure accounting
- adaptive-state bytes reported for every method
- no permanent parameter growth hidden from resource accounting

## Methods

1. Sequential fine-tuning
2. Experience Replay (ER)
3. DER++
4. ER-ACE
5. Offline joint training — reference only, not a continual method
6. Akili learning engine without lifecycle governance
7. DER++ + Akili admission/validation
8. DER++ + Akili admission + lifecycle/budget controller
9. Full Akili candidate system

The exact method list may be reduced **before** official runs if compute is insufficient. It may not be changed after results are observed.

## Metrics

- final average class-IL accuracy
- average forgetting
- backward transfer
- new-task accuracy
- learned-task rate
- raw replay examples and bytes
- total adaptive-state bytes
- training time and optimizer updates
- stale/obsolete capability errors
- corrupted-update damage
- activation, rejection and rollback counts
- dormant recovery accuracy

## Required ablations

```text
DER++ alone
DER++ + Akili validation
DER++ + Akili validation + lifecycle
full Akili
```

This identifies where an established learning method stops and where runtime governance adds value.

## Oracle diagnostics

The existing 87.50% three-action oracle is preserved as a diagnostic only. It must never appear in a table as Akili's deployable accuracy. The publication result must use learned routing/gating with no oracle labels.

## Release conditions

A result is publication-ready only when:

- all three seeds complete;
- the same frozen protocol is used for every method;
- no official-test leakage occurs;
- raw per-task metrics are present;
- resource accounting is complete;
- results and environment are hashed;
- rerunning the aggregation reproduces the tables.

## Official baseline runner

Use `Akili_Mammoth_DERPP_Baseline_Suite_v1_Standalone_Colab.ipynb`.

It runs official Mammoth ER, DER++, and ER-ACE with a recorded repository commit. Start with smoke mode. The resulting scores are baseline evidence only, not the final Akili comparison.
