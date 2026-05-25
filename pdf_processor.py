import os
from PIL import Image

POPPLER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "pdf2img_extractor", "poppler-25.12.0", "Library", "bin"
)


def get_pdf_page_count(pdf_bytes: bytes) -> int:
    from pdf2image.pdf2image import pdfinfo_from_bytes
    info = pdfinfo_from_bytes(pdf_bytes, poppler_path=POPPLER_PATH)
    return int(info.get("Pages", 0))


def pdf_page_to_image(pdf_bytes: bytes, page_number: int, dpi: int = 200) -> Image.Image:
    """Convert a single PDF page (1-indexed) to a PIL Image."""
    from pdf2image import convert_from_bytes
    images = convert_from_bytes(
        pdf_bytes,
        dpi=dpi,
        first_page=page_number,
        last_page=page_number,
        poppler_path=POPPLER_PATH,
    )
    return images[0] if images else None
