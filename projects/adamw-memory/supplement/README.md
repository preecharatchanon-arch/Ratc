# AdamW memory research supplement

The complete, original ZIP archive is preserved as byte-for-byte parts. No archive contents were edited or repacked.

## Restore the archive

Download the repository ZIP or clone it, then run `python restore_supplements.py` at the repository root. The script restores `projects/adamw-memory/supplement.zip`, checks each part's checksum, checks the complete archive hash, and validates the ZIP. It does not execute notebooks or training code.

The archive parts are stored this way to fit the publishing connection's per-request size limit.

- [Part 1](archive.part01) — 10,485,760 bytes
- [Part 2](archive.part02) — 10,485,760 bytes
- [Part 3](archive.part03) — 10,485,760 bytes
- [Part 4](archive.part04) — 10,485,760 bytes
- [Part 5](archive.part05) — 5,408,168 bytes

Full archive SHA-256:

```text
7cef3351d60e985b283ba08c07cbf545dc5000dcfd5d8c905ec5e97dd563befe
```

[Restoration script](../../../restore_supplements.py) · [Manifest](manifest.json) · [Project overview](../README.md)
