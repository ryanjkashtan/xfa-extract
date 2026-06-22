---
name: xfa-extract
description: >-
  Read the entered values out of XFA / LiveCycle / "dynamic" PDF forms (most government
  and immigration forms, e.g. IRCC). Use this whenever a fillable PDF's field values appear
  blank or missing after normal extraction, when pypdf get_fields() or pdftk
  dump_data_fields returns empty/sparse on a form you know is filled, when a PDF shows the
  "Please wait… if this message is not eventually replaced" page, or when a PDF has an /XFA
  entry. Extracts the values from the XFA datasets XML packet that the /V layer does not
  contain. READING ONLY — do NOT use this for filling forms (use the pdf skill) or for
  flattening/rendering.
---

# xfa-extract

Reads the **entered values** out of XFA ("dynamic" / Adobe LiveCycle) PDF forms — the kind
most government and immigration forms are (e.g. IRCC). Standard field extraction misses
these values because XFA does not store them in the `/V` layer; it keeps them in an XML
`datasets` packet under `/AcroForm /XFA`. This skill detects XFA, pulls that packet, parses
it, and emits the field → value mapping plus the raw XML.

**Reading only. Never mutates the source PDF.**

## When to use it (detect-and-route)

Reach for this skill when **standard field extraction comes back empty or sparse on a form
you know is filled.** Concretely:

1. Run normal extraction first — `pypdf.get_fields()` (or the `pdf-reading` skill).
2. If that returns **empty/sparse values** *and* the PDF has an **`/XFA`** entry under its
   AcroForm (or it opened to a "Please wait… if this message is not eventually replaced"
   page), the data is in the XFA datasets packet. Run this skill.
3. If `get_fields()` returns real values, it's a plain AcroForm — you're done; don't use
   this skill.

`extract_xfa.py` performs that detection itself and tells you which case you're in via its
exit code, so when in doubt you can just run it.

## How to run it

Install once (`pip install xfa-extract`), then invoke the `xfa-extract` command:

```bash
xfa-extract FORM.pdf [--json] [--flatten] [--raw-out PATH] [--quiet]
```

- **(no flags)** — human-readable indented tree **and** a flattened `path: value` table;
  also writes the raw datasets XML to `--raw-out` (default `./xfa_datasets.xml`).
- **`--json`** — emit only the JSON object (below) to stdout. **Use this when you (Claude)
  are consuming the result.**
- **`--flatten`** — print only the `path: value` table.
- **`--raw-out PATH`** — where to write the raw datasets XML (always written when present).
- **`--quiet`** — suppress the informational notes on stderr.

Install: `pip install xfa-extract` (add `pikepdf` via `pip install "xfa-extract[robust]"` for
the robust fallback on unusual PDFs). Equivalent: `python -m xfa_extract.cli FORM.pdf`.

### Exit codes — branch on these

| code | meaning | what to do |
|------|---------|------------|
| `0` | XFA data extracted (≥1 non-empty value) | use the values |
| `2` | **not XFA** — AcroForm-only or no form | use standard `get_fields()` / the `pdf-reading` skill (this skill prints the AcroForm values too, as a convenience) |
| `3` | XFA but no `datasets` packet, or form is empty/unfilled | report "form is unfilled / has no entered data" |
| `4` | parse failure | raw XML was still written to `--raw-out` — inspect it by hand |

### JSON output shape (`--json`, exit 0)

```json
{
  "form_kind": "xfa",
  "source": "form.pdf",
  "tree":  { "form1": { "PersonalInfo": { "Surname": "Smith" }, "Dependents": { "Dependent": [ {"Name": "Alex"}, {"Name": "Sam"} ] } } },
  "flat":  { "form1.PersonalInfo.Surname": "Smith", "form1.Dependents.Dependent[0].Name": "Alex" },
  "field_count": 11,
  "filled_count": 10,
  "raw_datasets_path": "./xfa_datasets.xml"
}
```

`tree` mirrors the XML hierarchy: a string is a leaf value, a dict is a group, and a **list**
is a repeating section (multiple dependents/applicants). `flat` renders repeats as
`parent.child[0]`, `parent.child[1]`, … — repeats are indexed, never collapsed.

## Notes / gotchas

- **Checkbox & radio values are surfaced raw** (often the export value or `1`/`0`).
  Interpreting them into human captions needs the `template` packet — out of scope for v1;
  see `REFERENCE.md`.
- **Hybrid forms** (both `/V` and `/XFA` populated): the **XFA datasets packet is
  authoritative** — that's what this skill reads.
- **Former-XFA forms exported to AcroForm.** Some filled IRCC forms come back as
  `form_kind="acroform"` (exit 2) with **XFA-style field names** like
  `CIT_0001[0].page1[0].section4[0].DOB[0]` and `NeedAppearances=true`. That means a dynamic
  XFA form was filled and its data exported down into the `/V` layer while the `/XFA` packet
  was stripped. The skill flags this and the values come through `get_fields()` — but note a
  plain `extract_text()` will return the blank template only, so **use the field values, not
  text extraction.**
- Always check the **raw datasets XML** (`raw_datasets_path`) if a value looks wrong; it's
  the unmodified source of truth.

## Relationship to neighboring skills

- **Complements `pdf-reading`** (standard `get_fields()` extraction). This skill is the
  fallback for the specific case standard extraction can't handle: XFA dynamic forms.
- **Defers all form *filling / creation* to the `pdf` skill.** Writing values into an XFA
  form is fragile and is deliberately not attempted here.
- **Explicitly out of scope:** filling, flattening/rendering to static pages, OCR. This
  skill only *reads entered data* from an XFA form.

For XFA internals, the `/XFA` packet layout, and edge-case handling, see `REFERENCE.md`.
