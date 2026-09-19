"""Tests for find_document_families.py (TODO.md Path 2: Semantic
Deduplication + Document Family & Version Clustering). Exercises the report/
apply logic directly against temp-dir markdown fixtures - no real corpus, no
config loading through find_document_families.run() needed for most cases
since that's a thin wrapper around load_config()+load_documents(), both of
which are already covered elsewhere (settings tests, IndexingPipeline
tests)."""
import yaml

import find_document_families as fdf


TEXT_A = (
    "The quick brown fox jumps over the lazy dog near the riverbank at dawn "
    "every single morning without fail."
)
TEXT_A_VARIANT = TEXT_A + " Additional errata paragraph appended at the very end of this edition."
TEXT_B = (
    "Warforged are constructs built for the Last War, animated by a mix of "
    "arcane magic and living wood."
)


def _cluster(documents, threshold=0.5):
    fingerprints = fdf.build_fingerprints(documents, shingle_size=5, num_perm=64)
    return fdf.cluster_families(fingerprints, threshold)


def test_report_families_returns_only_multi_member_groups(capsys):
    documents = {"a.md": TEXT_A, "a_variant.md": TEXT_A_VARIANT, "b.md": TEXT_B}
    families = _cluster(documents)

    multi = fdf.report_families(families, documents)

    assert multi == [["a.md", "a_variant.md"]]


def test_apply_supersession_moves_non_canonical_members(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "a.md").write_text(TEXT_A)
    (output_dir / "a_variant.md").write_text(TEXT_A_VARIANT)
    documents = {"a.md": TEXT_A, "a_variant.md": TEXT_A_VARIANT}

    fdf.apply_supersession([["a.md", "a_variant.md"]], documents, output_dir)

    # a_variant.md has more content, so it's the canonical pick and stays.
    assert (output_dir / "a_variant.md").exists()
    assert not (output_dir / "a.md").exists()
    assert (output_dir.parent / "superseded" / "a.md").exists()
    assert (output_dir.parent / "superseded" / "a.md").read_text() == TEXT_A


def test_apply_temporal_tags_frontmatter_without_moving_files(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    (output_dir / "a.md").write_text(
        "---\npipeline_phases:\n  - extract\n---\n\n" + TEXT_A
    )
    (output_dir / "a_variant.md").write_text(TEXT_A_VARIANT)
    documents = {"a.md": TEXT_A, "a_variant.md": TEXT_A_VARIANT}

    fdf.apply_temporal([["a.md", "a_variant.md"]], documents, output_dir)

    # Both files stay in place.
    assert (output_dir / "a.md").exists()
    assert (output_dir / "a_variant.md").exists()

    raw_a = (output_dir / "a.md").read_text()
    parts = raw_a.split("---", 2)
    meta_a = yaml.safe_load(parts[1])
    assert meta_a["pipeline_phases"] == ["extract"]  # existing frontmatter preserved
    assert meta_a["family_role"] == "variant"
    assert TEXT_A in parts[2]

    raw_variant = (output_dir / "a_variant.md").read_text()
    meta_variant = yaml.safe_load(raw_variant.split("---", 2)[1])
    assert meta_variant["family_role"] == "canonical"
    assert meta_variant["family_id"] == meta_a["family_id"]
