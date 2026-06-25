import unittest

from aegis_stream.book import BookError, MultiSymbolOrderBook, OrderBookShard, compare_snapshot_depth
from aegis_stream.itch import (
    encode_add,
    encode_cancel,
    encode_delete,
    encode_execute,
    encode_replace,
    parse_messages,
)


class BookTests(unittest.TestCase):
    def test_order_lifecycle_and_top_of_book(self) -> None:
        book = OrderBookShard(top_k=4)
        payload = b"".join(
            [
                encode_add(order_ref=10, side="B", shares=100, stock="AEGIS", price=100_0000, timestamp_ns=1),
                encode_add(order_ref=11, side="S", shares=80, stock="AEGIS", price=100_0200, timestamp_ns=2),
                encode_cancel(order_ref=10, shares=20, timestamp_ns=3),
                encode_execute(order_ref=11, shares=30, match_number=200, timestamp_ns=4),
                encode_replace(old_order_ref=10, new_order_ref=12, shares=120, price=100_0100, timestamp_ns=5),
            ]
        )

        snapshots = [book.apply_event(event) for event in parse_messages(payload)]
        last = snapshots[-1]
        self.assertEqual(last.best_bid.price, 100_0100)
        self.assertEqual(last.best_bid.shares, 120)
        self.assertEqual(last.best_ask.price, 100_0200)
        self.assertEqual(last.best_ask.shares, 50)
        self.assertIn(12, book.orders)
        self.assertNotIn(10, book.orders)

    def test_delete_removes_depth(self) -> None:
        book = OrderBookShard()
        events = parse_messages(
            encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=10, timestamp_ns=1)
            + encode_delete(order_ref=1, timestamp_ns=2)
        )
        for event in events:
            snapshot = book.apply_event(event)
        self.assertIsNone(snapshot.best_bid)
        self.assertNotIn(1, book.orders)

    def test_over_cancel_is_rejected(self) -> None:
        book = OrderBookShard()
        events = parse_messages(
            encode_add(order_ref=1, side="B", shares=10, stock="AEGIS", price=10, timestamp_ns=1)
            + encode_cancel(order_ref=1, shares=11, timestamp_ns=2)
        )
        book.apply_event(events[0])
        with self.assertRaises(BookError):
            book.apply_event(events[1])

    def test_non_strict_mode_records_issue(self) -> None:
        book = OrderBookShard(strict=False)
        event = parse_messages(encode_cancel(order_ref=404, shares=1, timestamp_ns=1))[0]
        snapshot = book.apply_event(event)
        self.assertEqual(snapshot.event_count, 1)
        self.assertEqual(len(book.issues), 1)
        self.assertIn("missing order", book.issues[0].message)

    def test_multi_symbol_order_index_routes_updates(self) -> None:
        book = MultiSymbolOrderBook(top_k=2)
        events = parse_messages(
            encode_add(order_ref=1, side="B", shares=100, stock="AAA", price=100, timestamp_ns=1)
            + encode_add(order_ref=2, side="S", shares=50, stock="BBB", price=200, timestamp_ns=2)
            + encode_cancel(order_ref=1, shares=25, timestamp_ns=3)
            + encode_delete(order_ref=2, timestamp_ns=4)
        )
        for event in events:
            book.apply_event(event)

        aaa = book.snapshot("AAA")
        bbb = book.snapshot("BBB")
        self.assertEqual(aaa.best_bid.shares, 75)
        self.assertIsNone(bbb.best_ask)
        self.assertIn(1, book.order_to_symbol)
        self.assertNotIn(2, book.order_to_symbol)

    def test_top_k_mismatch_reporting(self) -> None:
        expected = OrderBookShard(symbol="AEGIS", top_k=2)
        actual = OrderBookShard(symbol="AEGIS", top_k=2)
        event = parse_messages(encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=100, timestamp_ns=1))[0]
        expected_snapshot = expected.apply_event(event)
        actual_snapshot = actual.snapshot()
        mismatches = compare_snapshot_depth(expected_snapshot, actual_snapshot, event_index=7)
        self.assertEqual(len(mismatches), 1)
        self.assertEqual(mismatches[0].event_index, 7)


if __name__ == "__main__":
    unittest.main()
