"""输出器注册"""
from qmail_ticket.outputs.base import OutputWriter
from qmail_ticket.outputs.jpg_out import JpgWriter
from qmail_ticket.outputs.csv_out import CsvWriter
from qmail_ticket.outputs.print_pdf import PrintPdfWriter

WRITERS: list[OutputWriter] = [JpgWriter(), CsvWriter(), PrintPdfWriter()]
