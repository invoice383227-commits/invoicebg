import csv
import os


CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'invoice_intake', 'config')
VENDOR_MAPPING_PATH = os.path.join(CONFIG_DIR, 'vendor_mapping.csv')

INITIAL_MAPPINGS = {
    'acmesupply.com': 'Acme Supply Co.',
    'boltfasteners.com': 'Bolt & Fasteners Ltd.',
    'precisionmachiningco.com': 'Precision Machining Co.',
    'summitelectrical.com': 'Summit Electrical Supply',
    'globaltools.com': 'Global Tools',
}


def _ensure_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(VENDOR_MAPPING_PATH):
        with open(VENDOR_MAPPING_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['domain', 'vendor_name'])
            for domain, name in INITIAL_MAPPINGS.items():
                writer.writerow([domain, name])


def load_vendor_mapping():
    _ensure_config()
    mapping = {}
    with open(VENDOR_MAPPING_PATH, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            mapping[row['domain'].strip()] = row['vendor_name'].strip()
    return mapping


def save_vendor_mapping(mapping: dict):
    _ensure_config()
    with open(VENDOR_MAPPING_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['domain', 'vendor_name'])
        for domain, name in mapping.items():
            writer.writerow([domain.strip().lower(), name.strip()])


def add_vendor_mapping(domain: str, vendor_name: str):
    mapping = load_vendor_mapping()
    mapping[domain.strip().lower()] = vendor_name.strip()
    save_vendor_mapping(mapping)
