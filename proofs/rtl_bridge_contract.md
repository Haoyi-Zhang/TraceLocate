# Public-RTL capture-to-language bridge contract

This note states what is proved by the retained UART simulation bridge and what is not. It is an evidence-chain argument over pinned files and deterministic transformations, not an RTL-equivalence proof, a gate-level timing claim, or a physical-fault validation.

## 1. Source identity

Let `U_tx`, `U_rx`, and `U_lic` be the retained byte strings. The checker recomputes their Git blob identifiers and byte counts and requires exact equality with the pinned `ben-marshall/uart` commit metadata. Therefore the experiment's upstream inputs are uniquely bound to those three retained files. This does not establish that the upstream design is correct for every UART use.

## 2. Compatibility transformation

For each RTL module the transformation removes the first four existing parameter declarations and inserts textually identical values in the ANSI module parameter list. The checker derives the expected transformed text directly from the pinned source and requires byte-for-byte equality. Hence the retained generated files differ from the pinned source only by that declaration-order rewrite. This is stronger than trusting a prose assertion, but it is not a general semantic equivalence checker.

## 3. Simulation and capture semantics

For each known payload and declared variant, the testbench runs one deterministic loopback execution. A nonnominal variant forces one target for one sampled rising edge. The harness records 48 rows after a fixed delta/time settle and rejects any X/Z coordinate. The manifest requires zero firings for nominal and exactly one firing otherwise. These checks establish the declared simulation intervention and capture schedule. They do not map that intervention to transistor-level behavior, metastability, analog line noise, or a population of manufactured defects.

## 4. Retained-trace integrity

Each manifest entry binds a CSV path to a SHA-256 digest, byte count, fault parameters, firing count, unknown-row count, and final receiver summary. The importer and independent checker both recompute the digest, parse all cycles, require binary coordinates, and recompute each 12-bit packed row. Therefore no retained row can change without invalidating the bridge evidence.

## 5. Trace-to-table exactness

For context `c`, variant `v`, and captured cycle `q`, the imported table edge emits exactly the packed row in the retained CSV and advances to `min(q+1,47)`. The independent checker evaluates this equality for all

`3 contexts x 11 variants x 48 cycles = 1,584`

cells. Context stimulus words repeat the corresponding context index for the full chain. Consequently the finite model used by the certificate engine is an exact deterministic encoding of the retained cycle traces. It is not an over-approximation of all RTL executions.

## 6. Campaign binding

The campaign is a fixed set of 28 identifiers: 24 Cartesian core cases over horizons `{16,24,32}`, budgets `{0,1}`, four context scopes, and offset `{0}`, plus four `h=24,d=0` controls with offsets `{0,1}`. The checker rebuilds this set and rejects missing, extra, duplicate, out-of-bound, or renamed cases. Certificate acceptance therefore refers to the complete declared campaign rather than a hidden favorable subset.

## 7. End-to-end accepted statement

Combining the bridge checker with the existing certificate consumer establishes:

> For every word pair reconstructed from the pinned 33 UART simulation traces under a frozen campaign case, the reported feasible interface satisfies the stated silent-complete-row-deletion contract and is minimum weighted cost among the 12 candidate taps; every reported infeasible case has a checked full-interface collision witness at or below the requested budget.

The statement is conditional on the fixed simulation traces and class declaration. It does not imply coverage of unmodeled RTL inputs, initial states, timings, faults, capture offsets, synthesis transformations, routed probes, finite trace-buffer effects beyond the model, or silicon executions.
