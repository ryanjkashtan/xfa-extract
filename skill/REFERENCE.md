# REFERENCE — XFA internals & edge cases

Deep background for `xfa-extract`. You do not need this to *run* the skill (see `SKILL.md`);
read it when a form behaves oddly, a value looks wrong, or you're extending the parser.

## 1. AcroForm vs XFA — where the data actually lives

A PDF interactive form comes in two flavours:

- **AcroForm** ("static" interactive PDF). Each field is a dictionary with the entered value
  in its **`/V`** entry. `pypdf.get_fields()` and `pdftk dump_data_fields` read these. This
  is the common case and this skill deliberately does **not** reinvent it.
- **XFA** (Adobe LiveCycle / "dynamic" PDF). The form template *and the entered data* live
  in an XML bundle (XDP) stored under **`/Root /AcroForm /XFA`**. The entered data is in a
  sub-packet named **`datasets`**. The `/V` layer is usually empty or stale, so ordinary
  extraction reports blanks even on a fully completed form. Most government / immigration
  forms (e.g. IRCC) are XFA. The giveaway when opened in a non-Adobe viewer is the purple
  **"Please wait… If this message is not eventually replaced…"** placeholder page.

This skill exists for the XFA case: the data is *there*, just not where standard tools look.

## 2. The `/XFA` entry — two physical shapes

`/Root /AcroForm /XFA` is one of:

1. **Array of alternating `name, stream` pairs** (most common):

   ```
   [ "preamble" <stream>  "config" <stream>  "template" <stream>
     "datasets" <stream>  "postamble" <stream> ... ]
   ```

   The entered data is the stream named **`datasets`**. Other packets: `template` (field
   layout + captions), `config` (processing instructions), `xmpmeta`, `sourceSet`, etc.

2. **A single stream** containing the whole XDP document, i.e.
   `<xdp:xdp> … <xfa:datasets> … </xdp:xdp>`. Here `datasets` is an *element* inside the one
   stream rather than its own array entry.

`extract_xfa.py` handles both: for the array it grabs the `datasets` stream bytes; for the
single stream it hands the whole XDP to the parser, which then *locates* the data container
(next section). Either way the raw bytes written to `--raw-out` are unmodified.

**Resolution engine.** pypdf is tried first. pikepdf is the fallback, used when pypdf raises
on open/resolve or reports XFA present but the `datasets` stream won't resolve to bytes.
pikepdf is an optional dependency — without it you simply lose the fallback path.

## 3. The datasets XML — namespaces and structure

```xml
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
  <xfa:data>
    <form1>
      <PersonalInfo>
        <Surname>Smith</Surname>
        ...
```

- The root is `<xfa:datasets>` in the namespace **`http://www.xfa.org/schema/xfa-data/1.0/`**
  (matched exactly). It contains **`<xfa:data>`**. **Everything under `xfa:data` is the
  user's form data.**
- The form-data nodes *under* `xfa:data` are typically in **no namespace** (or a
  form-defined default), so the parser walks them by **local name only**
  (`tag.split('}')[-1]`), ignoring any prefix — structure is preserved, prefixes are not.
- **Single-stream / whole-XDP inputs:** the parser searches for the data container in this
  order — an element with local name `data` in the xfa-data NS → any element named `data` →
  if the root itself is `datasets`, its children → otherwise the root (when it isn't
  `xdp`/`template`/`config`). This is why both `/XFA` shapes converge on the same output.

### Leaf values, empties, repeats

- **Leaf** (no element children) → its text is the value. Text that is empty or only
  whitespace becomes `""`; genuine text is preserved verbatim (not trimmed).
- **Repeating sections** — the same tag appearing ≥2 times under one parent (multiple
  dependents, applicants, addresses) — are **indexed, never collapsed**: `tree` holds a
  list, `flat` emits `parent.child[0]`, `parent.child[1]`, … A tag appearing once stays a
  single node, not a 1-element list.
- **Encoding** — raw packet *bytes* go straight to `lxml` so the XML declaration / BOM drive
  decoding. Pre-decoding to `str` would make lxml reject any packet that declares an
  encoding ("Unicode strings with encoding declaration are not supported").

## 4. Checkboxes, radios, and captions

The datasets packet stores **data values, not human captions**. A checkbox surfaces as its
*export value* (e.g. `1`, `0`, `Yes`, an option code) — not the question text. Mapping
`form1.Section8.Parent1.Surname` → "Applicant surname", or a radio's `1` → "Married",
requires the **`template`** packet, which holds the field captions and bind definitions.

Since 0.2.0 the package parses that packet: `parse_template(pdf)` returns
`{som_path: Field}` where each `Field` carries `kind` (text/checkbox/radio/choice/date/…),
`caption`, `choices` (export↔display pairs), `picture` (format mask), and `scripts`
(calculate/validate/event flags); `schema_for(schema, datasets_path)` looks up a field from a
datasets path by stripping its `[n]` repeat indices. The datasets views still surface raw
values faithfully — the schema is how you interpret them.

## 5. Edge cases the parser handles (BUILD §4)

| case | behaviour |
|------|-----------|
| `/XFA` array vs single stream | both; single-stream located inside the XDP |
| no `/AcroForm` | `form_kind="none"`, exit 2 |
| AcroForm without `/XFA` | exit 2; also prints `get_fields()` values as a convenience |
| XFA present, `datasets` missing/empty | exit 3, clean message, no crash |
| namespaces | data/datasets matched on the xfa-data NS; form nodes walked by local name |
| repeating nodes | indexed `[0]`, `[1]`, … — never collapsed |
| encoding / BOM | bytes → lxml; XML declaration honoured |
| hybrid AcroForm + XFA | XFA datasets is authoritative (what we read) |
| malformed XML | `recover=True` repairs mild damage; unrecoverable → raw written, exit 4 |
| deep nesting | depth-guarded recursion (`MAX_DEPTH`), won't blow the stack |

### "Recovered" vs "failed" parses

`lxml`'s `recover=True` deliberately repairs mild corruption (a truncated tail, a mismatched
end tag) and still extracts the data — that's a feature, not a silent error. Exit **4** is
reserved for input that yields **no parseable root at all** (e.g. binary garbage); in that
case the raw bytes are written to `--raw-out` first so a human can eyeball them.

## 6. Why reading-only

Writing values *into* an XFA form means editing the datasets XML, re-serialising, and often
reconciling the `template`/`config` packets and the `/V` layer so Adobe re-renders correctly
— fragile, and the failure mode on a legal/immigration document is bad. Form filling is
deferred to the `pdf` skill. Flattening/rendering and OCR are different operations and out of
scope. This skill does one thing: read entered data out of an XFA form.

## 7. Quick manual probe

To eyeball whether a PDF is XFA without the skill:

```python
from pypdf import PdfReader
acro = PdfReader("FORM.pdf").trailer["/Root"].get("/AcroForm")
print("XFA" if acro and acro.get_object().get("/XFA") is not None else "AcroForm/none")
```

If that prints `XFA`, standard `get_fields()` will under-report and you want this skill.

## 8. Real-world field notes (observed on live forms)

Validated against 14 real XFA PDFs (IRCC IMM5257/1295/1344/5710/5669, a DHL waybill, an
Indian MCA MGT-7, an Ontario lease, a US DOL form, French CERFA, etc.). What turned up:

- **Adobe's serialization puts a newline before each tag's `>`** — the datasets stream looks
  like `<AdultFlag\n>false</AdultFlag\n>`, not `<AdultFlag>false</AdultFlag>`. `lxml` parses
  this correctly; a naïve `grep`/regex over the raw XML will *miss* values. This is a
  concrete reason the skill parses rather than pattern-matches — don't "verify" output by
  grepping the raw file.
- **Root structure varies.** Most forms wrap data in `<form1>` (so paths read
  `form1.Page1.…`); some put values straight under `<xfa:data>` (the MGT-7 form yields
  `data.PGCOUNT`, `data.VERSION`, …). The data-locator (§3) handles both.
- **Some forms embed base64 image blobs as datasets values** (e.g. an Ontario lease's
  `…guideStdLease.ul.li[17].item_imageF` is a full JPEG). These are legitimately part of the
  datasets, so they're extracted faithfully — but the **human-readable views truncate long
  values** to `first-80-chars… (N chars)`. The `--json` output and the raw XML keep the
  complete value.
- **`xfa:dataNode="dataGroup"`** marks an empty container group; such elements parse to empty
  leaves and are correctly counted as *unfilled* (they contribute to `field_count` but not
  `filled_count`). A form that is all `dataGroup`/empty elements is a blank form → exit 3.
- **Blank government forms ship with a few default values** (e.g. `FormVersion`,
  `AdultFlag=false`, phone-type flags `0`). So a freshly downloaded "empty" IRCC form may
  report a handful of filled fields (exit 0) rather than exit 3 — those are real datasets
  values, just form defaults rather than user input.
