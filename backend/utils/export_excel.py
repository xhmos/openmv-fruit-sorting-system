# -*- coding: utf-8 -*-
"""把分拣记录导出成 Excel。"""

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = ["ID", "果实品种", "分拣结果", "置信度", "像素面积", "图片路径", "分拣时间"]
WIDTHS = [10, 16, 12, 10, 12, 42, 22]


def build_records_workbook(records):
    wb = Workbook()
    ws = wb.active
    ws.title = "分拣记录"

    header_fill = PatternFill("solid", fgColor="1677FF")
    header_font = Font(color="FFFFFF", bold=True)

    for col, title in enumerate(HEADERS, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for row_idx, r in enumerate(records, start=2):
        ws.cell(row=row_idx, column=1, value=r.id)
        ws.cell(row=row_idx, column=2, value=r.fruit_type)
        ws.cell(row=row_idx, column=3, value="合格" if r.result == "good" else "不合格")
        ws.cell(row=row_idx, column=4, value=round(float(r.confidence or 0), 3))
        ws.cell(row=row_idx, column=5, value=r.area or 0)
        ws.cell(row=row_idx, column=6, value=r.img_path or "")
        ws.cell(
            row=row_idx,
            column=7,
            value=r.create_time.strftime("%Y-%m-%d %H:%M:%S") if r.create_time else "",
        )

    for i, width in enumerate(WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width

    ws.freeze_panes = "A2"
    return wb
