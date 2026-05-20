"""PDF 文本提取和图片转换工具"""
import fitz


def pdf_to_text(pdf_bytes: bytes) -> str:
    """从 PDF 字节提取文本。"""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception:
        return ""


def pdf_to_jpg_bytes(pdf_bytes: bytes, dpi: int = 150) -> bytes:
    """将 PDF 第一页转为 JPG bytes。"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    jpg_bytes = pix.tobytes("jpeg")
    doc.close()
    return jpg_bytes
