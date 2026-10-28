from __future__ import annotations

import importlib.util
import os
import sys
import stat
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw


OPS_DIR = Path(__file__).parents[2] / "ops" / "douyin-login"
SPEC = importlib.util.spec_from_file_location(
    "douyin_cover_template", OPS_DIR / "cover_template.py"
)
assert SPEC is not None and SPEC.loader is not None
cover_template = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cover_template
SPEC.loader.exec_module(cover_template)


def _system_font() -> Path:
    candidates = (
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    return next((path for path in candidates if path.is_file()), Path())


@pytest.fixture
def system_font_path() -> Path:
    path = _system_font()
    if not path.is_file():
        pytest.skip("当前系统没有可用的本机测试字体")
    return path


def _make_root(tmp_path: Path) -> tuple[Path, dict[str, bytes]]:
    root = tmp_path / "runtime"
    templates = root / "templates"
    templates.mkdir(parents=True)
    originals: dict[str, bytes] = {}
    for ratio, size in (("3x4", (1086, 1448)), ("4x3", (1448, 1086))):
        image = Image.new("RGB", size, (235, 225, 207))
        draw = ImageDraw.Draw(image)
        if ratio == "3x4":
            draw.line((82, 0, 82, size[1]), fill=(42, 183, 194), width=4)
        path = templates / f"template_{ratio}.png"
        image.save(path, format="PNG", compress_level=9)
        originals[ratio] = path.read_bytes()
    return root, originals


def _drawn_bounds(template_path: Path, rendered_path: Path) -> tuple[int, int, int, int] | None:
    with Image.open(template_path) as original, Image.open(rendered_path) as rendered:
        diff = ImageChops.difference(original.convert("RGBA"), rendered.convert("RGBA"))
        return diff.getbbox()


def _image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def _generate(
    root: Path,
    font_path: Path,
    *,
    release_id: str = "ep01",
    episode_label: str = "第一栞",
    subtitle: str = "它很亮，但里面有声音吗",
) -> tuple[Path, Path]:
    return cover_template.generate_cover_pair(
        root, release_id, episode_label, subtitle, font_path
    )


def test_generates_deterministic_portrait_and_landscape_pair_without_changing_templates(
    tmp_path: Path, system_font_path: Path
) -> None:
    first_root, first_templates = _make_root(tmp_path / "first")
    first_outputs = _generate(first_root, system_font_path)

    assert first_outputs == (
        first_root / "ep01" / "ep01_3x4.png",
        first_root / "ep01" / "ep01_4x3.png",
    )
    assert _image_size(first_outputs[0]) == (1086, 1448)
    assert _image_size(first_outputs[1]) == (1448, 1086)
    assert all(
        _drawn_bounds(first_root / "templates" / f"template_{ratio}.png", output)
        for ratio, output in zip(("3x4", "4x3"), first_outputs)
    )
    assert {
        ratio: (first_root / "templates" / f"template_{ratio}.png").read_bytes()
        for ratio in ("3x4", "4x3")
    } == first_templates

    second_root, second_templates = _make_root(tmp_path / "second")
    second_outputs = _generate(second_root, system_font_path)
    assert [path.read_bytes() for path in first_outputs] == [
        path.read_bytes() for path in second_outputs
    ]
    assert {
        ratio: (second_root / "templates" / f"template_{ratio}.png").read_bytes()
        for ratio in ("3x4", "4x3")
    } == second_templates


@pytest.mark.parametrize(
    "release_id",
    ("../escape", r"..\escape", "/absolute", r"C:\outside", "..", "a/b", "Ayan", "x" * 65),
)
def test_rejects_unsafe_release_ids_without_creating_outputs(
    tmp_path: Path, system_font_path: Path, release_id: str
) -> None:
    root, _ = _make_root(tmp_path)
    with pytest.raises(cover_template.CoverTemplateError):
        _generate(root, system_font_path, release_id=release_id)
    assert not (tmp_path / "escape").exists()
    assert not (root / "ep01").exists()


@pytest.mark.parametrize(
    ("episode_label", "subtitle"),
    (("第一\n栞", "副标题"), ("第一栞", "副\t标题"), ("第一栞\x00", "副标题"), ("第一栞", "副 标题")),
)
def test_rejects_multiline_or_control_characters(
    tmp_path: Path,
    system_font_path: Path,
    episode_label: str,
    subtitle: str,
) -> None:
    root, _ = _make_root(tmp_path)
    with pytest.raises(cover_template.CoverTemplateError, match="单行|控制"):
        _generate(
            root,
            system_font_path,
            episode_label=episode_label,
            subtitle=subtitle,
        )
    assert not (root / "ep01").exists()


def test_long_text_shrinks_to_safe_area_and_extreme_text_leaves_no_files(
    tmp_path: Path, system_font_path: Path
) -> None:
    root, _ = _make_root(tmp_path)
    portrait, landscape = _generate(
        root,
        system_font_path,
        subtitle="星际声谱关系与下一格" * 2,
    )
    bounds = _drawn_bounds(root / "templates" / "template_4x3.png", landscape)
    assert bounds is not None
    crop_left = (1448 - 1086 * 3 / 4) / 2
    crop_right = 1448 - crop_left
    margin = round(1086 * 0.035)
    assert bounds[0] >= 392
    assert bounds[2] <= crop_right - margin
    assert _image_size(portrait) == (1086, 1448)

    extreme_root, _ = _make_root(tmp_path / "extreme")
    with pytest.raises(cover_template.CoverTemplateError, match="过长"):
        _generate(extreme_root, system_font_path, subtitle="星" * 100)
    assert not (extreme_root / "ep01").exists()


def test_refuses_existing_output_and_preserves_templates_and_existing_bytes(
    tmp_path: Path, system_font_path: Path
) -> None:
    root, originals = _make_root(tmp_path)
    release_dir = root / "ep01"
    release_dir.mkdir()
    existing = release_dir / "ep01_3x4.png"
    sentinel = b"existing cover"
    existing.write_bytes(sentinel)

    with pytest.raises(cover_template.CoverTemplateError, match="拒绝覆盖"):
        _generate(root, system_font_path)

    assert existing.read_bytes() == sentinel
    assert not (release_dir / "ep01_4x3.png").exists()
    assert {
        ratio: (root / "templates" / f"template_{ratio}.png").read_bytes()
        for ratio in ("3x4", "4x3")
    } == originals


@pytest.mark.parametrize("link_target", ("templates", "release"))
def test_rejects_symlink_escape(
    tmp_path: Path, system_font_path: Path, link_target: str
) -> None:
    root, _ = _make_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    if link_target == "templates":
        for child in (root / "templates").iterdir():
            child.unlink()
        (root / "templates").rmdir()
        link = root / "templates"
        target = outside
        is_directory = True
    else:
        link = root / "ep01"
        target = outside
        is_directory = True
    try:
        link.symlink_to(target, target_is_directory=is_directory)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"系统未允许创建测试软链接：{exc}")

    with pytest.raises(cover_template.CoverTemplateError, match="软链接|路径"):
        _generate(root, system_font_path)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("relative", (Path("templates"), Path("ep01")))
def test_rejects_linked_path_components_even_when_os_symlinks_are_unavailable(
    tmp_path: Path,
    system_font_path: Path,
    relative: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _make_root(tmp_path)
    linked_path = root / relative
    real_lstat = Path.lstat

    class FakeLinkStat:
        st_mode = stat.S_IFLNK | 0o777
        st_file_attributes = 0

    def lstat_with_link(path: Path) -> os.stat_result | FakeLinkStat:
        if path == linked_path:
            return FakeLinkStat()
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_link)
    with pytest.raises(cover_template.CoverTemplateError, match="软链接"):
        _generate(root, system_font_path)

    assert not (root / "ep01" / "ep01_3x4.png").exists()
    assert not (root / "ep01" / "ep01_4x3.png").exists()


def test_second_output_write_failure_rolls_back_first_and_cleans_staging(
    tmp_path: Path, system_font_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _make_root(tmp_path)
    real_link = cover_template.os.link
    link_count = 0

    def fail_second_link(source: str | Path, destination: str | Path) -> None:
        nonlocal link_count
        link_count += 1
        if link_count == 2:
            raise OSError("simulated write failure")
        real_link(source, destination)

    monkeypatch.setattr(cover_template.os, "link", fail_second_link)
    with pytest.raises(cover_template.CoverTemplateError, match="写入封面失败"):
        _generate(root, system_font_path)

    assert not (root / "ep01").exists()


def test_cli_accepts_fixed_arguments_and_prints_only_output_paths(
    tmp_path: Path, system_font_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, _ = _make_root(tmp_path)
    result = cover_template.main(
        [
            "--root",
            str(root),
            "--release-id",
            "ep01",
            "--episode-label",
            "第一栞",
            "--subtitle",
            "它很亮，但里面有声音吗",
            "--font",
            str(system_font_path),
        ]
    )
    output = capsys.readouterr()
    assert result == 0
    assert output.err == ""
    assert str(root / "ep01" / "ep01_3x4.png") in output.out
    assert "1086x1448" in output.out
    assert str(root / "ep01" / "ep01_4x3.png") in output.out
    assert "1448x1086" in output.out


def test_cli_does_not_accept_arbitrary_output_paths(
    tmp_path: Path, system_font_path: Path
) -> None:
    root, _ = _make_root(tmp_path)
    with pytest.raises(SystemExit) as error:
        cover_template.main(
            [
                "--root",
                str(root),
                "--release-id",
                "ep01",
                "--episode-label",
                "第一栞",
                "--subtitle",
                "副标题",
                "--font",
                str(system_font_path),
                "--output",
                str(tmp_path / "outside.png"),
            ]
        )
    assert error.value.code == 2
    assert not (tmp_path / "outside.png").exists()
    assert not (root / "ep01").exists()


def test_rejects_wrong_template_dimensions_without_creating_release_directory(
    tmp_path: Path, system_font_path: Path
) -> None:
    root, _ = _make_root(tmp_path)
    wrong = Image.new("RGB", (1080, 1440), (235, 225, 207))
    wrong.save(root / "templates" / "template_3x4.png", format="PNG")

    with pytest.raises(cover_template.CoverTemplateError, match="必须是 1086x1448 PNG"):
        _generate(root, system_font_path)
    assert not (root / "ep01").exists()
