"""Research analysis for the self-contained CaSR Colab notebook."""
import os
os.environ['MPLBACKEND'] = 'Agg'
import sys, json, math, hashlib, platform, importlib.metadata
from pathlib import Path
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Draw, rdMolAlign
from scipy.stats import spearmanr
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from chemistry import build, tokenize, identity, middle_group

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'results'
REPORT=OUT/'notebook'; REPORT.mkdir(parents=True,exist_ok=True)
SOURCE=ROOT.parent/'toolkit_pilot/results/casr_compounds_for_datawarrior.csv'

def audit():
    data=pd.read_csv(SOURCE)
    rows=[]; excluded=[]
    for rec in data.to_dict('records'):
        try:
            m=build(rec['compound']); smi,formula=identity(m)
        except ValueError as exc:
            excluded.append({'compound':rec['compound'],'hek293_raw':rec['hek293_raw'],'reason':str(exc)}); continue
        # Independent check against earlier standard-residue assembly where available.
        if pd.notna(rec.get('SMILES')):
            old=Chem.MolFromSmiles(rec['SMILES'])
            if old is not None and Chem.MolToSmiles(old,isomericSmiles=True)!=smi:
                raise ValueError('Structure mismatch against input graph: '+rec['compound'])
        _,parts=tokenize(rec['compound']);label,key=middle_group(rec['compound'])
        rows.append({'compound':rec['compound'],'middle_family':label,'middle_group_key':key,
                     'terminal_family':'dipeptide' if len(parts)==2 else parts[-1].replace('D-',''),
                     'hek293_status':rec['hek293_status'],'SMILES':smi,'formula':formula})
    graphs=pd.DataFrame(rows)
    graphs.to_csv(REPORT/'reconstructed_structures.csv',index=False)
    pd.DataFrame(excluded).to_csv(REPORT/'structure_exclusions.csv',index=False)
    prose=pd.read_csv(ROOT.parent/'toolkit_pilot/results/narrative_inactive_annotations.csv')
    prose['SMILES']=[identity(build(n))[0] for n in prose.compound]
    prose['formula']=[identity(build(n))[1] for n in prose.compound]
    prose.to_csv(REPORT/'narrative_inactive_annotations.csv',index=False)
    native=next(m for m in Chem.SDMolSupplier(str(ROOT.parent/'toolkit_pilot/results/native_gamma_EVG.sdf')) if m is not None)
    if identity(Chem.RemoveHs(native))[0]!=identity(build('γ-Glu-Val-Gly'))[0]:
        raise ValueError('Native ligand graph/stereochemistry differs from assembled reference')
    source_audit=json.loads((ROOT.parent/'source_table_audit.json').read_text())
    if source_audit['unmatched']:raise ValueError('Unresolved source table discrepancies')
    coverage=pd.crosstab(graphs.middle_family,graphs.hek293_status)
    coverage.to_csv(REPORT/'assay_coverage_by_family.csv')
    summary={'source_labels':len(data),'reconstructed_structures':len(graphs),
             'source_status_counts':data.hek293_status.value_counts().to_dict(),
             'graph_status_counts':graphs.hek293_status.value_counts().to_dict(),
             'inactive_middle_families':graphs.loc[graphs.hek293_status=='reported_inactive','middle_family'].unique().tolist(),
             'inactive_scope':'The table-only extraction; 18 additional narrative-only inactive labels are supplied separately, with assay system unspecified in the sentence. They are not HEK-293 training labels.',
             'narrative_inactive_annotations':len(prose),
             'publisher_table_rows_checked':source_audit['publisher_rows'],'publisher_table_mismatches':len(source_audit['unmatched']),
             'native_reference_graph_matches':True,
             'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
             'Python':platform.python_version(),
             'packages':{p:importlib.metadata.version(p) for p in ['numpy','pandas','rdkit','scikit-learn','scipy','matplotlib','vina','meeko','gemmi']}}
    (REPORT/'data_audit.json').write_text(json.dumps(summary,indent=2))
    fig,ax=plt.subplots(figsize=(9,5))
    coverage.reindex(columns=['numeric','range','reported_inactive','lower_bound','missing'],fill_value=0).plot.bar(stacked=True,ax=ax)
    ax.set(title='Assay coverage: missing and inactive are different labels',ylabel='Compound labels',xlabel='Middle residue family')
    ax.legend(fontsize=8);fig.tight_layout();fig.savefig(REPORT/'assay_coverage.png',dpi=160);plt.close(fig)
    print(json.dumps(summary,indent=2)); print('Excluded structures are exported with reasons.')

def analyse():
    metrics=pd.read_csv(OUT/'model_metrics.csv')
    oof=pd.read_csv(OUT/'held_out_predictions.csv')
    data=pd.read_csv(OUT/'chemical_activity_dataset.csv')
    main=metrics.query('version=="journal" and split=="leave_middle_family_out"').copy()
    main['geometric_absolute_fold_error']=10**main.MAE_log10
    main.to_csv(REPORT/'main_metrics.csv',index=False)
    # Best observed model is a descriptive comparison, not an independently selected winner.
    best=main.sort_values('MAE_log10').iloc[0].model
    subset=oof.query('version=="journal" and split=="leave_middle_family_out"').copy()
    subset['absolute_error_log10']=abs(subset.observed_pEC50-subset.predicted_pEC50)
    wide=subset.pivot(index=['name','held_out_middle_family'],columns='model',values='absolute_error_log10').reset_index()
    rng=np.random.default_rng(777); families=wide.held_out_middle_family.unique(); samples=[]
    # Resample chemical families, preserving all compounds within each sampled family.
    grouped={f:(g['median']-g[best]).to_numpy() for f,g in wide.groupby('held_out_middle_family')}
    for _ in range(5000):
        drawn=rng.choice(families,len(families),replace=True)
        samples.append(np.concatenate([grouped[f] for f in drawn]).mean())
    bootstrap={'selected_model':best,'mean_error_reduction_log10':float((wide['median']-wide[best]).mean()),
               'percentile_95_interval':np.quantile(samples,[.025,.975]).tolist(),
               'interpretation':'Descriptive cluster bootstrap; winner chosen after comparison; no multiplicity correction.'}
    (REPORT/'bootstrap.json').write_text(json.dumps(bootstrap,indent=2))
    hard=subset[subset.model==best].sort_values('absolute_error_log10',ascending=False)
    # Preserve ranges: report an optimistic distance to the reported interval separately.
    observed=data.set_index('name')
    version_interval=[]
    from benchmark import ALT
    for (version,model),part in oof[oof.split=='leave_middle_family_out'].groupby(['version','model']):
        lo=part.name.map(observed.hek293_low_uM).to_numpy(float)
        hi=part.name.map(observed.hek293_high_uM).to_numpy(float)
        if version!='journal':
            for i,name in enumerate(part.name):
                if name in ALT:lo[i],hi[i]=ALT[name]
        lower=6-np.log10(hi);upper=6-np.log10(lo);pred=part.predicted_pEC50.to_numpy()
        distance=np.maximum(np.maximum(lower-pred,pred-upper),0)
        version_interval.append({'version':version,'model':model,'interval_distance_MAE_log10':distance.mean()})
    pd.DataFrame(version_interval).to_csv(REPORT/'interval_distance_metrics.csv',index=False)
    # Similarity is calculated against each held-out fold's actual training pool.
    from benchmark import features,similarity
    measured=data[data.hek293_status.isin(['numeric','range'])].reset_index(drop=True)
    fps,_=features([build(n) for n in measured.name])
    nearest={}
    for i,row in measured.iterrows():
        train=measured.middle_group_key.to_numpy()!=row.middle_group_key
        nearest[row['name']]=float(similarity(fps[i:i+1],fps[train]).max())
    hard['nearest_training_similarity']=hard.name.map(nearest)
    hard.to_csv(REPORT/'held_family_errors.csv',index=False)
    family_error=hard.groupby('held_out_middle_family').agg(n=('name','size'),MAE_log10=('absolute_error_log10','mean')).sort_values('MAE_log10',ascending=False)
    family_error.to_csv(REPORT/'family_errors.csv')
    fig,ax=plt.subplots(1,3,figsize=(14,4))
    ax[0].bar(main.model,main.geometric_absolute_fold_error,color='#426c99');ax[0].tick_params(axis='x',rotation=35)
    ax[0].set(ylabel='Geometric mean absolute fold error',title='Held-family prediction error')
    ax[1].scatter(hard.observed_pEC50,hard.predicted_pEC50,s=30,alpha=.75)
    lim=[min(hard.observed_pEC50.min(),hard.predicted_pEC50.min())-.2,max(hard.observed_pEC50.max(),hard.predicted_pEC50.max())+.2]
    ax[1].plot(lim,lim,'k--',lw=1);ax[1].set(xlabel='Observed pEC50 (range midpoint)',ylabel='Predicted pEC50',title=best)
    ax[2].scatter(hard.nearest_training_similarity,hard.absolute_error_log10,s=30,alpha=.75)
    ax[2].set(xlabel='Nearest training Tanimoto similarity',ylabel='Absolute error (log10)',title='Similarity is not a calibrated confidence score')
    fig.tight_layout();fig.savefig(REPORT/'prediction_validation.png',dpi=170);plt.close(fig)
    # Matched chemical comparisons, with source assignments kept distinct.
    pairs=pd.read_csv(OUT/'matched_glycine_extension_effects.csv')
    for middle in ['Val']:
        a=observed.loc['γ-Glu-'+middle];b=observed.loc['γ-Glu-'+middle+'-Gly']
        pairs=pd.concat([pairs,pd.DataFrame([{'middle':middle,'dipeptide_EC50_low_uM':a.hek293_low_uM,'dipeptide_EC50_high_uM':a.hek293_high_uM,'glycine_appended_EC50_low_uM':b.hek293_low_uM,'glycine_appended_EC50_high_uM':b.hek293_high_uM,'glycine_potency_gain_low':a.hek293_low_uM/b.hek293_high_uM,'glycine_potency_gain_high':a.hek293_high_uM/b.hek293_low_uM}])],ignore_index=True)
    pairs.to_csv(REPORT/'matched_glycine_effects.csv',index=False)
    fig,ax=plt.subplots(figsize=(8,4))
    for i,r in pairs.iterrows():
        ax.plot([r.glycine_potency_gain_low,r.glycine_potency_gain_high],[i,i],lw=3,color='#267f79')
        ax.scatter(np.sqrt(r.glycine_potency_gain_low*r.glycine_potency_gain_high),i,color='#267f79')
    ax.axvline(1,color='gray',ls='--');ax.set_xscale('log');ax.set_yticks(range(len(pairs)),pairs.middle)
    ax.set(xlabel='EC50(core) / EC50(Gly appended); above 1 = increased potency',title='Tail effects depend on the middle residue')
    fig.tight_layout();fig.savefig(REPORT/'matched_chemical_effects.png',dpi=170);plt.close(fig)
    # Candidate rank sensitivity: these are forecasts, not calibrated uncertainty.
    cp=pd.read_csv(OUT/'candidate_predictions.csv')
    full=cp[~cp.model.str.endswith('_middle_excluded')].copy()
    full['rank']=full.groupby(['version','model']).predicted_pEC50.rank(ascending=False,method='min')
    summary=full.groupby('name').agg(best_rank=('rank','min'),worst_rank=('rank','max'),min_forecast_uM=('implied_EC50_uM','min'),max_forecast_uM=('implied_EC50_uM','max'))
    proposed=pd.read_csv(OUT/'candidate_shortlist.csv').set_index('name')
    summary=summary.join(proposed[['SMILES','nearest_measured_compound','nearest_similarity','middle_excluded_median_pEC50']])
    summary['status']='Unmeasured in extracted series; described ester family; novelty not established'
    summary.to_csv(REPORT/'candidate_rank_sensitivity.csv')
    pd.DataFrame([{'name':n,'formula':identity(build(n))[1],'SMILES':identity(build(n))[0]} for n in ['γ-Glu-Nva-L-Lacticacid','γ-Glu-Val-L-Lacticacid','γ-Glu-Nva','γ-Glu-Nva-Gly']]).to_csv(REPORT/'focused_comparison.csv',index=False)
    mols=[build(n) for n in ['γ-Glu-Val-L-Lacticacid','γ-Glu-Nva-L-Lacticacid','γ-Glu-Nva','γ-Glu-Nva-Gly']]
    Draw.MolsToGridImage(mols,molsPerRow=2,subImgSize=(480,270),legends=['Known Val ester','Unmeasured Nva ester combination','Measured Nva core','Measured Nva-Gly comparator']).save(REPORT/'focused_structures.png')
    statistics={'best_observed_model':best,'best_MAE_log10':float(main.loc[main.model==best,'MAE_log10'].iloc[0]),'best_fold_error':float(main.loc[main.model==best,'geometric_absolute_fold_error'].iloc[0]),'bootstrap':bootstrap,
                'candidate_count':len(summary),'scope':'Chemical-family generalization in one compiled series. No sensory prediction or new activity measurement.'}
    (REPORT/'analysis_summary.json').write_text(json.dumps(statistics,indent=2))
    print(main.to_string(index=False));print(json.dumps(bootstrap,indent=2));print(hard[['name','absolute_error_log10','nearest_training_similarity']].head(8).to_string(index=False))

def dock_analysis():
    mode=sys.argv[2] if len(sys.argv)>2 else 'current'
    if mode not in ['current','archived']:raise ValueError('Unknown docking analysis mode')
    dock=OUT/'docking' if mode=='current' else ROOT.parent/'prior_reference/docking'
    results=pd.read_csv(dock/'docking_results.csv')
    measured=pd.read_csv(OUT/'chemical_activity_dataset.csv').set_index('name')
    results['hek293_status']=results.name.map(measured.hek293_status).fillna('unmeasured_proposal')
    results['EC50_low_uM']=results.name.map(measured.hek293_low_uM)
    results['EC50_high_uM']=results.name.map(measured.hek293_high_uM)
    numeric=results[results.hek293_status.isin(['numeric','range'])].copy()
    numeric['pEC50']=6-np.log10(np.sqrt(numeric.EC50_low_uM*numeric.EC50_high_uM))
    rho=float(spearmanr(-numeric.vina_top_score_kcal_mol,numeric.pEC50).statistic)
    results.to_csv(REPORT/'docking_with_assay_labels.csv',index=False)
    sensitivity=json.loads((dock/'native_search_sensitivity.json').read_text())
    s={'completed_jobs':len(results),'numeric_activity_comparisons':len(numeric),'score_activity_spearman':rho,'result_source':mode,
       'native_top_rmsd_A':float(results.native_top_rmsd_A.dropna().iloc[0]),
       'higher_search_top_rmsd_A':sensitivity['top_pose_rmsd_A'],'higher_search_best_rmsd_A':sensitivity['best_rmsd_A'],
       'limitations':'Selected analogue panel; rigid receptor and fixed ligand charge hypothesis; no modeled calcium ions; inactive is not synonymous with nonbinding.'}
    (REPORT/'docking_summary.json').write_text(json.dumps(s,indent=2))
    fig,axes=plt.subplots(1,2,figsize=(10,4))
    axes[0].scatter(-numeric.vina_top_score_kcal_mol,numeric.pEC50,color='#426c99')
    axes[0].set(xlabel='Negative Vina score (kcal/mol)',ylabel='Measured pEC50',title=f'Selected panel: Spearman = {rho:.2f}')
    values=[s['native_top_rmsd_A'],s['higher_search_top_rmsd_A'],s['higher_search_best_rmsd_A']]
    panel_info=json.loads((dock/'run_summary.json').read_text())
    panel_ex=panel_info.get('protocol',{}).get('panel_exhaustiveness',panel_info.get('exhaustiveness',4))
    axes[1].bar([f'Top: search {panel_ex}',f'Top: search {sensitivity["exhaustiveness"]}',f'Closest of {len(sensitivity["all_pose_rmsds_A"])}'],values,color=['#bd6b42','#bd6b42','#267f79'])
    axes[1].set(ylabel='Reference heavy-atom RMSD (Å)',title='Closest pose is not necessarily top-ranked')
    fig.tight_layout();fig.savefig(REPORT/'docking_validation.png',dpi=170);plt.close(fig)
    native=next(m for m in Chem.SDMolSupplier(str(ROOT.parent/'toolkit_pilot/results/native_gamma_EVG.sdf')) if m)
    from meeko import PDBQTMolecule,RDKitMolCreate
    p=RDKitMolCreate.from_pdbqt_mol(PDBQTMolecule((dock/'native_exhaustiveness16.pdbqt').read_text(),skip_typing=True))[0]
    native=Chem.RemoveHs(native);p=Chem.RemoveHs(p)
    # Compare coordinates in the common receptor frame; do not align away docking error.
    a=np.asarray(native.GetConformer().GetPositions());b=np.asarray(p.GetConformer(0).GetPositions())
    fig=plt.figure(figsize=(6,5));ax=fig.add_subplot(projection='3d')
    for m,xyz,col,label in [(native,a,'#267f79','Observed ligand'),(p,b,'#bd6b42',f'Top pose; search {sensitivity["exhaustiveness"]}')]:
        ax.scatter(*xyz.T,s=24,color=col,label=label)
        for bond in m.GetBonds():
            i,j=bond.GetBeginAtomIdx(),bond.GetEndAtomIdx();ax.plot(*xyz[[i,j]].T,color=col,lw=1.6)
    ax.set(xlabel='x (Å)',ylabel='y (Å)',zlabel='z (Å)',title='Ligands in the receptor coordinate frame');ax.legend(fontsize=8)
    ax.set_box_aspect(np.maximum(np.ptp(np.vstack([a,b]),axis=0),.01))
    fig.tight_layout();fig.savefig(REPORT/'native_pose_comparison.png',dpi=160);plt.close(fig)
    print(json.dumps(s,indent=2));print(results[['name','hek293_status','vina_top_score_kcal_mol']].to_string(index=False))

def decision():
    a=json.loads((REPORT/'analysis_summary.json').read_text());d=json.loads((REPORT/'docking_summary.json').read_text())
    mode=json.loads((REPORT/'execution_mode.json').read_text())
    pose_note='The top-ranked reference pose remains displaced; this protocol is weak support for structural prioritization.' if d['higher_search_top_rmsd_A']>3 else 'Reference pose recovery is reported descriptively; it does not by itself validate activity or sensory ranking.'
    text=f'''# Executed CaSR notebook: research decisions

Best observed chemical-family model MAE: {a['best_MAE_log10']:.3f} log10; geometric mean absolute fold error: {a['best_fold_error']:.2f}.
The descriptive bootstrap does not establish a reliable advantage over the median comparator. Random folds are secondary; they do not establish external generalization.

Docking source: {mode['docking_mode']}. {d['completed_jobs']} compound results, {d['numeric_activity_comparisons']} numeric assay comparisons; score/activity Spearman {d['score_activity_spearman']:.3f}.
Top native RMSD {d['native_top_rmsd_A']:.2f} Å, larger-search top {d['higher_search_top_rmsd_A']:.2f} Å, closest returned pose {d['higher_search_best_rmsd_A']:.2f} Å. {pose_note}

What can be used: explicit structures, assay labels, matched chemical effects, failure examples and reproducible comparison conditions.
What remains unknown: activity of the proposed compounds, taste effects, food stability and suitability.

The Nva ester is an unmeasured combination within an explicitly described patent scaffold. PubChem absence does not establish novelty. Keep it as a secondary chemical comparison rather than promoting it as a hit.

The regression is not an active/inactive classifier. The table-only inactive set is narrow. Additional narrative-only inactive annotations have no assay-system assignment in their sentences and are exported separately. Review assay compatibility before combining labels. Do not convert missingness, inactivity or censored EC50 into arbitrary numeric targets.

Next meaningful evidence: independent matched receptor responses for the proposed analogue and known comparators, followed by separate direct saltiness evidence at matched sodium, dose and food matrix. More docking jobs alone do not supply that evidence.
'''
    (REPORT/'research_decisions.md').write_text(text)
    print(text)

if __name__=='__main__':
    {'audit':audit,'analyse':analyse,'dock_analysis':dock_analysis,'decision':decision}[sys.argv[1]]()
