import re

from config_manager import load_vendor_mapping


INVOICE_NUM_PATTERNS = [
    re.compile(r'Invoice\s*(?:Number|No|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]*\d[A-Z0-9\-]*)', re.IGNORECASE),
    re.compile(r'Invoice\s*#?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]*\d[A-Z0-9\-]*)', re.IGNORECASE),
]

PO_NUMBER_PATTERNS = [
    re.compile(r'(?:P\.?O\.?|Purchase\s*Order|Customer\s*Order|Order)\s*(?:Number|No|#)?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]*\d[A-Z0-9\-]*)', re.IGNORECASE),
    re.compile(r'PO\s*#?\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-]*\d[A-Z0-9\-]*)', re.IGNORECASE),
]


def extract_invoice_number(text: str):
    for pattern in INVOICE_NUM_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def extract_po_number(text: str):
    for pattern in PO_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def extract_vendor_from_text(text: str):
    lines = text.strip().split('\n')
    if lines:
        first = lines[0].strip()
        if first and len(first) < 80:
            return first
    return None


def resolve_vendor_name(sender_email: str, text: str):
    mapping = load_vendor_mapping()
    domain = sender_email.split('@')[-1].lower() if '@' in sender_email else ''
    if domain in mapping:
        return mapping[domain]
    fallback = extract_vendor_from_text(text)
    return fallback
