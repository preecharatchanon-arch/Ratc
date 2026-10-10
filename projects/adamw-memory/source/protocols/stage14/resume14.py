"""Read-only resume accounting; does not change the scientific experiment."""
import json
from pathlib import Path


def progress(root, config):
    root = Path(root)
    rows = []
    for ds in config.datasets:
        for seed in config.seeds:
            unit = root / 'units' / f'{ds}_{seed}'
            complete = (unit / 'COMPLETE.json').exists()
            training_step = None
            if (unit / 'state.resume.npz').exists():
                import numpy as np
                with np.load(unit / 'state.resume.npz',allow_pickle=False) as state:
                    training_step=int(state['clock'])
            if (unit / 'TRAINING.json').exists():
                history = json.loads((unit / 'TRAINING.json').read_text())
                if history and training_step is None:
                    training_step = history[-1]['clock']
            fits = [f'H{h}/n{n}' for n in config.fit_sizes for h in (1, config.fit_horizon)
                    if (unit / f'fit_h{h}_n{n}.json').exists()]
            branches = sum((p.with_suffix('.json')).exists() for p in unit.glob('path*/branch_*.npz'))
            working = []
            for p in sorted(unit.glob('*.resume.npz')):
                if p.name.startswith(('operator_', 'trace_', 'basis_', 'prediction_work')):
                    working.append(p.name)
            if complete:
                next_task = 'complete; skipped'
            elif not (unit / 'STABILITY14.json').exists():
                next_task = 'training/stability screen'
            elif not (unit / 'QUALIFICATION.json').exists():
                next_task = 'full-effect qualification'
            else:
                missing = [(h,n) for n in config.fit_sizes for h in (1, config.fit_horizon)
                           if not (unit / f'fit_h{h}_n{n}.json').exists()]
                next_task = f'H{missing[0][0]} fit/capture/qualification (n={missing[0][1]})' if missing else 'predictions/remaining branches'
            rows.append(dict(unit=unit.name, complete=complete, training_step=training_step,
                             stability_saved=(unit / 'STABILITY14.json').exists(), fits=fits,
                             saved_branches=branches, working=working, next_task=next_task))
    return rows


def report(camp, config):
    rows = progress(camp.local, config)
    receipt = dict(source=camp.restored_from, sha256=camp.restored_sha256,
                   bytes=camp.restored_bytes, completed=sum(r['complete'] for r in rows),
                   total=len(rows), units=rows)
    print('\nVERIFIED DRIVE RESUME', flush=True)
    print('Source:', camp.restored_from, flush=True)
    print('SHA256:', camp.restored_sha256, flush=True)
    print('Completed histories:', receipt['completed'], '/', receipt['total'], flush=True)
    for ds in config.datasets:
        cohort = [r for r in rows if r['unit'].startswith(ds + '_')]
        trained = sum(r['complete'] or r['training_step'] == config.train_steps for r in cohort)
        stable = sum(r['stability_saved'] for r in cohort)
        print(f'{ds}: {trained}/{len(cohort)} trained; {stable}/{len(cohort)} saved stability screens; '
              f'{sum(r["complete"] for r in cohort)}/{len(cohort)} complete', flush=True)
    next_row = next((r for r in rows if not r['complete']), None)
    if next_row:
        print('Next unfinished history:', next_row['unit'], '|', next_row['next_task'], flush=True)
        print('Saved fits:', ', '.join(next_row['fits']) or 'none', flush=True)
        if next_row['working']:
            print('Working snapshots:', ', '.join(next_row['working']), flush=True)
    print('Completed histories, fits and branches are reused. Unsaved work since the last commit may repeat.\n', flush=True)
    return receipt
