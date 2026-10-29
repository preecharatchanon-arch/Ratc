"""Primary-source extraction, not an experimental or inferential analysis."""


def add_primary_assay_review(data):
    data["sources"]["OHSU2010"].update({
        "access": "original article text recovered on public ResearchGate page; original PDF/figure axes not visually verified",
        "recovered_text_url": "https://www.researchgate.net/publication/38070202_Involvement_of_the_Calcium-sensing_Receptor_in_Human_Taste_Perception",
        "locator": "HEK and sensory methods pp1017-1018; Figure2 caption p1019; Figure3 caption and Table2 p1020",
        "organization": "Ajinomoto",
        "sampling": "authors describe five non-reference peptides as randomly chosen from previously identified CaSR agonists; not an unselected peptide panel",
        "new_independent_saltiness_validation": False,
        "visual_review": [],
        "retrieved_text_conflicts_require_original_page": True
    })
    data["receptor_contexts"]["R_OHSU"].update({
        "construct": "hCaSR in pcDNA3.1; transient expression",
        "readout": "Calcium-4 fluorescence, FlexStation",
        "CaCl2_mM": 0.9,
        "pH": None, "NaCl_mM": None,
        "context_warning": "do not transfer the oocyte buffer (1.8mM CaCl2, 96mM NaCl, pH7.2) to the HEK assay",
        "EC50_definition": "as reported in Figure3A caption; Emax separately relative to calcium=100%; raw curves not re-fitted"
    })
    data["compounds"].update({
        "GC": {"identity": "gamma-glutamyl cysteine", "linkage": "gamma", "same_receptor_sensory_lot": None},
        "ABUG": {"identity": "gamma-glutamyl 2-aminobutyryl glycine", "linkage": "gamma", "same_receptor_sensory_lot": None},
        "SMG": {"identity": "S-methylglutathione", "linkage": "gamma", "same_receptor_sensory_lot": None}
    })
    # R2 already retains the EVG Figure3A value; do not duplicate it.
    data["receptor_rows"].extend([
        ["R7", "GSH", "R_OHSU", 76.5, "nM", "numeric"],
        ["R8", "EA", "R_OHSU", 3.65, "uM", "numeric"],
        ["R9", "EV", "R_OHSU", 1.34, "uM", "numeric"],
        ["R10", "GC", "R_OHSU", 458, "nM", "numeric"],
        ["R11", "ABUG", "R_OHSU", 18.1, "nM", "numeric"]
    ])
    data["ohsu_Fig3A_Emax_percent_calcium"] = {
        "R2": 40.8, "R7": 27.6, "R8": 42.6,
        "R9": 53.3, "R10": 38.0, "R11": 25.6
    }
    data["ohsu_Table1_HEK_columns"] = ["compound", "parenthetical_EC50_uM_in_retrieved_text"]
    data["ohsu_Table1_HEK_rows"] = [
        ["EA", 3.7], ["EV", 1.6], ["GC", 0.46],
        ["GSH", 0.71], ["ABUG", 0.025], ["EVG", 0.039]
    ]
    data["ohsu_internal_value_warning"] = (
        "Table1 parenthetical HEK values and Figure3A caption values differ in the retrieved original text, "
        "especially GSH 0.71uM versus 76.5nM. Table1 is not a second independent experiment by assumption. "
        "No silent correction, averaging or selection of the value that fits a desired association. "
        "Original page/correction required to adjudicate possible printed versus extraction discrepancy."
    )
    data["sensory_contexts"]["S_OHSU_NACL_THICKNESS"] = {
        "source": "OHSU2010", "matrix": "aqueous NaCl", "NaCl_percent_as_printed": 0.9,
        "percent_basis": "percent as printed; no conversion to molar peptide dose",
        "endpoint": "kokumi thickness, operationalized as taste intensity about 5s after tasting",
        "not_separately_rated_saltiness": True,
        "assessors": 20, "training": "well trained", "blind": True,
        "randomization": None, "scale": [-2, -1, 0, 1, 2],
        "pH_reported_range": [6.8, 7.2], "pH_adjustment_reagent": "NaOH",
        "total_sodium_measured": None,
        "source_statistics": "Student t test against control; means and SE bars in Figure2A",
        "numerical_effect_or_paired_uncertainty_extracted": None,
        "figure_axes_visually_verified": False
    }
    data["ohsu_salt_solution_thickness_columns"] = ["compound", "context", "dose_percent_as_printed", "direction", "numerical_score"]
    data["ohsu_salt_solution_thickness_rows"] = [
        ["GSH", "S_OHSU_NACL_THICKNESS", 0.1, "enhancement reported", None],
        ["EVG", "S_OHSU_NACL_THICKNESS", 0.01, "enhancement reported", None]
    ]
    data["sensory_contexts"]["S_OHSU_KOKUMI_PSE"] = {
        "source": "OHSU2010", "matrix": "0.05% MSG + 0.05% IMP + 0.5% NaCl",
        "endpoint": "taste thickness/kokumi PSE against GSH, not NaCl-equivalent saltiness",
        "assessors": 17, "training": "well trained",
        "reference_GSH_percent_w_v": [0.02, 0.03, 0.044, 0.07, 0.10, 0.15, 0.23, 0.34],
        "comparisons": "each sample paired twice with each reference; dichotomous more/less intense; probit",
        "dose_selection": "preliminary tests", "pH": None,
        "pH_note": "do not automatically copy the final pH range from the separate five-point subsection",
        "total_sodium_measured": None, "raw_assessor_data": None, "PSE_uncertainty": None,
        "blind_randomized_for_this_subsection": None
    }
    data["ohsu_kokumi_PSE_columns"] = ["compound", "sample_percent_as_printed", "GSH_percent_at_PSE", "relative_kokumi_intensity"]
    data["ohsu_kokumi_PSE_rows"] = [
        ["GSH", None, None, 1], ["EA", 0.5, 0.074, 0.15],
        ["EV", 0.15, 0.092, 0.61], ["GC", 0.15, 0.094, 0.63],
        ["ABUG", 0.05, 0.085, 1.7], ["EVG", 0.01, 0.128, 12.8]
    ]
    data["ohsu_published_association"] = {
        "r_squared_as_printed": 0.660, "P_as_printed": 0.0496,
        "endpoint": "relative kokumi intensity versus receptor activity",
        "source_locator": "Figure3B caption; refers to Table1 although numerical kokumi table is Table2",
        "recalculated_by_us": False, "independent_selector_validation": False
    }
    data["sources"]["BROADHEAD2011"] = {
        "doi": "10.1074/jbc.M110.149724", "PMCID": "PMC3059007",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC3059007/",
        "author_copy": "https://www.researchgate.net/profile/William-Church-2/publication/49710778_Allosteric_modulation_of_the_calcium-sensing_receptor_by_g-glutamyl_peptides_Inhibition_of_PTH_secretion_suppression_of_intracellular_cAMP_levels_and_a_common_mechanism_of_action_with_L-amino_acids/links/5666102308ae192bbf9278c5/Allosteric-modulation-of-the-calcium-sensing-receptor-by-g-glutamyl-peptides-Inhibition-of-PTH-secretion-suppression-of-intracellular-cAMP-levels-and-a-common-mechanism-of-action-with-L-amino-acids.pdf",
        "access": "complete original PDF viewed through indexed author copy; no local PDF downloaded",
        "locator": "Experimental Procedures pp8787-8788; Table1 and Figure1 p8789",
        "visual_review": ["PDF p2 assay buffer", "PDF p3 statistics", "PDF p4 Table1 and Figure1 caption"],
        "organization": "University of Sydney / Monash / Royal North Shore Hospital",
        "source_overlap": "different named authors and affiliations from Ohsu/Amino; no claimed human sensory experiment or selector validation",
        "human_saltiness_measurement": None,
        "table_vs_figure_n_warning": "Table1 GSH n4; Figure1C caption GSH n5. Retain table n for its EC50; do not silently reconcile."
    }
    data["sources"]["MUN2005_PROTOCOL"] = {
        "doi": "10.1074/jbc.M500002200", "url": "https://pubmed.ncbi.nlm.nih.gov/15888439/",
        "access": "indexed primary Materials text specifies wild-type human CaR in pcDNA3.1(+)",
        "role": "Broadhead2011 reference15 for stable cell protocol; not a new peptide measurement"
    }
    data["receptor_contexts"]["R_BROADHEAD_HEK"] = {
        "source": "BROADHEAD2011", "species": "human",
        "species_basis": "stable cell protocol cites Mun2005, whose indexed primary Materials specify human CaR",
        "construct": "wild-type CaR, stable HEK293 expression; distinct from double-mutant branch",
        "readout": "fura2-AM 340/380nm microfluorimetry; baseline-subtracted integrated response",
        "CaCl2_mM": 2.5, "pH": 7.4, "NaCl_mM": 125,
        "buffer_other_components": "4mM KCl, 1mM MgCl2, 20mM HEPES(NaOH), 0.1% D-glucose; phosphate-free",
        "baseline_CaCl2_mM_in_PSS": 0.5,
        "peptide_preparation": "fresh physiological-saline solutions used on experiment day",
        "experiment_n_note": "reported n counts experiments, not individual imaged cells or human tasters; batch-level independence unresolved",
        "reported_uncertainty": "mean +/- SE, following general statistical methods",
        "normalization": "integrated baseline-corrected fluorescence; results may be normalized to L-Phe/R467 controls; not identical to Ohsu calcium-normalized Emax"
    }
    data["receptor_rows"].extend([
        ["R12", "SMG", "R_BROADHEAD_HEK", 1.7, "uM", "numeric"],
        ["R13", "GSH", "R_BROADHEAD_HEK", 3.9, "uM", "numeric"],
        ["R14", "GC", "R_BROADHEAD_HEK", 4.7, "uM", "numeric"],
        ["R15", "EA", "R_BROADHEAD_HEK", 4.8, "uM", "numeric"]
    ])
    data["receptor_row_uncertainty"] = {
        "R12": {"SE_uM": 0.5, "experiment_n": 4},
        "R13": {"SE_uM": 0.7, "experiment_n": 4},
        "R14": {"SE_uM": 0.9, "experiment_n": 3},
        "R15": {"SE_uM": 0.7, "experiment_n": 3}
    }
    data["additional_named_links_not_new_saltiness_rows"] = [
        {"compound": "GSH", "receptor_record": "R13", "sensory_contexts": ["S_UEDA_NACL_043", "S_UEDA_NACL_062"], "same_lot": None},
        {"compound": "EA", "receptor_record": "R15", "sensory_contexts": ["S_YANG_SS", "S_YANG_BCB"], "same_lot": None}
    ]
    data["broadhead_conditional_nonresponse"] = {
        "source": "BROADHEAD2011", "condition": "0.5mM extracellular calcium, HEK-CaR",
        "finding": "authors report tested peptides ineffective up to 100uM; not shown",
        "not_numeric_EC50_bound": True, "not_human_saltiness_inactivity": True
    }
    data["counting"].update({
        "identity_count_scope": "five named saltiness/receptor-linked identities ABU, EVG, EA, EV, GSH; excludes kokumi-only GC/ABUG and receptor-only SMG",
        "ohsu_kokumi_panel_identities_including_reference": 6,
        "broadhead_receptor_table_peptides": 4,
        "new_separate_human_saltiness_conditions_this_pass": 0,
        "independent_external_selector_validation": False
    })
    data["scope_notes"].extend([
        "Ohsu Figure2A supports thickness/taste enhancement in a NaCl-only background, not a separately rated saltiness dimension; retain evidence without relabeling.",
        "Ohsu Table2 PSE is against GSH, not NaCl. Six linked kokumi identities do not become six saltiness targets.",
        "New assay records are retained separately by protocol and locator. No assay pooling, potency averaging, rank test or calibration fit was performed.",
        "Broadhead supports calcium-dependent receptor activity in another group; parathyroid/PTH responses are not oral human saltiness.",
        "Assay conditions co-vary; cross-publication potency differences cannot be attributed to calcium alone.",
        "Scientific tests in this continuation remain zero; new work is primary evidence recovery and endpoint qualification."
    ])
    return data
