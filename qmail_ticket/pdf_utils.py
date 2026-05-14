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


def pdf_to_jpg(pdf_bytes: bytes, jpg_path: str, dpi: int = 200) -> None:
    """将 PDF 第一页转为 JPG。"""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[0].get_pixmap(dpi=dpi)
    pix.save(jpg_path)
    doc.close()
