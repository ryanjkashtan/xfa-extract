#!/usr/bin/env python3
"""Fetch a corpus of real XFA PDFs for testing xfa-extract.

Source: Mozilla pdf.js's public test suite (test/pdfs/xfa_*.pdf.link), which points at real
LiveCycle/XFA forms — IRCC immigration forms, a DHL waybill, an Indian MCA MGT-7, an Ontario
lease, French CERFA, etc. We resolve the .link files via the GitHub API and download the
subset whose hosts are reachable (GitHub assets, bugzilla.mozilla.org, web.archive.org).

Usage:  python fetch_corpus.py        # downloads into this directory
Then:   python test_real.py
"""
import json, os, re, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# Curated subset (diverse form origins). Names are pdf.js test ids.
WANT = [
    "xfa_imm5257e.pdf", "xfa_imm1295e.pdf", "xfa_imm1344e.pdf",   # IRCC immigration
    "xfa_issue13855.pdf", "xfa_issue14071.pdf",                   # more IRCC (imm5710f, eimm5669e)
    "xfa_issue13213.pdf", "xfa_issue13611.pdf", "xfa_issue13679.pdf",  # CERFA, Ontario lease, India MGT-7
    "xfa_issue14150.pdf", "xfa_dhl_shipment.pdf", "xfa_fish_licence.pdf",
    "xfa_bug1716047.pdf", "xfa_bug1717668_1.pdf", "xfa_bug1721600.pdf",
]


def _gh(url, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": "x", "Accept": "application/vnd.github+json"})
    r = urllib.request.urlopen(req, timeout=60)
    return r.read() if raw else json.load(r)


def main():
    tree = _gh("https://api.github.com/repos/mozilla/pdf.js/git/trees/master?recursive=1")
    link_for = {t["path"].split("/")[-1].replace(".link", ""): t["path"]
                for t in tree["tree"] if "xfa" in t["path"].lower() and t["path"].endswith(".link")}
    RAW = "https://raw.githubusercontent.com/mozilla/pdf.js/master/"
    opener = urllib.request.build_opener()
    opener.addheaders = [("User-Agent", UA)]
    os.makedirs(HERE, exist_ok=True)
    got = 0
    for name in WANT:
        if name not in link_for:
            print(f"  {name:<30} NO .link entry"); continue
        url = _gh(RAW + link_for[name], raw=True).decode().strip()
        url = re.sub(r"(/web/\d{14})/", r"\1id_/", url, count=1)  # Wayback raw-bytes modifier
        try:
            data = opener.open(url, timeout=120).read()
            if data[:5] == b"%PDF-":
                (HERE / name).write_bytes(data); got += 1
                print(f"  {name:<30} {len(data):>8} bytes  ok")
            else:
                print(f"  {name:<30} not a PDF (got {data[:16]!r})")
        except Exception as e:
            print(f"  {name:<30} ERROR {str(e)[:45]}")
        time.sleep(0.4)
    print(f"\n{got}/{len(WANT)} downloaded into {HERE}")


if __name__ == "__main__":
    main()
