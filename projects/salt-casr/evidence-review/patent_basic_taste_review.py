"""Attributed primary-source extraction. No predictive or inferential test."""


def add_patent_basic_taste_review(data):
    data["review_date"] = "2026-10-29"
    data["sources"]["US8420144_BASIC"] = {
        "publication": "US8420144B2",
        "kind": "patent_report_not_our_experiment",
        "url": "https://patents.google.com/patent/US8420144B2/en",
        "pdf_url": "https://patentimages.storage.googleapis.com/71/46/5c/03bf28255622e1/US8420144.pdf",
        "locator": "Example24/Table8, PDFpp19-20, printed columns23-26; Example19/Table3, PDFp18",
        "visual_review": ["Table3 PDFp18", "Example24/Table8 PDFpp19-20"],
        "assignee_as_reported": "Ajinomoto",
        "same_publication_family_versions": ["US20100136197A1"],
        "parent_publication": "US8173605B2",
        "parent_url": "https://patents.google.com/patent/US8173605B2/en",
        "parent_same_sensory_table": "Example16/Table7; same formulation, n12 and all twelve basic-taste numbers",
        "parent_family_versions": ["US20090239310A1", "WO2007055393A1"],
        "duplicate_sensory_tables_counted_once": True,
        "shared_source_with_Ohsu_Amino": "same organization; parent inventors include Ohsu/Eto/Amino; exact overlap of material, assessors and observations with journal experiments unresolved",
        "independent_external_selector_validation": False,
        "source_experiment_cluster": "AJINOMOTO_BASIC_GSH_EVG_NACL_070",
    }
    data["sensory_contexts"]["S_PATENT_BASIC_NACL_070"] = {
        "source": "US8420144_BASIC",
        "matrix": "aqueous NaCl standard",
        "NaCl_g_per_dL": 0.7,
        "sodium_basis": "nominal recipe NaCl; total sodium and NaOH addition amounts not measured here",
        "endpoint": "relative activity enhancing separately named salty taste",
        "scale_anchors": {"0": "control", "1": "fairly intense enhancement relative to control", "2": "intense enhancement relative to control"},
        "table_control_header_as_printed": "Distilled water",
        "control_interpretation": "Example24 describes a NaCl standard without peptide; zero is a relative scale anchor, not evidence that NaCl has zero absolute saltiness",
        "control_is_an_independent_zero_observation": False,
        "reported_n": 12,
        "n_definition_and_assessor_details": None,
        "blind": None,
        "randomization": None,
        "independent_sessions": None,
        "taste_time_endpoint_seconds": None,
        "dose_selection": "typical concentrations selected from stated 0.0001-1g/dL testing range; no complete dose series recovered",
        "pH": None,
        "pH_matching_policy": "acidified samples adjusted using NaOH to within +/-0.2pH units of the relevant no-peptide standard",
        "free_calcium": None,
        "raw_paired_assessor_data": None,
        "SD_SE_CI": None,
        "P_value": None,
        "same_receptor_sensory_lot": None,
        "selection_frame": "selected known CaSR activators; not an unselected or independently evaluated candidate panel",
    }
    data["patent_basic_saltiness_columns"] = [
        "compound", "context", "dose_g_per_dL", "source_relative_enhancement_score"
    ]
    data["patent_basic_saltiness_rows"] = [
        ["GSH", "S_PATENT_BASIC_NACL_070", 0.10, 0.2],
        ["EVG", "S_PATENT_BASIC_NACL_070", 0.005, 0.5],
        ["EVG", "S_PATENT_BASIC_NACL_070", 0.01, 1.0],
    ]
    # Retain the table's other endpoints without assigning them to saltiness.
    data["patent_basic_all_taste_columns"] = [
        "taste", "background_standard_g_per_dL", "GSH_0_10g_dL", "EVG_0_005g_dL", "EVG_0_01g_dL"
    ]
    data["patent_basic_all_taste_rows"] = [
        ["umami", "MSG0.2", 0.7, 0.7, 1.5],
        ["sweet", "sucrose5", 1.5, 0.5, 1.0],
        ["salty", "NaCl0.7", 0.2, 0.5, 1.0],
        ["sour", "citric_acid0.05", 1.5, 0.5, 1.0],
    ]
    data["receptor_contexts"]["R_US8420144_HEK"] = {
        "source": "US8420144_BASIC", "species": "human", "cells": "HEK293",
        "construct": "humanCaSR cDNA from WO2007/055393A1;CMV-promoter vector;FuGENE6 transfection",
        "stable_or_transient_explicitly_established": None,
        "readout": "Calcium3 dye/FlexStation calcium imaging",
        "EC50_definition": "peptide concentration giving50%of maximal activity on dose-characteristic curve, as source states",
        "CaCl2_mM": None, "pH": None, "NaCl_mM": None,
        "buffer_warning": "do not import the separately described oocyte buffer into HEK conditions",
        "range_definition": "source reports multiple experimental values;not a confidence interval",
        "experiment_n": "single values n1;range rows n2or3;EVG-specific exact n unresolved",
        "Emax": None,
    }
    data["receptor_rows"].append([
        "R16", "EVG", "R_US8420144_HEK", "0.023-0.055", "uM", "reported_range_not_CI"
    ])
    data["receptor_row_uncertainty"]["R16"] = {
        "source_reported_range_uM": [0.023, 0.055],
        "experiment_n_possible": [2, 3], "CI": None,
        "independent_of_Ohsu_Amino": None,
    }
    data["patent_nonEC50_functional_observations"] = [{
        "compound": "GSH", "source": "US8420144_BASIC",
        "locator": "Example17/Figure4",
        "species": "human receptor expressed in Xenopus laevis oocytes",
        "test_dose_uM": 50,
        "readout": "Ca-dependent chloride current, two-electrode voltage clamp -70mV",
        "buffer_mM": {"NaCl": 96, "KCl": 2, "MgCl2": 1, "CaCl2": 1.8, "HEPES": 5},
        "pH": 7.2, "control": "water-injected oocytes",
        "result": "functional activation reported",
        "EC50": None, "response_amplitude_transcribed": None,
        "experiment_n": None, "same_sensory_lot": None,
        "test_concentration_is_not_an_EC50_or_MEC": True,
    }]
    data["patent_Table3_columns"] = ["compound_as_printed", "EC50_uM_as_printed"]
    data["patent_Table3_rows"] = [
        ["gamma-Glu-Val-Gly", "0.023-0.055"],
        ["gamma-Glu-Cle-Gly", "0.5-1.5"],
        ["gamma-Glu-Aib-Gly", "0.349-1.167"],
        ["gamma-Glu-t-Leu-Gly", "0.043-0.077"],
        ["gamma-Glu-Pen-Gly", "0.159-0.233"],
        ["gamma-Glu-Val-GlyA", "0.14"],
        ["gamma-Glu-t-Leu-GlyA", "0.05"],
        ["gamma-Glu-Abu-GlyA", "0.065-0.079"],
        ["gamma-Glu-Val-LacA", "0.057"],
        ["gamma-Glu-t-Leu-LacA", "0.038"],
        ["gamma-Glu-Abu-LacA", "0.102"],
    ]
    data["patent_Table3_transcription_notes"] = {
        "GlyA": "glycolic acid terminus;source synthesis uses benzyl glycolate",
        "LacA": "source synthesis uses benzyl(S)-lactate",
        "t_Leu_or_Tle": "tert-leucine spelling variants retained in source comparison",
        "all11_source_rows_retained": True,
        "main_receptor_row_scope": "R16 adds the human-saltiness-linked EVG range;remaining Table3 compounds stay in full source transcript, not new human labels",
    }
    data["reported_source_assignment_comparison"] = [
        {"compound": "gamma-Glu-Val-glycolic acid", "US8420144_Table3_uM": "0.14", "Amino2016_Table3_uM": "0.05"},
        {"compound": "gamma-Glu-Abu-glycolic acid", "US8420144_Table3_uM": "0.065-0.079", "Amino2016_Table3_uM": "0.14"},
        {"compound": "gamma-Glu-Tle-glycolic acid", "US8420144_Table3_uM": "0.05", "Amino2016_Table3_uM": "0.065-0.079"},
        {"compound": "gamma-Glu-Val-L-lactic acid", "US8420144_Table3_uM": "0.057", "Amino2016_Table3_uM": "0.102"},
        {"compound": "gamma-Glu-Abu-L-lactic acid", "US8420144_Table3_uM": "0.102", "Amino2016_Table3_uM": "0.038"},
        {"compound": "gamma-Glu-Tle-L-lactic acid", "US8420144_Table3_uM": "0.038", "Amino2016_Table3_uM": "0.057"},
    ]
    data["reported_source_assignment_note"] = (
        "Original patent Table3 and Amino2016 Table3 were visually inspected. "
        "These six compound-to-value assignments differ. Different runs/protocols, "
        "publication errors and source reuse are not adjudicated by this comparison. "
        "These are the same six alternate assignments already evaluated in the earlier "
        "frozen benchmark, not a newly discovered conflict. This pass rechecked the "
        "original source images. No new correction or re-fit was run. The2017erratum "
        "concerns another citation, not these assignments."
    )
    data["links"].extend([
        ["S_PATENT_BASIC_NACL_070", "EVG", "R16", "same named identity within patent;not established shared lot", None],
        ["S_PATENT_BASIC_NACL_070", "GSH", "R5", "same named identity across reports;patent also reports direct oocyte response", None],
    ])
    data["counting"].update({
        "pure_peptide_conditions_with_numerical_saltiness": 12,
        "numerical_saltiness_endpoint_values_for_named_links": 14,
        "new_separate_human_saltiness_conditions_this_pass": 3,
        "new_linked_peptide_identities_this_pass": 0,
        "patent_basic_saltiness_conditions": 3,
        "numeric_count_warning": "fourteen heterogeneous values include PSE concentrations and relative enhancement scores;not one common scale or fourteen independent candidates",
        "independent_external_selector_validation": False,
    })
    data["scope_notes"].extend([
        "US8420144Table8 repeats US8173605Table7;three saltiness conditions count once,not six.",
        "The new source gives nominal0.7g/dLNaCl and NaOH pH adjustment,not matched measured total sodium.",
        "Reported positive relative scores have no recoverable paired uncertainty/P values;statistical significance is not invented.",
        "Two EVG doses are not two independent compounds. Unequal source-selected doses cannot identify a general CaSR-guided selector or potency multiplier.",
        "The source adds reported receptor/saltiness overlap,not independent validation or CaSR-specific sensory causality.",
    ])
    return data
