# Tests pour blocklist_fuzzy: stem indexing + label/TLD-spray indexing + variant matching

from noisy_lib.blocklist_fuzzy import (
    build_stem_index,
    host_matches_stem,
    build_label_tld_index,
    host_matches_label,
    _build_indexes_cached,
    host_matches_any,
    _stem_of,
)


def test_stem_extraction():
    assert _stem_of("grandpashabet7092") == "grandpashabet"
    assert _stem_of("foo") == "foo"
    assert _stem_of("bar2bar") == "bar2bar"
    assert _stem_of("a1") == "a"
    assert _stem_of("9999") == "9999"  # all digits, no match


def test_stem_index_threshold():
    # Need >=3 variants of same stem+TLD to be indexed
    bl = {"grandpashabet1.com", "grandpashabet2.com", "grandpashabet3.com"}
    idx = build_stem_index(bl)
    assert ("grandpashabet", "com") in idx


def test_stem_index_below_threshold():
    bl = {"foo1.com", "foo2.com"}  # only 2 variants
    idx = build_stem_index(bl)
    assert len(idx) == 0


def test_stem_too_short():
    # "ab" stem too short (< 8 chars)
    bl = {"ab1.com", "ab2.com", "ab3.com"}
    idx = build_stem_index(bl)
    assert len(idx) == 0


def test_variant_caught():
    bl = {f"grandpashabet{i}.com" for i in range(1, 25)}
    idx = build_stem_index(bl)
    assert host_matches_stem("grandpashabet7092.com", idx)
    assert host_matches_stem("www.grandpashabet9999.com", idx)


def test_legitimate_unaffected():
    # Real domain should not be falsely flagged
    bl = {f"grandpashabet{i}.com" for i in range(1, 25)}
    idx = build_stem_index(bl)
    assert not host_matches_stem("google.com", idx)
    assert not host_matches_stem("github.com", idx)


def test_different_tld_not_matched():
    bl = {f"grandpashabet{i}.com" for i in range(1, 25)}
    idx = build_stem_index(bl)
    # Same stem on different TLD shouldn't match
    assert not host_matches_stem("grandpashabet7092.org", idx)


# === Label/TLD spray index (themoviesflix.{com,net,cc,llc} pattern) ===

def test_label_tld_index_threshold():
    bl = {"themoviesflix.com", "themoviesflix.net", "themoviesflix.cc"}
    idx = build_label_tld_index(bl)
    assert "themoviesflix" in idx


def test_label_tld_below_threshold():
    bl = {"themoviesflix.com", "themoviesflix.net"}  # only 2 TLDs
    idx = build_label_tld_index(bl)
    assert len(idx) == 0


def test_label_too_short():
    # 'short' < 10 chars
    bl = {"short.com", "short.net", "short.cc"}
    idx = build_label_tld_index(bl)
    assert len(idx) == 0


def test_label_variant_caught():
    bl = {"themoviesflix.com", "themoviesflix.net", "themoviesflix.cc", "themoviesflix.in"}
    idx = build_label_tld_index(bl)
    # New TLD never seen in blocklist
    assert host_matches_label("themoviesflix.llc", idx)
    assert host_matches_label("themoviesflix.xyz", idx)
    # Subdomain on novel TLD
    assert host_matches_label("www.themoviesflix.app", idx)


def test_label_legitimate_unaffected():
    bl = {"themoviesflix.com", "themoviesflix.net", "themoviesflix.cc"}
    idx = build_label_tld_index(bl)
    assert not host_matches_label("github.com", idx)
    assert not host_matches_label("google.com", idx)


def test_label_index_skips_subdomain_entries():
    # 'cdn.themoviesflix.com' -> label = 'themoviesflix' (last label before TLD)
    bl = {
        "cdn.themoviesflix.com",
        "img.themoviesflix.net",
        "static.themoviesflix.cc",
    }
    idx = build_label_tld_index(bl)
    assert "themoviesflix" in idx


def test_combined_index_both_patterns():
    bl = {
        # Numeric variants
        *(f"grandpashabet{i}.com" for i in range(1, 25)),
        # TLD spray
        "themoviesflix.com", "themoviesflix.net", "themoviesflix.cc",
    }
    idxs = _build_indexes_cached(bl)
    assert host_matches_any("grandpashabet9999.com", idxs)
    assert host_matches_any("themoviesflix.llc", idxs)
    assert not host_matches_any("github.com", idxs)
    # Cache returns same object on second call
    assert _build_indexes_cached(bl) is idxs
