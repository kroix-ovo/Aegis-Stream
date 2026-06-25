import unittest

from aegis_stream.itch import (
    EventType,
    ItchParseError,
    encode_add,
    encode_cancel,
    encode_delete,
    encode_execute,
    encode_replace,
    encode_trade,
    parse_messages,
)


class ItchParserTests(unittest.TestCase):
    def test_parse_supported_messages(self) -> None:
        payload = b"".join(
            [
                encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=100_0000, timestamp_ns=10),
                encode_execute(order_ref=1, shares=25, match_number=99, timestamp_ns=11),
                encode_cancel(order_ref=1, shares=10, timestamp_ns=12),
                encode_replace(old_order_ref=1, new_order_ref=2, shares=90, price=100_0100, timestamp_ns=13),
                encode_trade(
                    order_ref=3,
                    side="S",
                    shares=5,
                    stock="AEGIS",
                    price=100_0200,
                    match_number=100,
                    timestamp_ns=14,
                ),
                encode_delete(order_ref=2, timestamp_ns=15),
            ]
        )

        events = parse_messages(payload)
        self.assertEqual([event.event_type for event in events], [
            EventType.ADD,
            EventType.EXECUTE,
            EventType.CANCEL,
            EventType.REPLACE,
            EventType.TRADE,
            EventType.DELETE,
        ])
        self.assertEqual(events[0].symbol, "AEGIS")
        self.assertEqual(events[0].side, "B")
        self.assertEqual(events[3].old_order_ref, 1)
        self.assertEqual(events[3].new_order_ref, 2)
        self.assertEqual(events[4].match_number, 100)

    def test_canonical_word_layout(self) -> None:
        event = parse_messages(
            encode_add(order_ref=0x1234, side="B", shares=100, stock="AEGIS", price=200, timestamp_ns=300)
        )[0]
        word = event.to_word256()
        self.assertEqual((word >> 248) & 0xFF, 1)
        self.assertEqual((word >> 168) & 0xFFFFFFFFFFFFFFFF, 0x1234)
        self.assertEqual((word >> 136) & 0xFFFFFFFF, 200)
        self.assertEqual((word >> 104) & 0xFFFFFFFF, 100)
        self.assertEqual((word >> 96) & 0xFF, 1)
        self.assertEqual((word >> 32) & 0xFFFFFFFFFFFFFFFF, 300)

    def test_rejects_truncated_payload(self) -> None:
        with self.assertRaises(ItchParseError):
            parse_messages(b"A\x00")


if __name__ == "__main__":
    unittest.main()
