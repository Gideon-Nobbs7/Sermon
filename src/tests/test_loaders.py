import io

import pytest

from src.app.services.loaders import load_document
from src.app.schemas.sermon import SourceType


def _minimal_pdf(text: str = "Hello world") -> bytes:
    """Build a minimal single-page PDF whose text layer pypdf can extract."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
    ]
    stream = b"BT /F1 12 Tf 72 720 Td (" + text.encode() + b") Tj ET"
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
                + stream + b"\nendstream")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for i, o in enumerate(objs, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode())
        out.write(o + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objs)+1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\nstartxref\n"
              f"{xref_pos}\n%%EOF\n".encode())
    return out.getvalue()


def test_unsupported_extension_raises():
    with pytest.raises(ValueError):
        load_document("file.txt")


def test_load_document_pdf(tmp_path):
    pdf_path = tmp_path / "sample.pdf"
    pdf_path.write_bytes(_minimal_pdf())

    chunks = load_document(str(pdf_path))
    assert len(chunks) >= 1
    assert chunks[0].source_type == SourceType.DOCUMENT
    assert chunks[0].source_file == "sample.pdf"
    assert chunks[0].page == 0
    assert "Hello world" in chunks[0].text
