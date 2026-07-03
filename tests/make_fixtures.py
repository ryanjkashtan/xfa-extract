#!/usr/bin/env python3
"""Generate synthetic test PDFs for xfa-extract acceptance checks.

Builds, in this directory:
  filled_xfa.pdf       — XFA array form with a datasets packet (repeating section)  -> exit 0
  filled_xdp.pdf       — XFA single-stream form (whole XDP inside one /XFA stream)   -> exit 0
  filled_acroform.pdf  — plain AcroForm with a /V value (no /XFA)                    -> exit 2
  no_form.pdf          — a page with no /AcroForm at all                             -> exit 2
  empty_xfa.pdf        — XFA datasets present but every value blank                  -> exit 3
  corrupt_xfa.pdf      — XFA datasets stream that is not parseable XML               -> exit 4
  templated_xfa.pdf    — XFA array form WITH a template packet (choice/checkbox/
                         radio/date/scripted fields) — exercises xfa_extract.template

These are stand-ins for a real filled IRCC form (Ryan to supply). Requires pikepdf.
"""
from pathlib import Path

import pikepdf
from pikepdf import Array, Dictionary, Name, String

HERE = Path(__file__).resolve().parent

DATASETS_FILLED = b"""<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
  <xfa:data>
    <form1>
      <PersonalInfo>
        <Surname>Smith</Surname>
        <GivenName>Jane</GivenName>
        <DateOfBirth>1990-04-12</DateOfBirth>
      </PersonalInfo>
      <Dependents>
        <Dependent><Name>Alex</Name><Age>10</Age></Dependent>
        <Dependent><Name>Sam</Name><Age>7</Age></Dependent>
        <Dependent><Name>Robin</Name><Age>3</Age></Dependent>
      </Dependents>
      <Consent>1</Consent>
      <Notes></Notes>
    </form1>
  </xfa:data>
</xfa:datasets>"""

XDP_FILLED = b"""<?xml version="1.0" encoding="UTF-8"?>
<xdp:xdp xmlns:xdp="http://ns.adobe.com/xdp/">
  <config xmlns="http://www.xfa.org/schema/xci/1.0/"></config>
  <template xmlns="http://www.xfa.org/schema/xfa-template/3.0/"></template>
  <xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
    <xfa:data>
      <form1>
        <Applicant>
          <Surname>Okonkwo</Surname>
          <GivenName>Ada</GivenName>
        </Applicant>
      </form1>
    </xfa:data>
  </xfa:datasets>
</xdp:xdp>"""

DATASETS_EMPTY = b"""<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
  <xfa:data>
    <form1>
      <PersonalInfo>
        <Surname></Surname>
        <GivenName>   </GivenName>
      </PersonalInfo>
    </form1>
  </xfa:data>
</xfa:datasets>"""

# Binary noise: lxml's recover mode finds no usable root -> exit 4.
DATASETS_CORRUPT = b"\x00\x01\x02\x03 not xml at all <<< \xff\xfe garbage"

# A real-shaped template packet (modelled on IRCC CIT0001 structure): a dropdown with paired
# display/export items lists, a single checkbox with an on-value, a radio exclGroup, a date
# field with a picture clause, and a text field with an exit-event script.
TEMPLATE_RICH = b"""<template xmlns="http://www.xfa.org/schema/xfa-template/3.3/">
  <subform name="form1">
    <field name="country">
      <ui><choiceList/></ui>
      <caption><value><text>Country of birth</text></value></caption>
      <items><text>Canada</text><text>Other</text></items>
      <items save="1" presence="hidden"><text>1</text><text>2</text></items>
    </field>
    <field name="agree">
      <ui><checkButton mark="check"/></ui>
      <caption><value><text>I agree to the terms</text></value></caption>
      <items><text>Y</text></items>
    </field>
    <exclGroup name="sex">
      <field name="male"><ui><checkButton/></ui>
        <caption><value><text>Male</text></value></caption>
        <items><text>M</text></items></field>
      <field name="female"><ui><checkButton/></ui>
        <caption><value><text>Female</text></value></caption>
        <items><text>F</text></items></field>
    </exclGroup>
    <field name="dob">
      <ui><dateTimeEdit/></ui>
      <caption><value><text>Date of birth (YYYY-MM-DD)</text></value></caption>
      <format><picture>date{YYYY-MM-DD}</picture></format>
    </field>
    <field name="notes">
      <ui><textEdit/></ui>
      <event activity="exit" name="event__exit">
        <script contentType="application/x-javascript">xfa.host.messageBox("bye")</script>
      </event>
    </field>
  </subform>
</template>"""

DATASETS_TEMPLATED = b"""<?xml version="1.0" encoding="UTF-8"?>
<xfa:datasets xmlns:xfa="http://www.xfa.org/schema/xfa-data/1.0/">
  <xfa:data>
    <form1>
      <country>1</country><agree></agree><sex></sex><dob></dob><notes></notes>
    </form1>
  </xfa:data>
</xfa:datasets>"""


def _xfa_array_pdf(path: Path, datasets: bytes, with_extra_packets: bool = True) -> None:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    ds = pdf.make_stream(datasets)
    entries = []
    if with_extra_packets:
        entries += [String("preamble"), pdf.make_stream(b"<preamble/>")]
        entries += [String("config"), pdf.make_stream(b"<config/>")]
        entries += [String("template"), pdf.make_stream(b"<template/>")]
    entries += [String("datasets"), ds]
    if with_extra_packets:
        entries += [String("postamble"), pdf.make_stream(b"</preamble>")]
    pdf.Root.AcroForm = pdf.make_indirect(Dictionary(XFA=Array(entries), Fields=Array([])))
    pdf.save(path)
    pdf.close()


def _xdp_single_stream_pdf(path: Path, xdp: bytes) -> None:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.Root.AcroForm = pdf.make_indirect(
        Dictionary(XFA=pdf.make_stream(xdp), Fields=Array([])))
    pdf.save(path)
    pdf.close()


def _acroform_pdf(path: Path) -> None:
    pdf = pikepdf.Pdf.new()
    page = pdf.add_blank_page(page_size=(612, 792))
    field = pdf.make_indirect(Dictionary(
        FT=Name.Tx, T=String("FullName"), V=String("John Doe"),
        Type=Name.Annot, Subtype=Name.Widget, Rect=Array([100, 700, 300, 720]),
    ))
    page.Annots = Array([field])
    pdf.Root.AcroForm = pdf.make_indirect(Dictionary(Fields=Array([field]), DR=Dictionary()))
    pdf.save(path)
    pdf.close()


def _no_form_pdf(path: Path) -> None:
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    pdf.save(path)
    pdf.close()


def _templated_xfa_pdf(path: Path) -> None:
    """XFA array form with a REAL template packet (choice/checkbox/radio/date/scripted)."""
    pdf = pikepdf.Pdf.new()
    pdf.add_blank_page(page_size=(612, 792))
    entries = [
        String("template"), pdf.make_stream(TEMPLATE_RICH),
        String("datasets"), pdf.make_stream(DATASETS_TEMPLATED),
    ]
    pdf.Root.AcroForm = pdf.make_indirect(Dictionary(XFA=Array(entries), Fields=Array([])))
    pdf.save(path)
    pdf.close()


def main() -> None:
    _xfa_array_pdf(HERE / "filled_xfa.pdf", DATASETS_FILLED)
    _xdp_single_stream_pdf(HERE / "filled_xdp.pdf", XDP_FILLED)
    _acroform_pdf(HERE / "filled_acroform.pdf")
    _no_form_pdf(HERE / "no_form.pdf")
    _xfa_array_pdf(HERE / "empty_xfa.pdf", DATASETS_EMPTY, with_extra_packets=False)
    _xfa_array_pdf(HERE / "corrupt_xfa.pdf", DATASETS_CORRUPT, with_extra_packets=False)
    _templated_xfa_pdf(HERE / "templated_xfa.pdf")
    for name in ("filled_xfa", "filled_xdp", "filled_acroform", "no_form",
                 "empty_xfa", "corrupt_xfa", "templated_xfa"):
        print(f"wrote {name}.pdf")


if __name__ == "__main__":
    main()
