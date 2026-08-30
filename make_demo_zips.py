"""Bundle each persona's demo documents into one zip for easy upload.

Run:  python3 make_demo_zips.py
Out:  demo_docs/<persona>_case_file.zip (6 zips: resume/background PDF,
      financials PDF, and the workable xlsx worksheet)
"""
from __future__ import annotations

import zipfile
from pathlib import Path

DOCS = Path(__file__).parent / "demo_docs"

BUNDLES = {
    "mei_case_file.zip": ["mei_resume.pdf", "mei_financials.pdf", "mei_worksheet.xlsx"],
    "luis_case_file.zip": ["luis_resume.pdf", "luis_financials.pdf", "luis_worksheet.xlsx"],
    "sichuan_case_file.zip": ["sichuan_profile.pdf", "sichuan_financials.pdf", "sichuan_books.xlsx"],
    "nimbus_case_file.zip": ["nimbus_profile.pdf", "nimbus_financials.pdf", "nimbus_revenue.xlsx"],
    "nori_case_file.zip": ["nori_profile.pdf", "nori_financials.pdf", "nori_captable.xlsx"],
    "chen_case_file.zip": ["chen_background.pdf", "chen_financials.pdf", "chen_trust.xlsx"],
}

for zip_name, members in BUNDLES.items():
    missing = [m for m in members if not (DOCS / m).exists()]
    if missing:
        raise SystemExit(f"{zip_name}: missing {missing} — run make_demo_pdfs.py / make_demo_sheets.py first")
    with zipfile.ZipFile(DOCS / zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for m in members:
            zf.write(DOCS / m, arcname=m)
    print("wrote", DOCS / zip_name)
