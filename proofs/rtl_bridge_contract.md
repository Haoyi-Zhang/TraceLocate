# Public-UART capture-to-language bridge contract

This note states what is established by the retained UART simulation bridge. It is an evidence-chain argument over pinned files and deterministic transformations, not an RTL-equivalence theorem, gate-level timing result, or physical-fault validation.

## 1. Source and compatibility rewrite

The checker recomputes the byte counts and Git blob identifiers of the retained `uart_tx.v`, `uart_rx.v`, and MIT license at commit `5fd2db850a41b65aa34f3a31c663fc8704c7abd8`. It independently reconstructs the Icarus-compatible copies by moving the four existing parameter declarations into each ANSI module parameter list and requires byte equality. No logic expression, state transition, assignment, or port is permitted to change.

## 2. Ordered observation binding

For every tap index 0--11, the bridge checker fixes one six-field record: packed bit number, CSV column, testbench RTL expression, model tap name, tap kind, and cost. It parses both the packed `row` concatenation and the CSV `$fdisplay` argument order from `trace_tb.sv`, reverses the concatenation into least-significant-bit order, and requires both to equal the fixed binding list. The imported model's ordered tap records must then match the name/kind/cost projection of that list exactly. Exchanging the equal-cost names `tx_busy` and `rxd` is therefore rejected even when every trace byte and numerical cost remains unchanged.

## 3. Simulation schedule and timebase

Each nonnominal run forces one declared target for exactly one sampled rising edge. `tx_data_early/late` are fixed at cycles 10/17; `rx_sample_early/late` at cycles 12/17. Their values are recomputed as the inverse of the nominal trace coordinate at that exact cycle and must equal both the trace entry and `resolved_faults`. A mutation that moves only `payload-5/tx_data_early` from cycle 10 to 11, while retaining all traces and hashes, is rejected.

The testbench declares ``timescale 1ns/1ps`` and uses `always #5 clk=~clk`, hence its absolute simulation clock is 100 MHz. `CLK_HZ=4_000_000` and `BIT_RATE=1_000_000` are RTL parameters that set cycle ratios. The evidence is interpreted in sampled-cycle coordinates and is not a measured 4 MHz clock or 1 MHz physical line-rate implementation.

## 4. Retained traces and exact import

For each of three known payloads and 11 variants, the harness retains 48 synchronized binary rows: 33 traces and 1,584 rows in total. Every manifest entry binds the path, SHA-256 digest, byte count, fixed fault parameters, firing count, unknown-row count, and receiver summary. The importer and independent checker both parse cycle order, require binary coordinates, and recompute each 12-bit packed row.

For context `c`, variant `v`, and cycle `q`, the imported deterministic table emits exactly the retained packed row and advances to `min(q+1,47)`. The checker evaluates this equality for all `3 x 11 x 48 = 1,584` cells. The model is therefore an exact encoding of the retained executions, not an over-approximation of all UART behavior.

## 5. Campaign and certificate boundary

The canonical campaign contains exactly 28 identifiers: 24 core cases over horizons `{16,24,32}`, budgets `{0,1}`, four context scopes, and offset `{0}`, plus four `h=24,d=0` controls with offsets `{0,1}`. The checker reconstructs the Cartesian set and rejects missing, extra, duplicate, renamed, or out-of-bound cases.

Combining the bridge checker with the independent certificate consumer establishes the following conditional statement:

> For every word pair reconstructed from the pinned 33 UART simulation traces under a frozen campaign case, a reported feasible interface satisfies the complete-row deletion contract and has checked minimum weighted cost among the 12 declared taps; a reported infeasible case carries a checked full-interface collision at or below the requested budget.

The statement does not cover unmodeled stimuli, states, timings, faults, offsets, synthesis transformations, routed probes, recorder control, electrical effects, or silicon executions.
