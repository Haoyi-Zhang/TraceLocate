# Pinned UART simulation bridge

This directory is the only public-RTL bridge included in the supported evidence. It converts one pinned MIT-licensed UART TX/RX implementation into a deterministic finite row language and one canonical 28-case campaign. It is a simulation-to-language validation, not a physical UART, synthesis, routed-probe, electrical-fault, FPGA, or silicon experiment.

## Retained source

The unmodified upstream files are retained under `upstream/` at commit `5fd2db850a41b65aa34f3a31c663fc8704c7abd8`. `upstream/SOURCE.json` records byte sizes, Git blob identifiers, and source locations. The MIT license is retained verbatim. Icarus Verilog 13 needs parameters to be declared before their use in ANSI port widths, so `prepare_upstream.py` makes declaration-order-only compatibility copies under `generated/`; the checker independently reconstructs and compares that rewrite.

## Capture and timebase

`trace_tb.sv` uses ``timescale 1ns/1ps`` and toggles `clk` every 5 ns. The absolute simulation clock is therefore 100 MHz. The instance parameters `CLK_HZ=4_000_000` and `BIT_RATE=1_000_000` determine internal cycle ratios, but the retained experiment is interpreted only in sampled-cycle coordinates. It does **not** claim an implemented 4 MHz clock, an achieved 1 MHz physical line rate, or line-rate fidelity.

Three known payload contexts (`0x5`, `0xA`, `0x3`) and 11 variants yield 33 traces. Each trace contains 48 rising-edge rows sampled after nonblocking-assignment settling. The imported deletion unit is one complete synchronized 12-bit row; no timestamp is included in the finite language.

The checker binds every ordered bit position to all of the following, simultaneously:

| Bit | CSV column | RTL expression | Model tap | Kind | Cost |
|---:|---|---|---|---|---:|
| 0 | `txd` | `uart_txd` | `txd` | port | 1 |
| 1 | `tx_busy` | `uart_tx_busy` | `tx_busy` | port | 1 |
| 2 | `tx_fsm0` | `tx.fsm_state[0]` | `tx_fsm[0]` | internal | 2 |
| 3 | `tx_fsm1` | `tx.fsm_state[1]` | `tx_fsm[1]` | internal | 2 |
| 4 | `tx_bit0` | `tx.bit_counter[0]` | `tx_bit_count[0]` | internal | 2 |
| 5 | `tx_bit1` | `tx.bit_counter[1]` | `tx_bit_count[1]` | internal | 2 |
| 6 | `tx_data0` | `tx.data_to_send[0]` | `tx_payload_shift[0]` | internal | 3 |
| 7 | `rxd` | `uart_rxd` | `rxd` | interconnect | 1 |
| 8 | `rx_valid` | `uart_rx_valid` | `rx_valid` | port | 1 |
| 9 | `rx_fsm0` | `rx.fsm_state[0]` | `rx_fsm[0]` | internal | 2 |
| 10 | `rx_fsm1` | `rx.fsm_state[1]` | `rx_fsm[1]` | internal | 2 |
| 11 | `rx_sample` | `rx.bit_sample` | `rx_sample` | internal | 2 |

## Fixed interventions

Every nonnominal execution forces one declared RTL quantity for one sampled rising edge. The derived nominal-inversion interventions are fixed at:

- `tx_data_early`: cycle 10;
- `tx_data_late`: cycle 17;
- `rx_sample_early`: cycle 12;
- `rx_sample_late`: cycle 17.

For each context, the checker re-derives the forced value as the complement of the nominal column at that exact cycle and compares it with both trace metadata and `resolved_faults`. These are controlled digital simulation interventions, not calibrated physical defects.

## Translation and campaign

`rebuild.py` compiles the pinned source, produces 33 raw CSV traces, rejects X/Z rows and missing or repeated intervention firings, and calls `import_traces.py`. The importer verifies headers, cycles, bits, packed rows, lengths, and trace digests before creating `models/uart-loopback-rtl.json`. Every one of the 1,584 transition-table cells is copied from a retained row.

The only authoritative campaign is `models/rtl-campaign.json`: 24 core tasks from horizons `{16,24,32}`, budgets `{0,1}`, and four context scopes at offset `{0}`, plus four `h=24,d=0` controls with offsets `{0,1}`. It contains exactly 28 cases. The retained outcomes are 12 feasible, 16 infeasible, and 8 zero-loss full-interface aliases.

`src/check_rtl_bridge.py` independently checks source identity, compatibility copies, testbench bit/column/signal ordering, tap name/kind/cost ordering, timing declarations, fixed intervention cycles and values, all trace rows and hashes, all imported cells, and the exact campaign Cartesian product.

`tests/test_rtl_bridge.py` rejects ten directed corruptions, including renamed or exchanged campaign identifiers. Two additional regressions are: (1) exchanging only the equal-cost `tx_busy` and `rxd` model names is rejected, and (2) changing only `payload-5/tx_data_early` from cycle 10 to 11 while retaining all trace bytes and hashes is rejected. `tests/test_uart_regressions.py` additionally proves for the frozen `payload-5,h=24,d=0` task that mask 2176 selects `{rxd, rx_sample}`, whereas mask 2050 selects `{tx_busy, rx_sample}` and leaves full-length cross-class aliases.

## Commands

From the standalone artifact root, validate retained bridge evidence:

```sh
python src/check_rtl_bridge.py --root . --out results/rtl-bridge-check.json
python tests/test_rtl_bridge.py results/rtl-bridge-mutations.json
python tests/test_uart_regressions.py --out results/uart-regressions.json
```

Full source-level reproduction requires Icarus Verilog and a sibling `vvp`, and writes only to a new dedicated directory:

```sh
python reproduce.py --iverilog /path/to/iverilog --out reproductions/full-run
```

The explicitly weaker retained-only mode does not claim RTL recompilation:

```sh
python reproduce.py --retained-only --out reproductions/retained-run
```
