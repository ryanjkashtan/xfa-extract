"""Acceptance tests for xfa-extract, run against synthetic fixtures.

Covers: filled XFA (array + single-stream XDP), AcroForm routing, empty XFA, corrupt XFA,
and that every source PDF is byte-for-byte unchanged. Invokes the CLI as a subprocess via
`python -m xfa_extract.cli`, so the package must be importable (`pip install -e .`).
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cli(pdf_name, *flags):
    raw = HERE / f"_raw_{Path(pdf_name).stem}.xml"
    proc = subprocess.run(
        [sys.executable, "-m", "xfa_extract.cli", str(HERE / pdf_name),
         "--raw-out", str(raw), *flags],
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr, raw


def cli_json(pdf_name, *flags):
    code, out, err, raw = cli(pdf_name, "--json", *flags)
    data = json.loads(out) if out.strip() else {}
    return code, data, raw


def sha(name):
    return hashlib.sha256((HERE / name).read_bytes()).hexdigest()


# --- (a) filled XFA array form -------------------------------------------------------
def test_filled_xfa_values_and_exit_code():
    code, d, _ = cli_json("filled_xfa.pdf")
    assert code == 0
    assert d["form_kind"] == "xfa"
    flat = d["flat"]
    assert flat["form1.PersonalInfo.Surname"] == "Smith"
    assert flat["form1.PersonalInfo.GivenName"] == "Jane"


def test_repeating_sections_indexed_not_collapsed():
    code, d, _ = cli_json("filled_xfa.pdf")
    deps = d["tree"]["form1"]["Dependents"]["Dependent"]
    assert isinstance(deps, list) and len(deps) == 3
    assert d["flat"]["form1.Dependents.Dependent[0].Name"] == "Alex"
    assert d["flat"]["form1.Dependents.Dependent[2].Age"] == "3"


def test_empty_leaf_preserved_and_counts():
    code, d, _ = cli_json("filled_xfa.pdf")
    assert d["flat"]["form1.Notes"] == ""
    assert d["field_count"] == 11
    assert d["filled_count"] == 10


# --- (a') single-stream XDP ----------------------------------------------------------
def test_single_stream_xdp_locates_data_inside():
    code, d, _ = cli_json("filled_xdp.pdf")
    assert code == 0
    assert d["flat"]["form1.Applicant.Surname"] == "Okonkwo"


# --- (b) AcroForm routing ------------------------------------------------------------
def test_acroform_routes_to_exit_2_with_values():
    code, out, err, _ = cli("filled_acroform.pdf")
    assert code == 2
    assert "standard" in (out + err).lower()
    assert "John Doe" in out


def test_acroform_json_still_emits_object():
    code, d, _ = cli_json("filled_acroform.pdf")
    assert code == 2
    assert d["form_kind"] == "acroform"


def test_no_form_exits_2():
    code, _, _, _ = cli("no_form.pdf")
    assert code == 2


# --- (c) empty / unfilled XFA --------------------------------------------------------
def test_empty_xfa_exits_3_cleanly():
    code, _, err, _ = cli("empty_xfa.pdf")
    assert code == 3
    assert "Traceback" not in err


# --- (d) corrupt datasets ------------------------------------------------------------
def test_corrupt_datasets_exits_4_and_writes_raw():
    code, _, _, raw = cli("corrupt_xfa.pdf")
    assert code == 4
    assert raw.exists() and raw.stat().st_size > 0


# --- (e) source PDFs unchanged -------------------------------------------------------
def test_source_pdfs_byte_for_byte_unchanged():
    names = ["filled_xfa.pdf", "filled_xdp.pdf", "filled_acroform.pdf",
             "no_form.pdf", "empty_xfa.pdf", "corrupt_xfa.pdf"]
    before = {n: sha(n) for n in names}
    for n in names:
        cli(n)
    for n in names:
        assert sha(n) == before[n], f"{n} was modified"
