#!/usr/bin/env python
"""Page-wise Malayalam translation audit for HTML templates.

This script audits template i18n in two layers:
1) Runtime layer from compiled .mo (what users currently see)
2) Source layer from .po (draft status: approved/fuzzy/empty)

Outputs:
- translation_audit_pagewise.md
- translation_audit_pagewise.csv
"""

from __future__ import annotations

import argparse
import ast
import csv
import gettext
import glob
import html
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


SOURCE_I18N = "i18n_msgid_occurrence"
SOURCE_HARDCODED = "hardcoded_html"
REVIEW_MEANING_CHECK = "meaning_check"


KNOWN_MEANING_DIVERGENCE_MSGIDS: Set[str] = set()

KNOWN_BRAND_WHITELIST = {
    "Vasudha Foundation",
    "EMC Keralam",
    "Keralam Clean Cooking Tool",
}

COUNTRY_LABELS = {"India", "UAE", "Sri Lanka", "UK", "USA"}

STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "into",
    "your",
    "you",
    "have",
    "more",
    "what",
    "when",
    "where",
    "then",
    "next",
    "step",
    "steps",
    "for",
    "and",
    "the",
    "are",
    "how",
    "all",
    "per",
    "day",
    "month",
    "year",
    "cost",
    "risk",
}


@dataclass
class PoEntry:
    msgid: str
    msgstr: str
    flags: Set[str]
    occurrences: List[Tuple[str, int]]
    obsolete: bool = False


@dataclass
class AuditRow:
    page: str
    line: int
    msgid: str
    runtime_text: str
    po_msgstr: str
    po_status: str
    runtime_status: str
    review_flag: str
    source_type: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit Malayalam template translations from both runtime (.mo) and source (.po)."
    )
    parser.add_argument(
        "--scope",
        nargs="+",
        default=["templates/*.html"],
        help="Glob(s) for template files to audit (default: templates/*.html).",
    )
    parser.add_argument(
        "--locale",
        default="ml",
        help="Locale code to audit (default: ml).",
    )
    parser.add_argument(
        "--mode",
        choices=["runtime", "po", "both"],
        default="both",
        help="Audit mode (default: both).",
    )
    parser.add_argument(
        "--format",
        default="md,csv",
        help="Output formats: comma-separated subset of md,csv (default: md,csv).",
    )
    parser.add_argument(
        "--po-path",
        default=None,
        help="Path to PO file (default: translations/<locale>/LC_MESSAGES/messages.po).",
    )
    parser.add_argument(
        "--mo-path",
        default=None,
        help="Path to MO file (default: translations/<locale>/LC_MESSAGES/messages.mo).",
    )
    parser.add_argument(
        "--out-md",
        default="translation_audit_pagewise.md",
        help="Markdown output path (default: translation_audit_pagewise.md).",
    )
    parser.add_argument(
        "--out-csv",
        default="translation_audit_pagewise.csv",
        help="CSV output path (default: translation_audit_pagewise.csv).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic spot-check sampling (default: 42).",
    )
    return parser.parse_args()


def normalize_page_path(path_str: str) -> str:
    return Path(path_str).as_posix()


def collapse_ws(text: str) -> str:
    return " ".join(text.split())


def unquote_po_literal(value: str) -> str:
    value = value.strip()
    if not value.startswith('"'):
        return ""
    try:
        parsed = ast.literal_eval(value)
    except Exception:
        parsed = value.strip('"')
    return str(parsed)


def parse_po(po_path: Path) -> List[PoEntry]:
    raw = po_path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", raw)
    entries: List[PoEntry] = []

    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        occurrences: List[Tuple[str, int]] = []
        flags: Set[str] = set()
        msgid = ""
        msgstr = ""
        state: Optional[str] = None
        obsolete = False

        for line in lines:
            if line.startswith("#~"):
                obsolete = True
                break

            if line.startswith("#:"):
                for token in line[2:].strip().split():
                    if ":" not in token:
                        continue
                    page, ln = token.rsplit(":", 1)
                    if not ln.isdigit():
                        continue
                    occurrences.append((normalize_page_path(page), int(ln)))
                continue

            if line.startswith("#,"):
                for flag in line[2:].split(","):
                    cleaned = flag.strip()
                    if cleaned:
                        flags.add(cleaned)
                continue

            if line.startswith("msgid "):
                state = "msgid"
                msgid = unquote_po_literal(line[6:])
                continue

            if line.startswith("msgstr "):
                state = "msgstr"
                msgstr = unquote_po_literal(line[7:])
                continue

            if line.startswith("msgid_plural"):
                state = "msgid_plural"
                continue

            if line.startswith("msgstr["):
                state = "msgstr_plural"
                closing = line.find("]")
                payload = line[closing + 1 :] if closing != -1 else ""
                piece = unquote_po_literal(payload)
                if piece:
                    msgstr += piece
                continue

            if line.startswith('"'):
                piece = unquote_po_literal(line)
                if state == "msgid":
                    msgid += piece
                elif state in {"msgstr", "msgstr_plural"}:
                    msgstr += piece
                continue

        if obsolete:
            continue

        if not msgid:
            # Header entry has empty msgid and is not useful for this audit.
            continue

        entries.append(
            PoEntry(
                msgid=msgid,
                msgstr=msgstr,
                flags=flags,
                occurrences=occurrences,
                obsolete=False,
            )
        )

    return entries


def load_runtime_translation(mo_path: Path) -> gettext.NullTranslations:
    if not mo_path.exists():
        return gettext.NullTranslations()
    with mo_path.open("rb") as handle:
        return gettext.GNUTranslations(handle)


def expand_scope(patterns: Sequence[str]) -> List[Path]:
    files: Set[Path] = set()
    for pattern in patterns:
        for item in glob.glob(pattern):
            p = Path(item)
            if p.is_file():
                files.add(p)
    return sorted(files)


def in_scope(page: str, scoped_pages: Set[str]) -> bool:
    return normalize_page_path(page) in scoped_pages


def classify_po_status(msgstr: str, flags: Set[str], mode: str) -> str:
    if mode not in {"po", "both"}:
        return "not_checked"
    if not msgstr.strip():
        return "empty"
    if "fuzzy" in flags:
        return "fuzzy"
    return "approved"


def classify_runtime_status(msgid: str, runtime_text: str, mode: str) -> str:
    if mode not in {"runtime", "both"}:
        return "not_checked"
    if runtime_text == msgid:
        return "english_fallback"
    return "translated_ml"


def looks_like_placeholder_or_sample(text: str) -> bool:
    lower = text.lower()
    if "example" in lower:
        return True
    if "@" in text:
        return True
    if "www." in lower or "http://" in lower or "https://" in lower:
        return True
    return False


def detect_placeholder_drift(msgid: str, po_msgstr: str) -> bool:
    if not msgid or not po_msgstr:
        return False
    if not looks_like_placeholder_or_sample(msgid):
        return False

    id_lower = msgid.lower()
    out_lower = po_msgstr.lower()

    if "@" in msgid and "@" not in po_msgstr:
        return True
    if "example.com" in id_lower and "example.com" not in out_lower:
        return True
    if "www." in id_lower and "www." not in out_lower:
        return True
    if id_lower.startswith("http") and not out_lower.startswith("http"):
        return True
    return False


def build_i18n_rows(
    entries: Sequence[PoEntry],
    scoped_pages: Set[str],
    runtime_translation: gettext.NullTranslations,
    mode: str,
) -> Tuple[List[AuditRow], int]:
    rows: List[AuditRow] = []
    seen: Set[Tuple[str, int, str, str]] = set()
    expected_unique_occurrences: Set[Tuple[str, int, str]] = set()

    for entry in entries:
        po_status = classify_po_status(entry.msgstr, entry.flags, mode)
        runtime_text = runtime_translation.gettext(entry.msgid) if mode in {"runtime", "both"} else ""
        runtime_status = classify_runtime_status(entry.msgid, runtime_text, mode)

        review_flag = ""
        if (
            po_status == "fuzzy"
            or detect_placeholder_drift(entry.msgid, entry.msgstr)
            or entry.msgid in KNOWN_MEANING_DIVERGENCE_MSGIDS
        ):
            review_flag = REVIEW_MEANING_CHECK

        for page, line in entry.occurrences:
            if not in_scope(page, scoped_pages):
                continue

            expected_unique_occurrences.add((page, line, entry.msgid))
            key = (page, line, entry.msgid, SOURCE_I18N)
            if key in seen:
                continue
            seen.add(key)

            rows.append(
                AuditRow(
                    page=page,
                    line=line,
                    msgid=entry.msgid,
                    runtime_text=runtime_text,
                    po_msgstr=entry.msgstr,
                    po_status=po_status,
                    runtime_status=runtime_status,
                    review_flag=review_flag,
                    source_type=SOURCE_I18N,
                )
            )

    rows.sort(key=lambda row: (row.page, row.line, row.msgid))
    return rows, len(expected_unique_occurrences)


def blank_non_newline(match: re.Match[str]) -> str:
    return "".join("\n" if ch == "\n" else " " for ch in match.group(0))


def mask_non_visible_template_regions(content: str) -> str:
    masked = content
    patterns = [
        (r"<!--.*?-->", re.S),
        (r"<script\b.*?</script>", re.S | re.I),
        (r"<style\b.*?</style>", re.S | re.I),
        (r"\{#.*?#\}", re.S),
        (r"\{%.*?%\}", re.S),
        (r"\{\{.*?\}\}", re.S),
    ]
    for pattern, flags in patterns:
        masked = re.sub(pattern, blank_non_newline, masked, flags=flags)
    return masked


def is_likely_technical_token(text: str) -> bool:
    compact = text.strip()
    if not compact:
        return True
    if re.fullmatch(r"[+0-9()\s/.,:-]+", compact):
        return True
    if re.fullmatch(r"[0-9.,]+\s*(kg|kwh|kw|mj|co2|scm|m2|m\^2)?", compact.lower()):
        return True
    if compact in {"kg", "kWh", "kW", "MJ", "SCM", "CO2", "m2", "x"}:
        return True
    return False


def is_email_or_url(text: str) -> bool:
    lowered = text.lower()
    if re.fullmatch(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", lowered):
        return True
    if lowered.startswith("http://") or lowered.startswith("https://"):
        return True
    if lowered.startswith("www.") and "." in lowered:
        return True
    return False


def should_keep_hardcoded_candidate(text: str) -> bool:
    norm = collapse_ws(html.unescape(text))
    if not norm:
        return False
    if norm in KNOWN_BRAND_WHITELIST:
        return False
    if is_email_or_url(norm):
        return False
    if is_likely_technical_token(norm):
        return False
    if not re.search(r"[A-Za-z]", norm):
        return False
    return True


def extract_hardcoded_rows(scoped_files: Sequence[Path]) -> List[AuditRow]:
    rows: List[AuditRow] = []
    seen: Set[Tuple[str, int, str, str]] = set()
    attr_names = {"alt", "placeholder", "title", "aria-label"}

    for file_path in scoped_files:
        page = normalize_page_path(str(file_path))
        raw = file_path.read_text(encoding="utf-8")
        masked = mask_non_visible_template_regions(raw)

        # Visible text nodes
        for match in re.finditer(r">([^<]+)<", masked):
            candidate = collapse_ws(html.unescape(match.group(1)))
            if not should_keep_hardcoded_candidate(candidate):
                continue
            line = raw.count("\n", 0, match.start()) + 1
            key = (page, line, candidate, SOURCE_HARDCODED)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                AuditRow(
                    page=page,
                    line=line,
                    msgid=candidate,
                    runtime_text=candidate,
                    po_msgstr="",
                    po_status="not_applicable",
                    runtime_status="hardcoded_english",
                    review_flag=REVIEW_MEANING_CHECK,
                    source_type=SOURCE_HARDCODED,
                )
            )

        # Static attributes
        for match in re.finditer(r'(\w[\w:-]*)\s*=\s*(["\'])(.*?)\2', masked, flags=re.S):
            attr_name = match.group(1)
            attr_value = collapse_ws(html.unescape(match.group(3)))
            if attr_name not in attr_names:
                continue
            if not should_keep_hardcoded_candidate(attr_value):
                continue
            line = raw.count("\n", 0, match.start()) + 1
            key = (page, line, f"{attr_name}={attr_value}", SOURCE_HARDCODED)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                AuditRow(
                    page=page,
                    line=line,
                    msgid=f"{attr_name}=\"{attr_value}\"",
                    runtime_text=attr_value,
                    po_msgstr="",
                    po_status="not_applicable",
                    runtime_status="hardcoded_english",
                    review_flag=REVIEW_MEANING_CHECK,
                    source_type=SOURCE_HARDCODED,
                )
            )

    rows.sort(key=lambda row: (row.page, row.line, row.msgid))
    return rows


def compute_global_counts(rows: Sequence[AuditRow]) -> Dict[str, int]:
    i18n_rows = [row for row in rows if row.source_type == SOURCE_I18N]
    return {
        "total_translatable_occurrences": len(i18n_rows),
        "runtime_ml": sum(1 for row in i18n_rows if row.runtime_status == "translated_ml"),
        "runtime_fallback": sum(1 for row in i18n_rows if row.runtime_status == "english_fallback"),
        "po_empty": sum(1 for row in i18n_rows if row.po_status == "empty"),
        "po_fuzzy": sum(1 for row in i18n_rows if row.po_status == "fuzzy"),
        "hardcoded_english": sum(1 for row in rows if row.source_type == SOURCE_HARDCODED),
    }


def rows_by_page(rows: Sequence[AuditRow]) -> Dict[str, List[AuditRow]]:
    grouped: Dict[str, List[AuditRow]] = defaultdict(list)
    for row in rows:
        grouped[row.page].append(row)
    for page in grouped:
        grouped[page].sort(key=lambda row: (row.line, row.msgid, row.source_type))
    return grouped


def find_high_priority_findings(rows: Sequence[AuditRow]) -> List[str]:
    findings: List[str] = []
    indexed = {(row.page, row.line, collapse_ws(row.msgid)): row for row in rows}

    expected_empty = [
        ("templates/analysis.html", 469, "Next Steps & Actions"),
        ("templates/commercial_analysis.html", 738, "Next Steps & Actions"),
        (
            "templates/energy_calculation.html",
            502,
            "Select and enter the consumption details for each fuel type you use for cooking.",
        ),
        (
            "templates/commercial_energy_calculation.html",
            488,
            "Select and enter the consumption details for each fuel type you use for cooking.",
        ),
        (
            "templates/feedback_success.html",
            28,
            "Government authorities will contact you regarding your selected schemes",
        ),
        ("templates/feedback_success.html", 51, "Schemes You Selected"),
    ]

    for page, line, msg in expected_empty:
        key = (page, line, msg)
        row = indexed.get(key)
        if row and row.po_status == "empty":
            findings.append(f"[check] Still PO-empty: `{page}:{line}` -> `{msg}`")
        elif row and row.po_status in {"approved", "fuzzy"}:
            findings.append(f"[resolved] PO-empty fixed: `{page}:{line}` -> `{msg}`")
        else:
            findings.append(f"[check] Expected entry not found: `{page}:{line}` -> `{msg}`")

    hardcoded_rows = [row for row in rows if row.source_type == SOURCE_HARDCODED]
    hardcoded_by_page = rows_by_page(hardcoded_rows)
    i18n_rows = [row for row in rows if row.source_type == SOURCE_I18N]
    i18n_by_page = rows_by_page(i18n_rows)
    for page in ("templates/household_profile.html", "templates/commercial_selection.html"):
        labels_hardcoded: Set[str] = set()
        for row in hardcoded_by_page.get(page, []):
            for label in COUNTRY_LABELS:
                if label in row.msgid:
                    labels_hardcoded.add(label)

        labels_i18n_translated: Set[str] = set()
        for row in i18n_by_page.get(page, []):
            if row.msgid in COUNTRY_LABELS and row.runtime_status == "translated_ml":
                labels_i18n_translated.add(row.msgid)

        if labels_hardcoded == COUNTRY_LABELS:
            findings.append(f"[check] Country labels are still hardcoded in `{page}`")
        elif labels_i18n_translated == COUNTRY_LABELS:
            findings.append(f"[resolved] Country labels localized via i18n in `{page}`")
        else:
            missing = sorted(COUNTRY_LABELS - labels_i18n_translated)
            findings.append(f"[check] Country-label localization incomplete in `{page}`: {', '.join(missing)}")

    contact_rows = [row for row in rows if row.msgid == "Contact Us" and row.source_type == SOURCE_I18N]
    if contact_rows:
        sample = contact_rows[0]
        runtime = collapse_ws(sample.runtime_text)
        if runtime == "ബന്ധപ്പെടേണ്ട വ്യക്തി":
            findings.append(
                "[check] Potential semantic mismatch: "
                f"`Contact Us` -> runtime `{runtime}` (review manually)"
            )
        else:
            findings.append(f"[resolved] `Contact Us` updated to runtime `{runtime}`")
    else:
        findings.append("[check] Could not locate `Contact Us` in i18n rows.")

    email_rows = [row for row in rows if row.msgid == "email@example.com" and row.source_type == SOURCE_I18N]
    if email_rows:
        sample = email_rows[0]
        po_val = collapse_ws(sample.po_msgstr)
        if po_val != "email@example.com":
            findings.append(
                "[check] Placeholder drift candidate: "
                f"`email@example.com` -> PO `{po_val}`"
            )
        else:
            findings.append("[resolved] Placeholder fixed: `email@example.com` preserved in PO")
    else:
        findings.append("[check] Could not locate `email@example.com` in i18n rows.")

    for page in ("templates/energy_calculation.html", "templates/commercial_energy_calculation.html"):
        fuzzy_count = sum(
            1
            for row in rows
            if row.source_type == SOURCE_I18N and row.page == page and row.po_status == "fuzzy"
        )
        findings.append(f"[info] Fuzzy draft entries in `{page}`: {fuzzy_count}")

    return findings


def token_set_for_msgid(msgid: str) -> Set[str]:
    tokens = {token.lower() for token in re.findall(r"[A-Za-z]{4,}", msgid)}
    return {token for token in tokens if token not in STOPWORDS}


def line_context(lines: List[str], line_number: int, radius: int = 2) -> str:
    start = max(0, line_number - 1 - radius)
    end = min(len(lines), line_number + radius)
    context = " ".join(lines[start:end])
    return collapse_ws(context).lower()


def run_validations(
    rows: Sequence[AuditRow],
    expected_unique_occurrence_count: int,
    scoped_files: Sequence[Path],
    seed: int,
) -> Dict[str, object]:
    i18n_rows = [row for row in rows if row.source_type == SOURCE_I18N]
    hardcoded_rows = [row for row in rows if row.source_type == SOURCE_HARDCODED]

    represented_once_pass = len(i18n_rows) == expected_unique_occurrence_count

    fuzzy_rows = [row for row in i18n_rows if row.po_status == "fuzzy"]
    fuzzy_runtime_fallback = [row for row in fuzzy_rows if row.runtime_status == "english_fallback"]
    fuzzy_runtime_check_pass = len(fuzzy_rows) == len(fuzzy_runtime_fallback)
    fuzzy_runtime_nonfallback = [row for row in fuzzy_rows if row.runtime_status != "english_fallback"]

    po_empty_rows = [row for row in i18n_rows if row.po_status == "empty"]
    po_empty_runtime_fallback = [row for row in po_empty_rows if row.runtime_status == "english_fallback"]
    po_empty_check_pass = len(po_empty_rows) == len(po_empty_runtime_fallback)

    hardcoded_country_pass = True
    for page in ("templates/household_profile.html", "templates/commercial_selection.html"):
        labels_found: Set[str] = set()
        for row in hardcoded_rows:
            if row.page != page:
                continue
            for label in COUNTRY_LABELS:
                if label in row.msgid:
                    labels_found.add(label)
        if labels_found != COUNTRY_LABELS:
            hardcoded_country_pass = False

    hardcoded_brand_leak = [
        row
        for row in hardcoded_rows
        if any(brand in row.msgid for brand in KNOWN_BRAND_WHITELIST)
    ]
    hardcoded_brand_pass = len(hardcoded_brand_leak) == 0

    random.seed(seed)
    by_page_i18n = rows_by_page(i18n_rows)
    major_pages = sorted(by_page_i18n, key=lambda page: len(by_page_i18n[page]), reverse=True)[:5]

    page_content: Dict[str, List[str]] = {}
    for file_path in scoped_files:
        page_content[normalize_page_path(str(file_path))] = file_path.read_text(encoding="utf-8").splitlines()

    spot_checks: Dict[str, Dict[str, int]] = {}
    for page in major_pages:
        candidates = by_page_i18n[page]
        sample_size = min(10, len(candidates))
        sampled = random.sample(candidates, sample_size) if sample_size else []
        passed = 0
        lines = page_content.get(page, [])
        for row in sampled:
            if not lines:
                continue
            tokens = token_set_for_msgid(row.msgid)
            if not tokens:
                passed += 1
                continue
            context = line_context(lines, row.line, radius=2)
            if any(token in context for token in tokens):
                passed += 1
        spot_checks[page] = {"sampled": sample_size, "passed": passed}

    return {
        "represented_once_pass": represented_once_pass,
        "represented_once_actual": len(i18n_rows),
        "represented_once_expected": expected_unique_occurrence_count,
        "fuzzy_runtime_check_pass": fuzzy_runtime_check_pass,
        "fuzzy_count": len(fuzzy_rows),
        "fuzzy_runtime_fallback_count": len(fuzzy_runtime_fallback),
        "fuzzy_runtime_nonfallback": fuzzy_runtime_nonfallback,
        "po_empty_check_pass": po_empty_check_pass,
        "po_empty_count": len(po_empty_rows),
        "po_empty_runtime_fallback_count": len(po_empty_runtime_fallback),
        "hardcoded_country_pass": hardcoded_country_pass,
        "hardcoded_brand_pass": hardcoded_brand_pass,
        "hardcoded_brand_leak_count": len(hardcoded_brand_leak),
        "spot_checks": spot_checks,
    }


def write_csv(rows: Sequence[AuditRow], out_path: Path) -> None:
    fieldnames = [
        "page",
        "line",
        "msgid",
        "runtime_text",
        "po_msgstr",
        "po_status",
        "runtime_status",
        "review_flag",
        "source_type",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "page": row.page,
                    "line": row.line,
                    "msgid": collapse_ws(row.msgid),
                    "runtime_text": collapse_ws(row.runtime_text),
                    "po_msgstr": collapse_ws(row.po_msgstr),
                    "po_status": row.po_status,
                    "runtime_status": row.runtime_status,
                    "review_flag": row.review_flag,
                    "source_type": row.source_type,
                }
            )


def md_escape(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|")


def format_row_for_list(row: AuditRow, include_runtime: bool, include_po: bool) -> str:
    bits = [f"`{row.page}:{row.line}`", f"`{md_escape(collapse_ws(row.msgid))}`"]
    if include_runtime:
        bits.append(f"runtime: `{md_escape(collapse_ws(row.runtime_text))}`")
    if include_po:
        bits.append(f"po: `{md_escape(collapse_ws(row.po_msgstr))}`")
    if row.review_flag:
        bits.append(f"flag: `{row.review_flag}`")
    return " - ".join(bits)


def write_markdown(
    rows: Sequence[AuditRow],
    out_path: Path,
    counts: Dict[str, int],
    validations: Dict[str, object],
    high_priority_findings: Sequence[str],
) -> None:
    by_page = rows_by_page(rows)
    pages = sorted(by_page)

    lines: List[str] = []
    lines.append("# Malayalam Translation Audit (Runtime + PO)")
    lines.append("")
    lines.append("## Scope")
    lines.append("- Templates: all files matching `templates/*.html` in this run")
    lines.append("- Runtime source: `translations/ml/LC_MESSAGES/messages.mo`")
    lines.append("- PO source: `translations/ml/LC_MESSAGES/messages.po`")
    lines.append("")
    lines.append("## Snapshot")
    lines.append(f"- Total translatable occurrences: `{counts['total_translatable_occurrences']}`")
    lines.append(f"- Runtime Malayalam shown: `{counts['runtime_ml']}`")
    lines.append(f"- Runtime English fallback: `{counts['runtime_fallback']}`")
    lines.append(f"- PO empty (`msgstr \"\"`): `{counts['po_empty']}`")
    lines.append(f"- PO fuzzy: `{counts['po_fuzzy']}`")
    lines.append(f"- Hardcoded HTML English (outside `_()`): `{counts['hardcoded_english']}`")
    lines.append("")
    lines.append("## High-priority Findings")
    for finding in high_priority_findings:
        lines.append(f"- {finding}")
    lines.append("")
    lines.append("## Validation Results")
    lines.append(
        "- Coverage check (every template msgid occurrence represented once): "
        f"`{'PASS' if validations['represented_once_pass'] else 'FAIL'}` "
        f"(`{validations['represented_once_actual']}` / `{validations['represented_once_expected']}`)"
    )
    lines.append(
        "- Fuzzy runtime fallback check: "
        f"`{'PASS' if validations['fuzzy_runtime_check_pass'] else 'FAIL'}` "
        f"(`{validations['fuzzy_runtime_fallback_count']}` / `{validations['fuzzy_count']}`)"
    )
    lines.append(
        "- PO-empty flagged in both runtime+po check: "
        f"`{'PASS' if validations['po_empty_check_pass'] else 'FAIL'}` "
        f"(`{validations['po_empty_runtime_fallback_count']}` / `{validations['po_empty_count']}`)"
    )
    lines.append(
        "- Hardcoded country-label capture check: "
        f"`{'PASS' if validations['hardcoded_country_pass'] else 'FAIL'}`"
    )
    lines.append(
        "- Hardcoded brand whitelist exclusion check: "
        f"`{'PASS' if validations['hardcoded_brand_pass'] else 'FAIL'}` "
        f"(leaks: `{validations['hardcoded_brand_leak_count']}`)"
    )
    lines.append("- Spot-checks (10 random entries per major page):")
    for page, stat in sorted(validations["spot_checks"].items()):
        lines.append(f"  - `{page}`: `{stat['passed']}` / `{stat['sampled']}`")
    lines.append("")

    for page in pages:
        page_rows = by_page[page]
        i18n_rows = [row for row in page_rows if row.source_type == SOURCE_I18N]
        hardcoded_rows = [row for row in page_rows if row.source_type == SOURCE_HARDCODED]

        total = len(i18n_rows)
        runtime_ml = sum(1 for row in i18n_rows if row.runtime_status == "translated_ml")
        runtime_fb = sum(1 for row in i18n_rows if row.runtime_status == "english_fallback")
        po_fuzzy = sum(1 for row in i18n_rows if row.po_status == "fuzzy")
        po_empty = sum(1 for row in i18n_rows if row.po_status == "empty")

        needs_now = [row for row in i18n_rows if row.runtime_status == "english_fallback"]
        draft_fuzzy = [row for row in i18n_rows if row.po_status == "fuzzy"]
        active = [row for row in i18n_rows if row.runtime_status == "translated_ml"]

        lines.append(f"## {page}")
        lines.append(f"- Total strings: `{total}`")
        lines.append(f"- Runtime Malayalam: `{runtime_ml}`")
        lines.append(f"- Runtime English fallback: `{runtime_fb}`")
        lines.append(f"- PO fuzzy: `{po_fuzzy}`")
        lines.append(f"- PO empty: `{po_empty}`")
        lines.append("")

        lines.append("### Needs translation now")
        if needs_now:
            for row in needs_now:
                lines.append(f"- {format_row_for_list(row, include_runtime=True, include_po=True)}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("### Draft Malayalam (PO fuzzy)")
        if draft_fuzzy:
            for row in draft_fuzzy:
                lines.append(f"- {format_row_for_list(row, include_runtime=False, include_po=True)}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("### Already translated and active")
        if active:
            for row in active:
                lines.append(f"- {format_row_for_list(row, include_runtime=True, include_po=False)}")
        else:
            lines.append("- None")
        lines.append("")

        lines.append("### Hardcoded HTML text not under `_()`")
        if hardcoded_rows:
            for row in hardcoded_rows:
                lines.append(f"- {format_row_for_list(row, include_runtime=False, include_po=False)}")
        else:
            lines.append("- None")
        lines.append("")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_formats(value: str) -> Set[str]:
    formats = {piece.strip().lower() for piece in value.split(",") if piece.strip()}
    invalid = formats - {"md", "csv"}
    if invalid:
        raise ValueError(f"Unsupported format(s): {', '.join(sorted(invalid))}")
    return formats or {"md", "csv"}


def main() -> int:
    args = parse_args()
    formats = parse_formats(args.format)

    po_path = Path(args.po_path or f"translations/{args.locale}/LC_MESSAGES/messages.po")
    mo_path = Path(args.mo_path or f"translations/{args.locale}/LC_MESSAGES/messages.mo")

    if not po_path.exists():
        raise FileNotFoundError(f"PO file not found: {po_path}")

    scoped_files = expand_scope(args.scope)
    if not scoped_files:
        raise ValueError("No files matched --scope.")
    scoped_pages = {normalize_page_path(str(path)) for path in scoped_files}

    po_entries = parse_po(po_path)
    runtime_translation = load_runtime_translation(mo_path)

    i18n_rows, expected_unique_occurrence_count = build_i18n_rows(
        entries=po_entries,
        scoped_pages=scoped_pages,
        runtime_translation=runtime_translation,
        mode=args.mode,
    )
    hardcoded_rows = extract_hardcoded_rows(scoped_files)

    all_rows = sorted(
        [*i18n_rows, *hardcoded_rows],
        key=lambda row: (row.page, row.line, row.source_type, row.msgid),
    )

    counts = compute_global_counts(all_rows)
    validations = run_validations(
        rows=all_rows,
        expected_unique_occurrence_count=expected_unique_occurrence_count,
        scoped_files=scoped_files,
        seed=args.seed,
    )
    high_priority_findings = find_high_priority_findings(all_rows)

    if "csv" in formats:
        write_csv(all_rows, Path(args.out_csv))
    if "md" in formats:
        write_markdown(
            rows=all_rows,
            out_path=Path(args.out_md),
            counts=counts,
            validations=validations,
            high_priority_findings=high_priority_findings,
        )

    print("Audit completed.")
    print(f"Template scope files: {len(scoped_files)}")
    print(f"Total i18n occurrences: {counts['total_translatable_occurrences']}")
    print(f"Runtime Malayalam: {counts['runtime_ml']}")
    print(f"Runtime English fallback: {counts['runtime_fallback']}")
    print(f"PO empty: {counts['po_empty']}")
    print(f"PO fuzzy: {counts['po_fuzzy']}")
    print(f"Hardcoded English (outside _()): {counts['hardcoded_english']}")
    if "csv" in formats:
        print(f"CSV: {Path(args.out_csv).resolve()}")
    if "md" in formats:
        print(f"MD: {Path(args.out_md).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
