"""PDF→JPG 输出器"""
import os
import sys

from qmail_ticket.models import Ticket
from qmail_ticket.pdf_utils import pdf_to_jpg
from qmail_ticket.outputs.base import OutputWriter

DEFAULT_DPI = 200


class JpgWriter(OutputWriter):
    """将 PDF 转为 JPG"""

    def write(self, tickets: list[Ticket], context: dict) -> None:
        output_dir = context['output_dir']
        pdf_data_list = context['pdf_data_list']
        dpi = context.get('jpg_dpi', DEFAULT_DPI)

        jpg_count = 0
        jpg_paths = []

        for pdf_data, pdf_name in pdf_data_list:
            jpg_path = os.path.join(output_dir, os.path.splitext(pdf_name)[0] + ".jpg")
            try:
                pdf_to_jpg(pdf_data, jpg_path, dpi)
                jpg_paths.append(jpg_path)
                jpg_count += 1
            except Exception as e:
                print(f"  {pdf_name} 转换失败: {e}", file=sys.stderr)

        context['jpg_paths'] = jpg_paths
        print(f"  成功转换: {jpg_count}")
