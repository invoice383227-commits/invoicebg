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

DATE_PATTERN = re.compile(r'(?:Invoice\s*Date|Date)\s*[:\-]?\s*([A-Z][a-z]+ \d{1,2}, \d{4}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4})', re.IGNORECASE)

TERMS_PATTERN = re.compile(r'Terms?\s*[:\-]?\s*([A-Za-z0-9]+(?:[ ][A-Za-z0-9]+)*)', re.IGNORECASE)

SUBTOTAL_PATTERN = re.compile(r'Subtotal\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})', re.IGNORECASE)

TAX_PATTERN = re.compile(r'Tax(?:\s*\([^)]*\))?\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})', re.IGNORECASE)

TOTAL_PATTERN = re.compile(r'(?<!Sub)(?:Total\s*Due|Total)\s*[:\-]?\s*\$?\s*([\d,]+\.\d{2})', re.IGNORECASE)

CURRENCY_PATTERN = re.compile(r'\$\s*[\d,]+\.\d{2}')


def _extract_first(pattern, text):
    match = pattern.search(text)
    if match:
        return match.group(1).strip()
    return None


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


def extract_invoice_date(text: str):
    return _extract_first(DATE_PATTERN, text)


def extract_terms(text: str):
    return _extract_first(TERMS_PATTERN, text)


def extract_subtotal(text: str):
    return _extract_first(SUBTOTAL_PATTERN, text)


def extract_tax(text: str):
    return _extract_first(TAX_PATTERN, text)


def extract_total(text: str):
    return _extract_first(TOTAL_PATTERN, text)


def extract_currency(text: str):
    match = CURRENCY_PATTERN.search(text)
    if match:
        return '$'
    return None


# Generic "Label: value" fields common across vendors. The app automatically
# extracts any of these that appear in an invoice, so no schema change is needed
# for fields like unit number, maintenance number, division number, etc.
EXTRA_FIELD_LABELS = [
    'unit number', 'unit no', 'unit #', 'unit',
    'maintenance number', 'maintenance no', 'maintenance #', 'maint number', 'maint no', 'maint #',
    'division number', 'division no', 'division #', 'division',
    'work order', 'work order number', 'work order no', 'work order #',
    'service order', 'service order number', 'service order no', 'service order #',
    'job number', 'job no', 'job #',
    'reference', 'reference number', 'reference no', 'reference #', 'ref no', 'ref #',
    'contract number', 'contract no', 'contract #',
    'account number', 'account no', 'account #', 'acct #',
    'project number', 'project no', 'project #',
    'customer number', 'customer no', 'customer #',
    'customer po', 'customer order',
    'due date', 'payment due',
    'ship date', 'order date', 'issue date',
    'tax id', 'gst number', 'gst #', 'hst number', 'hst #', 'vat number', 'vat #', 'ein',
    'remit to', 'bill to', 'ship to', 'location', 'site', 'store',
]

_EXTRA_FIELD_RE = re.compile(
    r'\b(' + '|'.join(re.escape(l) for l in EXTRA_FIELD_LABELS) + r')\s*[:\-]\s*(.+?)(?:\n|$)',
    re.IGNORECASE,
)


def extract_extra_fields(text: str):
    """Extract all 'Label: value' fields from arbitrary invoice text."""
    fields = {}
    for match in _EXTRA_FIELD_RE.finditer(text):
        label = match.group(1).strip()
        value = match.group(2).strip()
        key = re.sub(r'[^A-Za-z0-9]+', '_', label).strip('_').lower()
        if value and value not in fields.values():
            fields[key] = value
    return fields


def extract_all(text: str):
    return {
        'vendor_name': extract_vendor_from_text(text),
        'invoice_number': extract_invoice_number(text),
        'po_number': extract_po_number(text),
        'invoice_date': extract_invoice_date(text),
        'terms': extract_terms(text),
        'subtotal': extract_subtotal(text),
        'tax': extract_tax(text),
        'total': extract_total(text),
        'currency': extract_currency(text),
    }


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
