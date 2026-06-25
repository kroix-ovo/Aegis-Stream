"""Transport capture decoding for software replay.

The hardware architecture leaves Ethernet, MoldUDP64, and SoupBinTCP handling
ahead of the ITCH canonicalizer. This module provides a deterministic software
equivalent for captured payloads and regression tests. It intentionally does
not implement live sockets, QDMA, XRT, or board-specific drivers.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import struct
from typing import Iterable, Iterator, Literal


class TransportProtocol(str, Enum):
    RAW = "raw"
    MOLDUDP64 = "moldudp64"
    SOUPBINTCP = "soupbintcp"
    PCAP = "pcap"


class TransportError(ValueError):
    """Raised when a capture cannot be decoded under the requested protocol."""


@dataclass(frozen=True, slots=True)
class TransportPacket:
    protocol: TransportProtocol
    packet_index: int
    payload: bytes
    sequence: int | None = None
    message_count: int = 1
    session: str = ""
    timestamp_ns: int = 0
    errors: tuple[str, ...] = ()

    def to_jsonable(self) -> dict[str, object]:
        data = asdict(self)
        data["protocol"] = self.protocol.value
        data["payload_bytes"] = len(self.payload)
        data.pop("payload")
        return data


@dataclass(slots=True)
class TransportCounters:
    packets: int = 0
    payloads: int = 0
    payload_bytes: int = 0
    sequenced_payloads: int = 0
    gaps: int = 0
    gap_messages: int = 0
    duplicates: int = 0
    malformed_packets: int = 0
    malformed_messages: int = 0
    control_frames: int = 0
    pcap_records: int = 0
    pcap_udp_payloads: int = 0
    errors: list[str] = field(default_factory=list)

    def add_packet(self, packet: TransportPacket) -> None:
        self.payloads += 1
        self.payload_bytes += len(packet.payload)
        if packet.sequence is not None:
            self.sequenced_payloads += 1
        if packet.errors:
            self.malformed_packets += 1
            self.errors.extend(packet.errors)

    def to_jsonable(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TransportReplay:
    packets: tuple[TransportPacket, ...]
    counters: TransportCounters

    @property
    def payload(self) -> bytes:
        return b"".join(packet.payload for packet in self.packets)

    def to_jsonable(self) -> dict[str, object]:
        return {
            "packet_count": len(self.packets),
            "payload_bytes": len(self.payload),
            "counters": self.counters.to_jsonable(),
            "packets": [packet.to_jsonable() for packet in self.packets],
        }


PacketFraming = Literal["auto", "none", "u16", "u32"]


def decode_transport(
    data: bytes,
    *,
    protocol: str | TransportProtocol = TransportProtocol.RAW,
    packet_framing: PacketFraming = "auto",
    pcap_inner: str | TransportProtocol = TransportProtocol.MOLDUDP64,
    soup_initial_sequence: int = 1,
) -> TransportReplay:
    selected = TransportProtocol(protocol)
    if selected == TransportProtocol.RAW:
        return decode_raw_payload(data)
    if selected == TransportProtocol.MOLDUDP64:
        return decode_moldudp64_capture(data, packet_framing=packet_framing)
    if selected == TransportProtocol.SOUPBINTCP:
        return decode_soupbintcp_capture(data, initial_sequence=soup_initial_sequence)
    if selected == TransportProtocol.PCAP:
        return decode_pcap_capture(data, inner=pcap_inner)
    raise TransportError(f"unsupported transport protocol {protocol!r}")


def decode_raw_payload(data: bytes) -> TransportReplay:
    counters = TransportCounters(packets=1 if data else 0)
    packets = (TransportPacket(TransportProtocol.RAW, 0, data),) if data else ()
    for packet in packets:
        counters.add_packet(packet)
    return TransportReplay(packets, counters)


def decode_moldudp64_capture(data: bytes, *, packet_framing: PacketFraming = "auto") -> TransportReplay:
    counters = TransportCounters()
    packets: list[TransportPacket] = []
    expected_sequence: int | None = None
    for packet_index, datagram in enumerate(_split_capture_datagrams(data, framing=packet_framing)):
        counters.packets += 1
        decoded, next_sequence = _decode_moldudp64_datagram(
            datagram,
            packet_index=packet_index,
            expected_sequence=expected_sequence,
        )
        if decoded and decoded[0].sequence is not None and expected_sequence is not None:
            observed = decoded[0].sequence
            if observed > expected_sequence:
                counters.gaps += 1
                counters.gap_messages += observed - expected_sequence
            elif observed < expected_sequence:
                counters.duplicates += expected_sequence - observed
        expected_sequence = next_sequence if next_sequence is not None else expected_sequence
        for packet in decoded:
            counters.add_packet(packet)
            packets.append(packet)
            if packet.errors:
                counters.malformed_messages += 1
    return TransportReplay(tuple(packets), counters)


def _decode_moldudp64_datagram(
    datagram: bytes,
    *,
    packet_index: int,
    expected_sequence: int | None,
) -> tuple[list[TransportPacket], int | None]:
    if len(datagram) < 20:
        packet = TransportPacket(
            TransportProtocol.MOLDUDP64,
            packet_index,
            b"",
            errors=(f"moldudp64 header truncated: need 20, have {len(datagram)}",),
        )
        return [packet], expected_sequence

    session = datagram[:10].decode("ascii", errors="replace").rstrip()
    sequence = struct.unpack_from("!Q", datagram, 10)[0]
    message_count = struct.unpack_from("!H", datagram, 18)[0]
    offset = 20
    packets: list[TransportPacket] = []

    for message_index in range(message_count):
        if offset + 2 > len(datagram):
            packets.append(
                TransportPacket(
                    TransportProtocol.MOLDUDP64,
                    packet_index,
                    b"",
                    sequence=sequence + message_index,
                    message_count=message_count,
                    session=session,
                    errors=("moldudp64 message length truncated",),
                )
            )
            return packets, sequence + message_index
        message_length = struct.unpack_from("!H", datagram, offset)[0]
        offset += 2
        end = offset + message_length
        if end > len(datagram):
            packets.append(
                TransportPacket(
                    TransportProtocol.MOLDUDP64,
                    packet_index,
                    datagram[offset:],
                    sequence=sequence + message_index,
                    message_count=message_count,
                    session=session,
                    errors=(
                        f"moldudp64 message truncated: need {message_length}, have {len(datagram) - offset}",
                    ),
                )
            )
            return packets, sequence + message_index
        packets.append(
            TransportPacket(
                TransportProtocol.MOLDUDP64,
                packet_index,
                datagram[offset:end],
                sequence=sequence + message_index,
                message_count=message_count,
                session=session,
            )
        )
        offset = end

    if offset != len(datagram) and packets:
        last = packets[-1]
        packets[-1] = TransportPacket(
            last.protocol,
            last.packet_index,
            last.payload,
            sequence=last.sequence,
            message_count=last.message_count,
            session=last.session,
            timestamp_ns=last.timestamp_ns,
            errors=last.errors + (f"moldudp64 trailing bytes: {len(datagram) - offset}",),
        )
    next_sequence = sequence + message_count if message_count else expected_sequence
    return packets, next_sequence


def decode_soupbintcp_capture(data: bytes, *, initial_sequence: int = 1) -> TransportReplay:
    counters = TransportCounters()
    packets: list[TransportPacket] = []
    offset = 0
    sequence = initial_sequence
    packet_index = 0

    while offset < len(data):
        if offset + 2 > len(data):
            counters.malformed_packets += 1
            counters.errors.append(f"soupbintcp frame length truncated at byte {offset}")
            break
        frame_length = struct.unpack_from("!H", data, offset)[0]
        offset += 2
        if frame_length == 0:
            counters.malformed_packets += 1
            counters.errors.append(f"soupbintcp zero-length frame at byte {offset - 2}")
            continue
        end = offset + frame_length
        if end > len(data):
            counters.malformed_packets += 1
            counters.errors.append(
                f"soupbintcp frame truncated at byte {offset - 2}: need {frame_length}, have {len(data) - offset}"
            )
            break
        packet_type = chr(data[offset])
        payload = data[offset + 1 : end]
        if packet_type == "S":
            packet = TransportPacket(
                TransportProtocol.SOUPBINTCP,
                packet_index,
                payload,
                sequence=sequence,
                session="SOUP",
            )
            counters.packets += 1
            counters.add_packet(packet)
            packets.append(packet)
            packet_index += 1
            sequence += 1
        else:
            counters.control_frames += 1
        offset = end

    return TransportReplay(tuple(packets), counters)


def decode_pcap_capture(
    data: bytes,
    *,
    inner: str | TransportProtocol = TransportProtocol.MOLDUDP64,
) -> TransportReplay:
    inner_protocol = TransportProtocol(inner)
    counters = TransportCounters()
    packets: list[TransportPacket] = []
    expected_sequence: int | None = None
    for record_index, udp_payload in enumerate(iter_pcap_udp_payloads(data)):
        counters.pcap_records += 1
        counters.pcap_udp_payloads += 1
        if inner_protocol == TransportProtocol.RAW:
            packet = TransportPacket(TransportProtocol.PCAP, record_index, udp_payload)
            counters.packets += 1
            counters.add_packet(packet)
            packets.append(packet)
        elif inner_protocol == TransportProtocol.MOLDUDP64:
            counters.packets += 1
            decoded, next_sequence = _decode_moldudp64_datagram(
                udp_payload,
                packet_index=record_index,
                expected_sequence=expected_sequence,
            )
            if decoded and decoded[0].sequence is not None and expected_sequence is not None:
                observed = decoded[0].sequence
                if observed > expected_sequence:
                    counters.gaps += 1
                    counters.gap_messages += observed - expected_sequence
                elif observed < expected_sequence:
                    counters.duplicates += expected_sequence - observed
            expected_sequence = next_sequence if next_sequence is not None else expected_sequence
            for packet in decoded:
                counters.add_packet(packet)
                packets.append(packet)
        else:
            raise TransportError("pcap inner protocol must be raw or moldudp64")
    return TransportReplay(tuple(packets), counters)


def _split_capture_datagrams(data: bytes, *, framing: PacketFraming) -> Iterator[bytes]:
    if not data:
        return
    if framing == "none":
        yield data
        return
    if framing == "u16":
        yield from _split_length_prefixed(data, width=2)
        return
    if framing == "u32":
        yield from _split_length_prefixed(data, width=4)
        return
    if framing != "auto":
        raise TransportError(f"unsupported packet framing {framing!r}")

    for width in (2, 4):
        try:
            parts = list(_split_length_prefixed(data, width=width))
        except TransportError:
            continue
        if parts:
            yield from parts
            return
    yield data


def _split_length_prefixed(data: bytes, *, width: int) -> Iterator[bytes]:
    offset = 0
    parts: list[bytes] = []
    unpack = "!H" if width == 2 else "!I"
    while offset < len(data):
        if offset + width > len(data):
            raise TransportError("length-prefixed capture has truncated packet length")
        packet_length = struct.unpack_from(unpack, data, offset)[0]
        offset += width
        if packet_length == 0:
            raise TransportError("length-prefixed capture has zero-length packet")
        end = offset + packet_length
        if end > len(data):
            raise TransportError("length-prefixed capture has truncated packet data")
        parts.append(data[offset:end])
        offset = end
    yield from parts


def iter_pcap_udp_payloads(data: bytes) -> Iterator[bytes]:
    if len(data) < 24:
        raise TransportError("pcap global header truncated")
    endian = _pcap_endian(data[:4])
    offset = 24
    record_header = struct.Struct(endian + "IIII")
    while offset < len(data):
        if offset + record_header.size > len(data):
            raise TransportError("pcap packet header truncated")
        _ts_sec, _ts_frac, incl_len, _orig_len = record_header.unpack_from(data, offset)
        offset += record_header.size
        end = offset + incl_len
        if end > len(data):
            raise TransportError("pcap packet data truncated")
        payload = _extract_udp_payload(data[offset:end])
        if payload is not None:
            yield payload
        offset = end


def _pcap_endian(magic: bytes) -> str:
    if magic in {b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"}:
        return "<"
    if magic in {b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"}:
        return ">"
    raise TransportError("unsupported capture format; expected classic pcap")


def _extract_udp_payload(packet: bytes) -> bytes | None:
    if len(packet) < 14:
        return None
    eth_type = struct.unpack_from("!H", packet, 12)[0]
    ip_offset = 14
    if eth_type == 0x8100 and len(packet) >= 18:
        eth_type = struct.unpack_from("!H", packet, 16)[0]
        ip_offset = 18
    if eth_type != 0x0800 or len(packet) < ip_offset + 20:
        return None
    version_ihl = packet[ip_offset]
    if version_ihl >> 4 != 4:
        return None
    ihl = (version_ihl & 0x0F) * 4
    if ihl < 20 or len(packet) < ip_offset + ihl:
        return None
    protocol = packet[ip_offset + 9]
    if protocol != 17:
        return None
    total_length = struct.unpack_from("!H", packet, ip_offset + 2)[0]
    udp_offset = ip_offset + ihl
    if total_length < ihl + 8 or len(packet) < udp_offset + 8:
        return None
    udp_length = struct.unpack_from("!H", packet, udp_offset + 4)[0]
    if udp_length < 8:
        return None
    payload_start = udp_offset + 8
    payload_end = min(payload_start + udp_length - 8, ip_offset + total_length, len(packet))
    if payload_end < payload_start:
        return None
    return packet[payload_start:payload_end]


def encode_moldudp64_packet(
    messages: Iterable[bytes],
    *,
    sequence: int = 1,
    session: str = "AEGIS",
) -> bytes:
    encoded_messages = list(messages)
    session_bytes = session.encode("ascii", errors="strict")[:10].ljust(10, b" ")
    packet = bytearray(session_bytes)
    packet.extend(struct.pack("!QH", sequence, len(encoded_messages)))
    for message in encoded_messages:
        if len(message) > 0xFFFF:
            raise ValueError("MoldUDP64 message payload exceeds 65535 bytes")
        packet.extend(struct.pack("!H", len(message)))
        packet.extend(message)
    return bytes(packet)


def encode_soupbintcp_frame(payload: bytes, *, packet_type: str = "S") -> bytes:
    if len(packet_type) != 1:
        raise ValueError("SoupBinTCP packet type must be one byte")
    frame = packet_type.encode("ascii") + payload
    if len(frame) > 0xFFFF:
        raise ValueError("SoupBinTCP frame exceeds 65535 bytes")
    return struct.pack("!H", len(frame)) + frame


def encode_length_prefixed_datagrams(datagrams: Iterable[bytes], *, width: int = 2) -> bytes:
    pack = "!H" if width == 2 else "!I" if width == 4 else ""
    if not pack:
        raise ValueError("length prefix width must be 2 or 4")
    encoded = bytearray()
    for datagram in datagrams:
        encoded.extend(struct.pack(pack, len(datagram)))
        encoded.extend(datagram)
    return bytes(encoded)
