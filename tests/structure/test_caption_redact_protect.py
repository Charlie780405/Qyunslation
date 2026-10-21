import pymupdf

from qyunslation.structure.models import BoundingBox
from qyunslation.structure.table_writeback import redact_table_region


def test_redact_keeps_caption_above_table():
    doc = pymupdf.open()
    page = doc.new_page(width=600, height=400)
    page.insert_text((60, 96), "Table 1. Caption", fontsize=12)
    page.insert_text((60, 130), "table body text", fontsize=10)
    redact_table_region(page, BoundingBox(x0=55, y0=100, x1=550, y1=300), x_min_frac=None)
    text = page.get_text()
    assert "Caption" in text
    assert "table body" not in text
