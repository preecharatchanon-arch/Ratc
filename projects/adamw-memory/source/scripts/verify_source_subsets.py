#!/usr/bin/env python3
"""Verify every compact saved-output payload against its original archive manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    reports = []
    for stage in (10, 12, 13):
        base = ROOT / "evidence" / f"stage{stage}" / "original_compact"
        manifest_path = base / "ORIGINAL_SELECTION_MANIFEST.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = {item["path"]: item for item in manifest["selected_files"]}
        actual = {
            p.relative_to(base).as_posix(): p
            for p in base.rglob("*")
            if p.is_file() and p != manifest_path
        }
        if set(actual) != set(expected):
            missing = sorted(set(expected) - set(actual))
            extra = sorted(set(actual) - set(expected))
            raise SystemExit(f"stage {stage} membership mismatch; missing={missing}; extra={extra}")
        total = 0
        for name, path in actual.items():
            posix = PurePosixPath(name)
            if posix.is_absolute() or ".." in posix.parts or "\\" in name:
                raise SystemExit(f"unsafe path: {name}")
            entry = expected[name]
            size = path.stat().st_size
            if size != entry["bytes"] or digest(path) != entry["sha256"]:
                raise SystemExit(f"stage {stage} verification failed: {name}")
            total += size
        if total != manifest["selected_bytes"]:
            raise SystemExit(f"stage {stage} selected byte count differs")
        reports.append(
            {
                "stage": stage,
                "files": len(actual),
                "bytes": total,
                "source_archive": manifest["source_archive"],
                "source_archive_sha256": manifest["source_archive_sha256"],
            }
        )
    print(json.dumps({"verified": reports}, indent=2))


if __name__ == "__main__":
    main()
