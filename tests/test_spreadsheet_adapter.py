from pathlib import Path

from utils.spreadsheet_adapter import spreadsheet_to_markdown
from openpyxl import Workbook


def test_spreadsheet_to_markdown_csv(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("col1,col2\nvalue1,value2\n", encoding="utf-8")

    markdown = spreadsheet_to_markdown(csv_path)

    assert "value1" in markdown
    assert "| col1" in markdown


def test_spreadsheet_to_markdown_xlsx(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.append(["Field", "Value"])
    ws.append(["Stories", "10"])
    xlsx_path = tmp_path / "sample.xlsx"
    wb.save(str(xlsx_path))

    markdown = spreadsheet_to_markdown(xlsx_path)
    assert "Stories" in markdown
    assert "10" in markdown
