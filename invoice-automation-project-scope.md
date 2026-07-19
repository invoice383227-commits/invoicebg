# Automated Invoice Intake System — Implementation Spec (Phase 1, Streamlit-Driven)

## 1. Background

Invoices arrive through a designated mailbox at ~15–20/day. The current manual process:

1. Download PDF invoice from email, rename it.
2. Review PO number, invoice number, unit info, etc.; match invoice to PO; attach it.
3. Enter data into the internal invoice processing system (name/spelling TBD — referred to here as "the internal system").
4. File and organize the invoice.
5. Invoices without a PO number are routed to another person for PO assignment.
6. Some invoices are scanned/paper documents rather than born-digital PDFs.

## 2. Phase 1 Scope

Automate the administrative front-end of the workflow, driven manually through a Streamlit app rather than a background scheduled job:

| # | Task | In scope? |
|---|------|-----------|
| 1 | User opens the Streamlit app and clicks "Check for new invoices" | ✅ |
| 2 | App connects to mailbox and lists new invoice emails/attachments | ✅ |
| 3 | App downloads PDF attachments | ✅ |
| 4 | App determines if each PDF is digitally generated or scanned | ✅ |
| 5 | App extracts Vendor Name + Invoice Number for naming (text-layer parsing only, no OCR) | ✅ |
| 6 | App shows proposed filename for user review/edit before filing | ✅ |
| 7 | App renames and files the PDF into the target folder on user confirmation | ✅ |
| 8 | App marks the source email as read once handled | ✅ |
| 9 | App flags scanned/paper invoices in a separate "needs manual review" list | ✅ |
| 10 | PO matching, data entry into internal system, PO-less routing | ❌ Future phase |

**Key change from earlier draft:** this is intentionally **not** a background/unattended process for now. Nothing touches the mailbox or the file system until someone opens the app and clicks a button. This keeps a human in the loop for every batch while the system is being trialed, and it's a much easier thing to demo than a scheduled task that runs invisibly.

## 3. Application Flow (Streamlit)

A single-page (or simple multi-tab) Streamlit app:

**Tab 1 — Process Invoices**
1. Button: **"Check Inbox for New Invoices"** → connects to mailbox, pulls unread emails with PDF attachments, downloads them to a temp `/incoming/` folder, and lists them on screen.
2. For each attachment, the app shows:
   - Sender / subject / received date
   - Classification result: **Digital** or **Scanned (flagged)**
   - If digital: proposed filename (`VendorName_InvoiceNumber.pdf`), editable in a text box in case the auto-extraction guessed wrong
   - A PDF preview (Streamlit can render the PDF or at least page 1 as an image) so the user can visually confirm before filing
3. Button per item: **"Confirm & File"** → moves/renames the PDF into the target folder and marks that email as read.
4. Button per item: **"Send to Manual Review"** → moves the PDF into `/needs_manual_review/` instead (used for scanned docs automatically, or for anything the user doesn't want to auto-file).

**Tab 2 — Needs Manual Review**
- Lists everything sitting in `/needs_manual_review/scanned/` and `/needs_manual_review/unresolved/`.
- Lets the user manually type in a vendor name/invoice number and file it from here too, if they want the tool to still help even with the scanned ones.

**Tab 3 — Activity Log**
- Simple table view of everything processed this session/day, pulled from the log file.

**Tab 4 — Vendor Mapping (optional, nice-to-have)**
- Simple add/edit form for the sender-address → vendor-name lookup table, so the list of known vendors can grow without editing code.

Nothing runs unless the user is actively clicking through the app — this is the "monitor and process" model you described, not a background worker.

## 4. Mailbox Access

- **Test environment (now):** Gmail with an app password → use `imaplib` (IMAP). This is what the demo/prototype should run against.
- **Production environment (later):** Outlook/Exchange shared mailbox. Recommended path is the Microsoft Graph API with an app registration, but plain IMAP against Exchange is a fallback if Graph approval is a blocker — worth checking with IT.
- Keep mailbox access behind a small interface (`fetch_unread_invoice_emails()`, `download_attachment()`, `mark_as_read()`) so swapping Gmail/IMAP for Graph API later doesn't require touching the Streamlit UI code.

## 5. Classification & Naming Logic

### 5.1 Digital vs. scanned
Use `pdfplumber` (or `pypdf`) to extract text from page 1:
- Meaningful extracted text (e.g., >20 characters) → **digital**.
- Little/no extractable text → **scanned/image-based** → auto-flag for manual review.

### 5.2 Vendor name resolution
- Primary: look up the sending email address/domain in a small vendor-mapping table (CSV/JSON/SQLite).
- Fallback: best-effort parse of vendor name from PDF text.
- If neither is confident, leave the filename field blank/editable for the user rather than guessing.

### 5.3 Invoice number extraction
- Regex search over extracted PDF text (e.g., `Invoice\s*#?\s*[:\-]?\s*([A-Z0-9\-]+)`).
- Keep the exact string as found — letters, hyphens, leading zeros all preserved, per the stated naming requirement.
- Low-confidence or multiple matches → leave editable for user confirmation rather than auto-filing.

### 5.4 Filename collisions
- If the target filename already exists in the destination folder, append a short suffix (`_dup1`, etc.) and surface a warning in the UI rather than silently overwriting.

## 6. Folder Structure

```
/invoice_intake/
    /incoming/              <- temporary holding while a batch is being reviewed
    /processed/             <- final filed invoices (target folder)
    /needs_manual_review/
        /scanned/           <- scanned or non-digital PDFs
        /unresolved/        <- digital PDFs where vendor/invoice # couldn't be determined confidently
    /logs/
        activity_log.csv
    /config/
        vendor_mapping.csv
```

## 7. Marking Emails as Read

- Only mark an email as read once its attachment has actually been filed or explicitly sent to manual review by the user in the app — never automatically in the background at this stage.

## 8. Suggested Tech Stack

- **Language:** Python 3.11+
- **UI:** Streamlit
- **Mailbox (test):** `imaplib` against Gmail (app password already available)
- **Mailbox (production, later):** Microsoft Graph API, or IMAP against Exchange as fallback
- **PDF text extraction:** `pdfplumber`
- **PDF preview in-app:** render page 1 to an image (`pdf2image` + poppler, or `pypdfium2`) and display with `st.image`
- **Config/vendor table:** CSV to start

## 9. Demo Invoice Set

To demonstrate the workflow, five sample invoices were generated (see accompanying `demo_invoices/` folder):

| File | Purpose |
|---|---|
| `AcmeSupply_INV-10234.pdf` | Standard digital invoice, has a PO number — should auto-classify as digital and auto-fill vendor/invoice # cleanly |
| `BoltFasteners_BF-2024-0098A.pdf` | Digital invoice with a hyphenated, lettered invoice number — demonstrates that the naming logic preserves exact formatting |
| `PrecisionMachining_7741.pdf` | Digital invoice with **no PO number** — demonstrates the "needs manual routing" case |
| `SummitElectrical_SE-88213.pdf` | Another standard digital invoice, for volume/variety in the demo |
| `GlobalTools_scanned_00417.pdf` | Image-only PDF with no text layer, styled like a faxed/photocopied paper invoice — demonstrates the scanned-document detection and auto-flagging to manual review |

These are synthetic — vendor names, addresses, and dollar amounts are all made up — but structured like real invoices so the classification and extraction logic has something realistic to work against. To run a demo: load these five into the test Gmail inbox as attachments (or point the app at a local folder containing them, if you'd rather not wire up email for the first walkthrough), then run through the Streamlit flow live for your boss — four should sail through as "digital," one should get auto-flagged as scanned, and the PO-less one is a good moment to point out where step 5 of the original process still needs a human.

## 10. Open Items to Confirm

- Exact name/access method for the internal invoice processing system (not needed for Phase 1).
- Exact target folder path/network location for `/processed/`.
- Initial seed list of known vendors/sender addresses for the vendor mapping table.
- Whether a background/scheduled version is wanted later, once the manual Streamlit-driven version has been validated.

## 11. Explicitly Out of Scope (Phase 1)

- Background/unattended automation (deferred — see Section 2).
- OCR / scanned invoice reading.
- PO number extraction and PO matching.
- Data entry into the internal invoice processing system.
- Routing of PO-less invoices to a specific person.
