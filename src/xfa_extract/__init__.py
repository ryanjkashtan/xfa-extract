"""xfa-extract — read the entered values out of XFA / LiveCycle "dynamic" PDF forms.

Most government and immigration forms (e.g. IRCC) are XFA forms: they keep entered data in
an XML `datasets` packet under /AcroForm /XFA, not in the /V layer that pypdf.get_fields()
and pdftk read. This package detects XFA, pulls that packet, and emits field -> value maps.
Read-only; never mutates the source PDF.
"""
from .cli import (  # noqa: F401
    locate_datasets,
    parse_datasets,
    get_datasets_via_pypdf,
    get_datasets_via_pikepdf,
    read_acroform_fields,
    main,
)

__version__ = "0.1.0"
__all__ = [
    "locate_datasets",
    "parse_datasets",
    "get_datasets_via_pypdf",
    "get_datasets_via_pikepdf",
    "read_acroform_fields",
    "main",
    "__version__",
]
