# Isaac Lab flagship specification

## Objective

Show the same Akili lifecycle outside text: a robot receives a corrected or superseded procedure, retains the active version across interruptions, and executes it with an auditable contract.

## Flagship scenario: Warehouse Apprentice

1. Robot follows an initial placement procedure.
2. Operator corrects a rule after an observed failure.
3. Akili stores the verified procedure in the robot/task scope.
4. Robot performs an unrelated task.
5. Robot returns and restores the active procedure.
6. A safety or placement rule is superseded.
7. Robot applies the new rule and suppresses the old one.
8. The interface shows provenance, active version and audit chain.

## Reuse from proven work

- scoped lifecycle and zero cross-scope retrieval;
- active/superseded state;
- verified executable contract transport;
- semantic/safety verifier;
- rollback-ready audit trail;
- bounded memory.

## Boundary

The first Isaac demonstration is a procedural-memory and governance demonstration, not a claim of robotics policy-learning SOTA.
