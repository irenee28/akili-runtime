# Akili MuJoCo Robotics Benchmark v1

Three independent CPU-only seeds were supplied in the Kimi-side LITE handoff. Every seed passed all binding hard checks, preserved the frozen trunk, rejected `avoid_zone@v2`, kept `avoid_zone@v1` serving, validated a three-step mission, survived cold restart, and retained a valid audit chain.

## Aggregate

- Seeds: 0, 1, 2
- Overall mean skill success: **99.5%**
- Unsafe v2 state: `ROLLED_BACK` in all seeds
- Sequential fine-tuning `reach_A`: 100% initially → 0% after the final skill in all seeds
- Frozen model parameters: 17,923
- Trainable parameters per adapter: 2,048 (11.4%)
- Akili skill bank: 112.7 KiB
- Four isolated full models: 290.5 KiB
- GPU required: none

## Evidence boundary

The public export includes reports, hard checks, registries, audit logs, mission receipts, logs, and the seed-0 MP4 demo set. PyTorch checkpoints remain in the private handoff because `.pt` files use pickle serialization; the intended immutable Zenodo/Drive archive can carry them with the supplied checksums.

This is a small synthetic MuJoCo/kinematic-policy demonstration, not evidence of production robot manipulation or sim-to-real transfer.
