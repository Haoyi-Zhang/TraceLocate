#!/usr/bin/env python3
# CORE_REPRODUCER_WRAPPER
"""Single entry point for the production replay and independent finite oracle."""
from __future__ import annotations
import subprocess,sys
from pathlib import Path

def value_after(flag, default):
    try:return sys.argv[sys.argv.index(flag)+1]
    except (ValueError,IndexError):return default

def main():
    root=Path(__file__).resolve().parent
    core_args=list(sys.argv[1:])
    help_cp=subprocess.run([sys.executable,str(root/'_reproduce_core.py'),'--help'],cwd=root,text=True,capture_output=True)
    if '--iverilog' not in (help_cp.stdout+help_cp.stderr) and '--iverilog' in core_args:
        k=core_args.index('--iverilog');del core_args[k:k+2]
    subprocess.run([sys.executable,str(root/'_reproduce_core.py'),*core_args],cwd=root,check=True)
    out=Path(value_after('--out','results/reproduction'))
    if not out.is_absolute():out=root/out
    subprocess.run([sys.executable,str(root/'src/independent_math_validation.py'),'--out',str(out/'independent_math_validation.json')],cwd=root,check=True)
    iv=value_after('--iverilog','')
    bridge=root/'rtl/picorv32'
    if iv:
        bout=out/'picorv32/results'; braw=out/'picorv32/raw'
        subprocess.run([sys.executable,str(bridge/'run_bridge.py'),'--iverilog',iv,'--out',str(bout),'--raw-out',str(braw)],cwd=root,check=True)
        subprocess.run([sys.executable,str(bridge/'check_bridge.py'),'--root',str(bridge),'--results',str(bout),'--raw',str(braw)],cwd=root,check=True)
        subprocess.run([sys.executable,str(bridge/'compare_bridge.py'),'--reference',str(bridge/'results'),'--candidate',str(bout),'--reference-raw',str(bridge/'raw'),'--candidate-raw',str(braw)],cwd=root,check=True)
    else:
        subprocess.run([sys.executable,str(bridge/'check_bridge.py'),'--root',str(bridge)],cwd=root,check=True)
    subprocess.run([sys.executable,str(bridge/'mutation_test.py')],cwd=bridge,check=True)
    # Bibliographic checks run in the full paper package but are skipped by the
    # standalone code archive, where no manuscript is present.
    if (root.parent/'paper/references.bib').exists():
        subprocess.run([sys.executable,str(root/'src/verify_bibliography.py'),'--paper',str(root.parent/'paper'),'--out',str(out/'literature_audit')],cwd=root,check=True)
if __name__=='__main__':main()
