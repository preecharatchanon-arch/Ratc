"""Source qualification and a separately attributed published receptor record.

Bookkeeping only: this module performs no statistical or biological test.
"""


def add_endpoint_review(data):
    data["sources"]["GOTO2016"] = {
        "doi": "10.1093/chemse/bjw066",
        "url": "https://pubmed.ncbi.nlm.nih.gov/27353260/",
        "publisher": "https://academic.oup.com/chemse/article-abstract/41/7/623/1745023",
        "institutional_record": "https://hub.hku.hk/handle/10722/227165",
        "access_scope": "primary abstract; complete original methods/results not recovered",
        "retrieval_limit": "OUP article/PDF not recovered; exact HKU record has no attached files; checked current OpenAlex locations lack an accessible PDF",
        "functional_receptor_assay_established_here": None,
        "source_overlap": "same experiment reproduced in GOTO2024; GOTO2017 is an author synopsis, not another cohort"
    }
    data["sources"]["GOTO2024"] = {
        "doi": "10.1007/978-981-99-8303-2_10",
        "url": "https://link.springer.com/chapter/10.1007/978-981-99-8303-2_10",
        "access_scope": "publisher preview, abstract and declarations; not complete chapter",
        "reproduces": "GOTO2016",
        "reproduction_license_number": "5505180007666",
        "reproduction_license_date": "2023-03-10",
        "funding_as_reported": ["HKU766212M", "HKU201103159003", "Mitsubishi Shoji Foodtech"],
        "employment_as_reported": "Yuki Ito employed by Mitsubishi Shoji Foodtech",
        "new_independent_experiment": False
    }
    data["sources"]["GOTO2017"] = {
        "citation": "Tazuko K. Goto, Brain activities by Umami: fMRI study in humans, Japanese Journal of Taste and Smell Research24(2):77-80,2017",
        "url": "https://www.srut.org/wp/wp-content/uploads/6a05c324253a1cda76e12cde08472eeb.pdf",
        "pdf_bytes": 974732,
        "pdf_sha256": "1aa386f99589337ddbc709540e7761dde074d4cd6a25d2da069385e3ca91edcb",
        "access_scope": "complete public author symposium synopsis; not original Goto2016 paper",
        "relevant_locator": "p78 discussion and p79 reference2",
        "supplies_missing_Goto_formulation_or_saltiness_table": False,
        "new_independent_experiment": False
    }
    data["sources"]["JUNG2010"] = {
        "doi": "10.1111/j.1750-3841.2009.01411.x",
        "url": "https://pubmed.ncbi.nlm.nih.gov/20492200/",
        "institutional_record": "https://snu.elsevierpure.com/en/publications/sensory-characteristics-and-consumer-acceptability-of-beef-soup-w/",
        "lab_citation_record": "https://foodbiotech.ewha.ac.kr/foodbiotech/graduate/sensory-science-thesis.do?articleNo=498177&mode=view",
        "access_scope": "primary abstract and institutional citation/abstract records; no full results table",
        "retrieval_limit": "Wiley403; SNU and Ewha records have no recovered file link; OpenAlex has DOI/PubMed only",
        "saltiness_comparison_not_recovered": True
    }
    data["sources"]["KITAJIMA2023"] = {
        "doi": "10.3390/molecules28124585",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10303012/",
        "xml_url": "https://www.ebi.ac.uk/europepmc/webservices/rest/PMC10303012/fullTextXML",
        "xml_bytes": 87947,
        "xml_sha256": "0d3014a4561ab3216f0f7599f74555aeda5e0a3671da3063cf22cc44f6995071",
        "pdf_url": "https://pdfs.semanticscholar.org/9e0d/79d9e88e74c8d3a107c1327de0c07077d4d3.pdf",
        "pdf_bytes": 1689966,
        "pdf_sha256": "08f1640b9e1005fa7617269af2e4361de271c953c4196e064c2716020dd59d7d",
        "access_scope": "complete published XML and twelve-page PDF",
        "visual_review": ["Figure2 and caption PDF p4", "assay and sensory methods PDF pp9-10"],
        "source_overlap": "Ajinomoto authors and employee sensory panel; related source organization to earlier records, not independent selector validation",
        "same_study_preprint": "https://www.preprints.org/manuscript/202305.2134",
        "Figure6B_label_issue": "caption repeats IVAH; results prose identifies IVAH-versus-IVAA comparison; no numeric comparator row reconstructed"
    }
    data["receptor_contexts"]["R_KITAJIMA_PEAK"] = {
        "source": "KITAJIMA2023", "species": "human",
        "cells": "PEAKrapid", "construct": "hCaSR cDNA in pcDNA3.1, transient transfection",
        "readout": "Calcium-5 fluorescence, FDSS/microCELL; peak deltaF/F with baseline-noise subtraction",
        "assay_buffer_as_reported_mM": {
            "NaCl": 146, "MgSO4": 1, "HEPES": 20,
            "CaCl2": 1, "probenecid": 2.5, "glucose": 1.39
        },
        "pH": 7.4, "CaCl2_mM": 1, "NaCl_mM": 146,
        "recording_seconds": 180, "recording_interval_seconds": 1,
        "controls": ["vehicle", "mock-transfected cells", "EDTA1mM", "NPS2143 20uM"],
        "curve_uncertainty_as_reported": "mean +/- SEM; numeric curve data not digitized",
        "EC50_uncertainty": None, "biological_replicates": None,
        "same_EVG_material_as_other_studies": None,
        "EC50_note": "source-reported estimate, not re-fitted or averaged with earlier assay"
    }
    data["receptor_rows"].append(["R6", "EVG", "R_KITAJIMA_PEAK", 0.167, "uM", "numeric"])
    data["endpoint_qualification"] = [
        {
            "source": "GOTO2016", "compound": "GSH",
            "matrix_established": "MSG plus NaCl solution",
            "human_n": 26, "age_years": "19-27", "female_n": 12, "male_n": 14,
            "dose": None, "dose_basis": None, "pH": None,
            "total_sodium_measured": None, "delivery_details": None,
            "established_finding": "GSH addition increases mixture taste intensity; source P<0.001",
            "separate_saltiness_effect": None, "paired_effect_uncertainty": None,
            "uncertainty_scope": "not established by available primary abstract, not proof never measured",
            "new_saltiness_condition": False
        },
        {
            "source": "JUNG2010", "compound": "GSH",
            "matrix_established": "beef soup with GSH, MSG or their mixtures",
            "established_finding": "abstract distinguishes GSH-associated beef/garlic/green-onion flavor from MSG-associated salty/sweet/MSG taste; liking separately measured",
            "dose": None, "pH": None, "human_n": None,
            "total_sodium_measured": None, "separate_GSH_saltiness_contrast": None,
            "saltiness_effect": None, "saltiness_uncertainty": None,
            "new_saltiness_condition": False
        },
        {
            "source": "KITAJIMA2023", "sensory_compound": "isovaleraldehyde (IVAH)",
            "is_target_peptide": False,
            "matrix_as_reported": "NaCl0.5% plus MSG0.1%",
            "sensory_additive_dose_as_reported": "2ppb IVAH",
            "percent_and_ppb_basis": "not normalized here",
            "sample_volume_mL": 20, "pH": None, "total_sodium_measured": None,
            "sensory_room_temperature_C": 25,
            "endpoint": "2-AFC combined most-intense umami/salty choice",
            "separately_rated_saltiness": None, "EVG_sensory_outcome": None,
            "new_saltiness_condition": False,
            "interpretation": "mechanistic/methodological context only; no target peptide saltiness label"
        }
    ]
    data["excluded_sources"] = [{
        "publication": "CN120584963A",
        "url": "https://patents.google.com/patent/CN120584963A/en",
        "inspected": "description Examples1-2",
        "actual_domain": "cat-food hydrolysate intake and feline-CaSR assay",
        "exclusion": "not a pure-peptide controlled human saltiness panel",
        "not_a_negative_activity_label": True
    }]
    data["scope_notes"].extend([
        "Goto's accessible primary evidence establishes mixture intensity; an unverified separate saltiness outcome remains missing, not negative.",
        "Goto2024 explicitly reproduces Goto2016; author synopsis and preprint versions do not supply additional independent cohorts.",
        "Kitajima2023 adds another assay-specific EVG EC50, not a new linked peptide or numerical saltiness condition. Keep R2 and R6 separate; source SEM is not an EC50 CI.",
        "No model, numerical hypothesis test, graph digitization, causal interaction estimate or power calculation was executed in this continuation."
    ])
    return data
