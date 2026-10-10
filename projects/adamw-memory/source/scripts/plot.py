"""Paper figure exports; every point is an independently trained seed."""
from pathlib import Path
import argparse,csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
p=argparse.ArgumentParser();p.add_argument('--data',type=Path,default=Path(__file__).parent/'package');p.add_argument('--out',type=Path);a=p.parse_args();out=a.out or a.data/'figures';out.mkdir(parents=True,exist_ok=True)
def read(n):return list(csv.DictReader(open(a.data/n)))
rows=read('response_by_seed.csv');caps=read('operator_capture_by_seed.csv');drift=read('baseline_training_drift.csv')
NAVY='#203249';TEAL='#087e8b';PURPLE='#755391';GRAY='#7b8794';ORANGE='#d87626'
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':10.5,'axes.labelsize':10,'axes.spines.top':False,'axes.spines.right':False,'axes.edgecolor':'#a6afb9','text.color':NAVY,'axes.labelcolor':NAVY,'xtick.color':NAVY,'ytick.color':NAVY,'pdf.fonttype':42,'svg.fonttype':'none','savefig.facecolor':'white'})
def select(items,**kw):return [r for r in items if all(str(r[k])==str(v) for k,v in kw.items())]
def save(fig,name):
 for ext in ('png','pdf','svg'):fig.savefig(out/f'{name}.{ext}',dpi=240,bbox_inches='tight')
 plt.close(fig)
def grid(ax):ax.grid(axis='y',color='#e9edf1',lw=.65);ax.set_axisbelow(True)
fig,axs=plt.subplots(2,2,figsize=(7.7,5.5),sharey=True)
for i,ds in enumerate(('CIFAR10','CIFAR100')):
 for j,path in enumerate((0,1)):
  ax=axs[i,j];rr=select(rows,stage=13,dataset=ds,path=path,rank=16,fit_n=256,horizon=16)
  for seed in sorted(set(x['seed'] for x in rr)):
   q=select(rr,seed=seed);ys=[float(select(q,fit_horizon=H)[0]['error']) for H in (1,16)];ax.plot([0,1],ys,color=GRAY,alpha=.65,lw=.85);ax.scatter([0,1],ys,c=[PURPLE,TEAL],s=24,zorder=3)
  means=[np.mean([float(x['error']) for x in select(rr,fit_horizon=H)]) for H in (1,16)];ax.scatter([0,1],means,c=[PURPLE,TEAL],s=75,marker='D',edgecolor='white',lw=.8,zorder=4)
  ax.axhline(1,color=GRAY,ls=':',lw=1);ax.set_xticks([0,1],['Immediate basis','H16-matched basis']);ax.set_xlim(-.3,1.3);ax.set_title(f'{ds} · '+('fitted future' if path==0 else 'alternate future'));grid(ax)
  if j==0:ax.set_ylabel('Relative response error at H16')
  ax.text(.98,.94,f'Means: {means[0]:.3f} → {means[1]:.3f}',transform=ax.transAxes,ha='right',va='top',fontsize=9.5,bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
fig.suptitle('Fresh-history matching: fitted and alternate futures',fontsize=11,y=1.01)

fig.tight_layout();save(fig,'01_stage13_paired_fidelity')

fig,axs=plt.subplots(2,3,figsize=(7.5,5.1),sharex=True,sharey=True)
cohorts=[(12,'CIFAR10',64,'Small ConvGN · CIFAR10'),(13,'CIFAR10',256,'ResNet-GN · CIFAR10'),(13,'CIFAR100',256,'ResNet-GN · CIFAR100')]
for j,(stage,ds,n,title) in enumerate(cohorts):
 for i,path in enumerate((0,1)):
  ax=axs[i,j]
  for Hfit,color,label in [(1,PURPLE,'Immediate'),(16,TEAL,'H16 matched')]:
   rr=select(rows,stage=stage,dataset=ds,path=path,rank=16,fit_n=n,fit_horizon=Hfit);ys=np.array([[float(x['error']) for x in sorted(select(rr,horizon=H),key=lambda x:int(x['seed']))] for H in (1,4,16,64)])
   ax.plot(range(4),ys.mean(1),'o-',color=color,lw=1.4,ms=4,label=label);ax.fill_between(range(4),ys.min(1),ys.max(1),color=color,alpha=.12,lw=0)
  ax.axhline(1,color=GRAY,ls=':',lw=.9);ax.set_xticks(range(4),['1','4','16','64']);ax.set_ylim(0,1.7);grid(ax)
  if i==0:ax.set_title(title,fontsize=10)
  if i==1:ax.set_xlabel('Future optimizer updates')
  if j==0:ax.set_ylabel(('Fitted future' if path==0 else 'Alternate future')+'\nrelative response error')
handles,labels=axs[0,0].get_legend_handles_labels()
fig.legend(handles,labels,frameon=False,fontsize=9.5,loc='upper center',bbox_to_anchor=(.5,1.01),ncol=2)
fig.tight_layout(rect=(0,0,1,.93))

save(fig,'02_horizon_fidelity_and_transfer')

fig,axs=plt.subplots(1,2,figsize=(7.5,3.6),sharey=True)
for j,ds in enumerate(('CIFAR10','CIFAR100')):
 ax=axs[j]
 for k,(n,Hfit,color,alpha) in enumerate([(64,1,PURPLE,.5),(256,1,PURPLE,1),(64,16,TEAL,.5),(256,16,TEAL,1)]):
  for path in (0,1):
   rr=select(caps,stage=13,dataset=ds,path=path,rank=16,fit_n=n,fit_horizon=Hfit,evaluation_horizon=16);v=np.array([float(r['capture'])*100 for r in rr]);x=path+(k-1.5)*.18
   ax.bar(x,v.mean(),width=.16,color=color,alpha=alpha,zorder=2);ax.scatter(x+np.linspace(-.045,.045,len(v)),v,s=12,facecolor='white',edgecolor=color,lw=.7,zorder=3)
 ax.set_xticks([0,1],['Fitted future','Alternate future']);ax.set_title(ds);grid(ax)
axs[0].set_ylabel('Independent H16 energy capture (%)');fig.legend(handles=[Line2D([0],[0],lw=6,color=c,alpha=al,label=f'{"Immediate" if H==1 else "H16 matched"}, fit{n}') for n,H,c,al in [(64,1,PURPLE,.5),(256,1,PURPLE,1),(64,16,TEAL,.5),(256,16,TEAL,1)]],loc='lower center',bbox_to_anchor=(.5,-.12),ncol=2,frameon=False,fontsize=9.5);fig.tight_layout()

save(fig,'03_independent_operator_capture')

fig,axs=plt.subplots(1,2,figsize=(7.3,3.6),sharey=True)
for j,ds in enumerate(('CIFAR10','CIFAR100')):
 ax=axs[j]
 for path,color,label in [(0,TEAL,'Fitted future'),(1,ORANGE,'Alternate future')]:
  vals=[]
  for seed in (13000,13001,13002,13003):
   rr=select(rows,stage=13,dataset=ds,path=path,seed=seed,rank=16,fit_horizon=16,horizon=16);vals.append(float(select(rr,fit_n=64)[0]['error'])-float(select(rr,fit_n=256)[0]['error']))
  x=np.arange(4)+(path-.5)*.12;ax.plot(x,vals,'o-',color=color,ms=4,lw=.85,label=label)
 ax.axhline(0,color=GRAY,ls=':',lw=1);ax.set_xticks(range(4),['13000','13001','13002','13003']);ax.set_xlabel('Training seed');ax.set_title(ds);grid(ax)
axs[0].set_ylabel('Error reduction: fit 64 → fit 256');axs[0].legend(frameon=False,fontsize=9.5);fig.tight_layout();save(fig,'04_fitting_bank_growth')

fig,axs=plt.subplots(1,2,figsize=(7.3,3.8),sharey=True)
for j,ds in enumerate(('CIFAR10','CIFAR100')):
 ax=axs[j]
 for seed in (13000,13001,13002,13003):
  rr=select(drift,dataset=ds,seed=seed);cut=float(rr[0]['cut_accuracy'])*100;ax.scatter(0,cut,s=18,color=NAVY,zorder=3)
  for path,color,off in [(0,TEAL,-.04),(1,ORANGE,.04)]:
   end=float(select(rr,path=path)[0]['endpoint_accuracy'])*100;ax.plot([0,1+off],[cut,end],color=color,lw=.7,alpha=.55);ax.scatter(1+off,end,s=18,color=color,zorder=3)
 ax.set_xticks([0,1],['Cut (8,000 updates)','After 64 future updates']);ax.set_title(ds);ax.set_xlim(-.2,1.25);grid(ax)
axs[0].set_ylabel('Unperturbed baseline test accuracy (%)');fig.legend(handles=[Line2D([0],[0],marker='o',color=c,label=l,lw=.8,ms=4) for c,l in [(NAVY,'Cut'),(TEAL,'Fitted future'),(ORANGE,'Alternate future')]],loc='lower center',bbox_to_anchor=(.5,-.1),ncol=3,frameon=False,fontsize=9.5);fig.tight_layout();save(fig,'05_baseline_continuation_drift')
print('Exported five figures in PNG, PDF and SVG')
