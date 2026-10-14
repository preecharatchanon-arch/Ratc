"""Explicit atom graphs for the reported CaSR peptide/depsipeptide series."""
import re
from rdkit import Chem
from rdkit.Chem import rdMolDescriptors

AA = dict(zip('Ala Arg Asn Asp Cys Gln Glu Gly His Ile Leu Lys Met Phe Pro Ser Thr Trp Tyr Val'.split(), 'ARNDCQEGHILKMFPSTWYV'))
# Constitution from Amino 2016's definitions. Ambiguous extra stereocentres are excluded.
CUSTOM = {
 'Orn': ('N[C@@H](CCCN)C(=O)O', 'S'),
 'Nva': ('N[C@@H](CCC)C(=O)O', 'S'),
 'Abu': ('N[C@@H](CC)C(=O)O', 'S'),
 'Tle': ('N[C@@H](C(C)(C)C)C(=O)O', 'S'),
 'Nle': ('N[C@@H](CCCC)C(=O)O', 'S'),
 'Algly': ('N[C@@H](CC=C)C(=O)O', 'S'),
 'Ser(Me)': ('N[C@@H](COC)C(=O)O', 'S'),
 'Hse': ('N[C@@H](CCO)C(=O)O', 'S'),
 'Cys(Me)': ('N[C@@H](CSC)C(=O)O', 'R'),
 'Cys(n-Butyl)': ('N[C@@H](CSCCCC)C(=O)O', 'R'),
 'Cys(n-Propyl)': ('N[C@@H](CSCCC)C(=O)O', 'R'),
 'Cys(Allyl)': ('N[C@@H](CSCC=C)C(=O)O', 'R'),
 'Cys(Carboxymethyl)': ('N[C@@H](CSCC(=O)O)C(=O)O', 'R'),
 'Aib': ('NC(C)(C)C(=O)O', None),
 'Cle': ('NC1(CCCC1)C(=O)O', None),
 'Ape': ('N[C@@H](CC)CC(=O)O', 'S'),
 'β-homoAla': ('N[C@@H](C)CC(=O)O', 'S'),
 'βAla': ('NCCC(=O)O', None),
 'Glycolicacid': ('OCC(=O)O', None),
 'L-Lacticacid': ('O[C@@H](C)C(=O)O', 'S'),
 'D-Lacticacid': ('O[C@H](C)C(=O)O', 'R'),
}

def monomer(name):
    is_d = name.startswith('D-') and name != 'D-Lacticacid'
    if is_d: name = name[2:]
    if name in AA or name.startswith('allo-'):
        base = name.replace('allo-', '')
        m = Chem.MolFromFASTA(AA[base])
        n = next(a.GetIdx() for a in m.GetAtoms() if a.GetPDBResidueInfo().GetName().strip() == 'N')
        ca = next(a.GetIdx() for a in m.GetAtoms() if a.GetPDBResidueInfo().GetName().strip() == 'CA')
        if name.startswith('allo-'):
            cb = next(a.GetIdx() for a in m.GetAtoms() if a.GetPDBResidueInfo().GetName().strip() == 'CB')
            m.GetAtomWithIdx(cb).InvertChirality()
    elif name in CUSTOM:
        smi, expected = CUSTOM[name]; m = Chem.MolFromSmiles(smi); n = 0
        centres = [a for a in m.GetAtoms() if a.GetChiralTag() != Chem.ChiralType.CHI_UNSPECIFIED]
        ca = centres[0].GetIdx() if centres else None
        Chem.AssignStereochemistry(m, cleanIt=True, force=True)
        if expected and m.GetAtomWithIdx(ca).GetProp('_CIPCode') != expected:
            m.GetAtomWithIdx(ca).InvertChirality(); Chem.AssignStereochemistry(m, cleanIt=True, force=True)
        if expected: assert m.GetAtomWithIdx(ca).GetProp('_CIPCode') == expected
    else:
        raise ValueError('No unambiguous monomer definition: ' + name)
    if is_d:
        if ca is None: raise ValueError('D-prefix on achiral monomer')
        m.GetAtomWithIdx(ca).InvertChirality()
    # Backbone acid is the closest free carboxyl to the incoming amino/hydroxy atom.
    acids = [(match[0], match[2]) for match in m.GetSubstructMatches(Chem.MolFromSmarts('[CX3](=[OX1])[OX2H]'))]
    if not acids: raise ValueError('No free carboxyl: ' + name)
    carbon, hydroxyl = min(acids, key=lambda pair: len(Chem.GetShortestPath(m, n, pair[0])))
    return m, n, carbon, hydroxyl

def tokenize(name):
    name = re.sub(r'\s+', '', name)
    linkage = name[0] if name.startswith(('γ-', 'α-', 'β-')) else 'α'
    if name.startswith(('γ-', 'α-', 'β-')): name = name[2:]
    parts = re.split(r'-(?![^()]*\))', name); result = []; i = 0
    while i < len(parts):
        p = parts[i]
        if p in ['D', 'L', 'allo', 'β'] and i + 1 < len(parts):
            result.append(p + '-' + parts[i+1]); i += 2
        else: result.append(p); i += 1
    return linkage, result

def build(name):
    linkage, parts = tokenize(name)
    mol, _, c, oh = monomer(parts[0])
    if linkage in ['γ', 'β']:
        if parts[0].replace('D-', '') != ('Glu' if linkage == 'γ' else 'Asp'):
            raise ValueError('Unsupported sidechain linkage')
        acids = [(x[0], x[2]) for x in mol.GetSubstructMatches(Chem.MolFromSmarts('[CX3](=[OX1])[OX2H]'))]
        c, oh = next(x for x in acids if x[0] != c)
    for part in parts[1:]:
        right, rn, rc, roh = monomer(part); offset = mol.GetNumAtoms()
        rw = Chem.RWMol(Chem.CombineMols(mol, right)); rw.AddBond(c, offset+rn, Chem.BondType.SINGLE)
        rw.RemoveAtom(oh); mol = rw.GetMol(); Chem.SanitizeMol(mol)
        c, oh = offset+rc-1, offset+roh-1
    Chem.AssignStereochemistry(mol, cleanIt=True, force=True)
    return mol

def identity(mol):
    return Chem.MolToSmiles(mol, isomericSmiles=True), rdMolDescriptors.CalcMolFormula(mol)

def middle_group(name):
    """Constitutional monomer identity; L/D and allo forms stay in one fold."""
    _,parts=tokenize(name)
    middle=parts[1]
    m,*_=monomer(middle)
    label=middle.removeprefix('D-').removeprefix('allo-')
    return label,Chem.MolToSmiles(m,isomericSmiles=False)
