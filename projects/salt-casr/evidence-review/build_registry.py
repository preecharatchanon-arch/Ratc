"""Build an attributed evidence registry. No model fitting or biological testing."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent
data = {
    "status": "descriptive_published_evidence_not_predictor_validation",
    "review_date": "2026-10-28",
    "missing": "null means not established in inspected material, never zero",
    "compounds": {
        "ABU": {"identity": "gamma-L-Glu-L-Abu", "Abu": "L-2-aminobutyric acid", "linkage": "gamma", "sensory_purity": None, "sensory_counterion": None},
        "EVG": {"identity": "gamma-L-Glu-L-Val-Gly", "linkage": "gamma", "sensory_purity": None, "sensory_counterion": None},
        "BCO": {"identity": "beta-caryophyllene oxide", "is_peptide": False, "measured_CaSR_here": None}
    },
    "sources": {
        "EP2012": {"publication": "EP2415359A1", "url": "https://patents.google.com/patent/EP2415359A1/en", "pdf_url": "https://patentimages.storage.googleapis.com/d2/b0/52/5f25968c3e9273/EP2415359A1.pdf", "pdf_sha256": "72b0f6256602073e8474e2c133ae7b417848f397e876d79560d85529f0c2702d", "kind": "patent_report", "sensory_locator": "Example 3, paragraphs 0046-0047; Table 6; PDF pp18-19", "receptor_locator": "Test Example 2, paragraphs 0038-0039; Table 1; PDF p14", "visual_review": ["Table 1 p14", "Table 6 p19"]},
        "EP2025": {"publication": "EP4609725A1", "url": "https://patents.google.com/patent/EP4609725A1/en", "pdf_url": "https://data.epo.org/publication-server/rest/v1.2/publication-dates/20250903/patents/EP4609725NWA1/document.pdf", "pdf_sha256": "5dccf84505b5c231ae9213aef619d82cf7e43d7d625b6294f2046573c7080162", "kind": "patent_report", "locator": "Test 10 paragraphs 0205-0207, Tables 27-28, PDF pp39-40; reference formulation Table 1 p28", "same_experiment_family": ["US20250248431A1", "WO2024090519A1"], "visual_review": ["Tables 27-28 pp39-40"], "family_versions_are_not_replications": True},
        "OHSU2010": {"doi": "10.1074/jbc.M109.029165", "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC2801228/", "locator": "Figure 3A caption", "access": "indexed_primary_caption; full paper and curves not recovered in this pass"}
    },
    "receptor_contexts": {
        "R_EP": {"source": "EP2012", "species": "human", "construct": "hCaSR/pcDNA3.1", "cells": "293E (HEK293)", "readout": "calcium fluorescence", "pH": 7.2, "CaCl2_mM_reported_range": [0.75, 1.25], "NaCl_mM": 146, "normalization": "compound maximum tested response", "biological_replicates": None, "EC50_uncertainty": None},
        "R_OHSU": {"source": "OHSU2010", "species": "human", "cells": "HEK293", "readout": "calcium imaging", "pH": None, "CaCl2_mM": None, "biological_replicates": None, "EC50_uncertainty": None}
    },
    "receptor_columns": ["record_id", "compound", "context", "EC50_as_printed", "unit", "censoring"],
    "receptor_rows": [["R1", "ABU", "R_EP", 0.21, "uM", "numeric"], ["R2", "EVG", "R_OHSU", 41.9, "nM", "numeric"]],
    "sensory_contexts": {
        "S_EP": {"source": "EP2012", "matrix": "aqueous NaCl", "NaCl_g_dL": 0.5, "total_sodium_measured": None, "pH_absolute": None, "pH_adjustment": "NaOH when needed, within 0.2 of control; added sodium unquantified", "assessors": 5, "scale": {"control_anchor": 0, "NaCl_0.75_g_dL_anchor": 5}, "early_seconds": "0-2", "late_seconds": "2 onward", "dose_selection": "source-selected optimum", "SD_SE_CI": None, "raw_paired_ratings": None, "randomization_blinding": None},
        "S_CHEESE": {"source": "EP2025", "matrix": "52 g commercial cheese sauce + water to 100 g", "sodium_basis": "product label 2.5 g salt-equivalent/130 g; not measured total sodium", "pH": None, "assessors": 4, "scale": {"reference_1": 0, "reference_2": 5, "reference_3": 10}, "added_NaCl_g_per_100g_in_references_1_2_3": [0, 0.05, 0.1], "author_effect_threshold": 3, "time_window": None, "SD_SE_CI": None, "raw_paired_ratings": None, "randomization_blinding": None}
    },
    "salt_temporal_columns": ["compound", "context", "dose_g_dL", "early_score", "late_score"],
    "salt_temporal_rows": [["ABU", "S_EP", 0.004, 1.6, 1.5], ["EVG", "S_EP", 0.002, 0.8, 1.8]],
    "cheese_columns": ["source_sample", "BCO_ppb_w_w", "EVG_ppb_w_w", "saltiness_score", "reported_added_smell"],
    "cheese_rows": [[11, 50, None, 2.1, "none"], [12, 100, None, 3.8, "none"], [13, 1000, None, 5.8, "none"], [14, 10000, None, 6.8, "none"], [15, None, 500, 1.8, "none"], [16, None, 1000, 4.4, "none"], [17, None, 5000, 6.1, "none"], [18, 50, 500, 5.8, "none"], [19, 100, 1000, 6.3, "none"], [20, 1000, 5000, 8.8, "none"]],
    "cheese_blank_dose_convention": "null reproduces blank ingredient addition; no numerical sensory/receptor response is imputed",
    "link_columns": ["sensory_context", "compound", "receptor_record", "link_basis", "same_material_lot"],
    "links": [["S_EP", "ABU", "R1", "same named chemical identity within publication", None], ["S_EP", "EVG", "R2", "chemical identity across publications", None], ["S_CHEESE", "EVG", "R2", "chemical identity across publications", None]],
    "counting": {"linked_peptide_identities": 2, "salt_temporal_conditions": 2, "pure_EVG_cheese_doses": 3, "independent_external_selector_validation": False},
    "scope_notes": ["All ten cheese-table rows retained to expose mixtures and denominator; only samples 15-17 are EVG alone.", "Threshold 3 is the patent's decision rule, not our validated practical margin or significance test.", "Source claims and observations do not establish mechanism, safety, approval or sodium reduction.", "CaSR values overlap earlier source history; no receptor assay is claimed as newly performed or certainly independent."]
}
from extend_registry import extend
data = extend(data)
from primary_assay_review import add_primary_assay_review
data = add_primary_assay_review(data)
from patent_basic_taste_review import add_patent_basic_taste_review
data = add_patent_basic_taste_review(data)
window = json.loads((ROOT / "sensory_window_qualification.json").read_text())
data["sensory_window_source_qualification"] = window
data["counting"]["patent_recovery_added_saltiness_conditions"] = 3
data["counting"]["new_separate_human_saltiness_conditions_this_pass"] = window["counts"]["new_main_registry_saltiness_conditions"]
(ROOT / "evidence.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")

# Integrity only: verify selection/identity conventions, not scientific efficacy.
assert len(data["salt_temporal_rows"]) == 2
assert len(data["cheese_rows"]) == 10
assert [r[0] for r in data["cheese_rows"] if r[1] is None] == [15, 16, 17]
assert {r[0] for r in data["salt_temporal_rows"]} == {"ABU", "EVG"}
assert data["sensory_contexts"]["S_EP"]["SD_SE_CI"] is None
assert data["sensory_contexts"]["S_CHEESE"]["raw_paired_ratings"] is None
assert data["sources"]["EP2025"]["family_versions_are_not_replications"]
assert len(data["givaudan_isointensity_rows"]) == 9
assert len(data["yang_saltiness_rows"]) == 2
assert data["counting"]["linked_peptide_identities"] == 5
assert data["counting"]["linked_identities_with_numerical_saltiness"] == 4
assert len(data["ueda_saltiness_rows"]) == 2
assert data["sensory_contexts"]["S_UEDA_NACL_043"]["assessors"] is None
assert data["sensory_contexts"]["S_UEDA_NACL_043"]["pH"] is None
assert len(data["graphical_saltiness_rows"]) == 2
assert all(r[3] is None for r in data["graphical_saltiness_rows"])
assert data["provisional_links"][0]["promoted_to_confirmed_identity"] is False
assert all(r["CaSR_activity"] is None for r in data["wu_arginyl_panel"])
assert [r for r in data["receptor_rows"] if r[0] == "R6"] == [["R6", "EVG", "R_KITAJIMA_PEAK", 0.167, "uM", "numeric"]]
assert data["sources"]["GOTO2024"]["reproduces"] == "GOTO2016"
assert all(r["new_saltiness_condition"] is False for r in data["endpoint_qualification"])
assert len(data["givaudan_receptor_coverage"]) == 8
assert sum(r["contains_peptide_backbone"] for r in data["givaudan_receptor_coverage"]) == 5
assert data["givaudan_panel_qualification"]["confirmed_receptor_matches"] == 0
assert len({r[0] for r in data["receptor_rows"]}) == len(data["receptor_rows"]) == 16
assert len(data["ohsu_kokumi_PSE_rows"]) == 6
assert data["sensory_contexts"]["S_OHSU_NACL_THICKNESS"]["not_separately_rated_saltiness"]
assert data["counting"]["new_separate_human_saltiness_conditions_this_pass"] == 0
assert data["counting"]["pure_peptide_conditions_with_numerical_saltiness"] == 12
assert data["counting"]["numerical_saltiness_endpoint_values_for_named_links"] == 14
assert data["receptor_row_uncertainty"]["R13"]["experiment_n"] == 4
assert data["receptor_contexts"]["R_OHSU"]["pH"] is None
summary = {"execution_kind": "registry_integrity_only_not_discovery_test", "integrity": "passed", "selector_test": "not_executed", "blocking_reasons": ["five named linked identities across heterogeneous conditions and endpoints, one graphical only; not a jointly tested candidate panel", "unequal optimized doses in temporal comparison", "missing paired uncertainty", "provisional adduct link has unresolved material identity", "no prespecified candidate denominator or unseen comparison", "practical gain margin not justified"], "model_fits": 0}
screen = json.loads((ROOT / "search_screen.json").read_text())
qualification = json.loads((ROOT / "source_qualification.json").read_text())
summary["source_assessment"] = {
    "bounded_indexed_unique_records": screen["union_records"],
    "not_a_systematic_review": True,
    "new_qualified_candidate_panels": qualification["new_qualified_candidate_panels"],
    "contextual_cases_kept_separate_from_outcome_rows": len(qualification["cases"]),
    "source_assessment_is_not_empirical_validation": True,
}
processing = json.loads((ROOT / "processing_qualification.json").read_text())
assert processing["new_qualified_selector_panels"] == 0
assert processing["new_peptide_saltiness_labels"] == 0
summary["processing_source_assessment"] = {
    "contextual_cases_separate_from_outcome_rows": len(processing["cases"]),
    "new_qualified_selector_panels": processing["new_qualified_selector_panels"],
    "new_peptide_saltiness_labels": processing["new_peptide_saltiness_labels"],
    "not_a_new_scientific_test": True,
}
sensory = json.loads((ROOT / "sensory_contrast_qualification.json").read_text())
assert sensory["counts"]["new_confirmed_receptor_saltiness_links"] == 0
assert sensory["counts"]["new_qualified_selector_panels"] == 0
summary["sensory_contrast_assessment"] = {
    "source_assigned_sensory_only_peptides": len(sensory["synthetic_peptides"]),
    "new_confirmed_receptor_saltiness_links": 0,
    "new_qualified_selector_panels": 0,
    "not_a_new_scientific_test": True,
}
summary["latest_patent_assessment"] = {
    "new_separate_saltiness_conditions": 3,
    "new_linked_peptide_identities": 0,
    "total_numerical_conditions": 12,
    "total_heterogeneous_endpoint_values": 14,
    "parent_and_child_sensory_table_counted_once": True,
    "new_qualified_selector_panels": 0,
    "earlier_six_assignment_sensitivity_rechecked_not_new": True,
    "not_a_new_scientific_test": True,
}
summary["latest_sensory_window_assessment"] = {
    **window["counts"],
    "execution_gate": window["design_status"]["execution_gate"],
    "not_a_new_scientific_test": True,
}
(ROOT / "integrity.json").write_text(json.dumps(summary, indent=2) + "\n")
manifest = {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(ROOT.iterdir()) if p.is_file() and p.name != "MANIFEST.json"}
(ROOT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
archive = ROOT.parent / "CaSR_Matched_Evidence.zip"
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(ROOT.iterdir()):
        if p.is_file(): z.write(p, arcname=p.name)
print(json.dumps({"archive": str(archive), "integrity": "passed", "scientific_tests": 0, "linked_named_peptides": data["counting"]["linked_peptide_identities"]}))
