from src.dedup.family import cluster_families, estimate_jaccard, minhash_signature, pick_canonical, shingle

TEXT_A = (
    "The quick brown fox jumps over the lazy dog near the riverbank at dawn "
    "every single morning without fail."
)
TEXT_A_VARIANT = TEXT_A + " Additional errata paragraph appended at the very end of this edition."
TEXT_B = (
    "Warforged are constructs built for the Last War, animated by a mix of "
    "arcane magic and living wood."
)


def test_shingle_short_text_falls_back_to_one_shingle():
    assert shingle("hello world", k=5) == {"hello world"}


def test_shingle_empty_text_is_empty():
    assert shingle("   ", k=5) == set()


def test_estimate_jaccard_identical_signature_is_one():
    sig = minhash_signature(shingle(TEXT_A), num_perm=32)
    assert estimate_jaccard(sig, sig) == 1.0


def test_near_duplicate_text_scores_higher_than_unrelated_text():
    sig_a = minhash_signature(shingle(TEXT_A), num_perm=64)
    sig_a_variant = minhash_signature(shingle(TEXT_A_VARIANT), num_perm=64)
    sig_b = minhash_signature(shingle(TEXT_B), num_perm=64)

    near_dup_score = estimate_jaccard(sig_a, sig_a_variant)
    unrelated_score = estimate_jaccard(sig_a, sig_b)

    assert near_dup_score >= 0.4
    assert unrelated_score < near_dup_score


def test_cluster_families_groups_near_duplicates_transitively():
    fingerprints = {
        "a.md": minhash_signature(shingle(TEXT_A), num_perm=64),
        "a_variant.md": minhash_signature(shingle(TEXT_A_VARIANT), num_perm=64),
        "b.md": minhash_signature(shingle(TEXT_B), num_perm=64),
    }

    families = cluster_families(fingerprints, threshold=0.5)

    families_by_size = sorted(families, key=len)
    assert families_by_size[0] == ["b.md"]
    assert families_by_size[1] == ["a.md", "a_variant.md"]


def test_cluster_families_all_singletons_below_threshold():
    fingerprints = {
        "a.md": minhash_signature(shingle(TEXT_A), num_perm=64),
        "b.md": minhash_signature(shingle(TEXT_B), num_perm=64),
    }

    families = cluster_families(fingerprints, threshold=0.95)

    assert sorted(families) == [["a.md"], ["b.md"]]


def test_pick_canonical_prefers_longest_content():
    lengths = {"a.md": 100, "a_variant.md": 250}
    assert pick_canonical(["a.md", "a_variant.md"], lengths) == "a_variant.md"


def test_pick_canonical_breaks_ties_on_filename():
    lengths = {"a.md": 100, "b.md": 100}
    assert pick_canonical(["b.md", "a.md"], lengths) == "b.md"
