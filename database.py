import os
import json
import sqlite3
import io

import pandas as pd

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'invoice_intake', 'invoices.db')
DB_COLUMNS = [
    'timestamp', 'sender', 'vendor', 'invoice_number', 'po_number',
    'invoice_date', 'terms', 'subtotal', 'tax', 'total', 'currency',
    'extra_fields', 'filename', 'original_filename',
]

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    sender TEXT,
    vendor TEXT,
    invoice_number TEXT,
    po_number TEXT,
    invoice_date TEXT,
    terms TEXT,
    subtotal TEXT,
    tax TEXT,
    total TEXT,
    currency TEXT,
    extra_fields TEXT,
    filename TEXT,
    original_filename TEXT,
    UNIQUE (vendor, invoice_number)
)
"""


def _connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute(_CREATE_TABLE_SQL)
    return conn


def init_db(path=DB_PATH):
    _connect(path).close()


def empty_db():
    return pd.DataFrame(columns=DB_COLUMNS)


def load_db(path=DB_PATH):
    if not os.path.exists(path):
        return empty_db()
    try:
        conn = sqlite3.connect(path)
        df = pd.read_sql_query('SELECT * FROM invoices', conn)
        conn.close()
    except Exception:
        return empty_db()
    if df is None or df.empty:
        return empty_db()
    for col in DB_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    return df[DB_COLUMNS]


def save_db(df, path=DB_PATH):
    conn = _connect(path)
    try:
        conn.execute('DELETE FROM invoices')
        if df is not None and not df.empty:
            records = df.to_dict('records')
            for r in records:
                if isinstance(r.get('extra_fields'), dict):
                    r['extra_fields'] = json.dumps(r['extra_fields'], default=str)
            placeholders = ','.join(['?'] * len(DB_COLUMNS))
            cols = ','.join(DB_COLUMNS)
            conn.executemany(
                f'INSERT OR REPLACE INTO invoices ({cols}) VALUES ({placeholders})',
                [[r.get(c, '') for c in DB_COLUMNS] for r in records],
            )
        conn.commit()
    finally:
        conn.close()


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
    rec = dict(record)
    if isinstance(rec.get('extra_fields'), dict):
        rec['extra_fields'] = json.dumps(rec['extra_fields'], default=str)
    new_row = pd.DataFrame([rec], columns=DB_COLUMNS)
    return pd.concat([df, new_row], ignore_index=True)


def delete_invoice(df, pos, path=DB_PATH):
    if df is None or len(df) == 0:
        return empty_db()
    df = df.drop(df.index[pos]).reset_index(drop=True)
    save_db(df, path)
    return df


def csv_bytes(df):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    return buf.getvalue()


def import_spreadsheet(uploaded_bytes, path=DB_PATH):
    df = pd.read_csv(io.BytesIO(uploaded_bytes))
    for col in DB_COLUMNS:
        if col not in df.columns:
            df[col] = ''
    df = df[DB_COLUMNS]
    save_db(df, path)
    return df
