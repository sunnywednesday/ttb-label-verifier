"""
Field comparison logic for TTB label verification.

Design rationale (from stakeholder interviews):
- Dave (28yr agent): exact string matching produces false rejections on
  things like "STONE'S THROW" vs "Stone's Throw" -- same brand, different
  casing. Agents use judgment here, not literal matching. So most fields
  get a normalized comparison (case/whitespace/punctuation-insensitive)
  with a secondary fuzzy score, and we surface "needs human review"
  rather than silently auto-passing or auto-rejecting close-but-not-exact
  matches.
- Jenny (junior agent): the Government Warning is the one field where
  agents DON'T want leniency. It must be word-for-word, with the literal
  string "GOVERNMENT WARNING:" in all caps. So that field uses strict
  comparison with no fuzzy leniency, and explicitly checks the all-caps
  requirement on the warning label itself.
"""

import re
import difflib
from dataclasses import dataclass
from enum import Enum


class MatchStatus(Enum):
    PASS = "PASS"
    REVIEW = "NEEDS REVIEW"
    FAIL = "MISMATCH"
    MISSING = "MISSING ON LABEL"


@dataclass
class FieldResult:
    field: str
    application_value: str
    label_value: str
    status: MatchStatus
    similarity: float
    note: str = ""


REQUIRED_WARNING_TEXT = (
    "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT "
    "DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH "
    "DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO "
    "DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
)


def _normalize(s: str) -> str:
    """Lowercase, collapse whitespace, strip common punctuation noise."""
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"[\u2018\u2019]", "'", s)  # curly quotes -> straight
    s = re.sub(r"\s+", " ", s)
    return s


def _similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def compare_field(field_name: str, app_value: str, label_value: str,
                   review_threshold: float = 0.85) -> FieldResult:
    app_value = (app_value or "").strip()
    label_value = (label_value or "").strip()

    if not label_value:
        return FieldResult(field_name, app_value, label_value,
                            MatchStatus.MISSING, 0.0,
                            "Field not detected on label image.")

    if _normalize(app_value) == _normalize(label_value):
        return FieldResult(field_name, app_value, label_value,
                            MatchStatus.PASS, 1.0)

    sim = _similarity(app_value, label_value)
    if sim >= review_threshold:
        return FieldResult(field_name, app_value, label_value,
                            MatchStatus.REVIEW, sim,
                            "Close match (casing/punctuation difference) -- "
                            "likely same value, flagged for a quick human glance.")

    return FieldResult(field_name, app_value, label_value,
                        MatchStatus.FAIL, sim,
                        "Values do not appear to match.")


def compare_government_warning(label_warning_text: str) -> FieldResult:
    """
    Strict check: exact wording required, plus the 'GOVERNMENT WARNING:'
    lead-in must be present in all caps on the label (per Jenny's note that
    title-case warnings get rejected). No fuzzy leniency here by design.
    """
    label_warning_text = (label_warning_text or "").strip()

    if not label_warning_text:
        return FieldResult("Government Warning", REQUIRED_WARNING_TEXT, "",
                            MatchStatus.MISSING, 0.0,
                            "No warning statement detected on label.")

    has_caps_lead_in = "GOVERNMENT WARNING:" in label_warning_text

    normalized_label = _normalize(label_warning_text)
    normalized_required = _normalize(REQUIRED_WARNING_TEXT)

    if normalized_label == normalized_required and has_caps_lead_in:
        return FieldResult("Government Warning", REQUIRED_WARNING_TEXT,
                            label_warning_text, MatchStatus.PASS, 1.0)

    if normalized_label == normalized_required and not has_caps_lead_in:
        return FieldResult("Government Warning", REQUIRED_WARNING_TEXT,
                            label_warning_text, MatchStatus.FAIL, 0.99,
                            "Wording is correct but 'GOVERNMENT WARNING:' "
                            "lead-in is not in required all-caps format.")

    sim = difflib.SequenceMatcher(None, normalized_label, normalized_required).ratio()
    return FieldResult("Government Warning", REQUIRED_WARNING_TEXT,
                        label_warning_text, MatchStatus.FAIL, sim,
                        "Warning text deviates from the required statement. "
                        "No leniency applied -- this field must be verbatim.")


def run_comparison(application: dict, extracted: dict) -> list:
    """
    application: dict with keys brand_name, class_type, abv, net_contents,
                 producer_name_address, country_of_origin (optional)
    extracted:   same keys, values OCR'd/extracted from the label image,
                 plus government_warning_text
    """
    results = []
    fuzzy_fields = [
        ("brand_name", "Brand Name"),
        ("class_type", "Class/Type"),
        ("producer_name_address", "Name & Address of Bottler/Producer"),
    ]
    exact_fields = [
        ("abv", "Alcohol Content"),
        ("net_contents", "Net Contents"),
    ]

    for key, label in fuzzy_fields:
        if application.get(key):
            results.append(compare_field(label, application.get(key, ""),
                                          extracted.get(key, "")))

    for key, label in exact_fields:
        if application.get(key):
            results.append(compare_field(label, application.get(key, ""),
                                          extracted.get(key, ""),
                                          review_threshold=0.95))

    if application.get("country_of_origin"):
        results.append(compare_field("Country of Origin",
                                      application.get("country_of_origin", ""),
                                      extracted.get("country_of_origin", "")))

    results.append(compare_government_warning(extracted.get("government_warning_text", "")))

    return results


def overall_status(results: list) -> MatchStatus:
    statuses = {r.status for r in results}
    if MatchStatus.FAIL in statuses or MatchStatus.MISSING in statuses:
        return MatchStatus.FAIL
    if MatchStatus.REVIEW in statuses:
        return MatchStatus.REVIEW
    return MatchStatus.PASS
