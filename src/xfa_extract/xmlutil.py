"""xfa_extract.xmlutil — small public XML helpers shared across the XFA toolkit.

These operate on lxml/ElementTree-style element objects and carry no third-party imports of
their own. They are public API (also used by the companion `xfa-fill` package): stable under
semantic versioning from 0.2.0 on.
"""
from __future__ import annotations

# The xfa-data namespace URI is fixed by the XFA spec; match on it exactly.
XFA_DATA_NS = "http://www.xfa.org/schema/xfa-data/1.0/"


def localname(el) -> "str | None":
    """The element's tag without any namespace, or None for comments/PIs."""
    tag = el.tag
    if not isinstance(tag, str):
        return None  # comment / processing-instruction
    return tag.split("}", 1)[1] if tag.startswith("{") else tag


def namespace(el) -> "str | None":
    """The element's namespace URI, or None when it has none."""
    tag = el.tag
    if isinstance(tag, str) and tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return None


def find_data_element(root):
    """Find the <xfa:data> container in a datasets packet OR a whole XDP document.

    Heuristic by design (BUILD refinement #2) — search order: an element with localname
    `data` in the xfa-data namespace; any element named `data`; the root itself when it is
    `datasets` (children are the data) or is not a known non-data root. Returns None when
    no data container can be identified.
    """
    for el in root.iter():
        if localname(el) == "data" and namespace(el) == XFA_DATA_NS:
            return el
    for el in root.iter():
        if localname(el) == "data":
            return el
    if localname(root) == "datasets":
        return root  # no explicit <data> — treat datasets children as data
    if localname(root) not in ("xdp", "template", "config"):
        return root  # someone handed us the data subtree directly
    return None
