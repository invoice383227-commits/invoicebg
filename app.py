import os
import shutil
import sys
from datetime import datetime
from dataclasses import dataclass, field

import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mailbox import IMAPMailboxFetcher, EmailAttachment
from classifier import classify_pdf
from extractor import (
    resolve_vendor_name, extract_invoice_number, extract_po_number,
    extract_invoice_date, extract_terms, extract_subtotal,
    extract_tax, extract_total, extract_currency, extract_extra_fields,
)
from file_handler import (
    create_folder_structure, file_invoice, log_activity, repair_activity_log_schema,
    INCOMING_DIR, PROCESSED_DIR, SCANNED_DIR, UNRESOLVED_DIR,
    ACTIVITY_LOG_PATH, get_manual_review_files, get_processed_files,
)
from config_manager import load_vendor_mapping, add_vendor_mapping
from database import (
    DB_PATH, DB_COLUMNS, load_db, save_db, is_duplicate, add_invoice,
    csv_bytes, empty_db, init_db, import_spreadsheet,
)


@dataclass
class InvoiceItem:
    email_uid: str
    sender: str
    subject: str
    date: str
    original_filename: str
    local_path: str
    is_digital: bool
    extracted_text: str
    vendor_name: str
    invoice_number: str
    po_number: str
    invoice_date: str
    terms: str
    subtotal: str
    tax: str
    total: str
    currency: str
    proposed_filename: str
    extra_fields: dict = field(default_factory=dict)
    filed: bool = False
    sent_to_review: bool = False
    editable_vendor: str = ''
    editable_inv: str = ''
    editable_po: str = ''
    dest_path: str = ''


def render_pdf_preview(pdf_path):
    try:
        from pypdfium2 import PdfDocument
        doc = PdfDocument(pdf_path)
        page = doc[0]
        bitmap = page.render(scale=1.0)
        img = bitmap.to_pil()
        doc.close()
        return img
    except Exception as e:
        st.error(f"Preview unavailable: {e}")
        return None


def fetch_and_process(fetcher):
    with st.spinner("Checking for new invoices..."):
        try:
            if st.session_state.get("test_mode", True):
                emails = fetcher.fetch_recent_invoice_emails(3)
            else:
                emails = fetcher.fetch_unread_invoice_emails()
            if not emails:
                st.info("No new invoice emails found.")
                st.session_state.fetched = True
                return

            st.session_state.invoice_items = []
            progress_bar = st.progress(0, text="Processing invoices...")
            for i, email_att in enumerate(emails):
                try:
                    local_path = fetcher.download_attachment(email_att, INCOMING_DIR)
                    is_digital, extracted_text = classify_pdf(local_path)

                    if is_digital == 'digital':
                        vendor = resolve_vendor_name(email_att.sender, extracted_text)
                        inv_num = extract_invoice_number(extracted_text)
                        po_num = extract_po_number(extracted_text)
                        inv_date = extract_invoice_date(extracted_text)
                        terms = extract_terms(extracted_text)
                        subtotal = extract_subtotal(extracted_text)
                        tax = extract_tax(extracted_text)
                        total = extract_total(extracted_text)
                        currency = extract_currency(extracted_text)
                        extra = extract_extra_fields(extracted_text)
                    else:
                        vendor = ''
                        inv_num = ''
                        po_num = ''
                        inv_date = ''
                        terms = ''
                        subtotal = ''
                        tax = ''
                        total = ''
                        currency = ''
                        extra = {}

                    item = InvoiceItem(
                        email_uid=email_att.email_uid,
                        sender=email_att.sender,
                        subject=email_att.subject,
                        date=email_att.date,
                        original_filename=email_att.attachment_filename,
                        local_path=local_path,
                        is_digital=(is_digital == 'digital'),
                        extracted_text=extracted_text,
                        vendor_name=vendor or '',
                        invoice_number=inv_num or '',
                        po_number=po_num or '',
                        invoice_date=inv_date or '',
                        terms=terms or '',
                        subtotal=subtotal or '',
                        tax=tax or '',
                        total=total or '',
                        currency=currency or '',
                        extra_fields=extra,
                        proposed_filename='',
                        editable_vendor=vendor or '',
                        editable_inv=inv_num or '',
                        editable_po=po_num or '',
                    )
                    if vendor and inv_num and po_num:
                        item.proposed_filename = f"{vendor}_{inv_num}_{po_num}.pdf"
                    st.session_state.invoice_items.append(item)
                except Exception as e:
                    st.error(f"Error processing {email_att.attachment_filename}: {e}")
                    st.session_state.fetched = True
                progress_bar.progress((i + 1) / len(emails))
            st.session_state.fetched = True
            st.session_state.edit_idx = None
            st.rerun()
        except Exception as e:
            st.error(f"Failed to check inbox: {e}")


def _send_duplicate_to_review(item_idx, item, fetcher, safe_name, dest_path):
    item = st.session_state.invoice_items[item_idx]
    if fetcher:
        try:
            fetcher.mark_as_unread(EmailAttachment(
                sender=item.sender,
                subject=item.subject,
                date=item.date,
                email_uid=item.email_uid,
                attachment_filename=item.original_filename,
            ))
        except Exception:
            pass
    item.sent_to_review = True
    st.warning(f"Duplicate invoice — sent to manual review ({safe_name}), email left unread.")


def confirm_file_item(item_idx, item, fetcher):
    item = st.session_state.invoice_items[item_idx]
    vendor = item.editable_vendor or item.vendor_name
    inv_num = item.editable_inv or item.invoice_number
    po_num = item.editable_po or item.po_number

    db = st.session_state.get("invoices_db", empty_db())

    if not st.session_state.get("test_mode", True) and is_duplicate(inv_num, vendor, db):
        dest = UNRESOLVED_DIR
        safe_name, dest_path = file_invoice(item.local_path, dest, item.original_filename)
        log_activity(
            timestamp=item.date,
            action='duplicate_sent_to_manual_review',
            original_filename=item.original_filename,
            final_filename=safe_name,
            vendor=vendor,
            invoice_number=inv_num,
            po_number=po_num,
            status='duplicate',
        )
        _send_duplicate_to_review(item_idx, item, fetcher, safe_name, dest_path)
        st.rerun()
        return

    new_filename = item.proposed_filename or item.original_filename
    safe_name, dest_path = file_invoice(item.local_path, PROCESSED_DIR, new_filename)

    orig_dir = st.session_state.get("orig_dir", "")
    proc_dir = st.session_state.get("proc_dir", "")
    saved_to = []
    if orig_dir:
        os.makedirs(orig_dir, exist_ok=True)
        shutil.copy2(item.local_path, os.path.join(orig_dir, item.original_filename))
        saved_to.append(orig_dir)
    if proc_dir:
        os.makedirs(proc_dir, exist_ok=True)
        shutil.copy2(dest_path, os.path.join(proc_dir, safe_name))
        saved_to.append(proc_dir)

    record = {
        'timestamp': item.date,
        'sender': item.sender,
        'vendor': vendor,
        'invoice_number': inv_num,
        'po_number': po_num,
        'invoice_date': item.invoice_date,
        'terms': item.terms,
        'subtotal': item.subtotal,
        'tax': item.tax,
        'total': item.total,
        'currency': item.currency,
        'extra_fields': item.extra_fields,
        'filename': safe_name,
        'original_filename': item.original_filename,
    }
    db = add_invoice(record, db)
    save_db(db, DB_PATH)
    st.session_state.invoices_db = db

    log_activity(
        timestamp=item.date,
        action='filed',
        original_filename=item.original_filename,
        final_filename=safe_name,
        vendor=vendor,
        invoice_number=inv_num,
        po_number=po_num,
        status='digital',
    )
    if fetcher:
        try:
            fetcher.mark_as_read(EmailAttachment(
                sender=item.sender,
                subject=item.subject,
                date=item.date,
                email_uid=item.email_uid,
                attachment_filename=item.original_filename,
            ))
        except Exception:
            pass
    item.filed = True
    item.dest_path = dest_path
    extra = f"  ·  saved to {', '.join(saved_to)}" if saved_to else ""
    st.success(f"Filed as {safe_name}{extra}")
    st.rerun()


def send_to_review(item_idx, item, fetcher):
    item = st.session_state.invoice_items[item_idx]
    dest = SCANNED_DIR if not item.is_digital else UNRESOLVED_DIR
    safe_name, dest_path = file_invoice(item.local_path, dest, item.original_filename)
    log_activity(
        timestamp=item.date,
        action='sent_to_manual_review',
        original_filename=item.original_filename,
        final_filename=safe_name,
        vendor=item.editable_vendor or item.vendor_name,
        invoice_number=item.editable_inv or item.invoice_number,
        po_number=item.editable_po or item.po_number,
        status='scanned' if not item.is_digital else 'unresolved',
    )
    if fetcher:
        try:
            fetcher.mark_as_unread(EmailAttachment(
                sender=item.sender,
                subject=item.subject,
                date=item.date,
                email_uid=item.email_uid,
                attachment_filename=item.original_filename,
            ))
        except Exception:
            pass
    st.session_state.invoice_items[item_idx].sent_to_review = True
    st.success(f"Moved to manual review as {safe_name} (email left unread)")
    st.rerun()


def filed_items_section():
    filed = [i for i in st.session_state.invoice_items if i.filed and i.dest_path]
    if not filed:
        return
    st.divider()
    st.subheader(f"Filed — ready to download ({len(filed)})")
    for idx, item in enumerate(filed):
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**{item.proposed_filename or item.original_filename}**")
                st.caption(f"{item.sender} · {item.date}")
            with c2:
                try:
                    with open(item.dest_path, 'rb') as f:
                        file_bytes = f.read()
                    st.download_button(
                        label="Download",
                        data=file_bytes,
                        file_name=item.proposed_filename or item.original_filename,
                        mime="application/pdf",
                        key=f"dl_filed_{idx}_{item.email_uid}",
                    )
                except FileNotFoundError:
                    st.caption("File unavailable")


def _num(value):
    try:
        return float(str(value).replace(',', '').replace('$', '').strip()) or 0.0
    except (ValueError, TypeError):
        return 0.0


def _dash_df():
    db = st.session_state.get("invoices_db", empty_db())
    if db is None or db.empty:
        return empty_db()
    df = db.copy()
    df['total_num'] = df['total'].map(_num)
    df['subtotal_num'] = df['subtotal'].map(_num)
    df['tax_num'] = df['tax'].map(_num)
    return df


def tab_dashboard(fetcher):
    st.header("Dashboard")

    items = st.session_state.invoice_items
    db = st.session_state.get("invoices_db", empty_db())
    df = _dash_df() if db is not None and len(db) > 0 else empty_db()

    pending = [i for i in items if not i.filed and not i.sent_to_review]
    filed_sess = [i for i in items if i.filed]
    review = [i for i in items if i.sent_to_review]
    filed_total = len(db) if db is not None else 0
    total_amount = df['total_num'].sum() if df is not None and len(df) > 0 else 0
    vendor_count = df['vendor'].nunique() if df is not None and len(df) > 0 and 'vendor' in df.columns else 0
    avg_amount = total_amount / filed_total if filed_total else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Pending", len(pending))
    c2.metric("Filed", filed_total)
    c3.metric("In Review", len(review))
    c4.metric("Total Value", f"${total_amount:,.2f}")
    c5.metric("Vendors", vendor_count)

    st.divider()
    st.subheader("Invoice Workflow")

    if not items:
        st.info("No invoices fetched yet. Click **Check Inbox** or they are checked automatically on launch.")

    for idx, item in enumerate(items):
        with st.container(border=True):
            c1, c2, c3 = st.columns([2.5, 2, 1.5])
            with c1:
                status = "**:green[Filed]**" if item.filed else ("**:orange[In Review]**" if item.sent_to_review else "**:blue[Pending]**")
                st.markdown(f"**{item.proposed_filename or item.original_filename}**  {status}")
                st.markdown(f"**Vendor:** {item.editable_vendor or item.vendor_name}  ·  **Invoice #:** {item.editable_inv or item.invoice_number}  ·  **PO #:** {item.editable_po or item.po_number}")
                if item.invoice_date:
                    st.markdown(f"**Invoice Date:** {item.invoice_date}  ·  **Terms:** {item.terms}")
                if item.total:
                    st.markdown(f"**Total:** {item.currency}{item.total}  ({item.currency}{item.subtotal} + {item.currency}{item.tax} tax)")
                for k, v in item.extra_fields.items():
                    st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                st.caption(f"{item.sender} · {item.date}")
            with c2:
                img = render_pdf_preview(item.local_path)
                if img:
                    st.image(img, width=200)
                else:
                    st.markdown("*Preview unavailable*")
            with c3:
                if item.filed:
                    try:
                        with open(item.dest_path, 'rb') as f:
                            file_bytes = f.read()
                        st.download_button(
                            label="Download PDF",
                            data=file_bytes,
                            file_name=item.proposed_filename or item.original_filename,
                            mime="application/pdf",
                            key=f"dash_dl_filed_{idx}_{item.email_uid}",
                        )
                    except FileNotFoundError:
                        st.caption("File unavailable")
                elif item.sent_to_review:
                    st.caption("Waiting for manual review")
                else:
                    if st.button("Edit this invoice", key=f"dash_edit_{idx}", width='stretch'):
                        st.session_state.edit_idx = idx
                        st.session_state.active_tab = "Process Invoices"
                        st.rerun()
                    if st.button("Confirm & File", key=f"dash_file_{idx}", width='stretch'):
                        confirm_file_item(idx, item, fetcher)
                    if st.button("Send to Manual Review", key=f"dash_review_{idx}", width='stretch'):
                        send_to_review(idx, item, fetcher)

    st.divider()

    col_filters, col_charts = st.columns([1, 2])
    with col_filters:
        st.subheader("Analytics Filters")
        if df is None or df.empty:
            st.caption("No filed invoices yet.")
        else:
            vendors = ['All'] + sorted(df['vendor'].dropna().unique().tolist())
            sel_vendor = st.selectbox("Vendor", vendors, key="dash_vendor")
            view_df = df.copy()
            if sel_vendor != 'All':
                view_df = view_df[view_df['vendor'] == sel_vendor]

    with col_charts:
        if df is None or df.empty:
            st.caption("Spend by Vendor")
        else:
            st.subheader("Spend by Vendor")
            vendor_spend = view_df.groupby('vendor')['total_num'].sum().sort_values(ascending=False)
            st.bar_chart(vendor_spend)

            st.subheader("Invoices by Vendor")
            vendor_count_chart = view_df['vendor'].value_counts()
            st.bar_chart(vendor_count_chart)

    if df is not None and len(df) > 0:
        st.divider()
        st.subheader(f"Filed Invoice Details ({len(df)})")
        display_cols = [c for c in [
            'timestamp', 'sender', 'vendor', 'invoice_number', 'po_number',
            'invoice_date', 'terms', 'subtotal', 'tax', 'total', 'currency',
            'extra_fields', 'filename',
        ] if c in df.columns]
        st.dataframe(df[display_cols], width='stretch')
        st.download_button(
            label="Download results (.csv)",
            data=csv_bytes(df[display_cols]),
            file_name="dashboard_results.csv",
            mime="text/csv",
            key="dl_dashboard",
        )


def _render_editable_fields(item, idx):
    vendor_key = f"vendor_{idx}"
    inv_key = f"inv_{idx}"
    po_key = f"po_{idx}"
    ev = st.text_input("Vendor", value=item.editable_vendor or item.vendor_name, key=vendor_key)
    ei = st.text_input("Invoice #", value=item.editable_inv or item.invoice_number, key=inv_key)
    ep = st.text_input("PO #", value=item.editable_po or item.po_number, key=po_key)
    item.editable_vendor = ev
    item.editable_inv = ei
    item.editable_po = ep

    parts = [p for p in (ev, ei, ep) if p]
    proposed = f"{'_'.join(parts)}.pdf" if parts else item.original_filename
    name_key = f"name_{idx}"
    st.text_input("Filename", value=proposed, key=name_key, disabled=False)
    item.proposed_filename = proposed
    return ev, ei, ep


def _render_action_buttons(item, idx, fetcher):
    if item.filed:
        return
    if item.sent_to_review:
        return
    if item.is_digital:
        if st.button("Confirm & File", key=f"file_{idx}", width='stretch'):
            confirm_file_item(idx, item, fetcher)
    if st.button("Send to Manual Review", key=f"review_{idx}", width='stretch'):
        send_to_review(idx, item, fetcher)


def tab_process_invoices(fetcher):
    col1, col2 = st.columns([3, 1])
    with col1:
        st.header("Process Invoices")
    with col2:
        if st.button("Check Inbox for New Invoices", width='stretch', type="primary"):
            if fetcher is None:
                st.error("Configure mailbox access in the sidebar.")
            else:
                fetch_and_process(fetcher)

    edit_idx = st.session_state.get("edit_idx")
    if edit_idx is not None and 0 <= edit_idx < len(st.session_state.invoice_items):
        focus_item = st.session_state.invoice_items[edit_idx]
        if not focus_item.filed and not focus_item.sent_to_review:
            st.subheader("Editing selected invoice")
            with st.container(border=True):
                fcols = st.columns([2.5, 2, 2, 1.5])
                with fcols[0]:
                    st.markdown(f"**From:** {focus_item.sender}")
                    st.markdown(f"**Subject:** {focus_item.subject}")
                    st.markdown(f"**Date:** {focus_item.date}")
                    if focus_item.total:
                        st.markdown(f"**Total:** {focus_item.currency}{focus_item.total}")
                with fcols[1]:
                    _render_editable_fields(focus_item, edit_idx)
                with fcols[2]:
                    img = render_pdf_preview(focus_item.local_path)
                    if img:
                        st.image(img, width=200)
                    else:
                        st.markdown("*Preview unavailable*")
                with fcols[3]:
                    _render_action_buttons(focus_item, edit_idx, fetcher)

    if st.session_state.invoice_items:
        pending = [i for i in st.session_state.invoice_items if not i.filed and not i.sent_to_review]
        filed_count = sum(1 for i in st.session_state.invoice_items if i.filed)
        reviewed_count = sum(1 for i in st.session_state.invoice_items if i.sent_to_review)
        st.caption(f"{len(pending)} pending  ·  {filed_count} filed  ·  {reviewed_count} in review")

        for idx, item in enumerate(st.session_state.invoice_items):
            if item.filed or item.sent_to_review:
                continue

            with st.container(border=True):
                cols = st.columns([2.5, 2, 2, 1.5])

                with cols[0]:
                    st.markdown(f"**From:** {item.sender}")
                    st.markdown(f"**Subject:** {item.subject}")
                    st.markdown(f"**Date:** {item.date}")
                    if item.is_digital:
                        st.markdown("**:green[Digital]** — text layer detected")
                        if item.invoice_date:
                            st.markdown(f"**Invoice Date:** {item.invoice_date}")
                        if item.terms:
                            st.markdown(f"**Terms:** {item.terms}")
                        if item.subtotal:
                            st.markdown(f"**Subtotal:** {item.currency}{item.subtotal}")
                        if item.tax:
                            st.markdown(f"**Tax:** {item.currency}{item.tax}")
                        if item.total:
                            st.markdown(f"**Total:** {item.currency}{item.total}")
                        for k, v in item.extra_fields.items():
                            st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                    else:
                        st.markdown("**:red[Scanned]** — auto-flagged for manual review")

                with cols[1]:
                    if item.is_digital:
                        _render_editable_fields(item, idx)
                    else:
                        st.markdown("**Scanned document**")
                        st.markdown("No text layer available for extraction.")

                with cols[2]:
                    img = render_pdf_preview(item.local_path)
                    if img:
                        st.image(img, caption="Page 1", width='stretch')
                    else:
                        st.markdown("*Preview unavailable*")

                with cols[3]:
                    _render_action_buttons(item, idx, fetcher)
        filed_items_section()

    elif st.session_state.get('fetched'):
        st.info("No invoices to process. Click **Check Inbox** to search for new invoices.")


def tab_manual_review():
    st.header("Needs Manual Review")
    scanned_files, unresolved_files = get_manual_review_files()

    if scanned_files:
        st.subheader(f"Scanned Documents ({len(scanned_files)})")
        for f in scanned_files:
            with st.container(border=True):
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"**{os.path.basename(f)}**")
                with c2:
                    img = render_pdf_preview(f)
                    if img:
                        st.image(img, width=300)

    if unresolved_files:
        st.subheader(f"Unresolved Digital Documents ({len(unresolved_files)})")
        for f in unresolved_files:
            with st.container(border=True):
                c1, c2 = st.columns([1, 1])
                with c1:
                    st.markdown(f"**{os.path.basename(f)}**")
                with c2:
                    img = render_pdf_preview(f)
                    if img:
                        st.image(img, width=300)

    if not scanned_files and not unresolved_files:
        st.info("No documents in manual review.")


def tab_processed_files():
    st.header("Processed Files")
    files = get_processed_files()
    if not files:
        st.info("No processed files yet. Use the **Process Invoices** tab to file invoices.")
        return

    for f in files:
        with st.container(border=True):
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.markdown(f"**{os.path.basename(f)}**")
            with c2:
                img = render_pdf_preview(f)
                if img:
                    st.image(img, width=150)
            with c3:
                with open(f, 'rb') as fh:
                    st.download_button(
                        label="Download",
                        data=fh.read(),
                        file_name=os.path.basename(f),
                        mime="application/pdf",
                        key=f"dl_processed_{os.path.basename(f)}",
                    )


def tab_activity_log():
    st.header("Activity Log")
    if os.path.exists(ACTIVITY_LOG_PATH):
        repair_activity_log_schema()
        df = pd.read_csv(ACTIVITY_LOG_PATH)
        st.dataframe(df, width='stretch')
    else:
        st.info("No activity logged yet.")


def tab_invoice_database():
    st.header("Invoice Database")

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Upload spreadsheet")
        uploaded = st.file_uploader("Upload a CSV backup to restore the database (e.g. if the database is missing)", type=["csv"])
        if uploaded is not None:
            try:
                db = import_spreadsheet(uploaded.getvalue(), DB_PATH)
                st.session_state.invoices_db = db
                st.success(f"Imported {len(db)} records into the database.")
            except Exception as e:
                st.error(f"Could not import spreadsheet: {e}")
    with col2:
        st.subheader("Download backup")
        db = st.session_state.get("invoices_db", empty_db())
        if len(db) > 0:
            st.download_button(
                label="Download Invoice Database (.csv)",
                data=csv_bytes(db),
                file_name="invoices.csv",
                mime="text/csv",
                key="dl_db",
            )
        else:
            st.caption("No records yet — file invoices to populate the database.")

    st.divider()
    st.subheader("Records")
    db = st.session_state.get("invoices_db", empty_db())
    if len(db) > 0:
        st.dataframe(db, width='stretch')
    else:
        st.info("No records yet.")


def tab_vendor_mapping():
    st.header("Vendor Mapping")
    mapping = load_vendor_mapping()

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Current Mappings")
        if mapping:
            data = [{"Domain": d, "Vendor Name": n} for d, n in mapping.items()]
            st.dataframe(data, width='stretch')
        else:
            st.info("No vendor mappings configured.")

    with col2:
        st.subheader("Add / Edit")
        with st.form("vendor_form", clear_on_submit=True):
            domain = st.text_input("Email Domain", placeholder="acmesupply.com")
            vendor_name = st.text_input("Vendor Name", placeholder="Acme Supply Co.")
            submitted = st.form_submit_button("Save Mapping", width='stretch')
            if submitted and domain and vendor_name:
                add_vendor_mapping(domain.strip().lower(), vendor_name.strip())
                st.success(f"Saved: {domain} → {vendor_name}")
                st.rerun()


def _imap_fetcher_from_config(host, user, password):
    if host and user and password:
        return IMAPMailboxFetcher(host.strip(), user.strip(), password.strip())
    return None


def sidebar_config():
    with st.sidebar:
        st.header("Configuration")

        sec = st.secrets
        imap_host = sec.get("imap_host") or sec.get("email", {}).get("imap_host")
        imap_user = sec.get("imap_user") or sec.get("email", {}).get("imap_user") or sec.get("email", {}).get("smtp_user")
        imap_pass = sec.get("imap_pass") or sec.get("email", {}).get("imap_pass") or sec.get("email", {}).get("smtp_pass")
        fetcher = _imap_fetcher_from_config(imap_host, imap_user, imap_pass)
        if fetcher:
            st.success(f"Connected as {imap_user}")
        else:
            st.subheader("IMAP Settings")
            imap_host = st.text_input("Host", value=imap_host or "imap.gmail.com")
            imap_user = st.text_input("Username", value=imap_user or "", placeholder="you@gmail.com")
            imap_pass = st.text_input("App Password", type="password")
            fetcher = _imap_fetcher_from_config(imap_host, imap_user, imap_pass)
            if not fetcher:
                st.info("Enter IMAP credentials above or add them to .streamlit/secrets.toml")

        st.divider()
        st.subheader("Auto-save folders")
        orig_dir = st.text_input(
            "Original files folder",
            value=st.session_state.get("orig_dir", ""),
            placeholder=r"C:\Users\...\originals",
            help="Raw attachment saved here before renaming.",
        )
        proc_dir = st.text_input(
            "Processed files folder",
            value=st.session_state.get("proc_dir", ""),
            placeholder=r"C:\Users\...\processed",
            help="Renamed invoice (vendor_invoice#.pdf) saved here.",
        )
        st.session_state.orig_dir = orig_dir
        st.session_state.proc_dir = proc_dir

        st.divider()
        st.subheader("Test mode")
        st.session_state.test_mode = st.checkbox(
            "Fetch last 3 invoices even if already processed",
            value=st.session_state.get("test_mode", True),
            help="For testing only — ignores seen/duplicate status.",
        )

        st.divider()
        st.caption("Invoice Intake v1.0")

        return fetcher


def main():
    st.set_page_config(page_title="Invoice Intake System", layout="wide")
    st.title("Invoice Intake System")

    if 'invoice_items' not in st.session_state:
        st.session_state.invoice_items = []
    if 'fetched' not in st.session_state:
        st.session_state.fetched = False
    if 'invoices_db' not in st.session_state:
        init_db(DB_PATH)
        st.session_state.invoices_db = load_db(DB_PATH)
    if 'auto_checked' not in st.session_state:
        st.session_state.auto_checked = False
    if 'active_tab' not in st.session_state:
        st.session_state.active_tab = "Dashboard"
    if 'edit_idx' not in st.session_state:
        st.session_state.edit_idx = None

    create_folder_structure()

    fetcher = sidebar_config()

    if fetcher and not st.session_state.auto_checked:
        st.session_state.auto_checked = True
        fetch_and_process(fetcher)

    tabs = [
        "Dashboard",
        "Process Invoices",
        "Needs Manual Review",
        "Processed Files",
        "Activity Log",
        "Vendor Mapping",
        "Invoice Database",
    ]
    tab_cols = st.columns(len(tabs))
    for i, t in enumerate(tabs):
        with tab_cols[i]:
            active = st.session_state.active_tab == t
            if st.button(t, key=f"nav_{i}_{t}", width='stretch', type="primary" if active else "secondary"):
                st.session_state.active_tab = t
                st.session_state.edit_idx = None
                st.rerun()

    st.divider()

    if st.session_state.active_tab == "Dashboard":
        tab_dashboard(fetcher)
    elif st.session_state.active_tab == "Process Invoices":
        tab_process_invoices(fetcher)
    elif st.session_state.active_tab == "Needs Manual Review":
        tab_manual_review()
    elif st.session_state.active_tab == "Processed Files":
        tab_processed_files()
    elif st.session_state.active_tab == "Activity Log":
        tab_activity_log()
    elif st.session_state.active_tab == "Vendor Mapping":
        tab_vendor_mapping()
    else:
        tab_invoice_database()


if __name__ == '__main__':
    main()
