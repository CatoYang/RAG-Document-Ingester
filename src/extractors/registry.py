from typing import Type
from src.core.interfaces import BaseExtractor

from src.extractors.pdf import PdfTextExtractor, PdfVLMExtractor, HybridPdfExtractor, FreeTierMegaBatchExtractor, EnterpriseBatchExtractor
from src.extractors.universal import MarkItDownExtractor
from src.extractors.openoffice import OpenOfficeExtractor
from src.extractors.image import ImageVLMExtractor
from src.extractors.epub import EpubExtractor
from src.extractors.spreadsheet import SpreadsheetExtractor
from src.extractors.docx import DocxExtractor
from src.extractors.html import HtmlExtractor
from src.extractors.presentation import PresentationExtractor
from src.extractors.archive import ArchiveUnpacker

EXTRACTOR_REGISTRY = {
    "PdfTextExtractor": PdfTextExtractor,
    "PdfVLMExtractor": PdfVLMExtractor,
    "HybridPdfExtractor": HybridPdfExtractor,
    "FreeTierMegaBatchExtractor": FreeTierMegaBatchExtractor,
    "EnterpriseBatchExtractor": EnterpriseBatchExtractor,
    "MarkItDownExtractor": MarkItDownExtractor,
    "OpenOfficeExtractor": OpenOfficeExtractor,
    "ImageVLMExtractor": ImageVLMExtractor,
    "EpubExtractor": EpubExtractor,
    "SpreadsheetExtractor": SpreadsheetExtractor,
    "DocxExtractor": DocxExtractor,
    "HtmlExtractor": HtmlExtractor,
    "PresentationExtractor": PresentationExtractor,
    "ArchiveUnpacker": ArchiveUnpacker,
}


def register_extractor(name: str, cls: Type[BaseExtractor]):
    EXTRACTOR_REGISTRY[name] = cls


def get_extractor_class(name: str) -> Type[BaseExtractor]:
    if name not in EXTRACTOR_REGISTRY:
        raise ValueError(f"Extractor '{name}' not found in registry.")
    return EXTRACTOR_REGISTRY[name]
