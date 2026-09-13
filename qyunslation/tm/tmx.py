# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：TMX 最小读写（stdlib xml.etree）。"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable


MAX_TMX_BYTES = 8 * 1024 * 1024
MAX_TMX_UNITS = 20000
MAX_LANG_LEN = 16
MAX_SEG_CHARS = 20000


class TmxRejected(ValueError):
    """TMX 不可信或超出上限。"""


@dataclass(frozen=True)
class TmxUnit:
    source_text: str
    target_text: str
    src_lang: str
    tgt_lang: str


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_tmx(xml_text: str) -> list[TmxUnit]:
    """解析 TMX；只读 ``tu`` / ``tuv`` / ``seg``。

    ``xml.etree`` 会展开内部实体（十亿笑），故先拒 DOCTYPE/ENTITY 再解析。
    """
    text = xml_text or ""
    if len(text.encode("utf-8", "ignore")) > MAX_TMX_BYTES:
        raise TmxRejected(f"TMX exceeds {MAX_TMX_BYTES} bytes")
    head = text.lstrip()[:4096].upper()
    if "<!DOCTYPE" in head or "<!ENTITY" in head:
        raise TmxRejected("TMX must not declare DOCTYPE or ENTITY")
    root = ET.fromstring(text)
    units: list[TmxUnit] = []
    for tu in root.iter():
        if _local(tu.tag) != "tu":
            continue
        segs: list[tuple[str, str]] = []
        for tuv in list(tu):
            if _local(tuv.tag) != "tuv":
                continue
            lang = (
                tuv.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                or tuv.attrib.get("xml:lang")
                or tuv.attrib.get("lang")
                or ""
            )
            seg_text = ""
            for child in list(tuv):
                if _local(child.tag) == "seg":
                    seg_text = "".join(child.itertext()).strip()
                    break
            if not lang or not seg_text:
                continue
            if len(lang) > MAX_LANG_LEN:
                raise TmxRejected(f"xml:lang exceeds {MAX_LANG_LEN} chars: {lang[:24]}…")
            if len(seg_text) > MAX_SEG_CHARS:
                raise TmxRejected(f"seg exceeds {MAX_SEG_CHARS} chars")
            segs.append((lang, seg_text))
        if len(segs) >= 2:
            if len(units) >= MAX_TMX_UNITS:
                raise TmxRejected(f"TMX exceeds {MAX_TMX_UNITS} units")
            units.append(
                TmxUnit(
                    source_text=segs[0][1],
                    target_text=segs[1][1],
                    src_lang=segs[0][0],
                    tgt_lang=segs[1][0],
                )
            )
    return units


def build_tmx(
    units: Iterable[object],
    *,
    src_lang: str = "en",
    tgt_lang: str = "zh",
) -> str:
    """导出最小 TMX 1.4；``units`` 需有 source_text/target_text，可选 src/tgt_lang。"""
    tmx = ET.Element("tmx", version="1.4")
    header = ET.SubElement(
        tmx,
        "header",
        {
            "creationtool": "qyunslation",
            "creationtoolversion": "034e",
            "segtype": "sentence",
            "o-tmf": "qyunslation",
            "adminlang": "en",
            "srclang": src_lang,
            "datatype": "plaintext",
        },
    )
    _ = header
    body = ET.SubElement(tmx, "body")
    for u in units:
        tu = ET.SubElement(body, "tu")
        sl = str(getattr(u, "src_lang", None) or src_lang)
        tl = str(getattr(u, "tgt_lang", None) or tgt_lang)
        src = ET.SubElement(tu, "tuv")
        src.set("{http://www.w3.org/XML/1998/namespace}lang", sl)
        ET.SubElement(src, "seg").text = str(getattr(u, "source_text") or "")
        tgt = ET.SubElement(tu, "tuv")
        tgt.set("{http://www.w3.org/XML/1998/namespace}lang", tl)
        ET.SubElement(tgt, "seg").text = str(getattr(u, "target_text") or "")
    # ElementTree 默认会写 ns0；注册前缀以得到 xml:lang
    ET.register_namespace("xml", "http://www.w3.org/XML/1998/namespace")
    return ET.tostring(tmx, encoding="unicode", xml_declaration=True)
