"""Restore the two frozen ZIP archives from verified local parts.

Download the repository ZIP (or clone it), then run:
    python restore_supplements.py

This joins bytes and validates checksums. It never executes archive contents.
"""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parent

def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def restore(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    target = manifest_path.parent.parent / manifest["archive_name"]
    if target.exists():
        if file_sha(target) != manifest["sha256"]:
            raise FileExistsError(f"Refusing to replace a different existing file: {target}")
        print(f"Already verified: {target.relative_to(ROOT)}")
        return
    tmp_path = None
    try:
        h = hashlib.sha256()
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
            tmp_path = Path(output.name)
            for part in manifest["parts"]:
                source = manifest_path.parent / part["name"]
                if source.stat().st_size != part["bytes"] or file_sha(source) != part["sha256"]:
                    raise ValueError(f"Part integrity check failed: {source}")
                with source.open("rb") as f:
                    for block in iter(lambda: f.read(1024 * 1024), b""):
                        output.write(block)
                        h.update(block)
        if tmp_path.stat().st_size != manifest["bytes"] or h.hexdigest() != manifest["sha256"]:
            raise ValueError("Reconstructed archive does not match its frozen identity")
        with zipfile.ZipFile(tmp_path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ValueError(f"ZIP integrity check failed: {bad}")
        os.replace(tmp_path, target)
        tmp_path = None
        print(f"Restored and verified: {target.relative_to(ROOT)}")
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

if __name__ == "__main__":
    for project in ("fleetroute", "adamw-memory"):
        restore(ROOT / "projects" / project / "supplement" / "manifest.json")
