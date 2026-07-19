import pdfplumber


DIGITAL_THRESHOLD = 20


def classify_pdf(pdf_path: str):
    with pdfplumber.open(pdf_path) as pdf:
        text = ''
        if pdf.pages:
            text = pdf.pages[0].extract_text() or ''
    text = text.strip()
    if len(text) > DIGITAL_THRESHOLD:
        return 'digital', text
    return 'scanned', text
