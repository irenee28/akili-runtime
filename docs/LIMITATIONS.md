# Limitations

1. Current skill boundaries and version events are mostly declared rather than discovered autonomously.
2. The MuJoCo demonstration uses a small kinematic policy and synthetic tasks; it is not evidence of production manipulation, robustness to real sensors, or sim-to-real transfer.
3. The LLM workflows use generated enterprise-style tasks and small adapters; they are not evidence of broad language-model continual learning.
4. The raw Agent Evolution Drive run has not yet been imported, so that result remains reported rather than immutable publication evidence.
5. A dataset hash proves artifact identity, not that the underlying data was unbiased, lawful, or free from sensitive information.
6. Deleting an adapter removes that isolated capability artifact, but does not prove zero information leakage from the adapter before deletion.
7. No differential privacy or formal unlearning guarantee is currently implemented.
8. CIFAR oracle and candidate-union values require unavailable correctness information or union access and are diagnostic upper bounds, not deployable scores.
9. The v0.23 arbiter selected no rescue model and produced zero official-test gain; safe task-free arbitration remains unresolved.
10. A matched three-seed DER++/ER/ER-ACE comparison and DER++ + Akili ablation are planned but incomplete.
11. External benchmarks and physical edge devices have not yet validated the runtime.
