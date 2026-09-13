# SPDX-License-Identifier: MPL-2.0
"""PLAN-034e：TMX 最小读写（stdlib xml.etree）。"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable


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
    """解析 TMX；只读 ``tu`` / ``tuv`` / ``seg``。"""
    root = ET.fromstring(xml_text)
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
            if lang and seg_text:
                segs.append((lang, seg_text))
        if len(segs) >= 2:
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
