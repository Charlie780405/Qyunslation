# SPDX-FileCopyrightText: 2025 QinHan
# SPDX-License-Identifier: MPL-2.0
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Self

from qyunslation.exporter.base import ExporterConfig
from qyunslation.exporter.pptx.pptx2html_exporter import PPTX2HTMLExporterConfig, PPTX2HTMLExporter
from qyunslation.exporter.pptx.pptx2pptx_exporter import PPTX2PPTXExporter
from qyunslation.glossary.glossary import Glossary
from qyunslation.ir.document import Document
from qyunslation.structure import ManifestStore, PptxStructureScanner
from qyunslation.structure.execution_evidence import write_output_evidence
from qyunslation.structure.models import ExecutionStatus, ObjectType, ProcessingMode
from qyunslation.structure.scan_pptx import pack_image_pptx, render_pptx_slides
from qyunslation.translator.ai_translator.pptx_translator import PPTXTranslatorConfig, PPTXTranslator
from qyunslation.workflow.base import WorkflowConfig, Workflow
from qyunslation.workflow.interfaces import HTMLExportable, PPTXExportable


@dataclass(kw_only=True)
class PPTXWorkflowConfig(WorkflowConfig):
    translator_config: PPTXTranslatorConfig
    html_exporter_config: PPTX2HTMLExporterConfig
    processing_mode: ProcessingMode = ProcessingMode.NATIVE
    slide_renderer: Callable[[bytes], list[bytes]] | None = None


class PPTXWorkflow(Workflow[PPTXWorkflowConfig, Document, Document], HTMLExportable[PPTX2HTMLExporterConfig],
                   PPTXExportable[ExporterConfig]):
    def __init__(self, config: PPTXWorkflowConfig):
        super().__init__(config=config)
        self._translator: PPTXTranslator | None = None  # 保存translator引用
        if config.logger:
            for sub_config in [self.config.translator_config]:
                if sub_config:
                    sub_config.logger = config.logger

    def _pre_translate(self, document_original: Document):
        suffix = document_original.suffix.lower() if document_original.suffix else ""
        document = document_original.copy()
        if suffix == ".ppt":
            from qyunslation.structure.ingest import prepare_document

            prepared = prepare_document(f"{document.stem or 'deck'}.ppt", document.content)
            document = Document.from_bytes(
                prepared.content,
                suffix=".pptx",
                stem=document.stem or "deck",
            )
        elif suffix != ".pptx":
            raise ValueError(f"该工作流不支持{suffix}格式，请转为.pptx格式")
        translate_config = self.config.translator_config
        translator = PPTXTranslator(translate_config)
        return document, translator

    def _structure_manifest(self, document: Document):
        store = ManifestStore()
        import hashlib

        digest = hashlib.sha256(document.content).hexdigest()
        cached = store.get(digest)
        if cached is not None:
            return cached
        try:
            manifest = PptxStructureScanner(
                slide_renderer=self.config.slide_renderer,
            ).scan(
                document.content,
                source_name=f"{document.stem or 'deck'}.pptx",
                processing_mode=self.config.processing_mode,
            )
        except Exception as exc:
            if self.config.logger:
                self.config.logger.warning("PPTX structure scan failed, legacy path: %s", exc)
            return None
        store.put(manifest)
        return manifest

    def _translate_rendered(self, document: Document, structure_manifest) -> Document:
        from qyunslation.extensions.image_translate import translate_image_bytes

        pages = render_pptx_slides(document.content, renderer=self.config.slide_renderer)
        translated_pages = []
        to_lang = getattr(self.config.translator_config, "to_lang", None) or "简体中文"
        skip = bool(getattr(self.config.translator_config, "skip_translate", False))
        for page in pages:
            if skip:
                translated_pages.append(page)
                continue
            data, _n, _qc = translate_image_bytes(page, suffix=".png", to_lang=to_lang)
            translated_pages.append(data or page)

        first_canvas = structure_manifest.canvases[0] if structure_manifest and structure_manifest.canvases else None
        packed = pack_image_pptx(
            translated_pages,
            width_pt=first_canvas.width if first_canvas else 720.0,
            height_pt=first_canvas.height if first_canvas else 405.0,
        )
        if structure_manifest is not None:
            images = [obj for obj in structure_manifest.objects if obj.type is ObjectType.IMAGE]
            for obj in images:
                write_output_evidence(
                    obj,
                    status=ExecutionStatus.EXPLICITLY_SKIPPED if skip else ExecutionStatus.TRANSLATED,
                    reason_code="SKIP_TRANSLATE" if skip else None,
                    checks={"rendered": True},
                )
            ManifestStore().put_execution(structure_manifest.refresh_summary())
        return Document.from_bytes(packed, suffix=".pptx", stem=f"{document.stem or 'deck'}.zh")

    def translate(self) -> Self:
        # 准备阶段
        self.progress_tracker.update(percent=10, message="正在准备翻译...")
        document, translator = self._pre_translate(self.document_original)
        self._translator = translator  # 保存translator引用
        structure_manifest = self._structure_manifest(document)

        if self.config.processing_mode is ProcessingMode.RENDERED:
            self.document_translated = self._translate_rendered(document, structure_manifest)
            self.progress_tracker.update(percent=100, message="翻译完成")
            return self

        # 翻译阶段
        translator.translate(document, structure_manifest=structure_manifest)

        # 保存术语表阶段
        if translator.glossary.glossary_dict:
            self.progress_tracker.update(percent=95, message="正在保存术语表...")
            self.attachment.add_document("glossary", Glossary.glossary_dict2csv(translator.glossary.glossary_dict))

        self.progress_tracker.update(percent=100, message="翻译完成")
        self.document_translated = document
        return self

    async def translate_async(self) -> Self:
        # 准备阶段
        self.progress_tracker.update(percent=10, message="正在准备翻译...")
        document, translator = self._pre_translate(self.document_original)
        self._translator = translator  # 保存translator引用
        structure_manifest = self._structure_manifest(document)

        if self.config.processing_mode is ProcessingMode.RENDERED:
            self.document_translated = self._translate_rendered(document, structure_manifest)
            self.progress_tracker.update(percent=100, message="翻译完成")
            return self

        # 翻译阶段 - 由 agent 更新细粒度进度
        await translator.translate_async(document, structure_manifest=structure_manifest)

        # 保存术语表阶段
        if translator.glossary.glossary_dict:
            self.progress_tracker.update(percent=95, message="正在保存术语表...")
            self.attachment.add_document("glossary", Glossary.glossary_dict2csv(translator.glossary.glossary_dict))

        self.progress_tracker.update(percent=100, message="翻译完成")
        self.document_translated = document
        return self

    def get_statistics(self) -> dict:
        """
        获取翻译任务的统计信息。

        Returns:
            dict: 包含glossary、translation和total三个部分的统计信息
        """
        if self._translator:
            return self._translator.get_statistics()
        return {}

    def export_to_html(self, config: PPTX2HTMLExporterConfig = None) -> str:
        config = config or self.config.html_exporter_config
        docu = self._export(PPTX2HTMLExporter(config))
        return docu.content.decode()

    def export_to_pptx(self, _: ExporterConfig | None = None) -> bytes:
        docu = self._export(PPTX2PPTXExporter())
        return docu.content

    def save_as_html(self, name: str = None, output_dir: Path | str = "./output",
                     config: PPTX2HTMLExporterConfig | None = None) -> Self:
        config = config or self.config.html_exporter_config
        self._save(exporter=PPTX2HTMLExporter(config), name=name, output_dir=output_dir)
        return self

    def save_as_pptx(self, name: str = None, output_dir: Path | str = "./output",
                     _: ExporterConfig | None = None) -> Self:
        self._save(exporter=PPTX2PPTXExporter(), name=name, output_dir=output_dir)
        return self
