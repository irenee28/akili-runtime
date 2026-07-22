# Claims ledger

## Supported by uploaded MuJoCo three-seed evidence

- Three independent seeds completed the `akili-robotics-v0.2-mujoco-four-systems` protocol.
- All three seeds passed every binding hard check.
- Four skills were certified in all three seeds; 11/12 skill–seed evaluations scored 1.00, with `press_button@v1` scoring 0.94 in seed 1, yielding a 99.5% overall mean.
- `avoid_zone@v2` ended `ROLLED_BACK` in all seeds while `avoid_zone@v1` remained serving.
- Every seed completed the three-step certified mission and passed cold restart.
- Sequential fine-tuning retained `reach_A` at 100% initially and 0% after the final skill in all seeds.
- The frozen model had 17,923 parameters; each adapter trained 2,048 parameters (11.4%).
- The reported Akili bank was 115,441 bytes versus 297,460 bytes for four isolated full models.
- The complete lifecycle ran on CPU.

**Boundary:** this is a small synthetic MuJoCo/kinematic-policy demonstration, not production robotics or sim-to-real evidence.

## Supported by verified Agent Evolution lifecycle evidence

- All 43 binding hard checks are true.
- The final registry contains 4 ACTIVE, 3 DORMANT, and 1 ROLLED_BACK capability versions.
- `incident_response@v2` succeeded on 80/80 dedicated trigger attacks, was independently confirmed dangerous, and ended ROLLED_BACK.
- `incident_response@v1` remained ACTIVE and serving.
- All 24 audit entries form a valid recomputed SHA-256 chain from GENESIS.
- Registry adapter hashes match the eight `CANDIDATE_REGISTERED` audit events.
- The repair preserved the dataset hash and scientific contract and did not retrain the model.
- Production loads ACTIVE adapters only; DORMANT recovery uses an isolated vault runtime; ROLLED_BACK adapters are never loaded.

**Evidence limitation:** the five-system metric table remains reported evidence until the correct full comparison JSON is imported. The 320-example TF-IDF router summary is not the comparison file.

## Supported by the matched v0.22.3 CIFAR-100 project summary

- Protocol: Split CIFAR-100 Class-IL, 10 tasks × 10 classes, three seeds.
- The compared methods used the same frozen ResNet-50 ImageNet1K-V2 features, task orders, 400-example memory capacity, and DER++ coefficients α=β=0.5.
- Akili routed final Class-IL: 62.52% ± 0.19; average forgetting: 10.34%.
- Implemented DER++-400 final Class-IL: 22.16% ± 3.09; average forgetting: 71.70%.
- Difference: +40.36 final-accuracy points and −61.36 forgetting points for Akili under this protocol.
- Akili oracle: 79.38% ± 0.87 with zero oracle forgetting.
- The eight-prototype semantic-only diagnostic reached 62.55% ± 0.05, essentially matching Akili routed.

**Required boundary:** the current automatic DER++ win is primarily attributable to stable write-once semantic memory, not yet a unique expert-routing gain. The resource match does not include equal total adaptive-state bytes, and independent Mammoth replication remains pending.

## Supported as CIFAR capacity/failure analysis

- v0.23B three-seed baseline/final mean: 62.55%.
- Top-2 candidate union mean: 75.28%; top-3 union mean: 80.22%.
- No replay arbiter met the locked constraints; no candidate was deployed and final gain was zero.
- A later nonlinear development audit improved 66.42% to 70.08% on its development set, while the full oracle union was 87.50%; the replay gate failed.
- Union/oracle values are diagnostic ceilings, not task-free deployed accuracy.

## Pending

- Correct raw Agent Evolution five-system comparison JSON.
- Raw per-run v0.22.3 CIFAR bundle and independent Mammoth ER/DER++/ER-ACE replication.
- Governance ablations on top of independently reproduced CL engines.
- External CL-Bench, SkillLearnBench, or Morpheus evaluation.

## Not claimed

- Akili solves continual learning.
- Akili is universally safer than RAG.
- Oracle/union ceilings are achieved task-free accuracy.
- Structural notebook verification is a real model result.
- MuJoCo results transfer to physical robots.
- Big-technology licensing or production readiness.
