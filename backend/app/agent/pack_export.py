"""Claim pack downloads (DEV-016): one PDF (cover letter then every pack document) and an email draft (.eml).

Built from the same build_submission_pack() the user approves, so the files always match the approved
hash shown on screen. No model calls. Files that cannot be read are listed on a notice page, never
silently dropped.
"""

import io
from email.message import EmailMessage
from pathlib import Path

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter

from app.agent.claim import build_submission_pack
from app.agent.state import AgentState


def _latin(text: str) -> str:
    """The built-in PDF fonts cover Latin-1 only; replace anything else instead of failing."""
    return text.replace("₹", "Rs ").encode("latin-1", "replace").decode("latin-1")


def _text_page(title: str, body: str) -> bytes:
    """A simple A4 PDF with a title and wrapped body text."""
    pdf = FPDF(format="A4")
    pdf.set_margins(20, 20, 20)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 8, _latin(title))
    pdf.ln(4)
    pdf.set_font("Helvetica", size=11)
    pdf.multi_cell(0, 6, _latin(body))
    return bytes(pdf.output())


def _image_page(path: Path) -> bytes:
    """One A4 page with the photo scaled to fit the page."""
    pdf = FPDF(format="A4")
    pdf.add_page()
    pdf.image(str(path), x=10, y=10, w=190, h=277, keep_aspect_ratio=True)
    return bytes(pdf.output())


def _documents(state: AgentState, pack: dict) -> list[dict]:
    """Full document records for the pack's documents, in pack order."""
    by_id = {d["id"]: d for d in state.get("documents", [])}
    return [by_id[d["id"]] for d in pack["documents"] if d["id"] in by_id]


def approval_status(state: AgentState, pack: dict) -> str:
    """approved (this exact pack), changed (approved, then the documents changed) or not_approved."""
    approval = state.get("submission_approval")
    if not approval:
        return "not_approved"
    return "approved" if approval["hash"] == pack["hash"] else "changed"


def pack_pdf(state: AgentState) -> tuple[bytes, dict]:
    """Merge the cover letter and every pack document into one PDF.

    Returns:
        (PDF bytes, the pack it was built from).
    """
    pack = build_submission_pack(state)
    status = approval_status(state, pack).replace("_", " ")
    writer = PdfWriter()
    writer.append(io.BytesIO(_text_page(f"Claim pack ({status}, ref {pack['hash']})", pack["cover_letter"])))
    skipped = []
    for doc in _documents(state, pack):
        path = Path(doc["path"]) if doc.get("path") else None
        try:
            if path is None or not path.is_file():
                raise FileNotFoundError(doc["filename"])
            page = path.read_bytes() if doc["mime_type"] == "application/pdf" else _image_page(path)
            writer.append(PdfReader(io.BytesIO(page)))
        except Exception:  # noqa: BLE001 - a damaged file must not lose the rest of the pack
            skipped.append(doc["filename"])
    if skipped:
        body = "These files could not be added. Attach them separately:\n" + "\n".join(f"- {name}" for name in skipped)
        writer.append(io.BytesIO(_text_page("Files not included", body)))
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), pack


def pack_email(state: AgentState) -> tuple[bytes, dict]:
    """An unsent email draft: subject and body from the cover letter, every pack document attached.

    The recipient is left empty on purpose: the insurer's claims address is not known from documents.

    Returns:
        (.eml bytes, the pack it was built from).
    """
    pack = build_submission_pack(state)
    lines = pack["cover_letter"].splitlines()
    subject = next((line.removeprefix("Subject: ") for line in lines if line.startswith("Subject: ")), "Health insurance claim")
    docs = _documents(state, pack)
    present = [d for d in docs if d.get("path") and Path(d["path"]).is_file()]
    body = "\n".join(line for line in lines if not line.startswith(("To: ", "Subject: "))).strip()
    missing = [d["filename"] for d in docs if d not in present]
    if missing:
        body += "\n\n[Not attached, add before sending: " + ", ".join(missing) + "]"
    message = EmailMessage()
    message["Subject"] = subject
    message["X-Unsent"] = "1"  # mail apps open it as a draft to edit and send
    message.set_content(body + "\n")
    for doc in present:
        maintype, subtype = doc["mime_type"].split("/", 1)
        message.add_attachment(Path(doc["path"]).read_bytes(), maintype=maintype, subtype=subtype,
                               filename=doc["filename"])
    return bytes(message), pack
