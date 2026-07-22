# Split CIFAR-100: oracle capacity versus learned retrieval

The Phase-2 diagnostic was designed to answer one question:

> Is the failure caused by missing useful candidate actions, or by the learned controller failing to select and gate the useful actions that already exist?

## Development result

| Quantity | Value |
|---|---:|
| Baseline action accuracy | 0.6641667 |
| KEEP + expert-1 | 0.6883333 |
| Top-2 candidate union | 0.8133333 |
| Full three-action oracle union | **0.8750000** |
| Learned gate + learned selector | 0.7008333 |
| Oracle gate + learned ranker | 0.8291667 |
| Learned gate + oracle selector | 0.8250000 |

The full oracle could choose the correct action on 1,050 of 1,200 examples. The learned system reached 841 of 1,200.

## Interpretation

- Candidate capacity exists: the three actions collectively reach 87.50%.
- The deployed learned controller did not retrieve that capacity reliably.
- The remaining problem is not simply catastrophic forgetting; it includes gate calibration, action ranking, damage avoidance, and composition.
- The 87.50% value is not a system result because it uses unavailable oracle knowledge.

## Closed conclusion

The nonlinear Phase-2 verifier improved the baseline, but did not satisfy the utility and replay gates. The research track therefore moves to a cleaner matched continual-learning comparison and a redesigned controller rather than claiming the oracle score.
