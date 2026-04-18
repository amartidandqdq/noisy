# Tests pour blocklist_fuzzy: stem indexing + variant matching

from noisy_lib.blocklist_fuzzy import (
    build_stem_index,
    host_matches_stem,
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
