import struct
import unittest

from aegis_stream.itch import encode_add, parse_messages
from aegis_stream.transport import (
    decode_moldudp64_capture,
    decode_pcap_capture,
    decode_soupbintcp_capture,
    encode_length_prefixed_datagrams,
    encode_moldudp64_packet,
    encode_soupbintcp_frame,
)


class TransportTests(unittest.TestCase):
    def test_moldudp64_sequence_and_gap_detection(self) -> None:
        msg1 = encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=100, timestamp_ns=1)
        msg2 = encode_add(order_ref=2, side="S", shares=100, stock="AEGIS", price=101, timestamp_ns=2)
        first = encode_moldudp64_packet([msg1], sequence=10)
        second = encode_moldudp64_packet([msg2], sequence=12)

        replay = decode_moldudp64_capture(encode_length_prefixed_datagrams([first, second]), packet_framing="u16")
        self.assertEqual([packet.sequence for packet in replay.packets], [10, 12])
        self.assertEqual(replay.counters.gaps, 1)
        self.assertEqual(replay.counters.gap_messages, 1)
        self.assertEqual(len(parse_messages(replay.payload)), 2)

    def test_moldudp64_malformed_message_is_counted(self) -> None:
        datagram = b"AEGIS     " + struct.pack("!QH", 1, 1) + struct.pack("!H", 36) + b"A\x00"
        replay = decode_moldudp64_capture(datagram, packet_framing="none")
        self.assertEqual(replay.counters.malformed_packets, 1)
        self.assertTrue(replay.packets[0].errors)

    def test_soupbintcp_sequenced_frames(self) -> None:
        msg = encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=100, timestamp_ns=1)
        stream = encode_soupbintcp_frame(b"", packet_type="H") + encode_soupbintcp_frame(msg)
        replay = decode_soupbintcp_capture(stream, initial_sequence=50)
        self.assertEqual(replay.counters.control_frames, 1)
        self.assertEqual(replay.packets[0].sequence, 50)
        self.assertEqual(parse_messages(replay.payload)[0].order_ref, 1)

    def test_classic_pcap_udp_payload_extraction(self) -> None:
        msg = encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=100, timestamp_ns=1)
        mold = encode_moldudp64_packet([msg], sequence=1)
        pcap = _pcap_with_udp_payload(mold)
        replay = decode_pcap_capture(pcap, inner="moldudp64")
        self.assertEqual(len(replay.packets), 1)
        self.assertEqual(parse_messages(replay.payload)[0].order_ref, 1)


def _pcap_with_udp_payload(payload: bytes) -> bytes:
    ethernet = b"\x00" * 12 + struct.pack("!H", 0x0800)
    udp_length = 8 + len(payload)
    total_length = 20 + udp_length
    ipv4 = bytearray(20)
    ipv4[0] = 0x45
    struct.pack_into("!H", ipv4, 2, total_length)
    ipv4[8] = 64
    ipv4[9] = 17
    ipv4[12:16] = b"\x0a\x00\x00\x01"
    ipv4[16:20] = b"\x0a\x00\x00\x02"
    udp = struct.pack("!HHHH", 10000, 10001, udp_length, 0)
    packet = ethernet + bytes(ipv4) + udp + payload
    global_header = b"\xd4\xc3\xb2\xa1" + struct.pack("<HHIIII", 2, 4, 0, 0, 65535, 1)
    record_header = struct.pack("<IIII", 1, 0, len(packet), len(packet))
    return global_header + record_header + packet


if __name__ == "__main__":
    unittest.main()
