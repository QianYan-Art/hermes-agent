"""MEDIA 标签路径边界回归测试。"""

from gateway.platforms.base import MEDIA_TAG_CLEANUP_RE


def test_full_width_suffixes_terminate_media_path():
    cases = [
        "MEDIA:D:/workspace/out/report.pdf（782.6 KB）",
        "MEDIA:D:/workspace/out/report.pdf：内容",
        "MEDIA:D:/workspace/out/report.pdf。",
        "MEDIA:D:/workspace/out/report.pdf，下一条",
        "MEDIA:D:/workspace/out/report.pdf！",
        "MEDIA:D:/workspace/out/report.pdf？",
        "MEDIA:D:/workspace/out/report.pdf、",
        "MEDIA:D:/workspace/out/report.pdf”",
        "MEDIA:D:/workspace/out/report.pdf’",
    ]

    for text in cases:
        match = MEDIA_TAG_CLEANUP_RE.search(text)
        assert match is not None, text
        assert match.group("path").endswith(".pdf"), (text, match.group("path"))


def test_real_chinese_delivery_line_extracts_file_only():
    text = (
        "## 交付物\n\n- **PDF 早报**："
        "MEDIA:D:/workspace/zaobao/output/早报_2026-08-16.pdf（782.6 KB）"
    )

    match = MEDIA_TAG_CLEANUP_RE.search(text)

    assert match is not None
    assert match.group("path") == "D:/workspace/zaobao/output/早报_2026-08-16.pdf"


def test_adjacent_media_tags_remain_separate():
    text = "MEDIA:/tmp/first.pngMEDIA:/tmp/second.pdf"

    matches = list(MEDIA_TAG_CLEANUP_RE.finditer(text))

    assert [match.group("path") for match in matches] == [
        "/tmp/first.png",
        "/tmp/second.pdf",
    ]
