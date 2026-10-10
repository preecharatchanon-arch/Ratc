#!/usr/bin/env python3
"""Verify the complete original Stage 06 result archive against its artifact manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "evidence" / "stage06" / "source_archive" / "NEXUSII_v1.9.2_S6C_research_89d065fb5d_impl27cbbd1f_6a38ea_STAGE06_RESULTS.zip"
EXPECTED_ARCHIVE_SHA256 = "a017f8ed47b68bbff089d2b4bb823f469508340cbff3fd35f1667d0642ba2729"


def main() -> None:
    archive_hash = hashlib.file_digest(ARCHIVE.open("rb"), "sha256").hexdigest()
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise SystemExit("Stage 06 archive SHA-256 differs")
    with zipfile.ZipFile(ARCHIVE) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            raise SystemExit("Stage 06 archive has duplicate members")
        if any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name for name in names):
            raise SystemExit("Stage 06 archive has an unsafe member path")
        root = names[0].split("/", 1)[0]
        manifest_name = f"{root}/manifests/artifact_manifest.json"
        manifest = json.loads(zf.read(manifest_name))
        expected = {f"{root}/{entry['path']}": entry for entry in manifest}
        if set(names) != {manifest_name, *expected}:
            raise SystemExit("Stage 06 artifact-manifest membership differs")
        for name, entry in expected.items():
            data = zf.read(name)
            if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise SystemExit(f"Stage 06 payload differs: {name}")
        release = json.loads(zf.read(f"{root}/manifests/release_identity.json"))
    print(
        json.dumps(
            {
                "archive_sha256": archive_hash,
                "verified_payloads": len(expected),
                "implementation_revision": release["implementation_revision"],
                "scientific_code_hash": release["scientific_code_hash"],
                "claims": release["claims"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
