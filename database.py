import os

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'invoice_intake', 'invoices.xlsx')
DB_COLUMNS = [
    'timestamp', 'sender', 'vendor', 'invoice_number', 'po_number',
    'invoice_date', 'terms', 'subtotal', 'tax', 'total', 'currency',
    'filename', 'original_filename',
]


def empty_db():
    return pd.DataFrame(columns=DB_COLUMNS)


def load_db(path=DB_PATH):
    if not os.path.exists(path):
        return empty_db()
    try:
        df = pd.read_excel(path)
    except Exception:
        return empty_db()
    for col in DB_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    return df[DB_COLUMNS]


def save_db(df, path=DB_PATH):
    df.to_excel(path, index=False)


def is_duplicate(invoice_number, vendor, df):
    if not invoice_number or df is None or df.empty:
        return False
    inv_num = str(invoice_number).strip().lower()
    num_match = df['invoice_number'].astype(str).str.strip().str.lower() == inv_num
    if not num_match.any():
        return False
    if vendor:
        vend_match = df['vendor'].astype(str).str.lower().str.contains(str(vendor).lower(), na=False)
        return (num_match & vend_match).any()
    return num_match.any()


def add_invoice(record, df):
    if df is None:
        df = empty_db()
    new_row = pd.DataFrame([record], columns=DB_COLUMNS)
    return pd.concat([df, new_row], ignore_index=True)


def db_bytes(df):
    import io
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()
