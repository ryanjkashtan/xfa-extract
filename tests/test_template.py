"""Tests for xfa_extract.template — the XFA template-packet parser.

Runs against the synthetic `templated_xfa.pdf` fixture (a real-shaped template packet with a
dropdown, a checkbox, a radio exclGroup, a date field with a picture clause, and a scripted
text field — modelled on IRCC CIT0001 structure).
"""
from pathlib import Path

import pytest

from xfa_extract import Field, parse_template, schema_for

HERE = Path(__file__).resolve().parent
TEMPLATED = HERE / "templated_xfa.pdf"


@pytest.fixture(scope="module")
def schema():
    return parse_template(TEMPLATED)


# --- schema shape ----------------------------------------------------------------------
def test_schema_keyed_by_unindexed_som_paths(schema):
    assert "form1.country" in schema
    assert "form1.sex" in schema
    assert all("[" not in path for path in schema)


def test_choice_field(schema):
    f = schema["form1.country"]
    assert isinstance(f, Field)
    assert f.kind == "choice"
    assert f.choices == [("1", "Canada"), ("2", "Other")]
    assert f.export_values == ["1", "2"]
    assert f.caption == "Country of birth"


def test_checkbox_on_value(schema):
    f = schema["form1.agree"]
    assert f.kind == "checkbox"
    assert f.on_value == "Y"
    assert f.caption == "I agree to the terms"


def test_radio_exclgroup_members(schema):
    f = schema["form1.sex"]
    assert f.kind == "radio"
    assert f.choices == [("M", "Male"), ("F", "Female")]
    # member fields of an exclGroup must NOT appear as standalone schema entries
    assert "form1.sex.male" not in schema
    assert "form1.sex.female" not in schema


def test_date_picture(schema):
    f = schema["form1.dob"]
    assert f.kind == "date"
    assert f.picture == "date{YYYY-MM-DD}"
    assert not f.scripted


def test_scripted_field_detected(schema):
    f = schema["form1.notes"]
    assert f.scripted
    assert "event:exit" in f.scripts


# --- lookup helper -----------------------------------------------------------------------
def test_schema_for_strips_repeat_indices(schema):
    assert schema_for(schema, "form1[0].country[0]") is schema["form1.country"]
    assert schema_for(schema, "form1.country") is schema["form1.country"]
    assert schema_for(schema, "form1.not_a_field") is None


# --- degenerate inputs -------------------------------------------------------------------
def test_no_template_packet_returns_empty():
    # empty_xfa.pdf is built without a template packet at all
    assert parse_template(HERE / "empty_xfa.pdf") == {}


def test_empty_template_stream_returns_empty():
    # filled_xfa.pdf carries a bare "<template/>" placeholder packet
    assert parse_template(HERE / "filled_xfa.pdf") == {}


# --- public surface ------------------------------------------------------------------------
def test_public_api_importable():
    from xfa_extract import (  # noqa: F401
        XFA_DATA_NS,
        find_data_element,
        localname,
        namespace,
        parse_template,
        schema_for,
    )
