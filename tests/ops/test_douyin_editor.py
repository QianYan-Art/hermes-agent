"""抖音编辑器控件的边界与失败关闭测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import re

import pytest


EDITOR_PATH = Path(__file__).parents[2] / "ops" / "douyin-login" / "editor.py"
SPEC = importlib.util.spec_from_file_location("douyin_editor", EDITOR_PATH)
assert SPEC is not None and SPEC.loader is not None
editor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(editor)


def test_validate_settings_defaults_to_public_and_immediate():
    assert editor.validate_settings() == {
        "visibility": "public",
        "publish_at": None,
        "display_time": None,
    }


@pytest.mark.parametrize("visibility", ["public", "friends", "private"])
def test_validate_settings_accepts_each_visibility(visibility):
    assert editor.validate_settings(visibility)["visibility"] == visibility


def test_validate_settings_normalizes_utc_and_shanghai_display():
    now = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
    result = editor.validate_settings(
        "friends", "2026-10-23T10:00:00+08:00", now=now
    )
    assert result == {
        "visibility": "friends",
        "publish_at": "2026-10-23T02:00:00+00:00",
        "display_time": "2026-10-23 10:00",
    }


def test_validate_settings_accepts_inclusive_two_hour_and_fourteen_day_edges():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    earliest = (now + timedelta(hours=2)).isoformat()
    latest = (now + timedelta(days=14)).isoformat()
    assert editor.validate_settings(publish_at=earliest, now=now)["publish_at"] == earliest
    assert editor.validate_settings(publish_at=latest, now=now)["publish_at"] == latest


@pytest.mark.parametrize(
    "visibility,publish_at",
    [
        ("everyone", None),
        ("public", "2026-10-24T12:00:00"),
        ("public", "NaN"),
        ("public", "2026-02-30T12:00:00+08:00"),
        ("public", "2026-10-24T12:00:00+99:99"),
        ("public", float("nan")),
    ],
)
def test_validate_settings_rejects_invalid_visibility_and_timestamps(
    visibility, publish_at
):
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        editor.validate_settings(visibility, publish_at, now=now)


def test_validate_settings_rejects_schedule_outside_allowed_window():
    now = datetime(2026, 10, 23, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="至少.*2 小时"):
        editor.validate_settings(
            publish_at=(now + timedelta(hours=1, minutes=59, seconds=59)).isoformat(),
            now=now,
        )
    with pytest.raises(ValueError, match="不能超过.*14 天"):
        editor.validate_settings(
            publish_at=(now + timedelta(days=14, seconds=1)).isoformat(), now=now
        )


def test_validate_settings_requires_aware_injected_now():
    with pytest.raises(ValueError, match="now 必须"):
        editor.validate_settings(
            publish_at="2026-10-24T12:00:00+08:00", now=datetime(2026, 10, 23)
        )


class FakeRadio:
    def __init__(self, selected=False, accepts_click=True, input_type="radio"):
        self.selected = selected
        self.accepts_click = accepts_click
        self.input_type = input_type
        self.clicks = 0

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    async def is_checked(self):
        return self.selected

    async def get_attribute(self, name):
        return self.input_type if name == "type" else None

    async def click(self):
        self.clicks += 1
        if self.accepts_click:
            self.selected = True


class FakeLabel:
    def __init__(self, text, radio):
        self.text = text
        self.radio = radio

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    def locator(self, selector):
        assert selector == 'input[type="radio"], input[type="checkbox"]'
        return self.radio

    async def click(self):
        await self.radio.click()


class FakeLabels:
    def __init__(self, labels):
        self.labels = labels

    def filter(self, *, has_text):
        return FakeLabels([label for label in self.labels if has_text.search(label.text)])

    async def count(self):
        return len(self.labels)

    def nth(self, index):
        return self.labels[index]

    async def is_visible(self):
        return len(self.labels) == 1

    def locator(self, selector):
        return self.labels[0].locator(selector)

    async def click(self):
        await self.labels[0].click()


class FakeField:
    def __init__(self, name, input_type="text"):
        self.name = name
        self.input_type = input_type
        self.value = ""

    async def count(self):
        return 1

    def nth(self, index):
        assert index == 0
        return self

    async def is_visible(self):
        return True

    async def get_attribute(self, name):
        return self.input_type if name == "type" else None

    async def fill(self, value):
        self.value = value

    async def input_value(self):
        return self.value


class FakePage:
    def __init__(
        self,
        *,
        schedule_field=None,
        reject_label=None,
        input_type="radio",
        selected=(),
        duplicate_labels=(),
        extra_labels=("保存权限允许", "保存权限不允许"),
    ):
        labels = ["公开", "好友可见", "仅自己可见", "立即发布", "定时发布"]
        self.radios = {
            text: FakeRadio(
                selected=text in selected,
                accepts_click=text != reject_label,
                input_type=input_type,
            )
            for text in labels
        }
        self.labels = [FakeLabel(text, self.radios[text]) for text in labels]
        self.ignored_radios = {
            text: FakeRadio(input_type=input_type) for text in extra_labels
        }
        self.labels.extend(
            FakeLabel(text, self.ignored_radios[text]) for text in extra_labels
        )
        self.labels.extend(
            FakeLabel(text, FakeRadio(input_type=input_type))
            for text in duplicate_labels
        )
        self.schedule_field = schedule_field

    def locator(self, selector):
        assert selector == "label:visible"
        return FakeLabels(self.labels)

    def get_by_role(self, role, *, name):
        assert role == "textbox"
        if self.schedule_field is not None and name.search(self.schedule_field.name):
            return FakeFieldCollection([self.schedule_field])
        return FakeFieldCollection([])

    def get_by_placeholder(self, name):
        return FakeFieldCollection([])


class FakeFieldCollection(FakeLabels):
    pass


@pytest.mark.asyncio
async def test_apply_settings_clicks_and_reads_back_exact_visible_radios():
    page = FakePage()
    settings = editor.validate_settings("private")
    result = await editor.apply_settings(page, settings)
    assert result == settings
    assert page.radios["仅自己可见"].selected
    assert page.radios["立即发布"].selected
    assert all(radio.clicks == 0 for radio in page.ignored_radios.values())


@pytest.mark.asyncio
async def test_apply_settings_fails_when_radio_does_not_read_back_selected():
    page = FakePage(reject_label="公开")
    with pytest.raises(ValueError, match="点击后未选中"):
        await editor.apply_settings(page, editor.validate_settings())


@pytest.mark.asyncio
async def test_apply_settings_supports_checked_checkbox_options_without_toggling_them():
    page = FakePage(input_type="checkbox", selected=("公开", "立即发布"))
    settings = editor.validate_settings("public")
    assert await editor.apply_settings(page, settings) == settings
    assert page.radios["公开"].clicks == 0
    assert page.radios["立即发布"].clicks == 0


@pytest.mark.asyncio
async def test_apply_settings_rejects_duplicate_exact_visibility_labels():
    page = FakePage(duplicate_labels=("公开",))
    with pytest.raises(ValueError, match="无法唯一定位"):
        await editor.apply_settings(page, editor.validate_settings("public"))


@pytest.mark.asyncio
async def test_apply_settings_sets_and_verifies_shanghai_schedule():
    publish_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(
        timespec="minutes"
    )
    normalized = editor.validate_settings(publish_at=publish_at)
    field = FakeField("发布时间")
    page = FakePage(schedule_field=field)
    assert await editor.apply_settings(page, normalized) == normalized
    expected = datetime.fromisoformat(normalized["publish_at"]).astimezone(
        editor._SHANGHAI
    )
    assert field.value == expected.replace(tzinfo=None).isoformat(sep=" ", timespec="minutes")


@pytest.mark.asyncio
async def test_apply_settings_fails_closed_when_scheduled_input_is_not_unique():
    publish_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(
        timespec="minutes"
    )
    normalized = editor.validate_settings(publish_at=publish_at)
    page = FakePage()
    with pytest.raises(ValueError, match="无法通过可见的文本框名称或 placeholder"):
        await editor.apply_settings(page, normalized)


@pytest.mark.asyncio
async def test_apply_settings_fails_when_schedule_readback_differs():
    class MismatchingField(FakeField):
        async def fill(self, value):
            self.value = "2026-10-25 00:00"

    publish_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(
        timespec="minutes"
    )
    normalized = editor.validate_settings(publish_at=publish_at)
    page = FakePage(schedule_field=MismatchingField("发布时间"))
    with pytest.raises(ValueError, match="读回值与设置不一致"):
        await editor.apply_settings(page, normalized)


@pytest.mark.asyncio
async def test_verify_settings_is_read_only_and_checks_current_group_state():
    publish_at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(
        timespec="minutes"
    )
    normalized = editor.validate_settings(
        "friends", publish_at=publish_at
    )
    local_time = datetime.fromisoformat(normalized["publish_at"]).astimezone(
        editor._SHANGHAI
    )
    field = FakeField("发布时间")
    field.value = local_time.replace(tzinfo=None).isoformat(
        sep=" ", timespec="minutes"
    )
    page = FakePage(
        schedule_field=field,
        input_type="checkbox",
        selected=("好友可见", "定时发布"),
    )

    assert await editor.verify_settings(page, normalized) == normalized
    assert all(radio.clicks == 0 for radio in page.radios.values())
    assert all(radio.clicks == 0 for radio in page.ignored_radios.values())


@pytest.mark.asyncio
async def test_verify_settings_fails_without_changing_wrong_current_selection():
    settings = editor.validate_settings("private")
    page = FakePage(input_type="checkbox", selected=("公开", "立即发布"))
    with pytest.raises(ValueError, match="当前选项组"):
        await editor.verify_settings(page, settings)
    assert all(radio.clicks == 0 for radio in page.radios.values())


def _jpeg(path: Path) -> Path:
    path.write_bytes(b"fake jpeg")
    return path


@pytest.mark.asyncio
async def test_apply_cover_rejects_missing_orientation_label_before_click(tmp_path):
    asset = {
        "landscape_path": str(_jpeg(tmp_path / "landscape.jpg")),
        "portrait_path": str(_jpeg(tmp_path / "portrait.jpeg")),
        "cover_sha256": "a" * 64,
    }

    class PageWithoutCoverLabels:
        def get_by_text(self, text, *, exact):
            assert exact is True
            return FakeLabels([])

    with pytest.raises(ValueError, match="封面卡片标签"):
        await editor.apply_cover(PageWithoutCoverLabels(), asset)


@pytest.mark.asyncio
async def test_cover_confirmation_fails_closed_without_unique_cover_dialog():
    class PageWithoutDialog:
        def get_by_role(self, role):
            assert role == "dialog"
            return FakeLabels([])

    with pytest.raises(ValueError, match="无法唯一定位可见的封面确认弹窗"):
        await editor._confirm_cover_dialog(PageWithoutDialog())


class FakeImage:
    def __init__(self, source):
        self.source = source

    async def is_visible(self):
        return True

    async def get_attribute(self, name):
        return self.source if name == "src" else None


class FakeImages:
    def __init__(self, source):
        self.image = FakeImage(source)

    async def count(self):
        return 1

    def nth(self, index):
        assert index == 0
        return self.image


class FakeChooseButton:
    async def count(self):
        return 1

    async def is_visible(self):
        return True


class FakeCoverCard:
    def __init__(self, title, source):
        self.title = title
        self.source = source
        self.button = FakeChooseButton()

    def locator(self, selector):
        assert selector == ".." or selector == "img"
        if selector == "img":
            return FakeImages(self.source)
        return self

    async def evaluate(self, script):
        assert "tagName" in script
        return "DIV"

    async def inner_text(self):
        return self.title

    def get_by_role(self, role, *, name, exact):
        assert (role, name, exact) == ("button", "选择封面", True)
        return self.button


class FakeCoverPage:
    def __init__(self, landscape_source, portrait_source):
        self.cards = {
            "横封面4:3": FakeCoverCard("横封面4:3", landscape_source),
            "竖封面3:4": FakeCoverCard("竖封面3:4", portrait_source),
        }

    def get_by_text(self, text, *, exact):
        assert exact is True
        card = self.cards.get(text)
        return FakeLabels([card] if card else [])


@pytest.mark.asyncio
async def test_verify_cover_reads_each_thumbnail_without_reapplying():
    landscape = "https://cdn.test/land.jpg?signature=secret-one"
    portrait = "https://cdn.test/port.jpg?signature=secret-two"
    evidence = {
        "cover_sha256": "a" * 64,
        "covers": [
            {
                "orientation": "landscape",
                "thumbnail": editor._safe_source_summary(landscape),
            },
            {
                "orientation": "portrait",
                "thumbnail": editor._safe_source_summary(portrait),
            },
        ],
        "verified": True,
    }
    page = FakeCoverPage(landscape, portrait)

    result = await editor.verify_cover(page, evidence)
    assert result["verified"] is True
    assert result["covers"] == evidence["covers"]
    assert "secret" not in str(result)


@pytest.mark.asyncio
async def test_verify_cover_rejects_raw_asset_without_ui_evidence():
    asset = {
        "cover_sha256": "a" * 64,
        "landscape_path": "land.jpg",
        "portrait_path": "port.jpg",
    }
    with pytest.raises(ValueError, match="无法证明页面封面"):
        await editor.verify_cover(object(), asset)


@pytest.mark.asyncio
async def test_verify_cover_fails_when_current_thumbnail_differs_from_staged_evidence():
    landscape = "https://cdn.test/land.jpg?signature=expected"
    evidence = {
        "cover_sha256": "a" * 64,
        "covers": [
            {
                "orientation": "landscape",
                "thumbnail": editor._safe_source_summary(landscape),
            },
            {
                "orientation": "portrait",
                "thumbnail": editor._safe_source_summary("https://cdn.test/port.jpg"),
            },
        ],
    }
    page = FakeCoverPage(
        "https://cdn.test/land.jpg?signature=changed", "https://cdn.test/port.jpg"
    )

    with pytest.raises(ValueError, match="缩略图与 staged evidence 不一致"):
        await editor.verify_cover(page, evidence)


class SequenceImageCollection:
    def __init__(self, owner):
        self.owner = owner
        self.sources = None

    async def count(self):
        index = min(self.owner.reads, len(self.owner.source_sets) - 1)
        self.sources = self.owner.source_sets[index]
        self.owner.reads += 1
        return len(self.sources)

    def nth(self, index):
        return FakeImage(self.sources[index])


class SequenceCard:
    def __init__(self, source_sets):
        self.source_sets = source_sets
        self.reads = 0

    def locator(self, selector):
        assert selector == "img"
        return SequenceImageCollection(self)


@pytest.mark.asyncio
async def test_cover_thumbnail_waits_for_one_stable_source_change():
    card = SequenceCard([["old.jpg"], ["new.jpg"], ["new.jpg"]])
    assert await editor._wait_for_unique_thumbnail_change(card, ["old.jpg"]) == "new.jpg"


@pytest.mark.asyncio
async def test_cover_thumbnail_rejects_ambiguous_changes():
    card = SequenceCard([["new-land.jpg", "new-alt.jpg"]])
    with pytest.raises(ValueError, match="唯一且稳定"):
        await editor._wait_for_unique_thumbnail_change(card, ["old-land.jpg"], timeout=0)


def test_cover_source_summary_never_includes_query_or_fragment():
    signed_source = "https://cdn.example.test/covers/item.jpg?token=secret#preview"
    changed_query = "https://cdn.example.test/covers/item.jpg?token=other#preview"
    signed_summary = editor._safe_source_summary(signed_source)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", signed_summary)
    assert "secret" not in signed_summary and "cdn.example.test" not in signed_summary
    assert editor._safe_source_summary(changed_query) != signed_summary
    assert editor._safe_source_summary("data:image/jpeg;base64,private-data").startswith(
        "sha256:"
    )
