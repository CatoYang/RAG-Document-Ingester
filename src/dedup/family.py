"""MinHash-based near-duplicate/family clustering (TODO.md Path 2: Semantic
Deduplication + Document Family & Version Clustering).

Pure functions, no I/O - `find_document_families.py` (repo root) wires this
up against actual pipeline output. Corpus-scale here is dozens of documents,
so pairwise comparison of MinHash signatures (`cluster_families`) is used
instead of LSH banding - banding only pays for itself once pairwise
comparison stops being cheap, which isn't the case at this scale.
"""
import re
from collections import defaultdict
from typing import Dict, List, Set, Tuple

import mmh3

_WORD_RE = re.compile(r"\w+")


def shingle(text: str, k: int = 5) -> Set[str]:
    """Lowercased word k-shingles. A document shorter than k words becomes a
    single shingle of everything it has, rather than an empty set."""
    words = _WORD_RE.findall(text.lower())
    if not words:
        return set()
    if len(words) < k:
        return {" ".join(words)}
    return {" ".join(words[i:i + k]) for i in range(len(words) - k + 1)}


def minhash_signature(shingles: Set[str], num_perm: int = 64, seed: int = 0) -> Tuple[int, ...]:
    """Approximates the shingle set with `num_perm` hash-minimums (one
    MurmurHash3 seed per position) so `estimate_jaccard` can compare two
    documents without keeping their full shingle sets around."""
    if not shingles:
        return tuple(0 for _ in range(num_perm))
    return tuple(
        min(mmh3.hash(s, seed=seed + i, signed=False) for s in shingles)
        for i in range(num_perm)
    )


def estimate_jaccard(sig_a: Tuple[int, ...], sig_b: Tuple[int, ...]) -> float:
    """Fraction of matching MinHash positions - an unbiased estimator of the
    Jaccard similarity of the two original shingle sets."""
    if not sig_a or not sig_b or len(sig_a) != len(sig_b):
        return 0.0
    matches = sum(1 for a, b in zip(sig_a, sig_b) if a == b)
    return matches / len(sig_a)


class _UnionFind:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def cluster_families(fingerprints: Dict[str, Tuple[int, ...]], threshold: float) -> List[List[str]]:
    """Groups names whose estimated Jaccard similarity is >= threshold,
    transitively (A~B and B~C puts A, B, C in one family even if A~C alone
    wouldn't clear the threshold). Every name ends up in exactly one group,
    including singletons for names with no match."""
    names = list(fingerprints.keys())
    uf = _UnionFind(names)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            a, b = names[i], names[j]
            if estimate_jaccard(fingerprints[a], fingerprints[b]) >= threshold:
                uf.union(a, b)

    groups: Dict[str, List[str]] = defaultdict(list)
    for name in names:
        groups[uf.find(name)].append(name)
    return [sorted(members) for members in groups.values()]


def pick_canonical(members: List[str], content_lengths: Dict[str, int]) -> str:
    """Default canonical-version heuristic: longest extracted content wins,
    as a proxy for "most complete version". Ties break on filename so the
    choice is deterministic."""
    return max(members, key=lambda m: (content_lengths.get(m, 0), m))
