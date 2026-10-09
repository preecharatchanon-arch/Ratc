# FleetRoute submission supplement

The complete, original ZIP archive is preserved as byte-for-byte parts. No archive contents were edited or repacked.

## Restore the archive

Download the repository ZIP or clone it, then run `python restore_supplements.py` at the repository root. The script restores `projects/fleetroute/supplement.zip`, checks each part's checksum, checks the complete archive hash, and validates the ZIP. It does not execute notebooks or training code.

The archive parts are stored this way to fit the publishing connection's per-request size limit.

- [Part 1](archive.part01) — 10,485,760 bytes
- [Part 2](archive.part02) — 3,300,894 bytes

Full archive SHA-256:

```text
98598fd89c3b81ce934dc5fdf194b203888397431cae0db75ac715b09f585d73
```

[Restoration script](../../../restore_supplements.py) · [Manifest](manifest.json) · [Project overview](../README.md)
