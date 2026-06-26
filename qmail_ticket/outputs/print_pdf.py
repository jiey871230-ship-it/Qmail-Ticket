"""合并排版 PDF 输出器"""
import os

from qmail_ticket.models import Ticket
from qmail_ticket.outputs.base import OutputWriter

A4_DPI = 200


class PrintPdfWriter(OutputWriter):
    """将火车票和机票 JPG 合并排版为 print.pdf"""

    def write(self, tickets: list[Ticket], context: dict) -> None:
        try:
            from PIL import Image
        except ImportError:
            print("  需要 Pillow 库: pip3 install Pillow")
            return

        output_dir = context['output_dir']

        PAGE_W = int(210 / 25.4 * A4_DPI)
        PAGE_H = int(297 / 25.4 * A4_DPI)
        MARGIN = 80
        SPACING = 32

        trains = sorted(
            [t for t in tickets if t.ticket_type == '火车'],
            key=lambda x: x.travel_date
        )
        flights = sorted(
            [t for t in tickets if t.ticket_type == '飞机'],
            key=lambda x: x.travel_date
        )

        def get_jpg_path(t):
            suffix = "-机票" if t.ticket_type == '飞机' else ""
            return os.path.join(output_dir, f"{t.travel_date}-{t.route}{suffix}.jpg")

        def make_pages(ticket_list, cols, rows):
            pages = []
            per_page = cols * rows
            cell_w = (PAGE_W - 2 * MARGIN - (cols - 1) * SPACING) / cols
            cell_h = (PAGE_H - 2 * MARGIN - (rows - 1) * SPACING) / rows

            for i in range(0, len(ticket_list), per_page):
                page = Image.new('RGB', (PAGE_W, PAGE_H), 'white')
                batch = ticket_list[i:i + per_page]

                for j, t in enumerate(batch):
                    jpg_path = get_jpg_path(t)
                    if not os.path.isfile(jpg_path):
                        continue

                    img = Image.open(jpg_path)
                    img_ratio = img.width / img.height
                    cell_ratio = cell_w / cell_h
                    if img_ratio > cell_ratio:
                        new_w = cell_w
                        new_h = new_w / img_ratio
                    else:
                        new_h = cell_h
                        new_w = new_h * img_ratio

                    img_resized = img.resize((int(new_w), int(new_h)), Image.LANCZOS)

                    col = j % cols
                    row = j // cols
                    x = MARGIN + col * (cell_w + SPACING) + (cell_w - new_w) / 2
                    y = MARGIN + row * (cell_h + SPACING) + (cell_h - new_h) / 2

                    page.paste(img_resized, (int(x), int(y)))

                pages.append(page)
            return pages

        train_pages = make_pages(trains, cols=2, rows=4)
        flight_pages = make_pages(flights, cols=1, rows=3)
        all_pages = train_pages + flight_pages

        if not all_pages:
            print("  没有可合并的 JPG，跳过。")
            return

        pdf_path = os.path.join(output_dir, "print.pdf")
        for img in all_pages:
            img.info['dpi'] = (A4_DPI, A4_DPI)
        all_pages[0].save(
            pdf_path,
            save_all=True,
            append_images=all_pages[1:],
        )
        print(f"  print.pdf 已生成: {pdf_path} (共 {len(all_pages)} 页)")
