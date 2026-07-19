import imaplib
import email
from email.header import decode_header
import os
import shutil
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EmailAttachment:
    sender: str
    subject: str
    date: str
    email_uid: str
    attachment_filename: str
    local_path: Optional[str] = None


class IMAPMailboxFetcher:
    def __init__(self, host: str, username: str, password: str):
        self.host = host
        self.username = username
        self.password = password

    def fetch_unread_invoice_emails(self) -> List[EmailAttachment]:
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.username, self.password)
        mail.select('INBOX')

        status, messages = mail.search(None, 'UNSEEN')
        results: List[EmailAttachment] = []

        if status != 'OK':
            mail.logout()
            return results

        for num in messages[0].split():
            uid = num.decode()
            status, msg_data = mail.fetch(num, '(RFC822)')
            if status != 'OK':
                continue

            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)

            sender = str(msg.get('From', '')).strip()
            subject = str(msg.get('Subject', '')).strip()
            date = str(msg.get('Date', '')).strip()

            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                fn = part.get_filename()
                if fn and fn.lower().endswith('.pdf'):
                    results.append(EmailAttachment(
                        sender=sender,
                        subject=subject,
                        date=date,
                        email_uid=uid,
                        attachment_filename=str(fn),
                    ))

        mail.logout()
        return results

    def download_attachment(self, email_attachment: EmailAttachment, dest_dir: str) -> str:
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.username, self.password)
        mail.select('INBOX')

        status, msg_data = mail.fetch(email_attachment.email_uid.encode(), '(RFC822)')
        if status != 'OK':
            mail.logout()
            raise Exception(f"Failed to fetch email UID {email_attachment.email_uid}")

        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        pdf_data = None
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            fn = part.get_filename()
            if fn and fn.lower().endswith('.pdf') and fn == email_attachment.attachment_filename:
                pdf_data = part.get_payload(decode=True)
                break

        if not pdf_data:
            mail.logout()
            raise Exception(f"Could not find attachment {email_attachment.attachment_filename}")

        dest_path = os.path.join(dest_dir, email_attachment.attachment_filename)
        os.makedirs(dest_dir, exist_ok=True)
        with open(dest_path, 'wb') as f:
            f.write(pdf_data)

        mail.logout()
        email_attachment.local_path = dest_path
        return dest_path

    def mark_as_read(self, email_attachment: EmailAttachment):
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.username, self.password)
        mail.select('INBOX')
        mail.store(email_attachment.email_uid.encode(), '+FLAGS', '\\Seen')
        mail.logout()


class LocalFolderFetcher:
    def __init__(self, folder_path: str):
        self.folder_path = folder_path

    def fetch_unread_invoice_emails(self) -> List[EmailAttachment]:
        results: List[EmailAttachment] = []
        demo_map = {
            'AcmeSupply_INV-10234.pdf': (
                'billing@acmesupply.com',
                'Invoice from Acme Supply Co.',
                'Thu, 18 Jun 2026 10:00:00 -0600',
            ),
            'BoltFasteners_BF-2024-0098A.pdf': (
                'invoices@boltfasteners.com',
                'Invoice from Bolt & Fasteners Ltd.',
                'Sat, 20 Jun 2026 11:30:00 -0400',
            ),
            'PrecisionMachining_7741.pdf': (
                'accounts@precisionmachiningco.com',
                'Invoice from Precision Machining Co.',
                'Sun, 21 Jun 2026 09:15:00 -0400',
            ),
            'SummitElectrical_SE-88213.pdf': (
                'ar@summitelectrical.com',
                'Invoice from Summit Electrical Supply',
                'Tue, 23 Jun 2026 14:00:00 -0600',
            ),
            'GlobalTools_scanned_00417.pdf': (
                'ap@globaltools.com',
                'Invoice from Global Tools',
                'Thu, 25 Jun 2026 08:45:00 -0500',
            ),
        }
        for fname in os.listdir(self.folder_path):
            if fname.lower().endswith('.pdf'):
                info = demo_map.get(fname, ('unknown@unknown.com', f'Invoice: {fname}', 'Unknown date'))
                results.append(EmailAttachment(
                    sender=info[0],
                    subject=info[1],
                    date=info[2],
                    email_uid=fname,
                    attachment_filename=fname,
                ))
        return results

    def download_attachment(self, email_attachment: EmailAttachment, dest_dir: str) -> str:
        src = os.path.join(self.folder_path, email_attachment.attachment_filename)
        if not os.path.exists(src):
            raise FileNotFoundError(f"Demo file not found: {src}")
        dest = os.path.join(dest_dir, email_attachment.attachment_filename)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(src, dest)
        email_attachment.local_path = dest
        return dest

    def mark_as_read(self, email_attachment: EmailAttachment):
        pass
