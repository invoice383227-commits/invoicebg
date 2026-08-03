import imaplib
import email
import os
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

    def fetch_recent_invoice_emails(self, count: int = 3) -> List[EmailAttachment]:
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.username, self.password)
        mail.select('INBOX')

        status, messages = mail.search(None, 'ALL')
        results: List[EmailAttachment] = []

        if status != 'OK':
            mail.logout()
            return results

        for num in messages[0].split()[-count:]:
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

    def mark_as_unread(self, email_attachment: EmailAttachment):
        mail = imaplib.IMAP4_SSL(self.host)
        mail.login(self.username, self.password)
        mail.select('INBOX')
        mail.store(email_attachment.email_uid.encode(), '-FLAGS', '\\Seen')
        mail.logout()

