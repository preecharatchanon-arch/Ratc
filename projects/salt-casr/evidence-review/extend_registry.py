"""Attributed published observations acquired 28 October 2026; no inference."""

def extend(data):
    data["compounds"]["EA"] = {
        "identity": "gamma-glutamyl alanine", "linkage": "gamma",
        "sensory_supplier": "Peptide Biological Technology Co., Ltd., Nanjing",
        "stereochemical_material_certificate": None, "sensory_purity": None,
        "sensory_counterion": None,
        "link_scope": "same conventional named peptide, not verified identical assay/sensory material"
    }
    data["sources"]["YANG2022"] = {
        "doi": "10.1016/j.fshw.2022.06.015",
        "url": "https://www.chnfood.cn/magazineDetail/45962",
        "pdf_url": "https://bafs.ac.cn/storage/upload/fshw/FSHW2022-6-015.pdf",
        "pdf_sha256": "c32e0e8a8679942b7edc00e8bb2e0520c189cff67730a04c4b9f20fe459c20e7",
        "locator": "Sections 2.1, 2.4-2.5 p1574; Section 3.4 and Figure 5 p1578 (PDF pp2,6)",
        "access": "complete primary PDF recovered from journal-owner download link",
        "visual_review": ["Figure 5 PDF p6"],
        "human_tested_peptides": 1,
        "modeled_peptides_are_not_human_sensory_rows": True
    }
    data["sources"]["AMINO2016"] = {
        "doi": "10.1248/cpb.c16-00293",
        "url": "https://www.jstage.jst.go.jp/article/cpb/64/8/64_c16-00293/_html/-char/en",
        "pdf_url": "https://www.jstage.jst.go.jp/article/cpb/64/8/64_c16-00293/_pdf",
        "pdf_sha256": "51fd4a167fd7b9f5e1883851f42dbed375d7496c70d281a51fb50a4ea8b6cb23",
        "locator": "Tables 1-2 p1183; HEK-293 methods p1188",
        "visual_review": ["Tables 1-2 PDF p3"],
        "independent_new_receptor_data_claimed": False
    }
    data["sources"]["GIVAUDAN2009"] = {
        "publication": "US20090155440A1", "kind": "patent_report",
        "url": "https://patents.google.com/patent/US20090155440A1/en",
        "pdf_url": "https://patentimages.storage.googleapis.com/db/13/35/d075039f5d1ab2/US20090155440A1.pdf",
        "pdf_sha256": "2a9c597ab452da4293b4a326a4afa3ed57177dd595a5f46bf39b526cf62ef055",
        "locator": "Example 1a paragraphs 0065-0066, printed p6/PDF p7; general sensory methods 0061-0064 on PDF p6",
        "visual_review": ["Example 1a table PDF p7"],
        "same_experiment_family": ["WO2007042274A1", "EP1933642A1", "JP4885227B2"],
        "family_versions_are_not_replications": True,
        "measured_CaSR_in_this_source": None
    }
    data["sources"]["WU2022"] = {
        "doi": "10.1021/acs.jafc.2c03501",
        "url": "https://pubmed.ncbi.nlm.nih.gov/35984991/",
        "main_text_access": "primary abstract, not complete main article",
        "SI_doi": "10.1021/acs.jafc.2c03501.s001",
        "SI_public_api": "https://api.figshare.com/v2/articles/20520621",
        "SI_download": "https://ndownloader.figshare.com/files/36727605",
        "SI_sha256": "fe59d04b269edbaabf505bf41fa06bfe70d78dae57a8327450ae92afdf7159a8",
        "SI_bytes": 967135,
        "SI_scope": "cover and nine MS/MS figures; no sensory table or assessor ratings recovered"
    }
    data["receptor_contexts"]["R_AMINO_HEK"] = {
        "source": "AMINO2016", "species": "human", "cells": "HEK-293",
        "construct": "hCaSR in pcDNA3.1, transient transfection",
        "readout": "Calcium-4 fluorescence, FlexStation", "CaCl2_mM": 0.75,
        "pH": None, "NaCl_mM": None, "biological_replicates": None,
        "EC50_uncertainty": None,
        "range_warning": "printed activity range is not identified as a confidence interval"
    }
    data["receptor_rows"].append(["R3", "EA", "R_AMINO_HEK", 1.24, "uM", "numeric"])
    data["sensory_contexts"]["S_YANG_SS"] = {
        "source": "YANG2022", "matrix": "commercial soy sauce diluted 10-fold with boiled water",
        "NaCl_concentration": None, "total_sodium_measured": None,
        "pH": 6.5, "pH_adjustment_reagent": None,
        "peptide_final_mM": 2, "sample_temperature_C": "23 +/- 2",
        "sensory_room_temperature_C": "25 +/- 2", "sample_volume_mL": 10,
        "tasting_seconds_before_swallowing": 20, "assessors": 15,
        "age_years": "23-32", "scale_endpoints_as_printed": [0,5],
        "scale_wording": "source calls this a 5-point intensity scale; endpoints printed 0 and 5",
        "replication": "generic statement all experiments and analyses in triplicate; assessor/session/batch nesting unresolved",
        "reported_statistics": "means +/- SD and one-way ANOVA; Figure 5 stars and narrative P<0.05",
        "numeric_paired_difference_SD_SE_CI": None,
        "randomization_blinding": None, "raw_paired_ratings": None
    }
    data["sensory_contexts"]["S_YANG_BCB"] = dict(data["sensory_contexts"]["S_YANG_SS"])
    data["sensory_contexts"]["S_YANG_BCB"]["matrix"] = "commercial chicken stock powder moderately diluted, boiled 1 min, cooled; dilution factor unspecified"
    data["yang_saltiness_columns"] = ["compound", "context", "dose_mM", "reported_saltiness_score_increase", "source_reported_P"]
    data["yang_saltiness_rows"] = [
        ["EA", "S_YANG_SS", 2, 0.42, "<0.05"],
        ["EA", "S_YANG_BCB", 2, 0.37, "<0.05"]
    ]
    data["yang_transcription_note"] = "Deltas transcribed from Section 3.4; Figure 5 inspected for endpoint and ordering. Absolute scores and error bars not digitized. No SD/CI invented for differences. Other tastes remain distinct."
    data["links"].extend([
        ["S_YANG_SS", "EA", "R3", "same conventional named gamma-Glu-Ala across publications", None],
        ["S_YANG_BCB", "EA", "R3", "same conventional named gamma-Glu-Ala across publications", None]
    ])
    data["sensory_contexts"]["S_GIVAUDAN_WATER"] = {
        "source": "GIVAUDAN2009", "matrix": "aqueous NaCl", "NaCl_mM": 30,
        "pH": 6.5, "pH_adjustment_reagent": None,
        "additive_concentration_mM": 10, "total_sodium_measured": None,
        "material_counterions": None,
        "endpoint": "concentration of comparison NaCl solution judged isointense in saltiness",
        "comparison_NaCl_mM_range": [30,100],
        "exact_assessor_n": None,
        "n_reporting": "general paragraph 0063: 8-10; paragraph 0064: 6-8 except Example4 n10; Example1a exact n unresolved",
        "repeats": "general three sessions, independence and aggregation unresolved",
        "SD_SE_CI": None, "raw_paired_ratings": None,
        "sodium_caution": "sensory sample total sodium and salt form unreported; synthesis uses NaOH but amount carried into Example1a is not established"
    }
    data["givaudan_isointensity_columns"] = ["sample", "compound_as_reported", "additive_mM", "isointense_NaCl_mM"]
    data["givaudan_isointensity_rows"] = [
        [1, "reference without additive", None, 30],
        [2, "S-(alpha,beta-dicarboxyethyl)-L-cysteine", 10, 40],
        [3, "S-(alpha,beta-dicarboxyethyl) gamma-L-glutamyl-L-cysteinyl-glycine", 10, 48],
        [4, "S-(alpha,beta-dicarboxyethyl) gamma-L-glutamyl-cysteine", 10, 60],
        [5, "beta-S-(alpha,gamma-dicarboxypropyl) gamma-L-glutamyl-L-cysteinyl-glycine", 10, 48],
        [6, "S-(alpha,beta-dicarboxyethyl) gamma-L-glutamyl-cysteine ethyl ester", 10, 48],
        [7, "(S-alpha,beta-dicarboxyethyl)-cystein ethyl ester", 10, 42],
        [8, "beta-S-(carboxyethyl) gamma-L-glutamyl-L-cysteinyl-glycine", 10, 38],
        [9, "(S-alpha,beta-dicarboxyethyl)-cystein methyl ester", 10, 38]
    ]
    data["provisional_links"] = [{
        "sensory_source": "GIVAUDAN2009", "sensory_sample": 3,
        "receptor_source": "AMINO2016", "receptor_table": 2, "receptor_printed_compound": 58,
        "receptor_name": "gamma-Glu-Cys(1,2-Dicarboxyethyl)-Gly",
        "EC50_uM_as_printed_range": [5,10],
        "EC50_range_is_not_CI": True,
        "link_basis": "constitutional-name correspondence proposed; exact chemical material not verified",
        "unresolved": ["Amino Table2 abbreviation footnote instead prints S-(2,3-dicarboxymethyl)-cysteine", "configuration at added substituent stereocenter not matched", "counterion, purity and lot equivalence unknown"],
        "promoted_to_confirmed_identity": False
    }]
    data["wu_arginyl_panel"] = [
        {"gamma_Glu_repeat_n": n, "dose_mg_mL": 1.0,
         "saltiness_finding": "no significant effect reported" if n<3 else "significant increase reported",
         "finding_basis": "primary abstract", "numerical_saltiness_effect": None,
         "NaCl_concentration": None, "CaSR_activity": None,
         "not_a_binary_activity_label": True}
        for n in [1,2,3,4]
    ]
    data["counting"].update({
        "linked_peptide_identities": 3,
        "identity_count_scope": "named ABU, EVG and EA in this registry; not an exhaustive literature count or matched material lots",
        "pure_peptide_conditions_with_numerical_saltiness": 7,
        "numerical_saltiness_endpoint_values_for_named_links": 9,
        "provisional_additional_receptor_sensory_identity_links": 1,
        "givaudan_additives_in_common_dose_sensory_panel": 8,
        "givaudan_reference_rows": 1,
        "wu_pure_peptide_sensory_findings_without_CaSR": 4
    })
    data["scope_notes"].extend([
        "EA receptor measurement is existing published data; its human saltiness records expand named compound overlap but not a joint selection panel.",
        "Givaudan common-dose saltiness observations are retained despite unresolved receptor identity; missing receptor data for other additives are not inactivity.",
        "NaCl isointensity is perceived saltiness, not evidence that total sodium was reduced or that CaSR mediated the effect.",
        "Wu non-significance is not no effect or equivalence; mixture fold-changes are not assigned to individual peptides.",
        "All newly inspected evidence is exploratory/development material. No independent predictor confirmation is claimed."
    ])
    data["compounds"]["EV"] = {
        "identity": "gamma-glutamyl-valine", "linkage": "gamma",
        "sensory_supplier": "Nanjing peptide biotechnology company, as reported",
        "sensory_purity": None, "sensory_counterion": None,
        "stereochemical_material_certificate": None,
        "link_scope": "same conventional named peptide, not identical tested lots"
    }
    data["sources"]["GUO2022"] = {
        "doi": "10.7506/spkx1002-6630-20201225-288",
        "url": "https://www.spkx.net.cn/CN/10.7506/spkx1002-6630-20201225-288",
        "journal_owner_landing": "https://www.chnfood.cn/magazineDetail/1796",
        "pdf_url": "https://bafs.ac.cn/storage/upload/spkx/2022-43-3-005.pdf",
        "pdf_bytes": 3119994,
        "pdf_sha256": "da0e5e3ad516338ae5b731c15e311be878c1bf141791c04c98c6f05058f0086b",
        "locator": "Sections1.1 and1.3.1 printed pp34-35; Section1.4/2.1 p35; Figure1 p36 (PDF p4)",
        "access": "complete original primary PDF",
        "visual_review": ["Figure1 PDF p4, legend and saltiness bars"],
        "functional_receptor_assay_here": None,
        "modeling_receptors": ["T1R1", "T1R2", "T1R3"],
        "not_a_functional_CaSR_assay": True,
        "source_overlap": "substantial author and grant overlap with YANG2022; shared assessors, material batches or repeated data not established"
    }
    data["receptor_rows"].append(["R4", "EV", "R_AMINO_HEK", 1.03, "uM", "numeric"])
    data["sensory_contexts"]["S_GUO_SS"] = {
        "source": "GUO2022", "matrix": "1% v/v soy sauce solution",
        "peptide_concentration_as_reported_mM": 2,
        "dose_wording_note": "methods describe adding 2mM peptide to food solution; final mixing volumes not stated",
        "pH": 6.50, "pH_tolerance": 0.05, "pH_adjustment_reagent": None,
        "NaCl_concentration": None, "total_sodium_measured": None,
        "assessors": 11, "sex_counts_male_female": [6,5], "age_years": "21-32",
        "sensory_room_temperature_C": "23 +/- 2", "sample_volume_mL": 10,
        "tasting_seconds_before_swallowing": 25,
        "scale_endpoints_as_printed": [0,5],
        "scale_wording": "called five-point scoring, printed endpoints zero and five",
        "replication": "Section1.4 reports three parallel repeats; assessor/session/batch nesting unresolved",
        "uncertainty_reporting": "generic mean +/- SD; figure error bars; no numerical paired-error data extracted",
        "randomization_blinding": None, "raw_paired_ratings": None,
        "numeric_saltiness_effect_SD_SE_CI": None,
        "significance_test_or_numeric_P_for_saltiness": None
    }
    data["sensory_contexts"]["S_GUO_BROTH"] = dict(data["sensory_contexts"]["S_GUO_SS"])
    data["sensory_contexts"]["S_GUO_BROTH"]["matrix"] = "1% w/w chicken broth powder solution"
    data["graphical_saltiness_columns"] = ["compound", "context", "source_reported_direction", "numerical_effect", "evidence_basis"]
    data["graphical_saltiness_rows"] = [
        ["EV", "S_GUO_SS", "increase", None, "Section2.1 narrative and Figure1 saltiness group"],
        ["EV", "S_GUO_BROTH", "increase", None, "Section2.1 narrative and Figure1 saltiness group"]
    ]
    data["guo_graph_note"] = "Four labeled series depict food before/after addition. A note refers to score increases. No exact numbers are tabulated or labeled on saltiness bars; no visual estimates, effect zeros, P values or paired variances are manufactured. Kokumi is a separate category."
    data["links"].extend([
        ["S_GUO_SS", "EV", "R4", "same conventional gamma-Glu-Val identity across publications", None],
        ["S_GUO_BROTH", "EV", "R4", "same conventional gamma-Glu-Val identity across publications", None]
    ])
    data["sources"]["AMINO_ERRATUM2017"] = {
        "doi": "10.1248/cpb.c17-e6506",
        "url": "https://www.jstage.jst.go.jp/article/cpb/65/6/65_c17-e6506/_html/-char/en",
        "pdf_url": "https://www.jstage.jst.go.jp/article/cpb/65/6/65_c17-e6506/_pdf",
        "pdf_sha256": "b02f7b002fedf9de7bd83ead2e3a3deb1c73865c58ed39ad9ee1b9ffc95c2e32",
        "correction_scope": "Table1 compound20 citation and acknowledgement: gamma-Glu-Abu data from WO2010114022A1 / Seiichi Sato",
        "does_not_resolve_compound58_naming": True
    }
    data["sources"]["EP2012"]["same_experiment_family"] = ["WO2010114022A1"]
    data["sources"]["EP2012"]["family_versions_are_not_replications"] = True
    data["sources"]["AMINO2016"]["gamma_Glu_Abu_provenance"] = {
        "confirmed_by_erratum": "AMINO_ERRATUM2017",
        "original_data_source": "WO2010114022A1, same patent family as EP2012",
        "independent_Abu_receptor_replication": False
    }
    data["acquisition_status"] = {
        "pea_136988": {
            "status": "individual gamma-Glu-Val-Val sensory cell still missing",
            "openalex_metadata": "W4385190879: closed; no repository full-text location recorded",
            "datacite_related_DOI_query_records": 0,
            "interpretation": "these bounded searches do not prove no public copy or data exist",
            "group_range_not_assigned": True
        },
        "fish_sauce_thesis": {
            "status": "primary thesis identity and original panel still unrecovered",
            "official_journal_author": "GU Wenyu / 古汶玉 verified on 2019 paper",
            "thesis_author_link": "plausible, not verified",
            "new_route": "official SCAU library links to scholar.scau.edu.cn; endpoint returned 502",
            "author_patent_CN109287934A": "hydrolysate production process, not the peptide sensory panel",
            "secondary_gamma_peptide_outcomes_used_as_labels": False
        }
    }
    data["counting"].update({
        "linked_peptide_identities": 4,
        "linked_identities_with_numerical_saltiness": 3,
        "linked_identities_with_graphical_saltiness_only_in_this_registry": 1,
        "pure_peptide_conditions_with_graphical_saltiness_only": 2,
        "identity_count_scope": "named ABU, EVG, EA and EV; EV retained as graphical saltiness only. Not an exhaustive literature count or matched material lots."
    })
    data["scope_notes"].extend([
        "Guo2022 expands named overlap but is not a common-condition comparison against EA: 1% v/v soy versus Yang2022 ten-fold dilution, different assessors and tasting duration.",
        "Erratum confirms Abu receptor data reuse; it adds provenance, not an independent assay or evidence for a selector.",
        "The new Guo observations remain graphical/descriptive. Numerical condition and endpoint counts are unchanged."
    ])
    data["compounds"]["GSH"] = {
        "identity": "gamma-L-glutamyl-L-cysteinylglycine (reduced glutathione)",
        "linkage": "gamma", "sensory_supplier": "Merck & Co.",
        "sensory_processing": "10% w/v solution treated with 1% w/v activated charcoal for 30min, filtered and lyophilized for deodorization",
        "post_processing_purity_or_redox_verification": None,
        "sensory_counterion": None, "same_receptor_sensory_lot": None
    }
    data["sources"]["UEDA1997"] = {
        "doi": "10.1271/bbb.61.1977",
        "url": "https://www.jstage.jst.go.jp/article/bbb1992/61/12/61_12_1977/_article/-char/en",
        "pdf_url": "https://www.jstage.jst.go.jp/article/bbb1992/61/12/61_12_1977/_pdf",
        "pdf_sha256": "749323d3c8c95ff1e41462dfb705add65cdd35788953d4b9719fecc8f37f785e",
        "pdf_bytes": 665797,
        "locator": "Taste effects of GSH on basic taste solutions, p1977; TableIII and Results p1978 (PDF pp1-2)",
        "access": "complete four-page scanned primary PDF; OCR used for locating prose, relevant methods and table visually checked",
        "visual_review": ["PDF p1 methods", "PDF p2 TableIII"],
        "organization": "Ajinomoto Food Research and Development Laboratories",
        "source_overlap_warning": "shared organization with later receptor sources; independent sensory study is not independent validation of a CaSR selector"
    }
    data["receptor_rows"].append(["R5", "GSH", "R_AMINO_HEK", 0.7, "uM", "numeric"])
    data["sensory_contexts"]["S_UEDA_NACL_043"] = {
        "source": "UEDA1997", "matrix": "aqueous NaCl solution",
        "NaCl_as_printed_percent": 0.43,
        "GSH_as_printed_percent": 0.04,
        "percent_basis": "TableIII prints percent; basic-taste methods explicitly give w/v for sucrose but do not separately restate NaCl/GSH basis; no conversion performed",
        "pH": None,
        "pH_note": "pH7 adjustment belongs to the separate threshold subsection/TableII; not explicitly stated for TableIII PSE test",
        "total_sodium_measured": None, "pH_adjustment_reagent": None,
        "assessors": None,
        "n_note": "15 applies to threshold subsection and 20 to flavor-profile subsection; neither is assigned to basic-taste PSE without evidence",
        "comparison": "GSH-added sample paired with seven basic-tastant reference concentrations, 20% logarithmic steps",
        "readout": "point of subjective equality (PSE), probit analysis of dichotomous taste judgments",
        "time_window": None, "temperature": None,
        "randomization_blinding": None, "replication": None,
        "raw_paired_ratings": None, "PSE_CI": None,
        "source_reported_saltiness_finding": "no significant effect observed",
        "numeric_P_or_significance_threshold": None
    }
    data["sensory_contexts"]["S_UEDA_NACL_062"] = dict(data["sensory_contexts"]["S_UEDA_NACL_043"])
    data["sensory_contexts"]["S_UEDA_NACL_062"]["NaCl_as_printed_percent"] = 0.62
    data["ueda_saltiness_columns"] = ["compound", "context", "NaCl_nominal_percent", "GSH_percent", "PSE_as_printed_percent_NaCl", "source_reported_finding"]
    data["ueda_saltiness_rows"] = [
        ["GSH", "S_UEDA_NACL_043", 0.43, 0.04, 0.41, "no significant effect observed"],
        ["GSH", "S_UEDA_NACL_062", 0.62, 0.04, 0.58, "no significant effect observed"]
    ]
    data["links"].extend([
        ["S_UEDA_NACL_043", "GSH", "R5", "same named reduced glutathione across publications; different material provenance", None],
        ["S_UEDA_NACL_062", "GSH", "R5", "same named reduced glutathione across publications; different material provenance", None]
    ])
    data["counting"].update({
        "linked_peptide_identities": 5,
        "linked_identities_with_numerical_saltiness": 4,
        "pure_peptide_conditions_with_numerical_saltiness": 9,
        "numerical_saltiness_endpoint_values_for_named_links": 11,
        "numeric_count_warning": "includes two PSE concentrations, not eleven values on one common score scale",
        "identity_count_scope": "named ABU, EVG, EA, EV and GSH. EV graphical only; GSH has two reported non-significant PSE conditions. Not exhaustive or matched material lots."
    })
    data["contextual_evidence_not_compound_labels"] = [{
        "doi": "10.1021/acs.jafc.7b00897", "source": "Tang2017 primary abstract",
        "url": "https://pubmed.ncbi.nlm.nih.gov/28502176/",
        "finding": "GSH accumulation in L.sanfranciscensis sourdough bread did not enhance saltiness",
        "comparison_limitation": "fermentation changes GSH, gamma-glutamylcysteine, texture and other matrix properties; not an isolated GSH addition effect",
        "numeric_compound_response": None,
        "access": "complete primary paper not recovered; indexed university PDF returns404",
        "included_in_linked_compound_count": False
    }]
    data["scope_notes"].extend([
        "Ueda1997 adds actual non-significant saltiness conditions for a measured CaSR agonist. Non-significance is neither zero effect, equivalence nor a universal inactive-compound label.",
        "Ueda PSE concentrations remain separate from temporal score increases and cheese scores; no cross-scale pooling or inferred dose-normalized potency.",
        "TableIII PSE tests do not inherit pH or assessor n from neighboring sensory methods. Those unresolved fields are null."
    ])
    from endpoint_review import add_endpoint_review
    data = add_endpoint_review(data)
    from identity_review import add_identity_review
    return add_identity_review(data)
