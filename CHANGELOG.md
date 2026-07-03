# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/); this project adheres to
[Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-07-02

Template-aware release: the package can now parse the XFA *template* packet — the form's
schema — in addition to the datasets values.

### Added
- `xfa_extract.template`: `parse_template(pdf)` returns `{som_path: Field}` describing every
  fillable field — kind (text/checkbox/radio/choice/date/numeric/…), human caption, choice
  export↔display value pairs, format picture (e.g. `date{YYYY-MM-DD}`), and
  calculate/validate/event-script flags. `schema_for(schema, datasets_path)` looks a field up
  from a datasets path (strips `[n]` repeat indices).
- `xfa_extract.xmlutil`: small public XML helpers — `localname`, `namespace`,
  `find_data_element`, `XFA_DATA_NS` — promoted from private `cli` internals so downstream
  packages (e.g. `xfa-fill`) have a stable import surface.
- All of the above exported from the package top level.

### Changed
- `cli.py` re-imports the moved helpers under their old private names, so existing
  `from xfa_extract.cli import _localname, _find_data_element` code keeps working.

## [0.1.0] — 2026-06-22

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
