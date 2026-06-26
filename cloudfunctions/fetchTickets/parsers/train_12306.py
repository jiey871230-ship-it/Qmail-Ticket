"""12306 火车票解析器"""
from __future__ import annotations
import email.policy
import re
from email import message_from_bytes

from models import RawEmail, Ticket
from utils.email_utils import extract_12306_pdf
from utils.pdf_utils import pdf_to_text
from parsers.base import TicketParser


class Train12306Parser(TicketParser):
    """12306 火车票解析器"""

    def can_parse(self, raw_email: RawEmail) -> bool:
        return "网上购票系统" in raw_email.subject

    def parse(self, raw_email: RawEmail) -> list:
        msg = message_from_bytes(raw_email.raw_bytes, policy=email.policy.default)
        pdf_data = extract_12306_pdf(msg)
        if not pdf_data:
            return []

        text = pdf_to_text(pdf_data)
        if not text:
            return []

        tickets = _parse_12306_text(text, pdf_data)
        if not tickets:
            return []

        results = []
        for t in tickets:
            safe_date = t.travel_date.replace('/', '-')
            safe_station = t.route.replace('/', '-').replace('\\', '-')
            pdf_name = f"{safe_date}-{safe_station}.pdf"
            results.append((pdf_data, pdf_name, [t]))
        return results


def _parse_12306_text(text: str, pdf_bytes: bytes | None = None) -> list:
    """从 12306 PDF 文本提取车票信息。"""
    tickets = []
    lines = text.strip().split('\n')
    stations_cn = [l.strip() for l in lines if re.match(r'^[一-鿿]+站$', l.strip())]

    from_station, to_station = '', ''

    # 方法1: PDF span 坐标定位（最可靠，通过"站"字左侧中文定位发站/到站）
    if pdf_bytes:
        from_station, to_station = _match_by_span_positions(pdf_bytes)

    # 方法2: 纯文本拼音行定位
    if not from_station and len(stations_cn) >= 2:
        from_station, to_station = _match_by_pinyin_lines(lines, stations_cn)

    # 方法3: PDF 块级拼音 x 坐标定位
    if not from_station and pdf_bytes and len(stations_cn) >= 2:
        from_station, to_station = _match_by_pinyin_blocks(pdf_bytes, stations_cn)

    # 方法4: 纯文本顺序回退
    if not from_station and len(stations_cn) >= 2:
        from_station, to_station = stations_cn[0], stations_cn[1]

    # 车次
    trains = re.findall(r'\b([GCDKZT]\d{2,5})\b', text, re.IGNORECASE)
    train = trains[0].upper() if trains else ''

    # 乘车日期
    travel_date = _extract_travel_date(text)

    # 座次
    seat_class_m = re.search(r'(二等座|一等座|商务座|特等座|软卧|硬卧|硬座|无座|动卧|软座)', text)
    seat_class = seat_class_m.group(1) if seat_class_m else ''
    seat_dm = re.search(r'(\d{2}车[A-F\d]{3}[号位])', text)
    seat_detail = seat_dm.group(1) if seat_dm else ''
    vehicle = seat_class or seat_detail or '火车'

    # 票价
    amount = _extract_amount(text)

    # 发票项目
    item = '票价'
    if '退票' in text:
        item = '退票费'
    elif '改签' in text:
        item = '改签费'

    if from_station and to_station:
        from_short = from_station.replace('站', '')
        to_short = to_station.replace('站', '')
        tickets.append(Ticket(
            travel_date=travel_date,
            carrier=train,
            route=f"{from_short}-{to_short}",
            amount=amount,
            ticket_type='火车',
            vehicle=vehicle,
            item=item,
        ))

    return tickets


def _match_by_span_positions(pdf_bytes: bytes) -> tuple:
    """通过 PDF span 坐标定位发站和到站。

    12306 票面布局：发站在左，到站在右。找到所有"站"字 span，
    匹配其左侧同行的中文站名，按 x 坐标排序即可区分发站/到站。
    """
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        d = doc[0].get_text("dict")
        doc.close()

        all_spans = []
        for block in d["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text:
                        x, y = span["origin"]
                        all_spans.append((x, y, text))

        station_spans = []
        for x, y, text in all_spans:
            if text != "站":
                continue
            best = None
            best_dx = 999.0
            for x2, y2, text2 in all_spans:
                if abs(y2 - y) < 3 and x2 < x and re.match(r'^[一-鿿]+$', text2) and len(text2) >= 2:
                    dx = x - x2
                    if dx < best_dx:
                        best_dx = dx
                        best = (x2, text2)
            if best and best not in station_spans:
                station_spans.append(best)

        station_spans.sort(key=lambda s: s[0])
        if len(station_spans) >= 2:
            return station_spans[0][1] + "站", station_spans[-1][1] + "站"
        return '', ''
    except Exception:
        return '', ''


def _match_by_pinyin_blocks(pdf_bytes: bytes, stations_cn: list) -> tuple:
    """通过 PDF 块级拼音 x 坐标定位发站和到站。"""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        blocks = doc[0].get_text("blocks")
        doc.close()

        pinyin_blocks = []
        for b in blocks:
            x0, y0, x1, y1, bt, _, _ = b
            bt = bt.strip()
            if re.match(r'^[A-Z][a-z]+$', bt) and len(bt) > 3:
                pinyin_blocks.append((x0, bt))

        if not pinyin_blocks:
            return '', ''

        pinyin_blocks.sort(key=lambda b: b[0])
        left_pinyin = pinyin_blocks[0][1]
        right_pinyin = pinyin_blocks[-1][1] if len(pinyin_blocks) > 1 else ''

        pinyin_map = {
            'chengdudong': '成都东站', 'chengdunan': '成都南站', 'chengduxi': '成都西站',
            'chongqingbei': '重庆北站', 'chongqingxi': '重庆西站',
            'leshan': '乐山站', 'yaan': '雅安站',
            'nanchong': '南充站', 'nanchongbei': '南充北站',
            'mianyang': '绵阳站', 'deyang': '德阳站',
            'guangyuan': '广元站', 'qianjiang': '黔江站',
            'shuangliujichang': '双流机场站', 'yibindong': '宜宾东站',
            'luzhou': '泸州站', 'panzhihunan': '攀枝花南站',
            'xichangxi': '西昌西站', 'zigong': '自贡站',
            'neijiangbei': '内江北站', 'zunyi': '遵义站',
            'guiyangbei': '贵阳北站',
        }

        def match_station(pinyin):
            pk = pinyin.lower().replace(' ', '')
            if pk in pinyin_map:
                return pinyin_map[pk]
            for s in stations_cn:
                s_no_zhan = s.replace('站', '')
                if pk[:4] == s_no_zhan[:4].lower()[:4]:
                    return s
            return ''

        from_station = match_station(left_pinyin)
        to_station = match_station(right_pinyin)

        if not to_station and len(stations_cn) >= 2:
            for s in stations_cn:
                if s != from_station:
                    to_station = s
                    break

        return from_station, to_station
    except Exception:
        return '', ''


def _match_by_pinyin_lines(lines: list, stations_cn: list) -> tuple:
    """通过纯文本拼音行定位发站和到站。"""
    for i, line in enumerate(lines):
        sline = line.strip()
        if re.match(r'^[A-Z][a-z]+$', sline) and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r'^[一-鿿]+站$', next_line):
                from_station = next_line
                to_station = ''
                for j in range(i + 2, len(lines)):
                    cand = lines[j].strip()
                    if re.match(r'^[一-鿿]+站$', cand):
                        to_station = cand
                        break
                return from_station, to_station
    return '', ''


def _extract_travel_date(text: str) -> str:
    """从 PDF 文本提取乘车日期（排除开票日期）。"""
    dates_all = re.findall(r'(\d{4})年(\d{2})月(\d{2})日', text)
    for y, m, d in dates_all:
        ds = f"{y}-{m}-{d}"
        pos = text.find(f"{y}年{m}月{d}日")
        prefix = text[max(0, pos - 8):pos]
        if '开票' not in prefix and '填开' not in prefix:
            return ds
    if dates_all:
        y, m, d = dates_all[0]
        return f"{y}-{m}-{d}"
    return ''


def _extract_amount(text: str) -> float:
    """从 PDF 文本提取票价。"""
    am1 = re.search(r'[票价退改签]+[费:]*\s*[￥¥]\s*(\d+\.?\d*)', text)
    if am1:
        return float(am1.group(1))
    am2 = re.search(r'[￥¥]\s*(\d+\.?\d{2})', text)
    if am2:
        return float(am2.group(1))
    return 0.0
