# questionnaire.py
"""
Fixed questionnaire framework.
Every uploaded document is checked against these fields.
Anything missing is asked conversationally, in order.
"""

from typing import List, Optional, Callable


# ─────────────────────────────────────────────────────────────
# MASTER QUESTION SET  (12 primary fields)
# Each entry now carries a UI-friendly `label`, Lucide `icon` name,
# and `type` so the frontend can render without hardcoding anything.
# ─────────────────────────────────────────────────────────────

QUESTION_SET: List[dict] = [
    {
        "field": "full_name",
        "label": "Full Name",
        "icon": "user",
        "type": "text",
        "question": "What is your full name?",
        "aliases": ["name", "customer_name", "insured_name", "policy_holder_name", "applicant_name"],
        "validator": None,
    },
        {
        "field": "age",
        "label": "Age",
        "icon": "cake",
        "type": "number",
        "question": "What is your age? (in years)",
        "aliases": ["dob", "date_of_birth", "birth_date", "birthdate", "years"],
        "validator": "regex:^\\d{1,3}$",
    },
    {
        "field": "gender",
        "label": "Gender",
        "icon": "user-circle",
        "type": "choice",
        "question": "What is your gender? (Male / Female / Other)",
        "aliases": ["sex"],
        "validator": "choice:male,female,other",
        "options": ["Male", "Female", "Other"],
    },
    {
        "field": "mobile_number",
        "label": "Mobile Number",
        "icon": "phone",
        "type": "text",
        "question": "What is your mobile number? (10 digits)",
        "aliases": ["phone", "mobile", "contact_number", "phone_number"],
        "validator": "regex:^\\d{10}$",
    },
    {
        "field": "aadhaar_number",
        "label": "Aadhaar Number",
        "icon": "fingerprint",
        "type": "text",
        "question": "What is your Aadhaar number? (12 digits)",
        "aliases": ["aadhaar", "aadhar", "aadhar_number", "uid", "uidai"],
        "validator": "regex:^\\d{12}$",
    },
    {
        "field": "pan_number",
        "label": "PAN Number",
        "icon": "credit-card",
        "type": "text",
        "question": "What is your PAN number? (e.g. ABCDE1234F)",
        "aliases": ["pan", "pan_card", "permanent_account_number"],
        "validator": "regex:^[A-Z]{5}\\d{4}[A-Z]$",
    },
    {
        "field": "email_address",
        "label": "Email Address",
        "icon": "mail",
        "type": "email",
        "question": "What is your email address?",
        "aliases": ["email", "email_id"],
        "validator": "regex:^[\\w.+-]+@[\\w-]+\\.[\\w.-]+$",
    },
    {
        "field": "address",
        "label": "Residential Address",
        "icon": "home",
        "type": "textarea",
        "question": "What is your current residential address and PIN code?",
        "aliases": ["full_address", "residential_address", "current_address", "permanent_address"],
        "validator": None,
    },
    {
        "field": "occupation",
        "label": "Occupation",
        "icon": "briefcase",
        "type": "text",
        "question": "What is your occupation?",
        "aliases": ["job", "profession", "employment", "designation"],
        "validator": None,
    },
    {
        "field": "annual_income",
        "label": "Annual Income",
        "icon": "coins",
        "type": "text",
        "question": "What is your approximate annual income?",
        "aliases": ["income", "yearly_income", "salary"],
        "validator": None,
    },
    {
        "field": "pre_existing_diseases",
        "label": "Pre-existing Diseases",
        "icon": "alert-triangle",
        "type": "choice",
        "question": "Do you have any pre-existing diseases or medical conditions (PED)?",
        "aliases": ["ped", "pre_existing_conditions", "medical_conditions", "diseases"],
        "validator": "choice:yes,no",
        "options": ["Yes", "No"],
    },
        {
        "field": "smoking_alcohol",
        "label": "Habits & Lifestyle",
        "icon": "cigarette",
        "type": "choice",
        "question": (
            "Do you have any habits like smoking, drinking alcohol, "
            "using tobacco, or anything similar?"
        ),
        "aliases": ["habits", "smoking", "alcohol", "lifestyle", "tobacco", "drugs"],
        "validator": (
            "choice:no,smoking,alcohol,tobacco,smoking and alcohol,"
            "smoking and tobacco,alcohol and tobacco,all of the above,"
            "prefer to provide details"
        ),
        "options": [
            "No",
            "Smoking",
            "Alcohol",
            "Tobacco",
            "Smoking and Alcohol",
            "Smoking and Tobacco",
            "Alcohol and Tobacco",
            "All of the above",
            "Prefer to provide details",
        ],
    },
]

QUESTION_MAP = {q["field"]: q for q in QUESTION_SET}


# ─────────────────────────────────────────────────────────────
# CONDITIONAL FOLLOW-UPS
# ─────────────────────────────────────────────────────────────

def _ped_followups(value: Optional[str]) -> Optional[List[dict]]:
    """'Yes' → ask for details. 'No' → nothing."""
    if not value:
        return None
    v = str(value).strip().lower()
    # Accept: yes, y, true, 1, "yes, diabetes", boolean True → "true"
    if v.startswith("y") or v in ("true", "1") or "yes" in v:
        return [{
            "field": "ped_details",
            "label": "PED Details",
            "icon": "stethoscope",
            "type": "textarea",
            "question": (
                "Please describe your pre-existing conditions — "
                "the name of the disease/condition, when it was diagnosed, "
                "and any current treatment or medication."
            ),
            "validator": None,
        }]
    return None


def _smoking_alcohol_followups(value: Optional[str]) -> Optional[List[dict]]:
    """
    - "Smoking" / "Alcohol" / "Both" → ask frequency for the applicable one(s)
    - "Prefer to provide details"    → ask a single open-ended details question
    - "No"                            → nothing
    """
    if not value:
        return None
    v = str(value).strip().lower()

    # ---- "Prefer to provide details" → one open-ended question
    if "prefer" in v:
        return [{
            "field": "smoking_alcohol_details",
            "label": "Habits Details",
            "icon": "cigarette",
            "type": "textarea",
            "question": (
                "Sure — please describe your smoking / alcohol habits "
                "(type, how often, since when, quantity, etc.)."
            ),
            "validator": None,
        }]

    # ---- Individual choices → ask frequency per applicable habit
    followups = []
    if "smoking" in v or v in ("both", "tobacco"):
        followups.append({
            "field": "smoking_frequency",
            "label": "Smoking Frequency",
            "icon": "cigarette",
            "type": "text",
            "question": "How frequently do you smoke?",
            "validator": None,
        })
    if "alcohol" in v or v == "both":
        followups.append({
            "field": "alcohol_frequency",
            "label": "Alcohol Frequency",
            "icon": "activity",
            "type": "text",
            "question": "How frequently do you consume alcohol?",
            "validator": None,
        })
    return followups or None


FOLLOWUPS: dict[str, Callable[[Optional[str]], Optional[List[dict]]]] = {
    "pre_existing_diseases": _ped_followups,
    "smoking_alcohol":       _smoking_alcohol_followups,
}


# ─────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────

def primary_fields() -> List[str]:
    return [q["field"] for q in QUESTION_SET]


def all_aliases_for(field: str) -> List[str]:
    q = QUESTION_MAP.get(field)
    if not q:
        return [field]
    return [field] + q.get("aliases", [])


# Registry of follow-up definitions keyed by field name,
# so we don't need to force-trigger the functions to look up a question.
_FOLLOWUP_DEFS: dict[str, dict] = {
    "ped_details": {
        "label": "PED Details",
        "icon": "stethoscope",
        "type": "textarea",
        "question": (
            "Please describe your pre-existing conditions — "
            "the name of the disease/condition, when it was diagnosed, "
            "and any current treatment or medication."
        ),
    },
    "smoking_frequency": {
        "label": "Smoking Frequency",
        "icon": "cigarette",
        "type": "text",
        "question": "How frequently do you smoke?",
    },
    "alcohol_frequency": {
        "label": "Alcohol Frequency",
        "icon": "activity",
        "type": "text",
        "question": "How frequently do you consume alcohol?",
    },
    "smoking_alcohol_details": {
        "label": "Habits Details",
        "icon": "cigarette",
        "type": "textarea",
        "question": (
            "Sure — please describe your smoking / alcohol habits "
            "(type, how often, since when, quantity, etc.)."
        ),
    },
}


def get_question(field: str) -> str:
    q = QUESTION_MAP.get(field)
    if q:
        return q["question"]
    if field in _FOLLOWUP_DEFS:
        return _FOLLOWUP_DEFS[field]["question"]
    return f"Please provide **{field.replace('_', ' ')}**."


def get_label(field: str) -> str:
    q = QUESTION_MAP.get(field)
    if q:
        return q.get("label") or field.replace("_", " ").title()
    if field in _FOLLOWUP_DEFS:
        return _FOLLOWUP_DEFS[field].get("label") or field.replace("_", " ").title()
    return field.replace("_", " ").title()

def get_options(field: str) -> Optional[List[str]]:
    q = QUESTION_MAP.get(field)
    return q.get("options") if q else None


def followups_for(field: str, value: Optional[str]) -> Optional[List[dict]]:
    fn = FOLLOWUPS.get(field)
    return fn(value) if fn else None


def is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip().lower() in ("", "null", "none", "n/a", "not provided"):
        return True
    return False


def find_missing_fields(data: dict) -> List[str]:
    missing = []
    for f in primary_fields():
        if is_blank(data.get(f)):
            missing.append(f)
    return missing


def normalize_alias_keys(data: dict) -> dict:
    out = {}
    reverse = {}
    for q in QUESTION_SET:
        reverse[q["field"].lower()] = q["field"]
        for a in q.get("aliases", []):
            reverse[a.lower()] = q["field"]

    for k, v in data.items():
        canonical = reverse.get(k.lower().replace(" ", "_"), k)
        if canonical in out and not is_blank(out[canonical]):
            continue
        out[canonical] = v
    return out


def validate(field: str, value: str) -> tuple[bool, Optional[str]]:
    if is_blank(value):
        return False, "Please provide a non-empty value."

    q = QUESTION_MAP.get(field)
    validator = q.get("validator") if q else None
    if not validator:
        return True, None

    import re
    v = str(value).strip()

    if validator == "date":
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            return True, None
        return False, "Please provide the date as YYYY-MM-DD."

    if validator.startswith("regex:"):
        pattern = validator[len("regex:"):]
        if re.match(pattern, v, re.IGNORECASE):
            return True, None
        return False, "That doesn't look valid. Please try again."

    if validator.startswith("choice:"):
        allowed = [c.strip().lower() for c in validator[len("choice:"):].split(",")]
        if v.lower() in allowed:
            return True, None
        return False, f"Please choose one of: {', '.join(allowed)}."

    return True, None


# ─────────────────────────────────────────────────────────────
# NEW — build the schema payload for the frontend
# ─────────────────────────────────────────────────────────────

def build_schema() -> dict:
    """
    Returns the full schema the frontend needs to render
    the sidebar, profile view, and option buttons.
    """
    primary = []
    for q in QUESTION_SET:
        primary.append({
            "field": q["field"],
            "label": q.get("label") or q["field"].replace("_", " ").title(),
            "icon": q.get("icon", "user"),
            "type": q.get("type", "text"),
            "question": q["question"],
            "options": q.get("options"),
            "required": True,
        })

    followups = []
    for field, meta in _FOLLOWUP_DEFS.items():
        followups.append({
            "field": field,
            "label": meta.get("label") or field.replace("_", " ").title(),
            "icon": meta.get("icon", "user"),
            "type": meta.get("type", "text"),
            "question": meta["question"],
            "options": meta.get("options"),
            "required": False,
        })

    return {
        "title": "HealthConcierge Pro",
        "subtitle": "Underwriting-Ready Intake & Insurance Passport",
        "primary_fields": primary,
        "followup_fields": followups,
    }