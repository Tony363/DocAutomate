#!/usr/bin/env python3
"""
Helpers for ingesting raw email submissions (including attachments) into DocAutomate.
"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from pathlib import Path
from typing import List, Optional, Tuple, Union

from datetime import datetime

from ingester import DocumentIngester, Document


@dataclass
class EmailIngestionResult:
    email_document: Document
    attachment_documents: List[Document]


def _parse_email(raw_email: Union[str, bytes]) -> EmailMessage:
    """Parse raw RFC822 email payload into an EmailMessage."""
    if isinstance(raw_email, str):
        raw_bytes = raw_email.encode("utf-8", errors="ignore")
    else:
        raw_bytes = raw_email
    return BytesParser(policy=policy.default).parsebytes(raw_bytes)


def _extract_body(message: EmailMessage) -> str:
    """Return the plain-text body of the message, falling back to HTML stripped content."""
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                return part.get_content().strip()
        # Fallback to HTML stripped text
        for part in message.walk():
            if part.get_content_type() == "text/html":
                html = part.get_content()
                # naive strip
                return html.replace("<br>", "\n").replace("<br/>", "\n")
    else:
        return message.get_content().strip()
    return ""


async def ingest_email(
    document_ingester: DocumentIngester,
    raw_email: Union[str, bytes],
    source: str = "mailbox",
    auto_process: bool = True,
) -> EmailIngestionResult:
    """
    Ingest a raw email payload. Returns the main email Document plus any attachment Documents.
    """
    message = await asyncio.to_thread(_parse_email, raw_email)

    subject = message.get("Subject", "(no subject)")
    sender = message.get("From", "(unknown sender)")
    to = message.get("To", "")
    cc = message.get("Cc", "")
    date_header = message.get("Date", "")
    body_text = _extract_body(message)

    attachments: List[Document] = []
    for index, part in enumerate(message.iter_attachments(), start=1):
        filename = part.get_filename() or f"attachment-{index}"
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        suffix = Path(filename).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(payload)
            tmp_path = tmp.name
        try:
            attachment_doc = await document_ingester.ingest_file(tmp_path)
            attachments.append(attachment_doc)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    email_text = "\n".join([
        f"Subject: {subject}",
        f"From: {sender}",
        f"To: {to}",
        f"Cc: {cc}",
        f"Date: {date_header}",
        "",
        "Body:",
        body_text,
    ])

    # Create metadata capturing attachment IDs
    metadata = {
        "source": source,
        "document_type": "email_submission",
        "attachments": [
            {"filename": doc.filename, "document_id": doc.id} for doc in attachments
        ],
    }

    doc_id = document_ingester.generate_document_id(f"{subject}|{sender}|{body_text}")
    email_document = Document(
        id=doc_id,
        filename=f"email-{email_document_id(subject, sender)}.txt",
        content_type="message/rfc822",
        text=email_text,
        metadata=metadata,
        ingested_at=datetime.utcnow().isoformat(),
        workflow_runs=[],
        delegation_status="email_parsed",
        delegation_details={"attachments": [doc.id for doc in attachments]},
    )
    await document_ingester._store_document(email_document)
    document_ingester.job_queue.put(email_document.id)

    return EmailIngestionResult(email_document=email_document, attachment_documents=attachments)


def email_document_id(subject: str, sender: str) -> str:
    normalized_subject = "".join(ch for ch in subject.lower() if ch.isalnum())[:24] or "email"
    normalized_sender = "".join(ch for ch in sender.lower() if ch.isalnum())[:16] or "sender"
    return f"{normalized_subject}-{normalized_sender}"
