"""One explicit configuration for the docking workers."""
import json
from pathlib import Path

DEFAULT={'docking_seed':777,'cpu_threads':2,'panel_exhaustiveness':4,
         'native_exhaustiveness':16,'panel_poses':10,'native_poses':20}

def load_protocol():
    path=Path(__file__).resolve().parent/'run_config.json'
    values=DEFAULT.copy()
    if path.exists():
        supplied=json.loads(path.read_text())
        unknown=set(supplied)-set(DEFAULT)
        if unknown:raise ValueError('Unknown protocol keys: '+repr(sorted(unknown)))
        values.update(supplied)
    for key,value in values.items():
        if type(value) is not int or value<=0:
            raise ValueError(f'{key} must be a positive integer')
    return values
