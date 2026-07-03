"""Parse the XFA *template* packet into a per-field schema.

The datasets packet holds values; the **template** holds the form's intelligence — each
field's UI type, human caption, valid choice values, format mask, and any calculate/validate/
event scripts. That's what makes reading and (especially) filling form-aware instead of
blindly poking strings into datasets.

`parse_template(pdf)` returns {som_path: Field}. Paths are un-indexed (the template is a
schema, not data); look them up from a datasets path with `schema_for(schema, datasets_path)`,
which strips the `[n]` repeat indices.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _dcfield

from .cli import locate_datasets
from .xmlutil import localname as _ln

# template UI widget localname -> our field kind
_UI_KIND = {
    "textEdit": "text", "checkButton": "checkbox", "dateTimeEdit": "date",
    "choiceList": "choice", "numericEdit": "numeric", "button": "button",
    "imageEdit": "image", "signature": "signature", "passwordEdit": "password",
    "barcode": "barcode", "defaultUi": "text",
}
_VALUE_TAGS = ("text", "integer", "float", "decimal", "boolean")
_INDEX = re.compile(r"\[\d+\]")


@dataclass
class Field:
    path: str
    kind: str                                   # text|checkbox|radio|choice|date|numeric|...
    caption: str = ""                           # human label
    picture: str = ""                           # format mask, e.g. "date{YYYY-MM-DD}"
    choices: list = _dcfield(default_factory=list)   # [(export, display), ...] for choice/radio
    on_value: "str | None" = None               # single checkbox "on" value (off == "")
    scripts: list = _dcfield(default_factory=list)   # ["calculate","validate","event:exit",...]

    @property
    def scripted(self) -> bool:
        return bool(self.scripts)

    @property
    def export_values(self) -> list:
        return [e for e, _ in self.choices]


def _som_path(el):
    parts = []
    cur = el
    while cur is not None:
        if _ln(cur) in ("field", "exclGroup", "subform") and cur.get("name"):
            parts.append(cur.get("name"))
        cur = cur.getparent()
    return ".".join(reversed(parts))


def _caption(el):
    cap = next((c for c in el if _ln(c) == "caption"), None)
    if cap is None:
        return ""
    return " ".join(t.text.strip() for t in cap.iter()
                    if _ln(t) == "text" and t.text and t.text.strip())


def _picture(el):
    for holder in ("format", "bind"):
        h = next((c for c in el if _ln(c) == holder), None)
        if h is not None:
            pic = next((g for g in h.iter() if _ln(g) == "picture"), None)
            if pic is not None and pic.text and pic.text.strip():
                return pic.text.strip()
    return ""


def _scripts(el):
    out = []
    if any(_ln(c) == "calculate" for c in el):
        out.append("calculate")
    if any(_ln(c) == "validate" for c in el):
        out.append("validate")
    for ev in el:
        if _ln(ev) == "event" and any(_ln(x) == "script" for x in ev):
            out.append("event:" + (ev.get("activity") or "event"))
    return out


def _item_lists(el):
    """A field's <items> -> (export_values, display_values). choiceList has two lists (one
    save='1' = export); a checkButton has one (the on value)."""
    save, disp = None, None
    for it in el:
        if _ln(it) != "items":
            continue
        vals = [(t.text or "") for t in it if _ln(t) in _VALUE_TAGS]
        if it.get("save") == "1":
            save = vals
        else:
            disp = vals
    if save is None and disp is None:
        return [], []
    if save is None:
        save = disp
    if disp is None:
        disp = save
    return save, disp


def _field(el):
    ui = next((c for c in el if _ln(c) == "ui"), None)
    widget = next((c for c in ui if isinstance(c.tag, str)), None) if ui is not None else None
    kind = _UI_KIND.get(_ln(widget), "text") if widget is not None else "text"

    f = Field(path=_som_path(el), kind=kind, caption=_caption(el),
              picture=_picture(el), scripts=_scripts(el))

    export, display = _item_lists(el)
    if kind == "choice":
        f.choices = list(zip(export, display))
    elif kind == "checkbox":
        f.on_value = export[0] if export else "1"
    return f


def _radio(el):
    """An exclGroup is one fillable field whose value is the on-value of the chosen member."""
    f = Field(path=_som_path(el), kind="radio", caption=_caption(el), scripts=_scripts(el))
    for member in (c for c in el if _ln(c) == "field"):
        export, _ = _item_lists(member)
        on = export[0] if export else "1"
        f.choices.append((on, _caption(member) or member.get("name") or on))
    return f


def parse_template(pdf_path) -> dict:
    """Return {som_path: Field} for every fillable field in the form's template packet."""
    from lxml import etree

    _, _, packets, _ = locate_datasets(str(pdf_path))
    tmpl = packets.get("template")
    if not tmpl:
        return {}
    root = etree.fromstring(tmpl, parser=etree.XMLParser(recover=True))
    schema = {}
    for el in root.iter():
        lname = _ln(el)
        if lname == "exclGroup" and el.get("name"):
            r = _radio(el)
            schema[r.path] = r
        elif lname == "field" and el.get("name"):
            if _ln(el.getparent()) == "exclGroup":
                continue  # member of a radio group, handled above
            fld = _field(el)
            schema[fld.path] = fld
    return schema


def schema_for(schema, datasets_path):
    """Look up the Field for a datasets path (strips `[n]` repeat indices)."""
    return schema.get(_INDEX.sub("", datasets_path))
