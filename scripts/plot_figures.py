"""Render retained counts and timing medians directly, without TeX or new runs."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter

ROOT=Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0,str(ROOT))
from src.figure_data import data

def render(out):
    counts,timing=data()
    plt.rcParams.update({'font.family':'STIXGeneral','mathtext.fontset':'stix',
        'font.size':8.5,'pdf.fonttype':42,'ps.fonttype':42,'text.usetex':False,
        'axes.labelsize':8.5,'xtick.labelsize':8.5,'ytick.labelsize':8.5,'axes.linewidth':.55})
    meta={'Creator':'Python Matplotlib','Producer':None,'CreationDate':None,'ModDate':None}
    fig=plt.figure(figsize=(3.5,5.2/2.54));ax=fig.add_axes([.14,.23,.83,.72])
    for loss,style,marker in [(0,'-','s'),(1,'--','^'),(2,':','o')]:
        ax.plot([r[0] for r in counts],[r[loss+1] for r in counts],
                color='black',linestyle=style,marker=marker,markersize=4,
                linewidth=.7,label=f'$d={loss}$')
    ax.set(xlim=(3.5,12.5),ylim=(0,16),xlabel='Capture horizon $h$ (rows)',ylabel='Feasible cases out of 48')
    ax.set_xticks([4,8,12]);ax.set_yticks([0,4,8,12,16]);ax.grid(color='.85',linewidth=.45)
    ax.tick_params(length=3,width=.55)
    ax.legend(loc='upper center',ncol=3,frameon=False,fontsize=8,handlelength=1.4,columnspacing=.9,borderaxespad=.25)
    fig.savefig(out/'coverage.pdf',metadata=meta);plt.close(fig)
    fig=plt.figure(figsize=(3.5,5.6/2.54));ax=fig.add_axes([.19,.23,.78,.72])
    for field,label,style,marker in [
        ('lcs_median_us','Full LCS grid',':','^'),
        ('frontier_median_us','Furthest frontier','--','s'),
        ('checker_median_us','Local certificate','-','o')]:
        ax.plot([int(r['h']) for r in timing],[float(r[field]) for r in timing],
            color='black',linestyle=style,marker=marker,markersize=4,linewidth=.7,label=label)
    ax.set_xscale('log',base=2);ax.set_yscale('log')
    ax.xaxis.set_major_locator(FixedLocator([32,64,128,256,512]))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v,pos:str(int(v))))
    ax.yaxis.set_major_locator(FixedLocator([10,100,1000,10000]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,pos:f'{v:,.0f}'))
    ax.set(xlim=(28,590),ylim=(8,60000),xlabel='Word length $h$ (rows)',ylabel=r'Median CPU time ($\mu$s)')
    ax.grid(which='major',color='.85',linewidth=.45);ax.tick_params(length=3,width=.55)
    ax.legend(loc='upper left',frameon=False,fontsize=8,handlelength=2,borderaxespad=.25,labelspacing=.25)
    fig.savefig(out/'local-checking.pdf',metadata=meta);plt.close(fig)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,default=ROOT/'figures')
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True);render(a.out)
