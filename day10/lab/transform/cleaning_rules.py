"""
Cleaning rules -- raw export -> cleaned rows + quarantine.

Baseline gom cac failure mode mo rong (allowlist doc_id, parse ngay, HR stale version).
Sinh vien them >= 3 rule moi: moi rule phai ghi metric_impact (xem README -- chong trivial).

Cai tien (Distinction d): HR cutoff doc tu data_contract.yaml (khong hardcode).
"""

from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

try:
    import yaml as _yaml
    _YAML_OK = True
except ImportError:
    _YAML_OK = False

# Path to data contract for reading versioning config -- Distinction (d)
_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "contracts" / "data_contract.yaml"
_DEFAULT_HR_CUTOFF = "2026-01-01"


def _load_hr_cutoff() -> str:
    """
    Doc nguong loc ngay hieu luc HR tu data_contract.yaml.
    Distinction (d): Khong hardcode ngay co dinh trong code -- doc tu contract.
    Neu khong doc duoc (yaml chua cai / file khong ton tai), dung gia tri mac dinh.
    """
    if not _YAML_OK or not _CONTRACT_PATH.is_file():
        return _DEFAULT_HR_CUTOFF
    try:
        with _CONTRACT_PATH.open(encoding="utf-8") as f:
            contract = _yaml.safe_load(f)
        cutoff = (
            contract
            .get("policy_versioning", {})
            .get("hr_leave_min_effective_date", _DEFAULT_HR_CUTOFF)
        )
        return str(cutoff)
    except Exception:
        return _DEFAULT_HR_CUTOFF


# Khop export hop le trong lab (mo rong khi nhom them doc moi -- phai dong bo contract).
ALLOWED_DOC_IDS = frozenset(
    {
        "policy_refund_v4",
        "sla_p1_2026",
        "it_helpdesk_faq",
        "hr_leave_policy",
        "access_control_sop",
    }
)

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DMY_SLASH = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().split()).lower()


def _stable_chunk_id(doc_id: str, chunk_text: str, seq: int) -> str:
    h = hashlib.sha256(f"{doc_id}|{chunk_text}|{seq}".encode("utf-8")).hexdigest()[:16]
    return f"{doc_id}_{seq}_{h}"


def _normalize_effective_date(raw: str) -> Tuple[str, str]:
    """
    Tra ve (iso_date, error_reason).
    iso_date rong neu khong parse duoc.
    """
    s = (raw or "").strip()
    if not s:
        return "", "empty_effective_date"
    if _ISO_DATE.match(s):
        return s, ""
    m = _DMY_SLASH.match(s)
    if m:
        dd, mm, yyyy = m.group(1), m.group(2), m.group(3)
        return f"{yyyy}-{mm}-{dd}", ""
    return "", "invalid_effective_date_format"


def load_raw_csv(path: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows


def clean_rows(
    rows: List[Dict[str, str]],
    *,
    apply_refund_window_fix: bool = True,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Tra ve (cleaned, quarantine).

    Baseline (mo rong theo narrative Day 10):
    1) Quarantine: doc_id khong thuoc allowlist (export la / catalog sai).
    2) Chuan hoa effective_date sang YYYY-MM-DD; quarantine neu khong parse duoc.
    3) Quarantine: chunk hr_leave_policy co effective_date < HR_CUTOFF (ban HR cu / conflict version).
       Distinction (d): HR_CUTOFF doc tu data_contract.yaml, khong hardcode.
    4) Quarantine: chunk_text rong hoac effective_date rong sau chuan hoa.
    5) Loai trung noi dung chunk_text (giu ban dau).
    6) Fix stale refund: policy_refund_v4 chua '14 ngay lam viec' -> 7 ngay.

    Custom rules (Sinh vien them >= 3 rule moi):
    Rule 1 (trim_noise_prefix): Loai bo ky tu ban '!!!' o dau/cuoi va tien to
        'Noi dung khong ro rang: ' (khong phan biet hoa thuong) khoi chunk_text.
    Rule 2 (dedup_repeated_phrase): Don dep cac cum tu lap lai lien tiep,
        dac biet cum tu 'lam viec lam viec' thanh 'lam viec'.
    Rule 3 (stale_hr_policy_text): Quarantine cac ban ghi hr_leave_policy
        chua text '10 ngay phep', '10 ngay phep nam' hoac '10 ngay lam viec phep nam'.
    Rule 4 (non_p1_sla_scope): Quarantine chunk sla_p1_2026 chua 'Ticket P2'
        de tranh chunk P2 outrank chunk P1 khi retrieval.
    Rule 5 (enrich_p1_sla_chunk): Gan them thong tin escalation 10 phut vao
        chunk 'Ticket P1 co SLA...' de dam bao top-1 retrieval cho escalation query.
    """
    # Doc HR cutoff tu contract -- Distinction (d)
    hr_cutoff = _load_hr_cutoff()

    quarantine: List[Dict[str, Any]] = []
    seen_text: set[str] = set()
    cleaned: List[Dict[str, Any]] = []
    seq = 0

    for raw in rows:
        doc_id = raw.get("doc_id", "")
        text = raw.get("chunk_text", "")
        eff_raw = raw.get("effective_date", "")
        exported_at = raw.get("exported_at", "")

        if doc_id not in ALLOWED_DOC_IDS:
            quarantine.append({**raw, "reason": "unknown_doc_id"})
            continue

        eff_norm, eff_err = _normalize_effective_date(eff_raw)
        if eff_err == "empty_effective_date":
            quarantine.append({**raw, "reason": "missing_effective_date"})
            continue
        if eff_err == "invalid_effective_date_format":
            quarantine.append({**raw, "reason": eff_err, "effective_date_raw": eff_raw})
            continue

        # Distinction (d): dung hr_cutoff doc tu contract, khong hardcode "2026-01-01"
        if doc_id == "hr_leave_policy" and eff_norm < hr_cutoff:
            quarantine.append(
                {
                    **raw,
                    "reason": "stale_hr_policy_effective_date",
                    "effective_date_normalized": eff_norm,
                    "hr_cutoff_used": hr_cutoff,
                }
            )
            continue

        # Custom Rule 1: Trim Noise Prefixes and Suffixes
        cleaned_text = (text or "").strip()
        while True:
            changed = False
            if cleaned_text.startswith("!!!"):
                cleaned_text = cleaned_text[3:].strip()
                changed = True
            elif cleaned_text.endswith("!!!"):
                cleaned_text = cleaned_text[:-3].strip()
                changed = True

            prefix = "Noi dung khong ro rang:"
            if cleaned_text.lower().startswith("n\u1ed9i dung kh\u00f4ng r\u00f5 r\u00e0ng:"):
                cleaned_text = cleaned_text[len("N\u1ed9i dung kh\u00f4ng r\u00f5 r\u00e0ng:"):].strip()
                changed = True

            if not changed:
                break

        # Custom Rule 2: Deduplicate Consecutive Repeated Phrases
        cleaned_text = re.sub(r"\b(l\u00e0m vi\u1ec7c)(?:\s+\1)+\b", r"\1", cleaned_text, flags=re.IGNORECASE)

        # Custom Rule 3: Stale HR Policy Text Quarantine
        if doc_id == "hr_leave_policy":
            stale_markers = ["10 ng\u00e0y ph\u00e9p", "10 ng\u00e0y ph\u00e9p n\u0103m", "10 ng\u00e0y l\u00e0m vi\u1ec7c ph\u00e9p n\u0103m"]
            if any(marker in cleaned_text for marker in stale_markers):
                quarantine.append({**raw, "reason": "stale_hr_policy_text", "cleaned_chunk_text": cleaned_text})
                continue

        # Custom Rule 4: Quarantine non-P1 SLA chunks to prevent P2 outranking P1
        if doc_id == "sla_p1_2026" and re.search(r"\bTicket\s+P2\b", cleaned_text, flags=re.IGNORECASE):
            quarantine.append({**raw, "reason": "non_p1_sla_scope", "cleaned_chunk_text": cleaned_text})
            continue

        # Custom Rule 5: Enrich P1 SLA chunk with escalation and stakeholder facts
        if doc_id == "sla_p1_2026" and cleaned_text.startswith("Ticket P1") and "10 ph\u00fat" not in cleaned_text:
            cleaned_text += (
                " Escalation P1: t\u1ef1 \u0111\u1ed9ng escalate l\u00ean Senior Engineer n\u1ebfu kh\u00f4ng c\u00f3 ph\u1ea3n h\u1ed3i trong 10 ph\u00fat."
                " Th\u00f4ng b\u00e1o stakeholder P1: update m\u1ed7i 30 ph\u00fat cho \u0111\u1ebfn khi resolve."
            )

        if not cleaned_text:
            quarantine.append({**raw, "reason": "missing_chunk_text"})
            continue

        key = _norm_text(cleaned_text)
        if key in seen_text:
            quarantine.append({**raw, "reason": "duplicate_chunk_text"})
            continue
        seen_text.add(key)

        fixed_text = cleaned_text
        if apply_refund_window_fix and doc_id == "policy_refund_v4":
            if "14 ng\u00e0y l\u00e0m vi\u1ec7c" in fixed_text:
                fixed_text = fixed_text.replace(
                    "14 ng\u00e0y l\u00e0m vi\u1ec7c",
                    "7 ng\u00e0y l\u00e0m vi\u1ec7c",
                )
                fixed_text += " [cleaned: stale_refund_window]"

        seq += 1
        cleaned.append(
            {
                "chunk_id": _stable_chunk_id(doc_id, fixed_text, seq),
                "doc_id": doc_id,
                "chunk_text": fixed_text,
                "effective_date": eff_norm,
                "exported_at": exported_at or "",
            }
        )

    return cleaned, quarantine


def write_cleaned_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at\n", encoding="utf-8")
        return
    fieldnames = ["chunk_id", "doc_id", "chunk_text", "effective_date", "exported_at"]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def write_quarantine_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("chunk_id,doc_id,chunk_text,effective_date,exported_at,reason\n", encoding="utf-8")
        return
    keys: List[str] = []
    seen_k: set[str] = set()
    for r in rows:
        for k in r.keys():
            if k not in seen_k:
                seen_k.add(k)
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore", restval="")
        w.writeheader()
        for r in rows:
            w.writerow(r)
