import unittest

from aegis_stream.book import BookError, OrderBookShard
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


if __name__ == "__main__":
    unittest.main()
