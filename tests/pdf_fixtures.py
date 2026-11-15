
from io import BytesIO


def _escape_pdf_text(text: str) -> bytes:
    """Escape text for a PDF literal string."""
    text = text.encode("ascii", errors="replace").decode("ascii")
    text = text.replace("\\", "\\\\")
    text = text.replace("(", "\\(")
    text = text.replace(")", "\\)")
    return text.encode("ascii")


def make_pdf(pages: list[str | None]) -> bytes:
    """Build a small PDF in memory.

    Each string represents a text page.
    None represents a page without extractable text.
    """
    objects = {}

    page_ids = []
    content_ids = []

    for index in range(len(pages)):
        page_ids.append(4 + index * 2)
        content_ids.append(5 + index * 2)

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[2] = (
        f"<< /Type /Pages /Kids [{kids}] "
        f"/Count {len(pages)} >>"
    ).encode("ascii")

    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for index, text in enumerate(pages):
        page_id = page_ids[index]
        content_id = content_ids[index]

        if text is None:
            stream = b""
        else:
            lines = text.splitlines() or [text]
            commands = [b"BT", b"/F1 12 Tf", b"50 750 Td"]

            for line_index, line in enumerate(lines):
                if line_index:
                    commands.append(b"0 -16 Td")

                escaped = _escape_pdf_text(line)
                commands.append(b"(" + escaped + b") Tj")

            commands.append(b"ET")
            stream = b"\n".join(commands)

        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")

        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream"
        )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (len(objects) + 1)

    for object_id in sorted(objects):
        offsets[object_id] = len(pdf)
        pdf.extend(f"{object_id} 0 obj\n".encode("ascii"))
        pdf.extend(objects[object_id])
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)

    pdf.extend(
        f"xref\n0 {len(offsets)}\n".encode("ascii")
    )
    pdf.extend(b"0000000000 65535 f \n")

    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))

    pdf.extend(
        (
            f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF"
        ).encode("ascii")
    )

    return bytes(pdf)


def make_encrypted_pdf(
    pages: list[str | None],
    user_password: str = "secret",
) -> bytes:
    """Build an encrypted PDF in memory."""
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(BytesIO(make_pdf(pages)))
    writer = PdfWriter()
    writer.append(reader)
    writer.encrypt(user_password)

    output = BytesIO()
    writer.write(output)

    return output.getvalue()
