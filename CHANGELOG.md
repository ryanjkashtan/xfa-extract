# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.1.0] — unreleased

Initial release.

### Added
- Detect XFA vs AcroForm-only vs no-form, and route accordingly.
- Extract the XFA `datasets` packet (both `/XFA` array and single-stream XDP shapes;
  pypdf-first with an optional pikepdf fallback).
- Parse `datasets` XML into three views from one run: nested JSON `tree`, flattened
  `path: value` map (repeating sections indexed, never collapsed), and a human-readable tree.
- Always write the raw `datasets` XML to disk for auditing.
- For AcroForm-only forms, surface `get_fields()` values and flag the common case of a
  former-XFA form whose data was exported into the `/V` layer.
- CLI (`xfa-extract`) with `--json` / `--flatten` / `--raw-out` / `--quiet` and meaningful
  exit codes (0 / 2 / 3 / 4).
- Importable library API (`locate_datasets`, `parse_datasets`, …).
