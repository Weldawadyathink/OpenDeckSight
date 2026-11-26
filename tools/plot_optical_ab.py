#!/usr/bin/env python3
"""Plot an analyzed optical A/B run without trimming timing outliers."""
import argparse
import json
from pathlib import Path


def plot(report,destination):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    model=report['model'];pairs=[p for p in report['pairs'] if p['phase']>=0]
    variable=[p for p in pairs if p['phase']==1]
    train=[p for p in pairs if p['phase']==0]
    vb=(variable[0]['source_us']/1e6,variable[-1]['source_us']/1e6)
    fig,axes=plt.subplots(3,1,figsize=(11,10))
    fig.subplots_adjust(left=.11,right=.98,bottom=.09,top=.91,hspace=.55)
    xx=[];gpu=[];optical=[]
    for a,b in zip(pairs,pairs[2:]):
        if a['phase']!=b['phase']:continue
        assert a['state']==b['state']
        steps=(b['sequence']-a['sequence'])&0xffffffff
        xx.append(b['source_us']/1e6)
        gpu.append((b['source_us']-a['source_us'])/steps/1000)
        optical.append((b['time_us']-a['time_us'])/model['scale']/steps/1000)
    axes[0].plot(xx,gpu,color='#2466a6',linewidth=.8,label='GPU events')
    axes[0].scatter(xx,optical,s=5,color='#d27827',alpha=.7,label='Optical sensor')
    axes[0].set(title='Frame-period estimates over two same-polarity content changes',
                xlabel='Source time from first flip (s)',ylabel='Period per vblank (ms)')
    axes[0].legend(loc='upper left',fontsize=9)
    axes[1].scatter([p['source_us']/1e6 for p in pairs],
                    [p['source_residual_us'] for p in pairs],s=7,color='#2466a6')
    axes[1].axhline(0,color='black',linewidth=.7)
    axes[1].axvspan(train[0]['source_us']/1e6,train[-1]['source_us']/1e6,color='#3579b5',alpha=.12,label='Clock/bias fit: first fixed phase only')
    axes[1].set(title='Optical transition minus GPU-based prediction; every matched edge retained',
                xlabel='Source time from first flip (s)',ylabel='Timing residual (us)')
    axes[1].legend(loc='upper left',fontsize=9)
    for ax in axes[:2]:
        ax.axvspan(*vb,color='#bd6a35',alpha=.1)
        ax.text(sum(vb)/2,.94,'VRR-requested frames' if report['mode']=='experiment' else 'Middle fixed phase',
                ha='center',va='top',transform=ax.get_xaxis_transform(),fontsize=9)
    times=[p['source_us']/1e6 for p in variable]
    axes[2].scatter(times,[p['fixed_native_grid_residual_us']/1000 for p in variable],
                    s=7,color='#8c6a9e',label='Distance to original 60 Hz grid')
    axes[2].scatter(times,[p['source_residual_us']/1000 for p in variable],
                    s=7,color='#2466a6',label='Residual against GPU timing')
    axes[2].set(title='Middle phase: fixed-clock countermodel versus source-following prediction',
                xlabel='Source time from first flip (s)',ylabel='Timing residual (ms)')
    axes[2].legend(loc='lower left',fontsize=9)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('DeckSight optical VRR comparison — one sensor, narrow 59–60 Hz window',fontsize=14,y=.975)
    fig.text(.11,.025,'50 s continuous capture at nominal 100 ksample/s. No whole-screen visual assessment or wider-range conclusion.',fontsize=9)
    fig.savefig(destination,dpi=160);plt.close(fig)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('analysis',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();plot(json.loads(a.analysis.read_text()),a.output)


if __name__=='__main__':main()
