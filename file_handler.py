import csv
import os
import shutil
from datetime import datetime


INTAKE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'invoice_intake')
INCOMING_DIR = os.path.join(INTAKE_DIR, 'incoming')
PROCESSED_DIR = os.path.join(INTAKE_DIR, 'processed')
MANUAL_REVIEW_DIR = os.path.join(INTAKE_DIR, 'needs_manual_review')
SCANNED_DIR = os.path.join(MANUAL_REVIEW_DIR, 'scanned')
UNRESOLVED_DIR = os.path.join(MANUAL_REVIEW_DIR, 'unresolved')
LOGS_DIR = os.path.join(INTAKE_DIR, 'logs')
ACTIVITY_LOG_PATH = os.path.join(LOGS_DIR, 'activity_log.csv')


def create_folder_structure():
    for d in [INCOMING_DIR, PROCESSED_DIR, SCANNED_DIR, UNRESOLVED_DIR, LOGS_DIR]:
        os.makedirs(d, exist_ok=True)
    if not os.path.exists(ACTIVITY_LOG_PATH):
        with open(ACTIVITY_LOG_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'action', 'original_filename', 'final_filename', 'vendor', 'invoice_number', 'status'])


def get_unique_filename(dest_dir: str, filename: str) -> str:
    name, ext = os.path.splitext(filename)
    counter = 1
    candidate = filename
    while os.path.exists(os.path.join(dest_dir, candidate)):
        candidate = f"{name}_dup{counter}{ext}"
        counter += 1
    return candidate


def file_invoice(src_path: str, dest_dir: str, new_filename: str):
    safe_name = get_unique_filename(dest_dir, new_filename)
    dest_path = os.path.join(dest_dir, safe_name)
    if os.path.exists(src_path):
        shutil.copy2(src_path, dest_path)
    return safe_name, dest_path


def log_activity(timestamp, action, original_filename, final_filename, vendor, invoice_number, status):
    if not timestamp:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    with open(ACTIVITY_LOG_PATH, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, action, original_filename, final_filename, vendor, invoice_number, status])


def get_manual_review_files():
    scanned_files = []
    unresolved_files = []
    for d, lst in [(SCANNED_DIR, scanned_files), (UNRESOLVED_DIR, unresolved_files)]:
        if os.path.exists(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith('.pdf'):
                    lst.append(os.path.join(d, f))
    return scanned_files, unresolved_files


def get_processed_files():
    files = []
    if os.path.exists(PROCESSED_DIR):
        for f in sorted(os.listdir(PROCESSED_DIR)):
            if f.lower().endswith('.pdf'):
                files.append(os.path.join(PROCESSED_DIR, f))
    return files
