# Claims ledger

## Supported by uploaded MuJoCo three-seed evidence

- Three independent seeds completed the `akili-robotics-v0.2-mujoco-four-systems` protocol.
- All three seeds passed every binding hard check.
- Mean skill success across four skills and three seeds was 99.5%.
- `avoid_zone@v2` ended `ROLLED_BACK` in all seeds while `avoid_zone@v1` remained serving.
- Every seed completed the three-step certified mission and passed cold restart.
- Sequential fine-tuning retained `reach_A` at 100% initially and 0% after the final skill in all seeds.
- The frozen model had 17,923 parameters; each adapter trained 2,048 parameters (11.4%).
- The reported Akili bank was 115,441 bytes versus 297,460 bytes for four isolated full models.
- The complete lifecycle ran on CPU.

**Boundary:** this is a small synthetic MuJoCo/kinematic-policy demonstration, not production robotics or sim-to-real evidence.

## Supported by reported Agent Evolution output

- Current-world accuracy: 100%.
- Stale-version error: 0%.
- Production attack rate: 0%.
- Dormant historical recovery: 100%.
- Naive adapter bank activated the malicious candidate on all held-out triggers.
- Tiny replay preserved most current capability but also preserved the malicious update.
- Frozen-base and lifecycle hard checks were reported as passing.

**Evidence limitation:** the raw Agent Evolution Drive run has not yet been imported.

## Supported as CIFAR capacity/failure analysis

- v0.23B three-seed baseline/final mean: 62.55%.
- Top-2 candidate union mean: 75.28%; top-3 union mean: 80.22%.
- No replay arbiter met the locked constraints; no candidate was deployed and final gain was zero.
- A later nonlinear development audit improved 66.42% to 70.08% on its development set, while the full oracle union was 87.50%; the replay gate failed.
- Union/oracle values are diagnostic ceilings, not task-free deployed accuracy.

## Pending

- Raw Agent Evolution immutable evidence bundle.
- Official Mammoth ER/DER++/ER-ACE results.
- Matched DER++ + Akili ablations.
- External CL-Bench, SkillLearnBench, or Morpheus evaluation.

## Not claimed

- Akili solves continual learning.
- Akili is universally safer than RAG.
- Oracle/union ceilings are achieved task-free accuracy.
- Structural notebook verification is a real model result.
- MuJoCo results transfer to physical robots.
- Big-technology licensing or production readiness.
