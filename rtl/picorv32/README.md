# Held-Out PicoRV32 Bridge

This bridge is an out-of-sample external-validity check and is not folded into the predeclared primary task count.

`upstream/picorv32.v` is the unmodified ISC-licensed source at commit `ef203c2b0a3fb793280f5114941416c425c5b461`. `tb_picorv32.v` supplies a small RV32I program, a deterministic memory model, and six controlled single-word instruction-memory perturbations. The bridge records 48 synchronous cycles per execution over scalar memory-interface, trace-interface, and internal program-counter candidates.

`run_bridge.py` recompiles all seven executions, retains raw CSV traces, forms the horizon/deletion-budget tasks, solves minimum-cardinality interfaces exactly, and evaluates a deterministic greedy LCS-margin baseline. `check_bridge.py` is independently implemented and re-enumerates every lower-cardinality mask for each feasible case; an infeasible case must collide even under the full candidate interface. `compare_bridge.py` checks regenerated traces and case records against the retained evidence. `mutation_test.py` verifies fail-closed behavior under directed changes to traces, witnesses, costs, class membership, and feasibility status.

The study validates a deterministic processor-source-to-finite-language path. It is not a processor defect-population study, does not modify or synthesize the core, and does not estimate physical trace-network cost.
