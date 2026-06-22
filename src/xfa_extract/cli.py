#!/usr/bin/env python3
"""extract_xfa.py — read the entered values out of XFA / LiveCycle "dynamic" PDF forms.

A normal interactive PDF (an AcroForm) stores each field's value as a /V entry, which
pypdf.get_fields() and pdftk read fine. An XFA form (Adobe LiveCycle / "dynamic" PDF — most
government / immigration forms, e.g. IRCC) keeps the entered data in an XML packet under
/AcroForm /XFA, in a sub-packet named `datasets`. So get_fields() looks blank even though
the form is filled. This tool detects XFA, pulls the `datasets` packet, parses it, and emits
field -> value mappings plus the raw XML for auditing.

READING ONLY. Never mutates the source PDF. See SKILL.md / REFERENCE.md for context.

Exit codes:
    0  success — XFA data extracted (at least one non-empty value)
    2  not XFA — AcroForm-only or no form at all; use standard get_fields()
    3  XFA but no `datasets` packet, or the form is empty / unfilled
    4  parse failure — raw XML written to --raw-out, but no parseable root
"""
from __future__ import annotations

import argparse
import json
import sys

# The xfa-data namespace URI is fixed by the XFA spec; match on it exactly.
XFA_DATA_NS = "http://www.xfa.org/schema/xfa-data/1.0/"

# Guard against pathological nesting (§4.10) — real forms are nowhere near this deep.
MAX_DEPTH = 400


# --------------------------------------------------------------------------------------
# Locating the /XFA datasets packet
# --------------------------------------------------------------------------------------

def _packets_from_pypdf_array(xfa) -> dict:
    """Walk an /XFA array of alternating (name, stream) pairs into {name: bytes}."""
    packets = {}
    it = iter(xfa)
    for name in it:
        try:
            stream = next(it)
        except StopIteration:
            break  # odd-length array — tolerate it
        try:
            packets[str(name)] = stream.get_object().get_data()
        except Exception:
            continue  # a single unreadable packet shouldn't sink the rest
    return packets


def get_datasets_via_pypdf(pdf_path: str):
    """Returns (form_kind, datasets_bytes, packets). form_kind in {xfa, acroform, none}."""
    from pypdf import PdfReader
    from pypdf.generic import ArrayObject

    reader = PdfReader(pdf_path)
    root = reader.trailer["/Root"]
    acro = root.get("/AcroForm")
    if acro is None:
        return ("none", None, {})
    acro = acro.get_object()
    xfa = acro.get("/XFA")
    if xfa is None:
        return ("acroform", None, {})
    xfa = xfa.get_object()

    if isinstance(xfa, ArrayObject):
        packets = _packets_from_pypdf_array(xfa)
        return ("xfa", packets.get("datasets"), packets)
    # single XDP stream — the datasets element lives inside it
    data = xfa.get_data()
    return ("xfa", data, {"__xdp__": data})


def get_datasets_via_pikepdf(pdf_path: str):
    """pikepdf fallback for raw object/stream access on weird PDFs."""
    import pikepdf

    with pikepdf.open(pdf_path) as pdf:
        try:
            acro = pdf.Root.AcroForm
        except (AttributeError, KeyError):
            return ("none", None, {})
        try:
            xfa = acro.XFA
        except (AttributeError, KeyError):
            return ("acroform", None, {})

        if isinstance(xfa, pikepdf.Array):
            packets = {}
            items = list(xfa)
            i = 0
            while i + 1 < len(items):
                try:
                    packets[str(items[i])] = bytes(items[i + 1].read_bytes())
                except Exception:
                    pass
                i += 2
            return ("xfa", packets.get("datasets"), packets)
        data = bytes(xfa.read_bytes())
        return ("xfa", data, {"__xdp__": data})


def locate_datasets(pdf_path: str):
    """pypdf-first, pikepdf-fallback resolution of the datasets packet.

    Returns (form_kind, datasets_bytes, packets, engine).
    """
    try:
        kind, datasets, packets = get_datasets_via_pypdf(pdf_path)
        engine = "pypdf"
    except Exception as exc:  # corrupt enough that pypdf can't even open it
        kind, datasets, packets, engine = None, None, {}, None
        pypdf_error = exc
    else:
        pypdf_error = None

    # Fall back to pikepdf when pypdf failed outright, or found XFA but couldn't
    # resolve the datasets stream to bytes (§7).
    needs_fallback = kind is None or (kind == "xfa" and datasets is None)
    if needs_fallback:
        try:
            import pikepdf  # noqa: F401
            k2, d2, p2 = get_datasets_via_pikepdf(pdf_path)
            if kind is None or d2 is not None:
                return (k2, d2, p2, "pikepdf")
        except ImportError:
            if kind is None:
                raise RuntimeError(
                    f"pypdf could not open {pdf_path!r} ({pypdf_error}); install pikepdf "
                    "for the robust fallback."
                )
        except Exception:
            if kind is None:
                raise
    return (kind, datasets, packets, engine)


# --------------------------------------------------------------------------------------
# Parsing datasets XML -> field map
# --------------------------------------------------------------------------------------

def _localname(el) -> "str | None":
    tag = el.tag
    if not isinstance(tag, str):
        return None  # comment / processing-instruction
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def _namespace(el) -> "str | None":
    tag = el.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


def _find_data_element(root):
    """Find the <xfa:data> container regardless of whether we were handed a bare
    datasets packet or a whole XDP document (refinement #2)."""
    for el in root.iter():
        if _localname(el) == "data" and _namespace(el) == XFA_DATA_NS:
            return el
    for el in root.iter():
        if _localname(el) == "data":
            return el
    if _localname(root) == "datasets":
        return root  # no explicit <data> — treat datasets children as data
    if _localname(root) not in ("xdp", "template", "config"):
        return root  # someone handed us the data subtree directly
    return None


def element_to_node(el, depth: int = 0):
    """str for a leaf, dict for a group, list when a tag repeats under one parent."""
    if depth > MAX_DEPTH:
        return "...<max depth exceeded>..."
    children = [c for c in el if isinstance(c.tag, str)]
    if not children:
        text = el.text or ""
        return text if text.strip() else ""

    groups: dict = {}
    order = []
    for c in children:
        name = _localname(c)
        if name not in groups:
            groups[name] = []
            order.append(name)
        groups[name].append(c)

    node: dict = {}
    for name in order:
        els = groups[name]
        if len(els) == 1:
            node[name] = element_to_node(els[0], depth + 1)
        else:
            node[name] = [element_to_node(e, depth + 1) for e in els]
    return node


def flatten(node, out: dict, prefix: str = "") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            flatten(value, out, f"{prefix}.{key}" if prefix else key)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            flatten(item, out, f"{prefix}[{i}]")
    else:
        out[prefix] = node


def parse_datasets(datasets_bytes: bytes):
    """Returns (tree, flat) or raises ValueError when there's no parseable root."""
    from lxml import etree

    parser = etree.XMLParser(recover=True, ns_clean=True, resolve_entities=False)
    root = etree.fromstring(datasets_bytes, parser=parser)
    if root is None:
        raise ValueError("no parseable XML root (datasets packet is unrecoverable)")

    data_el = _find_data_element(root)
    if data_el is None:
        return ({}, {})
    tree = element_to_node(data_el)
    if not isinstance(tree, dict):  # data node held bare text — wrap it
        tree = {"value": tree}
    flat: dict = {}
    flatten(tree, flat)
    return (tree, flat)


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------

def _display(value, limit: int = 80) -> str:
    """Human-view rendering of a leaf value: collapse internal whitespace/newlines to keep
    one field per line, and truncate very long values (e.g. base64 images some XFA forms
    embed in the datasets, which arrive with embedded line breaks). The --json output and
    the raw XML keep the full, faithful value."""
    if value == "":
        return "(empty)"
    raw = str(value)
    s = " ".join(raw.split())  # one physical line, no matter how the value was wrapped
    return f"{s[:limit]}… ({len(raw)} chars)" if len(s) > limit else s


def render_human_tree(node, lines: list, key=None, indent: int = 0) -> None:
    pad = "  " * indent
    if isinstance(node, dict):
        child_indent = indent
        if key is not None:
            lines.append(f"{pad}{key}:")
            child_indent = indent + 1
        for k, v in node.items():
            render_human_tree(v, lines, k, child_indent)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            render_human_tree(item, lines, f"{key}[{i}]", indent)
    else:
        lines.append(f"{pad}{key}: {_display(node)}")


def render_flat_table(flat: dict) -> str:
    if not flat:
        return "(no fields)"
    width = max(len(k) for k in flat)
    return "\n".join(f"{k.ljust(width)}  {_display(v)}" for k, v in flat.items())


# --------------------------------------------------------------------------------------
# AcroForm fallback values (so a non-XFA caller isn't left empty-handed)
# --------------------------------------------------------------------------------------

def read_acroform_fields(pdf_path: str) -> dict:
    try:
        from pypdf import PdfReader

        fields = PdfReader(pdf_path).get_fields()
        if not fields:
            return {}
        out = {}
        for name, fobj in fields.items():
            value = fobj.get("/V") if hasattr(fobj, "get") else None
            out[str(name)] = "" if value is None else str(value)
        return out
    except Exception:
        return {}


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _emit(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, file=sys.stderr)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Extract entered values from XFA / LiveCycle dynamic PDF forms (read-only)."
    )
    ap.add_argument("pdf", help="path to the PDF form")
    ap.add_argument("--json", action="store_true", help="emit only the JSON object to stdout")
    ap.add_argument("--flatten", action="store_true", help="print only the path: value table")
    ap.add_argument("--raw-out", default="./xfa_datasets.xml",
                    help="where to write the raw datasets XML (default ./xfa_datasets.xml)")
    ap.add_argument("--quiet", action="store_true", help="suppress informational notes on stderr")
    args = ap.parse_args(argv)

    try:
        kind, datasets, _packets, engine = locate_datasets(args.pdf)
    except FileNotFoundError:
        print(f"error: file not found: {args.pdf}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"error: could not open PDF: {exc}", file=sys.stderr)
        return 4

    # ---- not XFA: AcroForm-only or no form at all (exit 2) -------------------------
    if kind in ("acroform", "none"):
        af_fields = read_acroform_fields(args.pdf) if kind == "acroform" else {}
        # XFA SOM-style names (e.g. form1[0].page1[0].field[0]) on an AcroForm usually mean
        # a dynamic XFA form whose data was exported into the /V layer (XFA packet stripped).
        looks_exfa = sum(1 for k in af_fields if "[" in k and "]" in k) >= max(3, len(af_fields) // 4)
        if kind == "acroform":
            note = ("AcroForm form — values are in the /V layer; standard get_fields() reads "
                    "them (below). XFA datasets extraction does not apply.")
            if looks_exfa:
                note += (" NOTE: field names look like XFA SOM expressions — this is likely a "
                         "dynamic XFA form whose data was exported into the AcroForm /V layer. "
                         "A plain text extraction would MISS these values; use the field values "
                         "here (get_fields), not extract_text().")
        else:
            note = "No /AcroForm — this PDF has no interactive form data."
        filled = sum(1 for v in af_fields.values() if str(v).strip())
        if args.json:
            print(json.dumps(
                {"form_kind": kind, "source": args.pdf, "note": note,
                 "field_count": len(af_fields), "filled_count": filled,
                 "acroform_fields": af_fields},
                indent=2, ensure_ascii=False))
        else:
            _emit(f"[{kind}] {note}", args.quiet)
            if af_fields and not args.flatten:
                print("Standard AcroForm field values (via get_fields):\n")
            if af_fields:
                width = max(len(k) for k in af_fields)
                for k, v in af_fields.items():
                    print(f"{k.ljust(width)}  {_display(v)}")
        return 2

    # ---- XFA but no datasets packet (exit 3) --------------------------------------
    if datasets is None:
        note = "XFA form but no `datasets` packet — nothing was entered, or data is absent."
        if args.json:
            print(json.dumps(
                {"form_kind": "xfa", "source": args.pdf, "tree": {}, "flat": {},
                 "field_count": 0, "filled_count": 0, "raw_datasets_path": None,
                 "note": note}, indent=2, ensure_ascii=False))
        else:
            _emit(f"[xfa] {note}", args.quiet)
        return 3

    # We have datasets bytes — always write them for auditing/fallback (§2.4).
    raw_path = args.raw_out
    try:
        with open(raw_path, "wb") as fh:
            fh.write(datasets)
    except OSError as exc:
        _emit(f"warning: could not write raw datasets to {raw_path}: {exc}", args.quiet)
        raw_path = None

    # ---- parse (exit 4 on unrecoverable failure) ----------------------------------
    try:
        tree, flat = parse_datasets(datasets)
    except Exception as exc:
        print(f"error: datasets XML did not parse: {exc}", file=sys.stderr)
        if raw_path:
            _emit(f"raw datasets XML written to {raw_path} for inspection.", args.quiet)
        return 4

    field_count = len(flat)
    filled_count = sum(1 for v in flat.values() if str(v).strip())

    result = {
        "form_kind": "xfa",
        "source": args.pdf,
        "tree": tree,
        "flat": flat,
        "field_count": field_count,
        "filled_count": filled_count,
        "raw_datasets_path": raw_path,
    }

    # ---- empty / unfilled XFA (exit 3) --------------------------------------------
    if filled_count == 0:
        note = ("XFA datasets parsed but every field is empty — the form looks unfilled."
                if field_count else
                "XFA datasets parsed but contained no form fields under xfa:data.")
        if args.json:
            result["note"] = note
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _emit(f"[xfa] {note}", args.quiet)
            _emit(f"raw datasets XML written to {raw_path}.", args.quiet)
        return 3

    # ---- success (exit 0) ----------------------------------------------------------
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    if args.flatten:
        print(render_flat_table(flat))
        return 0

    # default view: human tree + flat table, with notes on stderr
    _emit(f"[xfa] extracted via {engine}: {filled_count} filled of {field_count} fields.",
          args.quiet)
    lines: list = []
    render_human_tree(tree, lines)
    print("XFA data tree")
    print("=============")
    print("\n".join(lines))
    print("\nFlattened path: value")
    print("=====================")
    print(render_flat_table(flat))
    _emit(f"\nraw datasets XML written to {raw_path}.", args.quiet)
    _emit("note: checkbox/radio values are shown raw (export value or 1/0); human meaning "
          "may need the template packet — see REFERENCE.md.", args.quiet)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
