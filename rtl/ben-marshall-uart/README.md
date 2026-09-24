# Pinned public-RTL UART bridge

This directory is the auditable bridge from executable public RTL to the finite synchronized-row language used by the certificate engine. It closes a source-to-table validation gap for one simulation setting; it does **not** validate a silicon acquisition path or claim that the injected transients are a complete physical defect model.

## Pinned source and licensing

The unmodified upstream files come from `ben-marshall/uart` at commit
`5fd2db850a41b65aa34f3a31c663fc8704c7abd8`:

| File | Bytes | Git blob |
|---|---:|---|
| `upstream/uart_tx.v` | 5,268 | `89906d6c5059a592dd086bbf60997368375cd1bb` |
| `upstream/uart_rx.v` | 5,718 | `1cb2eadcb544f57864b29d380e893f92fac5f38c` |
| `upstream/LICENSE` | 1,069 | `22b2e46c610d85f568e402c0c556821676d55253` |

`upstream/SOURCE.json` records the source URL, commit, file sizes, and blobs. The files are distributed under their retained MIT license; see `THIRD_PARTY_NOTICES.md` at the repository root.

Icarus Verilog 13 requires a parameter to be declared before it appears in an ANSI port width. `prepare_upstream.py` verifies every pinned blob, then creates `generated/uart_tx.v` and `generated/uart_rx.v` by moving the four existing parameter declarations into each module parameter list. It makes no expression, statement, assignment, state-machine, or port change. `generated/manifest.json` records the resulting digests, and the independent checker reconstructs the expected rewrite from the unmodified source.

## Capture experiment

`trace_tb.sv` instantiates the transmitter and receiver in loopback with:

- four payload bits, 1 MHz line rate, and 4 MHz clock;
- three known payload contexts: `0x5`, `0xA`, and `0x3`;
- 48 captured rising-edge rows per run, sampled after a one-time-unit nonblocking-assignment settle;
- one fixed 12-coordinate tuple per row; tap 0 is the packed row's least-significant bit;
- no timestamp in the imported language; the deletion unit is one entire synchronized row.

The candidate interface is:

| Index | Tap | Cost | Boundary |
|---:|---|---:|---|
| 0 | `txd` | 1 | transmitter output |
| 1 | `tx_busy` | 1 | transmitter output |
| 2-3 | `tx_fsm[0:1]` | 2 each | transmitter internal state |
| 4-5 | `tx_bit_count[0:1]` | 2 each | transmitter internal count |
| 6 | `tx_payload_shift[0]` | 3 | transmitter internal data |
| 7 | `rxd` | 1 | serial interconnect |
| 8 | `rx_valid` | 1 | receiver output |
| 9-10 | `rx_fsm[0:1]` | 2 each | receiver internal state |
| 11 | `rx_sample` | 2 | receiver internal sample |

The six declared classes contain 11 variants: nominal, two serial-line transients, two transmitter-control transients, two transmitter-payload transients, two receiver-control transients, and two receiver-sample transients. Every nonnominal run forces exactly one declared signal value for exactly one sampled rising edge. The payload/sample fault values are chosen as the opposite of the nominal value at the same cycle. These are controlled simulation interventions, not calibrated electrical faults.

`rebuild.py` compiles the pinned RTL, runs all 33 context/variant simulations, rejects X/Z rows or missing/duplicate fault firings, writes the raw CSV traces, and calls `import_traces.py`. The retained source-level regeneration produced all 33 traces and 1,584 rows identically on a second isolated run with Icarus Verilog 13.0.

## Deterministic trace-to-language translation

`import_traces.py` verifies each CSV header, cycle sequence, binary coordinate, packed row, length, and SHA-256 digest. It then creates `models/uart-loopback-rtl.json` as a 48-state deterministic chain for every variant: state `q` emits the retained row for context `c` and advances to `min(q+1,47)`. Thus every one of the 1,584 table cells is a direct copy of one retained trace row.

`src/check_rtl_bridge.py` independently verifies:

1. all three upstream Git blobs;
2. both declaration-only compatibility copies;
3. source commit, contexts, variant membership, and fault declarations;
4. all 33 trace hashes, binary rows, and packed values;
5. all 1,584 trace-to-table cells; and
6. the exact 28-case campaign and horizon bounds.

`tests/test_rtl_bridge.py` accepts the valid fixture and rejects six targeted corruptions: upstream source, compatibility copy, raw trace, fault metadata, imported table cell, and campaign membership.

## Frozen public-RTL campaign

The 24 core cases cross horizons `{16,24,32}`, row-loss budgets `{0,1}`, and context scopes `{payload-5}`, `{payload-A}`, `{payload-3}`, and all three known contexts, with offset set `{0}`. Four controls repeat `h=24,d=0` with offsets `{0,1}`. The matrix was frozen after a bounded timing pilot; it contains every cell in that declaration, not a post-hoc selection of favorable outcomes.

The exact outcome is 12 feasible and 16 infeasible cases. All `h=16` tasks already contain a full-row cross-class alias. At `h=24` and `h=32`, all `d=0` tasks are feasible with optimum weighted costs 3-5, while every `d=1` task is impossible because the full 12-tap interface has minimum ambiguity loss one. The `{0,1}` offset controls at `h=24,d=0` preserve the same optima. The selected taps are either `{rxd, rx_sample}` or that pair plus `tx_fsm[0]`/`tx_busy`, depending on payload and horizon. These are exact results for this declaration, not recommendations for UART instrumentation.

## Commands

Validate retained sources, traces, translation, and campaign:

```sh
python src/check_rtl_bridge.py
python tests/test_rtl_bridge.py
python src/run_campaign.py --instance models/rtl-campaign.json \
  --out results/new-rtl-campaign --seconds 120
python src/summarize.py --instance models/rtl-campaign.json \
  --results results/new-rtl-campaign --out results/new-rtl-summary
```

Regenerate from RTL when an Icarus Verilog 13 executable and adjacent `vvp` are available:

```sh
python rtl/ben-marshall-uart/rebuild.py --iverilog /path/to/iverilog
```

Or include source-level regeneration in the complete clean replay:

```sh
python reproduce.py --out results/reproduction --iverilog /path/to/iverilog
```

The default `reproduce.py` does not require or download a simulator. It verifies and reimports the retained raw traces exactly.
