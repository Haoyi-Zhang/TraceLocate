# Reproducibility Artifact

This standalone directory contains the computational evidence for 432 finite-model tasks and 28 tasks imported from one pinned public UART simulation bridge.

## Full one-command reproduction

A full replay runs on Linux and requires an Icarus Verilog executable with a
sibling `vvp`. Reference runs use Python 3.13.5; the Python code uses the standard
library, with no Python package installation. Run the commands from this artifact
directory. The output must be a new descendant of its `reproductions/` directory;
existing paths are refused and never deleted. The entry point and its children
disable bytecode writes so retained source directories stay free of cache files.

```bash
python -B reproduce.py \
  --iverilog /path/to/iverilog \
  --out reproductions/full-run
```

The command, in order:

1. tests output-path safety in disposable temporary fixtures;
2. regenerates and independently checks all 432 finite-model cases;
3. validates the retained UART source/trace/model bridge;
4. recompiles the pinned UART RTL in an isolated temporary copy and requires byte-identical traces, model, and 28-case campaign;
5. regenerates and independently checks all 28 UART cases;
6. runs the ten directed bridge mutations and the mask/fault regressions;
7. reruns the exact finite oracles, 24 certificate mutations, alias check, and bounded microbenchmarks; and
8. writes `summary.json` only after every prior stage succeeds.

For environments without a simulator, an explicitly weaker mode checks the retained UART traces and all downstream evidence but does not claim source-level re-simulation:

```bash
python -B reproduce.py \
  --retained-only \
  --out reproductions/retained-run
```

## Supported evidence

Current minimum-loss preparation discovers pair lengths with two scalar DP rows,
keeps the original first-maximum tie rule, then builds one unchanged full grid
for the winning alignment. Below-margin coverage and the independent consumer
are unchanged. This reduces full-grid construction, not the O(P h²) discovery
time bound or the O(h²) witness workspace. The bit-parallel exhaustive baseline
is unchanged. Frozen local-checking/producer measurements remain tied to their
original sources; no new timing or end-to-end gain is claimed.

The portable row, bibliography, and replay-diagnostic regressions require only
included current sources and the standard library:

```sh
python -B -m unittest discover -s tests -p test_minimum_loss_rows.py -v
python -B -m unittest discover -s tests -p test_bibliography.py -v
python -B -m unittest discover -s tests -p test_uart_replay_diagnostics.py -v
python -B -m unittest discover -s tests -p test_entrypoints.py -v
```

Scientific CI runs this as a required separate step. It does not replace the
460-case campaigns, 24 certificate controls, ten bridge controls or RTL replay.

`src/scientific_checks.py --out /absolute/new/output` runs the finite campaigns,
independent oracles, and passive retained-UART checks without a simulator. Its
output must be new and outside this artifact directory. The accompanying
`scientific-checks.yml` workflow retains this finite/retained-data job and adds
an independent full source-replay job. Both run from this flat artifact repository
on Ubuntu 24.04 and upload raw attempts after success or failure. The native job
builds the official Icarus 13.0 release at its fixed source commit, checks that
tracked tool inputs remain unchanged, and runs the complete reproduction on one
CPU with bounded time and memory. Exact comparisons include the tool provenance;
a mismatch retains the rebuilt inputs before failing.

`results/source-replay/` contains the original summary, environment, and execution
record from the completed native replay. It regenerated 33 UART traces and matched
41 bridge files and all 460 finite/UART certificates byte for byte. The ten bridge
mutations and 24 certificate mutations were rejected; the complete workflow took
79.219 seconds. Its bounded microbenchmark outputs are reproduction data, separate
from the historical measurements used in the paper's performance plots.

- `models/campaign.json` and six finite models: 432 cases, 85 feasible, 347 infeasible, and 327 zero-loss full-interface aliases.
- `models/rtl-campaign.json`: exactly 28 UART cases, 12 feasible, 16 infeasible, and 8 zero-loss aliases.
- `rtl/ben-marshall-uart/`: pinned MIT-licensed TX/RX source, declaration-only compatibility rewrite, deterministic testbench, 33 raw traces, 1,584 rows, manifest, and importer.
- `results/campaign/` and `results/rtl-campaign/`: one case record and one certificate per declared case.
- `src/check_certificate.py`: independent finite-model certificate consumer.
- `src/check_rtl_bridge.py`: independent source-to-language bridge checker, including the complete ordered mapping from 12 packed bits to CSV columns, RTL expressions, tap names, kinds, and costs.
- `tests/test_rtl_bridge.py`: ten directed bridge corruptions, including renamed/exchanged campaign identifiers, equal-cost `tx_busy`/`rxd` name exchange and a derived-fault cycle change with unchanged traces and hashes.
- `tests/test_uart_regressions.py`: verifies that mask 2176 is `{rxd, rx_sample}` and that mask 2050 is `{tx_busy, rx_sample}` and retains full-length cross-class aliases for `payload-5`, `h=24`, `d=0`.
- `tests/test_contract.py`: exact weighted oracles and 24 semantically invalid certificate packets, including four same-length multi-pair reorder/duplicate-replacement mutations.

## UART timebase

The testbench has ``timescale 1ns/1ps`` and toggles `clk` every 5 ns, so absolute simulated time corresponds to 100 MHz. Its RTL parameters `CLK_HZ=4_000_000` and `BIT_RATE=1_000_000` set cycle ratios inside the design. The experiment is interpreted only in sampled-cycle coordinates; it is not a measured 4 MHz clock or 1 MHz physical line-rate implementation.

## Boundaries

All guarantees concern finite, equal-length, synchronously sampled row languages with independent deletion of at most the declared number of complete rows. The artifact does not establish synthesis, routed probes, trace-buffer implementation, area, power, timing, FPGA or silicon behavior, electrical faults, or a defect-population distribution.
