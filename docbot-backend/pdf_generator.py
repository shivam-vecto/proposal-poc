# pdf_generator.py
"""
Generate a section-based insurance proposal PDF using FPDF.
Uses the visual design (colors, banner, zebra tables, dividers, footer)
but renders ONLY sections and fields that have actual data.

Habit choices ("All of the above", "Both", …) are expanded using
labels from questionnaire.py so both files stay in sync.

Optionally appends uploaded PDF attachments after the summary.
"""

from io import BytesIO
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

# Optional import — if questionnaire.py isn't importable, we fall
# back to safe default labels.
try:
    import questionnaire as Q
except ImportError:
    Q = None


# ─────────────────────────────────────────────────────────────
#  Colours
# ─────────────────────────────────────────────────────────────
COLOR_PRIMARY  = (28, 78, 138)     # deep blue
COLOR_ACCENT   = (0, 150, 136)     # teal
COLOR_LIGHT_BG = (240, 244, 248)   # light grey-blue
COLOR_BORDER   = (200, 210, 220)
COLOR_TEXT     = (33, 37, 41)
COLOR_MUTED    = (108, 117, 125)


# ─────────────────────────────────────────────────────────────
#  Section definitions
# ─────────────────────────────────────────────────────────────
SECTIONS = [
    {
        "title": "1. PROPOSER PROFILE",
        "fields": [
            ("full_name",       "Full Name"),
            ("age",             "Age"),
            ("gender",          "Gender"),
            ("marital_status",  "Marital Status"),
            ("father_name",     "Father's Name"),
            ("mother_name",     "Mother's Name"),
            ("occupation",      "Occupation"),
            ("company_name",    "Company Name"),
            ("annual_income",   "Annual Income"),
        ],
    },
    {
        "title": "2. CONTACT & ADDRESS",
        "fields": [
            ("mobile_number",    "Mobile Number"),
            ("alternate_mobile", "Alternate Mobile"),
            ("email_address",    "Email Address"),
            ("pincode",          "Pincode"),
            ("address",          "Full Address"),
        ],
    },
    {
        "title": "3. KYC / IDENTITY",
        "fields": [
            ("pan_number",     "PAN Number"),
            ("aadhaar_number", "Aadhaar Number"),
        ],
    },
    {
        "title": "4. BANK DETAILS",
        "fields": [
            ("bank_holder_name", "Account Holder"),
            ("bank_name",        "Bank Name"),
            ("branch_name",      "Branch Name"),
            ("account_number",   "Account Number"),
            ("ifsc_code",        "IFSC Code"),
        ],
    },
    {
        "title": "5. NOMINEE DETAILS",
        "fields": [
            ("nominee_name",         "Nominee Name"),
            ("nominee_relationship", "Relationship"),
            ("nominee_dob",          "Nominee DOB"),
            ("nominee_share",        "Nominee Share (%)"),
        ],
    },
    {
        "title": "6. MEDICAL HISTORY",
        "fields": [
            ("pre_existing_diseases",  "Pre-Existing Disease (PED)"),
            ("ped_since",              "PED Since"),
            ("ped_details",            "PED Details"),
            ("chronic_conditions",     "Chronic Conditions"),
            ("genetic_surgery_details","Genetic / Surgery Details"),
            ("medication_details",     "Medications"),
            ("other_illness_treatment","Other Illness / Treatment"),
        ],
    },
    {
        "title": "7. HABITS & LIFESTYLE",
        "fields": [
            ("smoking_alcohol",         "Habits"),
            ("smoking_frequency",       "Smoking"),
            ("alcohol_frequency",       "Alcohol"),
            ("tobacco_details",         "Tobacco"),
            ("drug_details",            "Drugs"),
            ("smoking_alcohol_details", "Other Details"),
        ],
    },
]


# ─────────────────────────────────────────────────────────────
#  Value cleaning
# ─────────────────────────────────────────────────────────────
def _clean(v: Any) -> str:
    """Return a display-safe string; empty string if blank."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        return ", ".join(x for x in (_clean(i) for i in v) if x)
    if isinstance(v, dict):
        return "; ".join(
            f"{k.replace('_', ' ')}: {_clean(val)}"
            for k, val in v.items() if _clean(val)
        )
    return str(v)


# ─────────────────────────────────────────────────────────────
#  Habit-value expansion — labels come from questionnaire.py
# ─────────────────────────────────────────────────────────────

# Each entry maps a follow-up field → its fallback label.
# If questionnaire.py is importable, we ask IT for the label;
# otherwise we use the fallback.
_HABIT_FOLLOWUP_FIELDS = [
    ("smoking_frequency", "Smoking"),
    ("alcohol_frequency", "Alcohol"),
    ("tobacco_details",   "Tobacco"),
    ("drug_details",      "Drugs"),
]


def _habit_label(field: str, fallback: str) -> str:
    """Get the pretty label for a habit follow-up field."""
    if Q is not None:
        try:
            return Q.get_label(field) or fallback
        except Exception:
            pass
    return fallback


def _expand_habit(value: Any) -> str:
    """
    Return a readable string for the smoking_alcohol field.

    Composite answers ("All of the above", "Both", "Multiple") are
    expanded into their implied habit categories, using labels pulled
    from questionnaire.py (fallback if unavailable).

    Single choices ("Smoking", "Alcohol", …) are shown as-is.
    """
    if not value:
        return ""
    raw = _clean(value)
    v = raw.strip().lower()

    # Composite → expand to category labels
    if v in ("all of the above", "multiple"):
        cats = [_habit_label(f, fb) for f, fb in _HABIT_FOLLOWUP_FIELDS]
        return ", ".join(cats)

    if v in ("both", "smoking and alcohol"):
        cats = [
            _habit_label("smoking_frequency", "Smoking"),
            _habit_label("alcohol_frequency", "Alcohol"),
        ]
        return " & ".join(cats)

    if v == "smoking and tobacco":
        return " & ".join([
            _habit_label("smoking_frequency", "Smoking"),
            _habit_label("tobacco_details",   "Tobacco"),
        ])

    if v == "alcohol and tobacco":
        return " & ".join([
            _habit_label("alcohol_frequency", "Alcohol"),
            _habit_label("tobacco_details",   "Tobacco"),
        ])

    if v in ("no", "none", "nil"):
        return "None"

    # Single choice — display as-is
    return raw


# ─────────────────────────────────────────────────────────────
#  Generator
# ─────────────────────────────────────────────────────────────
class ProposalPDF:
    _ASCII_MAP = {
        "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
        "\u201C": '"', "\u201D": '"', "\u2026": "...", "\u2022": "*",
        "\u00A0": " ", "\u20B9": "INR ",
    }

    def __init__(self, title: str = "Insurance Proposal"):
        self.title = title
        self._font_regular = self._font_bold = None
        self.use_unicode = self._detect_unicode_fonts()
        self._family = "DejaVu" if self.use_unicode else "Helvetica"

    # ----------------------------------------------------------
    #  Fonts
    # ----------------------------------------------------------
    def _detect_unicode_fonts(self) -> bool:
        base = Path(__file__).parent / "fonts"
        reg  = base / "DejaVuSans.ttf"
        bold = base / "DejaVuSans-Bold.ttf"
        if reg.exists() and bold.exists():
            self._font_regular = str(reg)
            self._font_bold = str(bold)
            return True
        return False

    def _setup_fonts(self, pdf: FPDF):
        if not self.use_unicode:
            return
        pdf.add_font("DejaVu", "",  self._font_regular, uni=True)
        pdf.add_font("DejaVu", "B", self._font_bold,    uni=True)

    # ----------------------------------------------------------
    #  Safe text
    # ----------------------------------------------------------
    def _safe(self, value: Any) -> str:
        if value is None or value == "":
            return ""
        s = str(value)
        if not self.use_unicode:
            for bad, good in self._ASCII_MAP.items():
                s = s.replace(bad, good)
            s = s.encode("latin-1", "replace").decode("latin-1")
        return s

    # ----------------------------------------------------------
    #  Section header — tight spacing
    # ----------------------------------------------------------
    def _section_header(self, pdf: FPDF, title: str):
        pdf.ln(1)
        pdf.set_fill_color(*COLOR_PRIMARY)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font(self._family, "B", 10)
        pdf.cell(0, 7, f"  {title}", ln=True, fill=True)
        pdf.set_text_color(*COLOR_TEXT)

    # ----------------------------------------------------------
    #  Field row — tight spacing
    # ----------------------------------------------------------
    def _field_row(self, pdf: FPDF, label: str, value: Any):
        safe = self._safe(_clean(value))
        if not safe:
            return

        pdf.set_font(self._family, "B", 9)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.cell(46, 6, f"{label}:")

        pdf.set_font(self._family, size=9)
        pdf.set_text_color(*COLOR_TEXT)
        if len(safe) > 90:
            pdf.multi_cell(0, 6, safe)
        else:
            pdf.cell(0, 6, safe, ln=True)

    # ----------------------------------------------------------
    #  Divider — tight spacing
    # ----------------------------------------------------------
    def _divider(self, pdf: FPDF):
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.set_line_width(0.3)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(2)

    # ----------------------------------------------------------
    #  Zebra table — tight rows
    # ----------------------------------------------------------
    def _zebra_table(self, pdf: FPDF, headers: List[str],
                     rows: List[List[Any]], col_widths: List[int],
                     line_h: int = 6):
        pdf.set_font(self._family, "B", 9)
        pdf.set_fill_color(*COLOR_PRIMARY)
        pdf.set_text_color(255, 255, 255)
        for h, w in zip(headers, col_widths):
            pdf.cell(w, line_h + 1, f" {h}", border=0, fill=True)
        pdf.ln(line_h + 1)

        pdf.set_font(self._family, size=9)
        pdf.set_text_color(*COLOR_TEXT)
        for i, row in enumerate(rows):
            pdf.set_fill_color(*(COLOR_LIGHT_BG if i % 2 == 0 else (255, 255, 255)))
            for cell, w in zip(row, col_widths):
                pdf.cell(w, line_h, f" {self._safe(cell)}", border="B", fill=True)
            pdf.ln(line_h)

    # ----------------------------------------------------------
    #  Header band + footer
    # ----------------------------------------------------------
    def _draw_header(self, pdf: FPDF):
        pdf.set_fill_color(*COLOR_PRIMARY)
        pdf.rect(0, 0, pdf.w, 22, style="F")

        pdf.set_text_color(255, 255, 255)
        pdf.set_font(self._family, "B", 14)
        pdf.set_xy(pdf.l_margin, 5)
        pdf.cell(0, 7, self.title.upper(), ln=True)

        pdf.set_font(self._family, size=8)
        pdf.set_x(pdf.l_margin)
        pdf.cell(0, 4,
                 f"Generated on {datetime.now().strftime('%d %B %Y, %I:%M %p')}",
                 ln=True)

        pdf.set_text_color(*COLOR_TEXT)
        pdf.set_y(27)

    def _draw_footer(self, pdf: FPDF):
        pdf.set_y(-12)
        pdf.set_font(self._family, "I", 7)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.cell(
            0, 8,
            self._safe(
                f"Page {pdf.page_no()}  |  Confidential - for internal use only"
            ),
            align="C",
        )

    # ----------------------------------------------------------
    #  Summary banner
    # ----------------------------------------------------------
    def _draw_summary_banner(self, pdf: FPDF, data: Dict[str, Any]):
        name   = self._safe(_clean(data.get("full_name"))) or "Unnamed"
        age    = self._safe(_clean(data.get("age")))
        gender = self._safe(_clean(data.get("gender")))
        phone  = self._safe(_clean(data.get("mobile_number")))

        pdf.set_fill_color(*COLOR_LIGHT_BG)
        pdf.set_draw_color(*COLOR_BORDER)
        pdf.set_line_width(0.3)

        x, y = pdf.l_margin, pdf.get_y()
        w = pdf.w - pdf.l_margin - pdf.r_margin
        h = 18
        pdf.rect(x, y, w, h, style="DF")

        pdf.set_xy(x + 4, y + 2)
        pdf.set_font(self._family, "B", 12)
        pdf.set_text_color(*COLOR_PRIMARY)
        pdf.cell(0, 6, name, ln=True)

        sub_parts = []
        if age:    sub_parts.append(f"Age: {age}")
        if gender: sub_parts.append(f"Gender: {gender}")
        if phone:  sub_parts.append(f"Phone: {phone}")
        if sub_parts:
            pdf.set_x(x + 4)
            pdf.set_font(self._family, size=9)
            pdf.set_text_color(*COLOR_MUTED)
            pdf.cell(0, 5, "   |   ".join(sub_parts), ln=True)

        pdf.set_text_color(*COLOR_TEXT)
        pdf.set_y(y + h + 3)

    # ==========================================================
    #  Public entry
    # ==========================================================
    def build(self, data: Dict[str, Any]) -> bytes:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)     # keep summary on 1 page
        pdf.set_margins(12, 12, 12)
        pdf.add_page()

        self._setup_fonts(pdf)
        self._draw_header(pdf)
        self._draw_summary_banner(pdf, data)

        # ---- Numbered sections (only non-empty) -------------
        for section in SECTIONS:
            rows = []
            for key, label in section["fields"]:
                raw = data.get(key)

                # ✨ special-case: expand habit choices using schema labels
                if key == "smoking_alcohol":
                    value = _expand_habit(raw)
                else:
                    value = _clean(raw)

                if value:
                    rows.append((label, value))

            if not rows:
                continue

            self._section_header(pdf, section["title"])
            for label, value in rows:
                self._field_row(pdf, label, value)
            self._divider(pdf)

        # ---- 8. INSURED PEOPLE ------------------------------
        insured = data.get("insured_people") or []
        if insured:
            self._section_header(pdf, "8. INSURED PEOPLE")
            headers = ["#", "Name", "Age", "Gender", "Relationship"]
            rows = []
            for i, p in enumerate(insured, 1):
                if isinstance(p, dict):
                    rows.append([
                        i,
                        _clean(p.get("name")),
                        _clean(p.get("age")),
                        _clean(p.get("gender")),
                        _clean(p.get("relationship")),
                    ])
                else:
                    rows.append([i, _clean(p), "", "", ""])
            self._zebra_table(pdf, headers, rows,
                              col_widths=[10, 55, 20, 30, 65])
            self._divider(pdf)

        # ---- 9. PER-PERSON MEDICAL --------------------------
        medical_rows = []
        for p in insured:
            if not isinstance(p, dict):
                continue
            peds = _clean(p.get("peds_summary") or p.get("peds"))
            meds = _clean(p.get("medications_summary"))
            if peds or meds:
                medical_rows.append([p.get("name", ""), peds, meds])

        if medical_rows:
            self._section_header(pdf, "9. PER-PERSON MEDICAL SUMMARY")
            self._zebra_table(
                pdf,
                ["Name", "Conditions", "Medications"],
                medical_rows,
                col_widths=[45, 65, 70],
            )
            self._divider(pdf)

        # ---- 10. KYC DOCUMENTS ------------------------------
        docs = data.get("kyc_documents") or []
        doc_rows = []
        for i, d in enumerate(docs, 1):
            fname = _clean(d.get("filename")) if isinstance(d, dict) else _clean(d)
            if fname:
                doc_rows.append([i, fname])

        if doc_rows:
            self._section_header(pdf, "10. KYC DOCUMENTS")
            self._zebra_table(pdf, ["#", "Filename"], doc_rows,
                              col_widths=[12, 168])
            self._divider(pdf)

        # ---- 11. PROPOSAL NOTES -----------------------------
        notes = _clean(data.get("notes"))
        if notes:
            self._section_header(pdf, "11. PROPOSAL NOTES")
            pdf.set_font(self._family, size=9)
            pdf.set_text_color(*COLOR_TEXT)
            pdf.multi_cell(0, 6, self._safe(notes))
            self._divider(pdf)

        # ---- Declaration (always) ---------------------------
        pdf.set_font(self._family, "I", 8)
        pdf.set_text_color(*COLOR_MUTED)
        pdf.multi_cell(
            0, 5,
            "Declaration: The information provided above is true and correct "
            "to the best of my knowledge. I understand that any misrepresentation "
            "may lead to rejection of the proposal or cancellation of the policy.",
        )

        self._draw_footer(pdf)
        return bytes(pdf.output())


# ─────────────────────────────────────────────────────────────
#  Merge with uploaded attachments
# ─────────────────────────────────────────────────────────────
def _append_attachments(summary_bytes: bytes,
                        attachment_paths: List[str]) -> bytes:
    writer = PdfWriter()
    for page in PdfReader(BytesIO(summary_bytes)).pages:
        writer.add_page(page)

    for p in attachment_paths:
        try:
            path = Path(p)
            if not path.exists():
                continue
            for page in PdfReader(str(path)).pages:
                writer.add_page(page)
        except Exception as e:
            print(f"[pdf_generator] skipping attachment {p}: {e}")

    out = BytesIO()
    writer.write(out)
    return out.getvalue()


# ─────────────────────────────────────────────────────────────
#  Public API (same signature — no main.py changes)
# ─────────────────────────────────────────────────────────────
def generate_document_pdf(
    title: str = "Insurance Proposal",
    data: Optional[Dict[str, Any]] = None,
    attachment_paths: Optional[List[str]] = None,
) -> bytes:
    data = data or {}
    summary = ProposalPDF(title=title).build(data)
    if not attachment_paths:
        return summary
    return _append_attachments(summary, attachment_paths)