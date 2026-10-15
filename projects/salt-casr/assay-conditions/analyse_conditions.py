"""Four frozen baseline fits, condition-specific evidence and chemical consistency.

This is a retrospective literature-panel diagnostic, not prospective validation.
See PROTOCOL.md for the pre-fit decisions and the known source limitations.
"""
from pathlib import Path
import json, time, hashlib, platform
import numpy as np
import pandas as pd
from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors
from baseline import features, groups, distance, fit_predict

ROOT = Path(__file__).resolve().parent

def main():
    started = time.monotonic()
    out = ROOT / 'results'; out.mkdir(exist_ok=True)
    benchmark = pd.read_csv(ROOT/'data/benchmark_records.csv').fillna('')
    panels = pd.read_csv(ROOT/'data/fixed_assay_panels.csv')
    doses = pd.read_csv(ROOT/'data/dose_response.csv')
    assert len(benchmark) == 580 and benchmark.sequence.nunique() == 580
    assert benchmark.sensory_tagged.dtype == bool and benchmark.sensory_tagged.sum() == 251
    assert len(panels) == 11 and panels.sequence.nunique() == 11
    assert len(doses) == 18 and doses.groupby('sequence').size().eq(6).all()
    # Preserve both contexts rather than overwriting a binary label.
    conflict = benchmark[benchmark.sequence.eq('NGYDMR')]
    assert len(conflict) == 1 and int(conflict.iloc[0].label) == 0
    conflict.to_csv(out/'NGYDMR_original_benchmark_record.csv',index=False)
    # Remove transitive similarity components using all 580 original sequences,
    # including records outside the sensory-tagged training subset.
    joint = pd.concat([benchmark[['sequence']],panels[['sequence']]],ignore_index=True)
    sim_groups, _ = groups(joint)
    heldout_groups = set(sim_groups[len(benchmark):])
    heldout_dois = set(panels.doi) | {'10.1016/j.foodchem.2025.145575'}
    exclusions = []; eligible = []
    for i,r in benchmark.iterrows():
        reasons = []
        if not bool(r.sensory_tagged): reasons.append('outside_sensory_tagged_cohort')
        if sim_groups[i] in heldout_groups: reasons.append('test_similarity_component')
        if set(str(r.doi_tokens).split(';')) & heldout_dois: reasons.append('test_source_or_NGYDMR_source')
        eligible.append(not reasons)
        exclusions.append(dict(sequence=r.sequence,label=r.label,eligible=not reasons,
                               reasons=';'.join(reasons),references=r.references))
    pd.DataFrame(exclusions).to_csv(out/'training_eligibility.csv',index=False)
    train = benchmark[np.array(eligible)].copy().reset_index(drop=True)
    assert len(train.label.unique()) == 2
    assert not set(train.sequence) & set(panels.sequence)
    assert not {v for s in train.doi_tokens for v in str(s).split(';')} & heldout_dois
    for a in train.sequence:
        for b in panels.sequence:
            assert 1-distance(a,b)/max(len(a),len(b)) < .8-1e-12
    joined = pd.concat([train[['sequence']],panels[['sequence']]],ignore_index=True)
    x = features(joined.sequence); y = train.label.to_numpy()
    scores = []; retrieval = []
    for model in ['length_only','charge_length','composition_logistic','extra_trees']:
        p = fit_predict(model,x,y,np.arange(len(train)),np.arange(len(train),len(joined)))
        scored = panels.copy(); scored['model'] = model; scored['score'] = p
        # Alphabetical tie break is explicit; tied ranks must not imply superiority.
        scored = scored.sort_values(['panel','score','sequence'],ascending=[True,False,True])
        scored['rank_within_panel'] = scored.groupby('panel').cumcount()+1
        scores.append(scored)
        for panel,g in scored.groupby('panel'):
            top = g.head(3)
            retrieval.append(dict(model=model,panel=panel,n_candidates=len(g),
                reported_significant_total=int(g.outcome.eq('significant_enhancement').sum()),
                reported_significant_in_top3=int(top.outcome.eq('significant_enhancement').sum()),
                expected_retrieval_uniform_random=3*g.outcome.eq('significant_enhancement').sum()/len(g),
                top3=';'.join(top.sequence),score_ties=bool(g.score.duplicated().any()),
                interpretation='Descriptive retrieval in selected panels; not general-population accuracy'))
    all_scores = pd.concat(scores,ignore_index=True)
    all_scores.to_csv(out/'heldout_panel_scores.csv',index=False)
    pd.DataFrame(retrieval).to_csv(out/'panel_retrieval.csv',index=False)
    # Convert mass concentration to molar concentration only for a stated neutral,
    # unmodified linear structure. Salt counterions and purity are not corrected.
    molar = panels[['panel','sequence','peptide_mg_mL']].copy()
    molar['neutral_average_MW'] = [Descriptors.MolWt(Chem.MolFromFASTA(s)) for s in molar.sequence]
    molar['nominal_peptide_mM_free_form'] = 1000*molar.peptide_mg_mL/molar.neutral_average_MW
    molar['assumption'] = 'Unmodified linear L-peptide, free termini; counterion/purity not corrected'
    molar.to_csv(out/'nominal_molar_doses.csv',index=False)
    # Published means: no reconstruction of individual observations or p-values.
    dose_summary = []
    for seq,g in doses.groupby('sequence'):
        g = g.sort_values('nominal_peptide_mM'); peak = g.loc[g.saltiness_mean.idxmax()]
        dose_summary.append(dict(sequence=seq,alias=g.alias.iloc[0],peak_nominal_mM=peak.nominal_peptide_mM,
            peak_mean=peak.saltiness_mean,last_mean=g.saltiness_mean.iloc[-1],
            peak_to_last_change=g.saltiness_mean.iloc[-1]-peak.saltiness_mean,
            nondecreasing_means=bool((np.diff(g.saltiness_mean)>=0).all())))
    pd.DataFrame(dose_summary).to_csv(out/'dose_summary.csv',index=False)
    ranking = []
    for dose,g in doses[doses.nominal_peptide_mM.gt(0)].groupby('nominal_peptide_mM'):
        g = g.sort_values('saltiness_mean',ascending=False)
        ranking.append(dict(nominal_peptide_mM=dose,ranked_aliases=' > '.join(g.alias)))
    pd.DataFrame(ranking).to_csv(out/'dose_rankings.csv',index=False)
    # The caption does not specify charge/adduct for each entry. This checks the
    # ordinary protonated-ion interpretation only, not every possible modification.
    mz = pd.read_csv(ROOT/'data/caption_mz.csv'); mass_rows = []
    proton = 1.007276466621
    for r in mz.itertuples():
        mol = Chem.MolFromFASTA(r.sequence); mass = rdMolDescriptors.CalcExactMolWt(mol)
        possibilities = [(z,(mass+z*proton)/z) for z in range(1,7)]
        z,calc = min(possibilities,key=lambda pair:abs(pair[1]-r.reported_mz))
        mass_rows.append(dict(sequence=r.sequence,neutral_monoisotopic_mass=mass,
            reported_mz=r.reported_mz,closest_protonated_charge=z,calculated_mz=calc,
            difference_Da=r.reported_mz-calc,matches_to_two_decimal_precision=abs(r.reported_mz-calc)<=.0051,
            mismatch_over_point1_Da=abs(r.reported_mz-calc)>.1,
            assumptions='Unmodified linear peptide; free termini; [M+zH]/z; z=1..6; not MS/MS validation'))
    pd.DataFrame(mass_rows).to_csv(out/'caption_mass_check.csv',index=False)
    # Plot our transcription, not a reproduction of the publisher's artwork.
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax = plt.subplots(figsize=(8.2,4.8),layout='constrained')
    for seq,g in doses.groupby('sequence',sort=False):
        g = g.sort_values('nominal_peptide_mM')
        ax.errorbar(g.nominal_peptide_mM,g.saltiness_mean,yerr=g.saltiness_SD.fillna(0),
                    marker='o',capsize=3,label=f'{g.alias.iloc[0]} ({seq})')
    ax.set(xlabel='Reported nominal peptide concentration (mM)',ylabel='Reported saltiness score (mean ± SD)',
           title='The preferred peptide changes with dose',ylim=(0,10))
    ax.legend(frameon=False,fontsize=9); ax.grid(alpha=.2)
    fig.savefig(out/'dose_rank_reversal.png',dpi=180); plt.close(fig)
    receipt = dict(runtime_s=time.monotonic()-started,python=platform.python_version(),
        train_n=len(train),train_class_counts={str(k):int(v) for k,v in train.label.value_counts().items()},
        models_fitted=4,panel_candidates=11,reported_enhancers=6,
        panel_sequences_in_original_benchmark=sorted(set(panels.sequence)&set(benchmark.sequence)),
        training_test_max_similarity=float(max(1-distance(a,b)/max(len(a),len(b)) for a in train.sequence for b in panels.sequence)),
        benchmark_input_sha256=hashlib.sha256((ROOT/'data/benchmark_records.csv').read_bytes()).hexdigest(),
        claims='Retrospective diagnostic; no novel molecule, receptor validation, prospective accuracy or measured sodium-reduction claim')
    (out/'run_receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))
    print(pd.DataFrame(retrieval)[['model','panel','reported_significant_in_top3','top3']].to_string(index=False))
    print(pd.DataFrame(dose_summary).to_string(index=False))
    print(pd.DataFrame(mass_rows)[['sequence','reported_mz','calculated_mz','matches_to_two_decimal_precision']].to_string(index=False))

if __name__ == '__main__':
    main()
