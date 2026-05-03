# Tests pour quic_probe: format binaire RFC 9000 du paquet Initial

from noisy_lib.quic_probe import (
    QUIC_CAPABLE_HOSTS,
    QUIC_VERSION,
    _build_quic_initial,
)


def test_quic_initial_min_size_anti_amplification():
    """RFC 9000 section 14.1 : Initial >= 1200 bytes (anti-amplification)."""
    pkt = _build_quic_initial(b"\x00" * 8, b"\x11" * 8)
    assert len(pkt) >= 1200


def test_quic_initial_header_byte():
    """Header byte: 0xC0 = long header (1) + fixed (1) + Initial type (00)."""
    pkt = _build_quic_initial(b"\x00" * 8, b"\x11" * 8)
    assert pkt[0] == 0xC0


def test_quic_initial_version_field():
    """Bytes 1-4 = version QUIC v1 = 0x00000001."""
    pkt = _build_quic_initial(b"\x00" * 8, b"\x11" * 8)
    assert pkt[1:5] == QUIC_VERSION
    assert QUIC_VERSION == b"\x00\x00\x00\x01"


def test_quic_initial_dcid_scid_layout():
    """Apres version: DCID len + DCID + SCID len + SCID."""
    dcid = b"\xaa" * 8
    scid = b"\xbb" * 12
    pkt = _build_quic_initial(dcid, scid)
    # offset 5: DCID length
    assert pkt[5] == 8
    # offset 6..14: DCID
    assert pkt[6:14] == dcid
    # offset 14: SCID length
    assert pkt[14] == 12
    # offset 15..27: SCID
    assert pkt[15:27] == scid


def test_quic_initial_token_length_zero():
    """Client Initial sans token: token length = 0 (varint, 1 byte)."""
    dcid = b"\x00" * 8
    scid = b"\x11" * 8
    pkt = _build_quic_initial(dcid, scid)
    # Apres DCID/SCID layout: position 5 + 1 + 8 + 1 + 8 = 23
    token_len_pos = 1 + 4 + 1 + len(dcid) + 1 + len(scid)
    assert pkt[token_len_pos] == 0


def test_quic_initial_distinct_random_per_call():
    """Payload random -> 2 paquets ne doivent pas etre identiques."""
    a = _build_quic_initial(b"\x00" * 8, b"\x11" * 8)
    b = _build_quic_initial(b"\x00" * 8, b"\x11" * 8)
    assert a != b


def test_quic_initial_different_cid_lengths():
    """DCID/SCID de tailles differentes acceptees."""
    pkt = _build_quic_initial(b"\xaa" * 4, b"\xbb" * 16)
    assert pkt[5] == 4
    assert pkt[5 + 1 + 4] == 16
    assert len(pkt) >= 1200


def test_quic_capable_hosts_sane():
    """Sanity: liste non vide, pas de schemas/ports parasites."""
    assert len(QUIC_CAPABLE_HOSTS) >= 5
    for host in QUIC_CAPABLE_HOSTS:
        assert "://" not in host
        assert ":" not in host  # pas de port
        assert "/" not in host
