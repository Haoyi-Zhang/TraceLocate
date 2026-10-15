#!/usr/bin/env python3
"""Public single-command entry point for the supported reproduction chain."""
import sys

sys.dont_write_bytecode = True
from _reproduce_core import main

if __name__ == "__main__":
    main()
