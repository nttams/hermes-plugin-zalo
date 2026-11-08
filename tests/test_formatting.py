"""Markdown preparation for parse_mode="markdown" and chunk splitting."""

from __future__ import annotations

import re

import pytest

from zalo.adapter import MAX_MESSAGE_LENGTH, ZaloAdapter

prepare = ZaloAdapter._prepare_for_zalo
split = ZaloAdapter._split_chunks


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("**đậm** và *nghiêng*", "**đậm** và *nghiêng*"),
        ("[Zalo](https://zalo.me)", "Zalo (https://zalo.me)"),
        ("![chart](https://x.io/a.png)", "https://x.io/a.png"),
        ("| a | b |\n|---|---|\n| 1 | 2 |", "a — b\n\n1 — 2"),
        ("- [ ] việc một\n- [x] việc hai", "- việc một\n- việc hai"),
        ("##### Rất sâu", "**Rất sâu**"),
        ("trước\n\n---\n\nsau", "trước\n\n———\n\nsau"),
        ("$$x^2$$", "x^2"),
        ("<details><summary>Ẩn</summary>Nội dung</details>", "Ẩn\nNội dung"),
        ("`code **** raw`", "`code **** raw`"),
    ],
)
def test_prepare_for_zalo(raw, expected):
    assert prepare(raw) == expected


def test_no_raw_marker_runs_survive():
    out = prepare("****lỗi**** ~~~~ +++++ ######## |||| ")
    assert not re.search(r"\*{3,}|~{2,}|\+{3,}|#{5,}|\|{3,}", out)


def test_short_text_is_one_chunk():
    assert split("xin chào") == ["xin chào"]


def test_chunks_respect_the_limit_and_keep_bold_balanced():
    text = "\n\n".join(f"**Mục {i}** " + "nội dung " * 60 for i in range(20))
    chunks = split(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= MAX_MESSAGE_LENGTH
        assert chunk.count("**") % 2 == 0


def test_one_huge_line_is_cut_at_spaces():
    chunks = split(("từ " * 1500).strip())
    assert all(len(c) <= MAX_MESSAGE_LENGTH for c in chunks)
    assert all(not c.startswith(" ") and not c.endswith(" ") for c in chunks)
