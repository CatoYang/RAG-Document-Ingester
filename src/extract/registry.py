from typing import Type
from src.core.interfaces import BaseExtractor

from src.extract.pdf import PdfExtractor
from src.extract.universal import MarkItDownExtractor
from src.extract.openoffice import OpenOfficeExtractor
from src.extract.image import ImageExtractor
from src.extract.epub import EpubExtractor
from src.extract.spreadsheet import SpreadsheetExtractor
from src.extract.docx import DocxExtractor
from src.extract.html import HtmlExtractor
from src.extract.presentation import PresentationExtractor
from src.extract.archive import ArchiveUnpacker

EXTRACTOR_REGISTRY = {
    "PdfExtractor": PdfExtractor,
    "MarkItDownExtractor": MarkItDownExtractor,
    "OpenOfficeExtractor": OpenOfficeExtractor,
    "ImageExtractor": ImageExtractor,
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
