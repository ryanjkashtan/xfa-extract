"""xfa-extract — read the entered values out of XFA / LiveCycle "dynamic" PDF forms.

Most government and immigration forms (e.g. IRCC) are XFA forms: they keep entered data in
an XML `datasets` packet under /AcroForm /XFA, not in the /V layer that pypdf.get_fields()
and pdftk read. This package detects XFA, pulls that packet, and emits field -> value maps.
It can also parse the XFA *template* packet into a per-field schema (field kinds, captions,
choice export/display values, format pictures, script flags). Read-only; never mutates the
source PDF.
"""
from .cli import (  # noqa: F401
    locate_datasets,
    parse_datasets,
    get_datasets_via_pypdf,
    get_datasets_via_pikepdf,
    read_acroform_fields,
    main,
)
from .template import Field, parse_template, schema_for  # noqa: F401
from .xmlutil import (  # noqa: F401
    XFA_DATA_NS,
    find_data_element,
    localname,
    namespace,
)

__version__ = "0.2.0"
__all__ = [
    "locate_datasets",
    "parse_datasets",
    "get_datasets_via_pypdf",
    "get_datasets_via_pikepdf",
    "read_acroform_fields",
    "main",
    "parse_template",
    "schema_for",
    "Field",
    "find_data_element",
    "localname",
    "namespace",
    "XFA_DATA_NS",
    "__version__",
]
