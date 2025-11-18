"""Very small sanity tests for core helpers.

This is not a full test suite but exercises the most critical utilities.
"""

from __future__ import annotations

from teltail.length_utils import tg_len, tg_slice_head, tg_slice_tail, tg_truncate_middle
from teltail.tail_buffer import TailBuffer


def test_length_utils() -> None:
    assert tg_len("") == 0
    assert tg_len("a") == 1
    # Simple BMP char vs emoji (likely surrogate pair)
    heart = "❤"
    rocket = "🚀"
    assert tg_len(heart) >= 1
    assert tg_len(rocket) >= 1

    text = "hello world"
    assert tg_slice_head(text, 5) == "hello"
    assert tg_slice_tail(text, 5) == "world"

    long = "abcdefghijklmnopqrstuvwxyz"
    truncated = tg_truncate_middle(long, 10)
    assert tg_len(truncated) <= 10


def test_tail_buffer() -> None:
    buf = TailBuffer(max_bytes=10)
    buf.append("hello")
    buf.append("world")
    s = buf.get_full_text()
    assert "world" in s


if __name__ == "__main__":
    test_length_utils()
    test_tail_buffer()
    print("tests passed")
