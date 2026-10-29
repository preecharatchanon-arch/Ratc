"""Preserve source-specific identity uncertainty and actual panel coverage.

This is evidence bookkeeping, not a numerical scientific test.
"""


def add_identity_review(data):
    data["sources"]["TSUBOI1999"] = {
        "doi": "10.1248/bpb.22.21",
        "url": "https://www.jstage.jst.go.jp/article/bpb1993/22/1/22_1_21/_pdf",
        "pdf_bytes": 811516,
        "pdf_sha256": "60922a2fd143ab4e1545fc9b62454885a887dabcccbf15bfd6bb9d122106929b",
        "access_scope": "complete five-page original scan; OCR for locating prose",
        "visual_review": ["Figure1 p21", "Chemicals subsection p22"],
        "identity_connectivity_as_drawn": "GSH-S-CH(COOH)-CH2-COOH",
        "added_carbon_stereochemistry_assigned_in_figure": False,
        "DCE_GS_standard_supplier_as_reported": "Senjyu Pharmaceutical Ind., Osaka, Japan",
        "linked_to_Amino_compound58_material": None,
        "linked_to_Givaudan_sensory_lot": None,
        "used_as_receptor_or_saltiness_observation": False
    }
    data["sources"]["AMINO2016"].update({
        "publisher_landing": "https://www.jstage.jst.go.jp/article/cpb/64/8/64_c16-00293/_article/-char/en",
        "publisher_supplement_count_at_review": 0,
        "compound58_specific_synthesis_or_spectrum_recovered": False,
        "compound58_figure_structure_recovered": False,
        "general_CaSR_material_purity_criterion_percent": 95,
        "purity_note": "general method criterion, not a disclosed compound58 analytical result or certificate"
    })
    link = data["provisional_links"][0]
    link.update({
        "identity_review_status": "bounded source audit complete; remains provisional; reopen only with compound-specific primary documentation",
        "new_support": "patent-cited Tsuboi1999 Figure1 supports intended DCE-GSH connectivity, not assay-material identity",
        "footnote_conflict_visually_reconfirmed": True,
        "constitutional_interpretation": "succinate-thioether intended-name correspondence supported, but internal receptor-source name conflict uncorrected",
        "stereochemical_or_lot_match_established": False,
        "promoted_to_confirmed_identity": False
    })
    status = {
        2: (False, "missing", "single modified cysteine, not gamma-Glu-Cys"),
        3: (True, "provisional", "Amino2016 compound58 internal name conflict and unmatched material"),
        4: (True, "missing", "dicarboxyethyl substituent differs from unmodified gamma-Glu-Cys"),
        5: (True, "missing", "dicarboxypropyl form is not dicarboxyethyl"),
        6: (True, "missing", "modified dipeptide ester cannot borrow another compound's potency"),
        7: (False, "missing", "single modified cysteine ethyl ester"),
        8: (True, "missing", "carboxyethyl-GSH differs from Amino carboxymethyl gamma-Glu-Cys"),
        9: (False, "missing", "single modified cysteine methyl ester")
    }
    data["givaudan_receptor_coverage"] = []
    for sample, name, dose, isointensity in data["givaudan_isointensity_rows"]:
        if sample == 1:
            continue
        peptide, match, reason = status[sample]
        data["givaudan_receptor_coverage"].append({
            "sample": sample, "compound_as_reported": name,
            "contains_peptide_backbone": peptide,
            "functional_CaSR_match_status_in_inspected_sources": match,
            "match_note": reason,
            "confirmed_numeric_CaSR_value": None,
            "missing_is_not_inactive": True
        })
    data["givaudan_panel_qualification"] = {
        "additives": 8, "peptide_backbone_additives": 5,
        "background_reference_rows": 1,
        "confirmed_receptor_matches": 0, "provisional_receptor_matches": 1,
        "missing_receptor_records_for_other_additives": 7,
        "candidate_sampling_frame_documented": False,
        "source_reports_all_additives_as_salt_enhancing": True,
        "usable_selector_panel": False,
        "coverage_scope": "published sources inspected here; not proof of universal absence"
    }
    data["sources"]["WU2022"].update({
        "new_access_check": "OpenAlexW4292393486 has DOI/PubMed locations only; bounded institutional/title searches found no manuscript",
        "official_author_profile": "https://www.qztc.edu.cn/hyyspxy/_t5/2025/0929/c6100a287991/page.htm",
        "author_listed_application": "CN202110379878.0",
        "application_resolves_to": "CN113080426A, already excluded lactoyl branch; not new gamma-Glu/Arg evidence",
        "main_full_text_recovered": False,
        "CaSR_absence_in_entire_paper_established": False,
        "next_source_action": "only assess a newly available legitimate main-text copy; do not repeat checked endpoints"
    })
    data["scope_notes"].extend([
        "Tsuboi's DCE-GSH structure supports intended connectivity but does not repair Amino compound58's contradictory footnote or establish stereochemical/material equivalence.",
        "Givaudan has eight additives, five containing peptide backbones. Missing receptor measurements remain missing; neighboring structural analogues do not supply potency labels.",
        "The identity branch is closed pending compound-specific primary evidence. No new saltiness outcome, linked compound, predictor validation or scientific test is added."
    ])
    return data
