# Split CIFAR-100 findings

Akili's frozen-expert work established a meaningful gap between task-free retrieval and available expert capacity:

- three-seed semantic baseline: **62.55%**;
- true-task oracle: **79.38%**;
- union of any available expert: **87.18%**;
- top-3 union ceiling: **80.22%**.

This means the bank contains substantially more correct knowledge than the task-free controller can safely retrieve.

A later nonlinear development audit improved 66.42% to 70.08% on 1,200 examples, but caused 23 damages across 142 interventions and failed the replay gate. The official test remained inaccessible. The correct conclusion is not an 87% Akili result: **87% is a capacity ceiling, and retrieval/arbitration remains the bottleneck.**

The next matched study is ER/DER++/ER-ACE alone versus the same learning engines governed by Akili admission and lifecycle controls.
