from pathlib import Path
import json,csv,math
import numpy as np
root=Path(__file__).resolve().parents[1]
raw=root/'evidence/stage14/raw'
rows=[]; drifts=[]; discrepancies=[]
for unit in sorted(raw.glob('CIFAR10_*')):
 seed=int(unit.name.split('_')[1]); saved=json.loads((unit/'RESULT.json').read_text()); st=json.loads((unit/'STABILITY14.json').read_text());assert st['passes']
 for path in (0,1):
  def effect(branch,h):
   a=np.load(unit/f'path{path}/branch_{branch}_plus.npz')[f'h{h}'].astype(float);b=np.load(unit/f'path{path}/branch_{branch}_minus.npz')[f'h{h}'].astype(float)
   d=(a-b)/2;return d-d.mean(axis=1,keepdims=True)
  for h in (1,4,16,64):
   full=effect('full',h)
   for fit in (1,16):
    for rank in (16,64):
     projected=effect(f'h{fit}_n256_r{rank}',h);nf=np.linalg.norm(full);np_=np.linalg.norm(projected)
     e=float(np.linalg.norm(full-projected)/nf);rho=float(np_/nf);cosine=float(np.sum(full*projected)/(nf*np_))
     assert abs(e*e-(1+rho*rho-2*rho*cosine))<1e-12
     discrepancies.append(abs(e-saved['paths'][str(path)]['comparisons'][f'h{fit}_n256_r{rank}@{h}']['projection_error']))
     rows.append(dict(seed=seed,path=path,horizon=h,fit_horizon=fit,rank=rank,error=e,norm_ratio=rho,cosine=cosine))
  for x in st['paths'][str(path)]:drifts.append(dict(seed=seed,path=path,horizon=x['horizon'],accuracy_change_pp=100*(x['accuracy']-st['cut']['accuracy']),nll_change=x['nll']-st['cut']['nll']))
assert max(discrepancies)<1e-4
for name,data in [('responses',rows),('stability',drifts)]:
 with (root/f'evidence/stage14/{name}.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
def values(path,h,fit,rank=16):return [x['error'] for x in rows if (x['path'],x['horizon'],x['fit_horizon'],x['rank'])==(path,h,fit,rank)]
gains=[np.array(values(p,16,1))-values(p,16,16) for p in (0,1)];inter=gains[0]-gains[1];positive=int(sum(inter>0));p=sum(math.comb(8,k) for k in range(positive,9))/256
summary={'histories':8,'maximum_saved_error_discrepancy':max(discrepancies),'H16':{str(path):{'immediate_mean_error':float(np.mean(values(path,16,1))),'matched_mean_error':float(np.mean(values(path,16,16))),'mean_matching_gain':float(np.mean(gains[path])),'positive_gains':int(sum(gains[path]>0))} for path in (0,1)},'interaction_mean':float(np.mean(inter)),'interaction_positive':positive,'interaction_one_sided_p':p,'registered_alpha':.025,'primary_pass':p<=.025,'H64_matched_mean_error':{str(p):float(np.mean(values(p,64,16))) for p in (0,1)},'H64_accuracy_change_range_pp':[min(x['accuracy_change_pp'] for x in drifts if x['horizon']==64),max(x['accuracy_change_pp'] for x in drifts if x['horizon']==64)]}
(root/'evidence/stage14/RECOMPUTED.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams['pdf.fonttype']=42
fig,axes=plt.subplots(1,2,figsize=(7,2.5),sharey=True)
for path,ax in enumerate(axes):
 for a,b in zip(values(path,16,1),values(path,16,16)):ax.plot([0,1],[a,b],'-o',alpha=.6,lw=.8,ms=3)
 ax.axhline(1,color='gray',ls=':');ax.set_xticks([0,1],['Immediate','H16 matched']);ax.set_title(['Fitted future','Alternate future'][path]);ax.set_ylabel('H16 relative error' if path==0 else '');ax.spines[['top','right']].set_visible(False)
fig.tight_layout()
for extension in ('png','pdf'):
 fig.savefig(root/f'figures/06_stage14_stable_cifar10.{extension}',dpi=240)

# Descriptive geometry across independent histories; no new primary test.
geometry={}
for path in (0,1):
 for rank in (16,64):
  for h in (16,64):
   selected=[x for x in rows if (x['path'],x['horizon'],x['fit_horizon'],x['rank'])==(path,h,16,rank)]
   geometry[f'path{path}_rank{rank}_H{h}']={k:float(np.mean([x[k] for x in selected])) for k in ('error','norm_ratio','cosine')}
(root/'evidence/stage14/GEOMETRY.json').write_text(json.dumps(geometry,indent=2))
fig,axes=plt.subplots(1,2,figsize=(7,3.0))
for rank,color in ((16,'#007b83'),(64,'#76509e')):
 for path,style in ((0,'-'),(1,'--')):
  for ax,metric in zip(axes,('cosine','norm_ratio')):
   means=[geometry[f'path{path}_rank{rank}_H{h}'][metric] for h in (16,64)]
   ax.plot([16,64],means,style+'o',color=color,label=f'rank {rank}, '+('fitted' if path==0 else 'alternate'),lw=1.5,ms=4)
   for unit in range(8):
    data=[x for x in rows if (x['path'],x['fit_horizon'],x['rank'],x['seed'])==(path,16,rank,14000+unit) and x['horizon'] in (16,64)]
    ax.plot([x['horizon'] for x in data],[x[metric] for x in data],style,color=color,alpha=.22,lw=.7)
for ax,title in zip(axes,('Alignment with full effect','Projected / full response norm')):
 ax.set_title(title);ax.set_xticks([16,64],['H16','H64']);ax.spines[['top','right']].set_visible(False);ax.set_ylim(0,1.6 if ax is axes[1] else 1)
axes[1].axhline(1,color='gray',ls=':',lw=.8)
handles,labels=axes[0].get_legend_handles_labels()
fig.legend(handles,labels,fontsize=9,loc='lower center',bbox_to_anchor=(.5,0),ncol=4,frameon=False)
fig.tight_layout(rect=(0,.12,1,1))
for extension in ('png','pdf'):
 fig.savefig(root/f'figures/07_stage14_alignment_and_norm.{extension}',dpi=240)
