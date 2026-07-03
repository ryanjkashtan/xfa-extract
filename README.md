# xfa-extract

[![PyPI version](https://img.shields.io/pypi/v/xfa-extract.svg)](https://pypi.org/project/xfa-extract/)
[![Python versions](https://img.shields.io/pypi/pyversions/xfa-extract.svg)](https://pypi.org/project/xfa-extract/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Read the entered values out of XFA / LiveCycle "dynamic" PDF forms — the ones where
`pypdf.get_fields()` comes back empty even though the form is clearly filled in.**

If you've ever hit this:

> I filled out a government PDF (an IRCC immigration form, a tax form, …), but when I run
> `PdfReader(...).get_fields()` or `pdftk dump_data_fields`, the values are **blank or
> missing**. The form *template* text extracts fine, but **none of the answers show up.**
> Or the PDF just shows *"Please wait… If this message is not eventually replaced…"*.

…then your PDF is an **XFA form**, and this tool reads it.

## Why standard extraction misses the data

A normal interactive PDF (an **AcroForm**) stores each field's value in its `/V` entry —
`pypdf`, `pdftk`, `pdfminer` all read those fine.

An **XFA form** (Adobe LiveCycle / "dynamic" PDF — what most government and immigration forms
are) does **not** keep the entered data in `/V`. It keeps it in an XML packet inside the
AcroForm dictionary under the `/XFA` key, in a sub-packet called **`datasets`**. So
`get_fields()` and text extraction look blank even on a fully completed form. `xfa-extract`
detects XFA, pulls the `datasets` packet, parses it, and gives you the field → value map.

**Read-only.** It never writes to or mutates your PDF.

## Install

```bash
pip install xfa-extract              # core (pypdf + lxml)
pip install "xfa-extract[robust]"    # + pikepdf fallback for unusual PDFs
```

## Use it — command line

```bash
xfa-extract FORM.pdf                 # human-readable tree + flat "path: value" table
xfa-extract FORM.pdf --json          # machine-readable JSON (for scripts / LLMs)
xfa-extract FORM.pdf --flatten       # just the path: value table
```

Every run also writes the raw `datasets` XML to `--raw-out` (default `./xfa_datasets.xml`)
for auditing.

```text
$ xfa-extract application.pdf --flatten
form1.PersonalInfo.Surname           Smith
form1.PersonalInfo.GivenName         Jane
form1.Dependents.Dependent[0].Name   Alex
form1.Dependents.Dependent[1].Name   Sam
```

Repeating sections (multiple dependents, applicants, addresses) are **indexed**
(`Dependent[0]`, `Dependent[1]`, …), never collapsed.

## Use it — as a library

```python
from xfa_extract import locate_datasets, parse_datasets

kind, datasets, _packets, _engine = locate_datasets("FORM.pdf")
if kind == "xfa" and datasets:
    tree, flat = parse_datasets(datasets)
    print(flat["form1.PersonalInfo.Surname"])   # -> "Smith"
```

### Understand the form's schema, not just its values

XFA forms also carry a **template** packet — the form's intelligence. `parse_template()`
turns it into a per-field schema: field kind, the human caption, a dropdown/radio's valid
values (export code ↔ display label), the expected format, and whether the field runs
scripts:

```python
from xfa_extract import parse_template, schema_for

schema = parse_template("FORM.pdf")
f = schema_for(schema, "form1.PersonalInfo.Country")
f.kind        # "choice"
f.caption     # "Country of birth or territory"
f.choices     # [("1", "Canada"), ("2", "Other")]  — datasets stores the export code
f.picture     # e.g. "date{YYYY-MM-DD}" on date fields
f.scripted    # True if the field has calculate/validate/event scripts
```

This is what lets a filler (see [`xfa-fill`](https://github.com/ryanjkashtan/xfa-fill))
accept `"Canada"` and write the `"1"` the form actually stores.

## Exit codes (the CLI tells you which case you're in)

| code | meaning | what to do |
|------|---------|------------|
| `0` | XFA data extracted (≥1 non-empty value) | use the values |
| `2` | **not XFA** — AcroForm-only or no form | use `get_fields()`; the tool prints those values for you as a convenience |
| `3` | XFA but no `datasets`, or the form is empty/unfilled | report "unfilled / no entered data" |
| `4` | parse failure | the raw XML is still written to `--raw-out` for inspection |

## Tested against real forms

Validated on synthetic fixtures (in CI) **and** 14 real-world XFA forms — IRCC IMM5257 /
1295 / 1344 / 5710 / 5669, a DHL waybill, an Indian MCA MGT-7, an Ontario lease, a US DOL
form, French CERFA — plus a real filled Canadian Proof-of-Citizenship application. Repeating
sections, namespaces, Adobe's quirky tag serialization, and base64-image-bearing datasets all
handled. See [`skill/REFERENCE.md`](skill/REFERENCE.md) for the deep dive.

## What it does **not** do

- **Fill / write** values into XFA forms — that's the job of the companion package
  [`xfa-fill`](https://github.com/ryanjkashtan/xfa-fill), which uses this package's template
  schema and read-back verification.
- **Flatten / render** XFA to static pages — different operation.
- **OCR** — these are digital forms, not scans.

## Use it with Claude / Claude Code

This repo also ships an [Agent Skill](skill/SKILL.md) so Claude Code automatically reaches
for it when a fillable PDF's values come back blank. Point Claude at `skill/`.

## License

MIT © Ryan Kashtan. See [LICENSE](LICENSE).
