"""Generate synthetic demo PDFs for the six clinic personas.

Run:  python3 make_demo_pdfs.py
Out:  demo_docs/<persona>_<doc>.pdf  (12 files)

Every figure matches the gold profiles in clinic/personas.py, and the wording
is deliberately extraction-friendly so uploading these PDFs into the clinic
reproduces the right findings. All persons, entities, and numbers are fictional.
"""
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT = Path(__file__).parent / "demo_docs"
OUT.mkdir(exist_ok=True)

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, spaceAfter=2)
SUB = ParagraphStyle("SUB", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#5a6570"), spaceAfter=10)
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, spaceBefore=12, spaceAfter=4, textColor=colors.HexColor("#0F6C78"))
BODY = ParagraphStyle("BODY", parent=styles["Normal"], fontSize=10, leading=14)
FOOT = ParagraphStyle("FOOT", parent=styles["Normal"], fontSize=7.5, textColor=colors.HexColor("#8a939c"))

DISCLAIMER = (
    "Synthetic sample document for the Global Tax Clinic demo (Sundai, 30 Aug 2026). "
    "All persons, entities, accounts, and figures are fictional."
)


def tbl(rows, widths=None, header=True):
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, colors.HexColor("#d3dae0")),
        ("LINEBELOW", (0, -1), (-1, -1), 0.75, colors.HexColor("#1b2430")),
    ]
    if header:
        style += [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
            ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.HexColor("#1b2430")),
        ]
    t.setStyle(TableStyle(style))
    return t


def build(name: str, title: str, subtitle: str, blocks: list):
    doc = SimpleDocTemplate(str(OUT / name), pagesize=letter, topMargin=0.8 * inch, bottomMargin=0.7 * inch)
    story = [Paragraph(title, H1), Paragraph(subtitle, SUB), HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1b2430")), Spacer(1, 8)]
    for b in blocks:
        if isinstance(b, str):
            story.append(Paragraph(b, BODY))
            story.append(Spacer(1, 4))
        else:
            story.append(b)
    story += [Spacer(1, 18), HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#d3dae0")), Spacer(1, 4), Paragraph(DISCLAIMER, FOOT)]
    doc.build(story)
    print("wrote", OUT / name)


# ============================ MEI ============================
build(
    "mei_resume.pdf",
    "Mei Zhang",
    "San Francisco, CA · mei.zhang@example.com · Individual — high net worth",
    [
        Paragraph("Profile", H2),
        "Senior product director based in California. US person (US tax resident); maintains family and "
        "financial ties to Hong Kong and mainland China, and spent about 40 days in mainland China this year.",
        Paragraph("Experience", H2),
        tbl([
            ["2021 – present", "Meridian Cloud Inc. (US employer)", "Senior Director, Product — compensation includes RSUs"],
            ["2016 – 2021", "Harbour Analytics Ltd., Hong Kong", "Head of Product"],
            ["2012 – 2016", "Shenzhen Lumen Tech", "Product Manager"],
        ], widths=[95, 200, 195], header=False),
        Paragraph("Education", H2),
        tbl([
            ["2010", "MSc Information Systems, HKUST, Hong Kong"],
            ["2008", "BEng, Shenzhen University"],
        ], widths=[95, 395], header=False),
        Paragraph("Other", H2),
        "Owns and rents out an apartment in Shenzhen. Holds retirement (MPF) and investment accounts in Hong Kong from prior residence.",
    ],
)

build(
    "mei_financials.pdf",
    "Mei Zhang — Personal Financial Statement",
    "Tax year 2026 · prepared for compliance check-up · figures in USD",
    [
        Paragraph("Foreign (non-US) financial accounts — maximum balance during the year", H2),
        tbl([
            ["Institution / account", "Type", "Country", "Max balance (USD)"],
            ["HSBC bank account", "bank", "Hong Kong", "3,200 USD"],
            ["Hang Seng bank account", "bank", "Hong Kong", "2,800 USD"],
            ["HK brokerage account", "brokerage", "Hong Kong", "4,100 USD"],
            ["MPF retirement account", "mpf", "Hong Kong", "1,400 USD"],
            ["HK retail equity fund", "fund", "Hong Kong", "3,500 USD"],
            ["Aggregate maximum", "", "", "15,000 USD"],
        ], widths=[190, 75, 90, 135]),
        Paragraph("Income", H2),
        tbl([
            ["RSU vesting — Meridian Cloud Inc. (US employer)", "RSU", "US"],
            ["Rental income — Shenzhen apartment (rent out)", "18,000 USD", "China"],
        ], header=False, widths=[280, 110, 100]),
        Paragraph("Gifts received", H2),
        "Cash gift of 180,000 USD received this year from parents in mainland China (foreign persons; wire from Shenzhen).",
        Paragraph("Notes", H2),
        "US person, filing single. States: California. The Hong Kong retail fund may be a passive foreign investment company.",
    ],
)

# ============================ LUIS ============================
build(
    "luis_resume.pdf",
    "Luis Ramirez",
    "Nashua, NH (moved from Boston, MA in July 2026) · luis.r@example.com",
    [
        Paragraph("Profile", H2),
        "Restaurant server and delivery driver. US person. Head of household with one child. "
        "Moved from Massachusetts to New Hampshire on 15 July 2026 (part-year resident of both states).",
        Paragraph("Work history", H2),
        tbl([
            ["2022 – present", "Beacon Hill Bistro, Boston MA", "Server (W-2) — wait tables, cash tips"],
            ["2024 – present", "DoorDash", "Delivery driver (1099-NEC, gig)"],
            ["2019 – 2022", "Harborside Diner, Quincy MA", "Server"],
        ], widths=[95, 205, 190], header=False),
        Paragraph("Skills & certifications", H2),
        "ServSafe food handler; TIPS-certified; bilingual English/Spanish.",
    ],
)

build(
    "luis_financials.pdf",
    "Luis Ramirez — 2026 Income Summary",
    "Prepared for tax check-up · figures in USD",
    [
        Paragraph("Income", H2),
        tbl([
            ["Source", "Form", "Amount (USD)"],
            ["Beacon Hill Bistro — wages (wait tables)", "W-2", "32,000"],
            ["Cash and charged tips", "tips", "14,000"],
            ["DoorDash — delivery (gig)", "1099-NEC", "9,000"],
            ["Total", "", "55,000"],
        ], widths=[260, 90, 140]),
        Paragraph("Household", H2),
        "Head of household. One child (dependent), age 6.",
        Paragraph("Residency", H2),
        "Part-year: Massachusetts (Jan 1 – Jul 15), New Hampshire (Jul 15 – Dec 31). Moved for lower rent.",
        Paragraph("Other", H2),
        "No foreign accounts. No gifts received. No investments other than a small US savings account.",
    ],
)

# ============================ SICHUAN GARDEN ============================
build(
    "sichuan_profile.pdf",
    "Sichuan Garden LLC — Company Background",
    "Massachusetts single-member LLC · restaurant · est. 2018",
    [
        Paragraph("Overview", H2),
        "Sichuan Garden is a Massachusetts single-member LLC operating a 60-seat restaurant in Brookline, MA. "
        "The company serves meals on premises, runs takeout, and sells retail merchandise (sauces, gift items). "
        "The owner is a US person and Massachusetts resident.",
        Paragraph("Operations", H2),
        tbl([
            ["Formed", "2018, Massachusetts (single-member LLC, disregarded entity)"],
            ["Location", "412 Harvard St, Brookline, MA"],
            ["Employees", "14 employees on payroll (kitchen, waitstaff, manager)"],
            ["Lines", "Restaurant meals · takeout · retail merchandise"],
        ], widths=[95, 395], header=False),
        Paragraph("Registrations", H2),
        "Registered on MassTaxConnect for sales tax, meals tax, and employer withholding.",
    ],
)

build(
    "sichuan_financials.pdf",
    "Sichuan Garden LLC — 2026 Financial Summary",
    "Internal P&L summary · figures in USD",
    [
        Paragraph("Revenue", H2),
        tbl([
            ["Line", "Amount (USD)"],
            ["Restaurant meals sales (Massachusetts)", "372,000"],
            ["Retail merchandise sales", "48,000"],
            ["Total sales", "420,000"],
        ], widths=[300, 150]),
        Paragraph("Costs", H2),
        tbl([
            ["Payroll (14 employees)", "185,000"],
            ["Food and supplies", "121,000"],
            ["Rent and utilities", "64,000"],
        ], widths=[300, 150], header=False),
        Paragraph("Notes", H2),
        "Meals are served and taxed in Massachusetts; the local option meals excise applies in Brookline. "
        "Owner is a US person. No foreign subsidiary and no foreign accounts.",
    ],
)

# ============================ NIMBUSFLOW ============================
build(
    "nimbus_profile.pdf",
    "NimbusFlow, Inc. — Company Background",
    "Massachusetts C-corporation · SaaS (NAICS 513210)",
    [
        Paragraph("Overview", H2),
        "NimbusFlow, Inc. is a Massachusetts C-corporation incorporated 15 March 2023, headquartered at "
        "12 Winter St, Boston. The company sells subscription workflow software (SaaS) delivered electronically. "
        "The company is a US person.",
        Paragraph("Team", H2),
        "Three employees, all working in Massachusetts. Annual payroll 490,000 USD.",
        Paragraph("Officers", H2),
        tbl([
            ["CEO", "A. Osei — Boston, MA"],
            ["CTO", "R. Bhatt — Cambridge, MA"],
            ["Head of Sales", "K. Doyle — Boston, MA"],
        ], widths=[95, 395], header=False),
        Paragraph("Filings on record", H2),
        "Federal Form 1120 (2023, 2024). MA corporate excise (2023, 2024). No foreign accounts, no foreign subsidiaries.",
    ],
)

build(
    "nimbus_financials.pdf",
    "NimbusFlow, Inc. — 2025 Revenue by Billing State",
    "Management accounts · figures in USD",
    [
        Paragraph("Revenue by state", H2),
        tbl([
            ["Billing state", "Customers", "Revenue (USD)", "SaaS taxable?"],
            ["Massachusetts sales", "14", "420,000", "yes (6.25%)"],
            ["New York sales", "8", "240,000", "yes"],
            ["California sales", "6", "180,000", "yes"],
            ["Texas sales", "5", "120,000", "exempt"],
            ["Illinois sales", "3", "90,000", "yes"],
            ["Other states", "14", "200,000", "review"],
            ["Total revenue", "50", "1,250,000", ""],
        ], widths=[150, 80, 120, 120]),
        Paragraph("Payroll", H2),
        "Payroll 490,000 USD; all three employees are Massachusetts-based; MA employer withholding in place.",
        Paragraph("Notes", H2),
        "Out-of-state receipts have not been reviewed for economic nexus. No foreign accounts.",
    ],
)

# ============================ NORI ROBOTICS ============================
build(
    "nori_profile.pdf",
    "Nori Robotics Inc. — Company Background",
    "Delaware C-corporation · operations in Massachusetts",
    [
        Paragraph("Overview", H2),
        "Nori Robotics Inc. is a Delaware C-corporation with engineering operations in Massachusetts. "
        "The company is a US person. The founders are Chinese tax residents and together own more than "
        "25 percent of the company.",
        Paragraph("Structure", H2),
        tbl([
            ["Parent", "Nori Robotics Inc. — Delaware C-corp"],
            ["Subsidiary", "Nori Robotics (Shanghai) Co. Ltd. — wholly owned subsidiary in Shanghai, China (100%)"],
            ["Founder A", "Chinese tax resident — owns 40% of parent"],
            ["Founder B", "Chinese tax resident — owns 18% of parent"],
        ], widths=[95, 395], header=False),
        Paragraph("Recent events", H2),
        "On 1 August 2026 the company granted unvested founder stock subject to vesting (83(b) window open). "
        "Employees on payroll in Massachusetts.",
    ],
)

build(
    "nori_financials.pdf",
    "Nori Robotics Inc. — Intercompany & Cap Table Summary",
    "Prepared for compliance review · figures in USD",
    [
        Paragraph("Cap table (fully diluted)", H2),
        tbl([
            ["Holder", "Country", "Ownership"],
            ["Founder A (Chinese founder)", "China", "40%"],
            ["Founder B (Chinese founder)", "China", "18%"],
            ["Employee pool", "US", "12%"],
            ["Seed investors", "US", "30%"],
        ], widths=[220, 110, 120]),
        Paragraph("Intercompany", H2),
        "The Shanghai subsidiary provides contract engineering to the US parent under a cost-plus services "
        "agreement (reimbursements 380,000 USD in 2026). Transactions between the US corporation and its "
        "25%+ foreign owners are reportable.",
        Paragraph("Equity", H2),
        "Unvested founder stock granted 1 August 2026; recipients considering an 83(b) election (30-day deadline).",
    ],
)

# ============================ CHEN FAMILY TRUST ============================
build(
    "chen_background.pdf",
    "Chen Family Trust — Background Memorandum",
    "US family trust · Massachusetts situs · settlor resident in Hong Kong",
    [
        Paragraph("The trust", H2),
        "The Chen Family Trust is a US family trust with Massachusetts situs. The trust is a US person. "
        "Trustee: Beacon Fiduciary Partners LLC, Boston, MA.",
        Paragraph("The settlor", H2),
        "David Chen founded Northline Inc., an industrial logistics software company, in 2004 and took it "
        "public on the NYSE about 20 years ago (IPO 2006). He funded the trust with founder shares. "
        "Mr. Chen and his family moved to Hong Kong 10 years ago (2016); he is a US person and a Hong Kong "
        "resident. Career summary: CEO of Northline Inc. 2004-2019; board member since; prior to that, "
        "engineering lead at a Boston-area logistics firm.",
        Paragraph("The company", H2),
        "Northline Inc. is listed on the NYSE. It operates in the US, mainland China, Hong Kong, and the EU "
        "through local subsidiaries (Northline (Shanghai) Ltd., Northline HK Ltd., Northline Europe B.V.). "
        "The trust holds shares only - it has no role in the operating subsidiaries.",
        Paragraph("Holdings", H2),
        "The trust still owns 8 percent of the listed shares of Northline Inc., held about 20 years. "
        "Dividends are paid to the trust each year. The trust also keeps Hong Kong accounts for the "
        "family's HK presence.",
    ],
)

build(
    "chen_financials.pdf",
    "Chen Family Trust — Financial Statement",
    "Tax year 2026 · prepared by trustee · figures in USD",
    [
        Paragraph("Principal holdings", H2),
        tbl([
            ["Holding", "Type", "Ownership"],
            ["Northline Inc. (NYSE-listed, founded by settlor)", "public company shares", "8 percent of listed shares"],
            ["Money-market sweep (US)", "cash", "-"],
        ], widths=[250, 120, 120]),
        Paragraph("Foreign (non-US) financial accounts — maximum balance during the year", H2),
        tbl([
            ["Institution / account", "Type", "Country", "Max balance (USD)"],
            ["HSBC Hong Kong bank account", "bank", "Hong Kong", "250,000 USD"],
            ["HK brokerage custody account", "brokerage", "Hong Kong", "1,750,000 USD"],
            ["Aggregate maximum", "", "", "2,000,000 USD"],
        ], widths=[190, 75, 90, 135]),
        Paragraph("Income", H2),
        "Quarterly dividends on Northline Inc. shares totaling 8,640,000 USD for the year, paid to the "
        "trust and partly distributed to beneficiaries.",
        Paragraph("Notes", H2),
        "US person; Massachusetts situs; calendar tax year. The settlor and family are Hong Kong residents "
        "(moved 2016) and US persons. Northline Inc. operates in the US, mainland China, Hong Kong, and "
        "the EU. The concentrated founder position has been held approximately 20 years.",
    ],
)

print("done:", len(list(OUT.glob("*.pdf"))), "PDFs in", OUT)
