from __future__ import annotations

from teltail.config import DefaultsConfig
from teltail.notifier import HeaderBuilder, LiveMessageBuilder, SummaryBuilder


def _make_defaults() -> DefaultsConfig:
    return DefaultsConfig()


def test_header_builder_basic() -> None:
    defaults = _make_defaults()
    hb = HeaderBuilder(defaults)
    cmd = ["echo", "hello"]
    header = hb.build_header("running", cmd)
    assert "Running" in header
    assert "echo hello" in header


def test_live_message_no_output_uses_total_stats() -> None:
    defaults = _make_defaults()
    lb = LiveMessageBuilder(defaults)
    text = lb.build_live_text("running", ["echo", "hello"], buffer_text="")
    # When there is no output, we still want a Tail line with total stats.
    assert "Tail (" in text
    assert "total 0 line" in text


def test_live_message_truncates_tail() -> None:
    defaults = _make_defaults()
    defaults.tail_length = 10
    lb = LiveMessageBuilder(defaults)
    buf = "".join(str(i) for i in range(100))
    text = lb.build_live_text("running", ["echo", "hello"], buffer_text=buf)
    # We expect that not all of the buffer is present due to tail_length.
    assert "Tail (" in text
    # At least some indication that bytes were skipped.
    assert "skipped" in text or "KB" in text or "bytes" in text


def test_summary_builder_includes_exit_code() -> None:
    defaults = _make_defaults()
    sb = SummaryBuilder(defaults)
    msg = sb.build_summary("success", ["echo", "hello"], exit_code=0, duration_secs=1.23)
    assert "Status:" in msg
    assert "exit code 0" in msg
    assert "1.2" in msg
