from src.extract.factory import DocumentRouter
from src.config.settings import FileRule


class _CountingExtractor:
    instances_created = 0

    def __init__(self, **kwargs):
        _CountingExtractor.instances_created += 1
        self.params = kwargs

    def extract(self, file_path, **kwargs):
        return None


def test_router_reuses_extractor_instance_across_files(mock_config, monkeypatch):
    """A prior bug meant DocumentRouter constructed a brand new extractor
    (and, for PdfExtractor, reloaded all of Marker's models) for every
    single file. Same extractor + same params should now be cached and
    reused within one router's lifetime."""
    _CountingExtractor.instances_created = 0
    monkeypatch.setattr("src.extract.factory.get_extractor_class", lambda name: _CountingExtractor)

    mock_config.file_rules[".pdf"] = FileRule(extractor="_CountingExtractor", params={"device": "cuda"})
    router = DocumentRouter(mock_config)

    a = router.get_extractor("book_one.pdf")
    b = router.get_extractor("book_two.pdf")

    assert a is b
    assert _CountingExtractor.instances_created == 1


def test_router_caches_extractors_with_nested_dict_params(mock_config, monkeypatch):
    """AutoPdfExtractor's `ocr_params` is itself a dict, which broke the
    original tuple(sorted(params.items()))-based cache key (unhashable)."""
    _CountingExtractor.instances_created = 0
    monkeypatch.setattr("src.extract.factory.get_extractor_class", lambda name: _CountingExtractor)

    mock_config.file_rules[".pdf"] = FileRule(
        extractor="_CountingExtractor",
        params={"ocr_extractor": "PdfExtractor", "ocr_params": {"device": "cuda", "batch_size": 2}},
    )
    router = DocumentRouter(mock_config)

    a = router.get_extractor("book_one.pdf")
    b = router.get_extractor("book_two.pdf")

    assert a is b
    assert _CountingExtractor.instances_created == 1


def test_router_creates_distinct_instances_for_distinct_params(mock_config, monkeypatch):
    _CountingExtractor.instances_created = 0
    monkeypatch.setattr("src.extract.factory.get_extractor_class", lambda name: _CountingExtractor)

    mock_config.file_rules[".pdf"] = FileRule(extractor="_CountingExtractor", params={"device": "cuda"})
    mock_config.file_rules[".txt"] = FileRule(extractor="_CountingExtractor", params={"device": "cpu"})
    router = DocumentRouter(mock_config)

    a = router.get_extractor("book.pdf")
    b = router.get_extractor("notes.txt")

    assert a is not b
    assert _CountingExtractor.instances_created == 2
