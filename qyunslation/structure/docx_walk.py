# SPDX-License-Identifier: MPL-2.0
"""Shared DOCX traversal for translation and structure scanning (PLAN-030e)."""
from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
from typing import Any

import docx
from docx.document import Document as DocumentObject
from docx.opc.part import Part
from docx.oxml.ns import qn
from docx.oxml.text.run import CT_R
from docx.section import _Footer, _Header
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run


def is_image_run(run: Run) -> bool:
    xml = getattr(run.element, "xml", "")
    return "<w:drawing" in xml or "<w:pict" in xml


def is_formatting_only_run(run: Run) -> bool:
    return run.text == ""


def is_tab_run(run: Run) -> bool:
    if run.text.strip():
        return False
    xml = getattr(run.element, "xml", "")
    return "<w:tab" in xml or "<w:ptab" in xml


def is_instr_text_run(run: Run) -> bool:
    return run.element.find(qn("w:instrText")) is not None


def _paragraph_closes_section(p_element) -> bool:
    """True when this paragraph ends a section (w:sectPr in pPr or on p)."""
    p_pr = p_element.find(qn("w:pPr"))
    if p_pr is not None and p_pr.find(qn("w:sectPr")) is not None:
        return True
    return p_element.find(qn("w:sectPr")) is not None


@dataclass
class DocxWalkSegment:
    """One translatable text segment in document order."""

    segment_index: int
    text: str
    container_ref: str
    section_index: int = 1
    is_textbox: bool = False
    table_path: tuple[int, int, int] | None = None
    element_info: dict[str, Any] = field(repr=False, default_factory=dict)


class DocxWalker:
    IGNORED_TAGS = {
        qn("w:proofErr"),
        qn("w:lastRenderedPageBreak"),
        qn("w:bookmarkStart"),
        qn("w:bookmarkEnd"),
        qn("w:commentRangeStart"),
        qn("w:commentRangeEnd"),
        qn("w:del"),
        qn("w:moveFrom"),
        qn("w:moveTo"),
    }
    RECURSIVE_CONTAINER_TAGS = {
        qn("w:smartTag"),
        qn("w:sdtContent"),
        qn("w:hyperlink"),
        qn("w:ins"),
    }

    def __init__(self) -> None:
        self._segment_index = 0
        self._section_index = 1
        self._container_ref = "section:1/body"
        self._is_textbox = False
        self._table_path: tuple[int, int, int] | None = None

    def walk(self, content: bytes) -> tuple[DocumentObject, list[DocxWalkSegment], list[dict[str, Any]], list[str]]:
        doc = docx.Document(BytesIO(content))
        elements: list[dict[str, Any]] = []
        texts: list[str] = []
        segments: list[DocxWalkSegment] = []
        self._segment_index = 0
        self._section_index = 1
        self._container_ref = "section:1/body"
        self._is_textbox = False
        self._table_path = None

        self._walk_document_body(doc, elements, texts, segments)

        for section_index, section in enumerate(doc.sections):
            self._section_index = section_index + 1
            for kind, container in (
                ("header.default", section.header),
                ("header.first", section.first_page_header),
                ("header.even", section.even_page_header),
                ("footer.default", section.footer),
                ("footer.first", section.first_page_footer),
                ("footer.even", section.even_page_footer),
            ):
                self._container_ref = f"section:{section_index + 1}/{kind}"
                self._is_textbox = False
                self._table_path = None
                self._traverse_container(container, elements, texts, segments)

        if hasattr(doc.part, "footnotes_part") and doc.part.footnotes_part is not None:
            self._section_index = 1
            self._container_ref = "footnotes"
            self._is_textbox = False
            self._table_path = None
            self._traverse_container(doc.part.footnotes_part, elements, texts, segments)
        if hasattr(doc.part, "endnotes_part") and doc.part.endnotes_part is not None:
            self._section_index = 1
            self._container_ref = "endnotes"
            self._is_textbox = False
            self._table_path = None
            self._traverse_container(doc.part.endnotes_part, elements, texts, segments)

        return doc, segments, elements, texts

    def _append_segment(
        self,
        elements: list[dict[str, Any]],
        texts: list[str],
        segments: list[DocxWalkSegment],
        *,
        runs: list[Run],
        paragraph: Paragraph,
        top_level_paragraph: Paragraph,
        full_text: str,
    ) -> None:
        info = {
            "type": "text_runs",
            "runs": list(runs),
            "paragraph": paragraph,
            "top_level_paragraph": top_level_paragraph,
            "container_ref": self._container_ref,
            "section_index": self._section_index,
            "segment_index": self._segment_index,
            "is_textbox": self._is_textbox,
            "table_path": self._table_path,
        }
        elements.append(info)
        texts.append(full_text)
        segments.append(
            DocxWalkSegment(
                segment_index=self._segment_index,
                text=full_text,
                container_ref=self._container_ref,
                section_index=self._section_index,
                is_textbox=self._is_textbox,
                table_path=self._table_path,
                element_info=info,
            )
        )
        self._segment_index += 1

    def _process_element_children(
        self,
        element,
        parent_paragraph: Paragraph,
        elements: list[dict[str, Any]],
        texts: list[str],
        segments: list[DocxWalkSegment],
        state: dict[str, Any],
        top_level_para: Paragraph,
    ) -> None:
        def flush_segment() -> None:
            current_runs = state["current_runs"]
            if not current_runs:
                return
            full_text = "".join(r.text for r in current_runs)
            if full_text.strip():
                self._append_segment(
                    elements,
                    texts,
                    segments,
                    runs=list(current_runs),
                    paragraph=parent_paragraph,
                    top_level_paragraph=top_level_para,
                    full_text=full_text,
                )
            state["current_runs"].clear()

        for child in element:
            if child.tag in self.IGNORED_TAGS:
                continue
            if child.tag in self.RECURSIVE_CONTAINER_TAGS:
                flush_segment()
                self._process_element_children(
                    child,
                    parent_paragraph,
                    elements,
                    texts,
                    segments,
                    state,
                    top_level_para,
                )
                flush_segment()
                continue

            field_char_element = child.find(qn("w:fldChar")) if isinstance(child, CT_R) else None
            if field_char_element is not None:
                fld_type = field_char_element.get(qn("w:fldCharType"))
                if fld_type in {"begin", "end"}:
                    flush_segment()
                continue

            if isinstance(child, CT_R):
                run = Run(child, parent_paragraph)
                text_boxes = list(run.element.iter(qn("w:txbxContent")))
                if text_boxes:
                    flush_segment()
                    saved = (self._container_ref, self._is_textbox, self._table_path)
                    self._is_textbox = True
                    for txbx_content in text_boxes:
                        container = (
                            parent_paragraph._parent
                            if parent_paragraph._parent is not None
                            else parent_paragraph
                        )
                        self._container_ref = f"{saved[0]}/textbox"
                        self._process_body_elements(
                            txbx_content,
                            container,
                            elements,
                            texts,
                            segments,
                            top_level_para=top_level_para,
                        )
                    self._container_ref, self._is_textbox, self._table_path = saved
                    continue

                if (
                    is_image_run(run)
                    or is_formatting_only_run(run)
                    or is_tab_run(run)
                    or is_instr_text_run(run)
                ):
                    flush_segment()
                    continue

                state["current_runs"].append(run)
                continue

            flush_segment()

    def _process_paragraph(
        self,
        para: Paragraph,
        elements: list[dict[str, Any]],
        texts: list[str],
        segments: list[DocxWalkSegment],
        top_level_para: Paragraph | None = None,
    ) -> None:
        if top_level_para is None:
            top_level_para = para
        state = {"current_runs": []}
        self._process_element_children(
            para._p, para, elements, texts, segments, state, top_level_para
        )
        current_runs = state["current_runs"]
        if current_runs:
            full_text = "".join(r.text for r in current_runs)
            if full_text.strip():
                self._append_segment(
                    elements,
                    texts,
                    segments,
                    runs=list(current_runs),
                    paragraph=para,
                    top_level_paragraph=top_level_para,
                    full_text=full_text,
                )
            current_runs.clear()

    def _walk_document_body(
        self,
        doc: DocumentObject,
        elements: list[dict[str, Any]],
        texts: list[str],
        segments: list[DocxWalkSegment],
    ) -> None:
        self._section_index = 1
        self._container_ref = f"section:{self._section_index}/body"
        self._is_textbox = False
        self._table_path = None
        body = doc.element.body
        self._process_body_elements(
            body, doc, elements, texts, segments, track_sections=True
        )

    def _process_body_elements(
        self,
        parent_element,
        container,
        elements: list[dict[str, Any]],
        texts: list[str],
        segments: list[DocxWalkSegment],
        *,
        top_level_para: Paragraph | None = None,
        table_index: int | None = None,
        track_sections: bool = False,
    ) -> None:
        tbl_idx = -1
        for child_element in parent_element:
            if child_element.tag.endswith("sectPr"):
                continue
            if child_element.tag.endswith("p"):
                self._process_paragraph(
                    Paragraph(child_element, container),
                    elements,
                    texts,
                    segments,
                    top_level_para=top_level_para,
                )
                if track_sections and _paragraph_closes_section(child_element):
                    self._section_index += 1
                    self._container_ref = f"section:{self._section_index}/body"
            elif child_element.tag.endswith("tbl"):
                tbl_idx += 1
                current_tbl = tbl_idx if table_index is None else table_index
                table = Table(child_element, container)
                for row_idx, row in enumerate(table.rows):
                    for col_idx, cell in enumerate(row.cells):
                        saved_path = self._table_path
                        self._table_path = (current_tbl, row_idx, col_idx)
                        self._traverse_container(cell, elements, texts, segments)
                        self._table_path = saved_path
            elif child_element.tag.endswith("sdt"):
                sdt_content = child_element.find(qn("w:sdtContent"))
                if sdt_content is not None:
                    self._process_body_elements(
                        sdt_content,
                        container,
                        elements,
                        texts,
                        segments,
                        top_level_para=top_level_para,
                        table_index=table_index,
                    )

    def _traverse_container(
        self,
        container: Any,
        elements: list[dict[str, Any]],
        texts: list[str],
        segments: list[DocxWalkSegment],
    ) -> None:
        if container is None:
            return

        parent_element = None
        if isinstance(container, (DocumentObject, Part)):
            parent_element = (
                container.element.body if hasattr(container.element, "body") else container.element
            )
        elif isinstance(container, (_Cell, _Header, _Footer)):
            parent_element = container._element
        else:
            return

        if parent_element is not None and parent_element.tag in [
            qn("w:footnotes"),
            qn("w:endnotes"),
        ]:
            for note_element in parent_element:
                self._process_body_elements(note_element, container, elements, texts, segments)
        elif parent_element is not None:
            self._process_body_elements(parent_element, container, elements, texts, segments)


def walk_docx(content: bytes) -> tuple[DocumentObject, list[DocxWalkSegment], list[dict[str, Any]], list[str]]:
    return DocxWalker().walk(content)
