# Environment

The artifact uses Python 3.13.5 and the Python standard library for the retained finite experiments. The tested optional RTL replay used `Icarus Verilog version 13.0 (stable) (v13_0)`. A compatible `iverilog` executable and its adjacent `vvp` runtime may be supplied through `--iverilog`; simulator binaries are not redistributed.

All randomized validation uses explicit fixed seeds, and the default replay uses one controlling Python process. Measured runtimes and memory are machine-specific diagnostics, not scientific invariants.
