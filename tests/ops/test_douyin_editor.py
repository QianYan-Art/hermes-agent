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
async def test_cover_confirmation_fails_closed_without_unique_cover_dialog(monkeypatch):
    class PageWithoutDialog:
        def get_by_role(self, role):
            assert role == "dialog"
            return FakeLabels([])

    ticks = iter([0, 11])
    monkeypatch.setattr(editor, "monotonic", lambda: next(ticks))
    with pytest.raises(ValueError, match="等待封面确认弹窗超时"):
        await editor._confirm_cover_dialog(PageWithoutDialog())


class FakeDialogButton:
    def __init__(self, on_click=None):
        self.click_count = 0
        self.on_click = on_click

    async def is_visible(self):
        return True

    async def click(self):
        self.click_count += 1
        if self.on_click is not None:
            await self.on_click()


class FakePromptHeading:
    def __init__(self, scope):
        self.scope = scope

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    def locator(self, selector):
        assert selector == ".."
        return self.scope


class FakePromptScope:
    def __init__(self, text, buttons):
        self.text = text
        self.buttons = buttons

    def locator(self, selector):
        assert selector == ".."
        return FakePromptScope("", {})

    async def evaluate(self, _script):
        return "DIV"

    async def inner_text(self):
        return self.text

    def get_by_role(self, role, *, name, exact):
        assert (role, exact) == ("button", True)
        return FakeLabels(self.buttons.get(name, []))


class FakeConfirmDialog:
    def __init__(self, text, buttons=None, visible=True, prompt_scope=None, role="dialog"):
        self.text = text
        self.buttons = buttons or {}
        self.visible = visible
        self.prompt_scope = prompt_scope
        self.role = role

    async def count(self):
        return 1

    async def is_visible(self):
        return self.visible

    async def inner_text(self):
        return self.text

    def get_by_role(self, role, *, name, exact):
        assert (role, exact) == ("button", True)
        return FakeLabels(self.buttons.get(name, []))

    def get_by_text(self, text, *, exact):
        assert exact is True
        if text == "设置竖封面获更多流量" and text in self.text:
            return FakeLabels([FakePromptHeading(self.prompt_scope)])
        return FakeLabels([])

    async def element_handle(self):
        return self

    async def element_handles(self):
        return [self] if self.visible else []

    async def evaluate(self, _script, original):
        return {
            "same": self is original,
            "connected": self.visible,
            "text": self.text,
        }

    async def wait_for(self, *, state, timeout):
        assert state == "hidden"
        assert 0 < timeout <= 10000
        assert not self.visible


class FakeConfirmationPage:
    def __init__(self, dialogs):
        self.dialogs = dialogs

    def get_by_role(self, role):
        if role == "dialog":
            return FakeLabels([dialog for dialog in self.dialogs if dialog.role == "dialog"])
        if role == "alertdialog":
            return FakeLabels([dialog for dialog in self.dialogs if dialog.role == "alertdialog"])
        raise AssertionError(f"unexpected role: {role}")


@pytest.mark.asyncio
async def test_cover_dialog_waits_for_asynchronous_open(monkeypatch):
    dialog = FakeConfirmDialog("设置横封面")
    page = FakeConfirmationPage([])

    async def opened(_):
        page.dialogs.append(dialog)

    monkeypatch.setattr(editor.asyncio, "sleep", opened)
    assert await editor._visible_cover_dialog(page) is dialog


@pytest.mark.asyncio
async def test_cover_dialog_rejects_ambiguity_without_waiting():
    page = FakeConfirmationPage([FakeConfirmDialog("设置横封面"), FakeConfirmDialog("设置竖封面")])
    with pytest.raises(ValueError, match="唯一定位"):
        await editor._visible_cover_dialog(page)


@pytest.mark.asyncio
async def test_cover_dialog_open_has_a_deadline(monkeypatch):
    ticks = iter([0, 11])
    monkeypatch.setattr(editor, "monotonic", lambda: next(ticks))
    with pytest.raises(ValueError, match="超时"):
        await editor._visible_cover_dialog(FakeConfirmationPage([]))


@pytest.mark.asyncio
async def test_confirmation_waits_for_cover_dialog_when_no_recommendation_appears():
    original = FakeConfirmDialog("设置横封面 设置竖封面 封面确认", {"完成": [FakeDialogButton()]})
    page = FakeConfirmationPage([original])

    async def close_cover_dialog():
        original.visible = False

    original.buttons["完成"][0].on_click = close_cover_dialog

    await editor._confirm_cover_dialog(page)

    assert not original.visible


@pytest.mark.asyncio
async def test_confirmation_skips_dialog_removed_before_handle_snapshot():
    class DisappearingDialog(FakeConfirmDialog):
        async def element_handles(self):
            self.visible = False
            return []

        async def evaluate(self, _script, original):
            raise AssertionError("不应对已移除弹窗执行候选快照")

    original = DisappearingDialog(
        "设置横封面 设置竖封面 封面确认", {"完成": [FakeDialogButton()]}
    )
    page = FakeConfirmationPage([original])

    await editor._confirm_cover_dialog(page)

    assert original.buttons["完成"][0].click_count == 1
    assert not original.visible


def _recommendation_dialog(original, *, defer_count=1):
    heading = "设置竖封面获更多流量"
    copy = (
        "你的作品可能会在抖音精选APP、个人页、搜索等多个页面以竖封面样式被展示。"
        "立即设置，可能会帮作品获取更多流量。个人页效果预览 搜索场景效果预览"
    )
    text = f"{heading} {copy}"
    prompt_dialog = FakeConfirmDialog(text)
    defer_buttons = [FakeDialogButton() for _ in range(defer_count)]
    setup_button = FakeDialogButton()

    async def defer():
        prompt_dialog.visible = False
        original.visible = False

    for button in defer_buttons:
        button.on_click = defer
    scope = FakePromptScope(text, {"暂不设置": defer_buttons, "设置竖封面": [setup_button]})
    prompt_dialog.prompt_scope = scope
    return prompt_dialog, defer_buttons, setup_button


@pytest.mark.asyncio
async def test_confirmation_dismisses_only_the_recognized_portrait_recommendation():
    original = FakeConfirmDialog("设置横封面 设置竖封面 封面确认", {"完成": [FakeDialogButton()]})
    prompt, defer_buttons, setup_button = _recommendation_dialog(original)

    class DelayedConfirmationPage(FakeConfirmationPage):
        def __init__(self):
            super().__init__([original])
            self.confirmed = False
            self.dialog_polls = 0

        def get_by_role(self, role):
            if role == "dialog" and self.confirmed:
                self.dialog_polls += 1
                if self.dialog_polls == 2:
                    original.text = "设置横封面 设置竖封面 图片处理中"
                if self.dialog_polls == 3:
                    prompt.role = "dialog"
                    self.dialogs.append(prompt)
            return super().get_by_role(role)

    page = DelayedConfirmationPage()

    async def confirm():
        page.confirmed = True

    original.buttons["完成"][0].on_click = confirm

    await editor._confirm_cover_dialog(page)

    assert original.buttons["完成"][0].click_count == 1
    assert defer_buttons[0].click_count == 1
    assert setup_button.click_count == 0
    assert page.dialog_polls >= 3
    assert not prompt.visible
    assert not original.visible


async def _show_prompt(page, prompt):
    prompt.role = "dialog"
    page.dialogs.append(prompt)


@pytest.mark.asyncio
async def test_confirmation_stops_on_unrecognized_followup_dialog():
    original = FakeConfirmDialog("设置横封面 设置竖封面 封面确认", {"完成": [FakeDialogButton()]})
    unknown = FakeConfirmDialog("账号验证")
    unknown.role = "dialog"
    page = FakeConfirmationPage([original])

    async def show_unknown():
        page.dialogs.append(unknown)

    original.buttons["完成"][0].on_click = show_unknown

    with pytest.raises(ValueError, match="未识别的对话框"):
        await editor._confirm_cover_dialog(page)

    assert original.buttons["完成"][0].click_count == 1
    assert unknown.visible


@pytest.mark.asyncio
async def test_confirmation_stops_when_original_dialog_changes_to_unknown_content():
    original = FakeConfirmDialog("设置横封面 设置竖封面 封面确认", {"完成": [FakeDialogButton()]})
    page = FakeConfirmationPage([original])

    async def change_content():
        original.text = "账号验证"

    original.buttons["完成"][0].on_click = change_content

    with pytest.raises(ValueError, match="原弹窗出现未识别内容"):
        await editor._confirm_cover_dialog(page)

    assert original.buttons["完成"][0].click_count == 1


@pytest.mark.asyncio
async def test_confirmation_rejects_duplicate_recommendation_buttons():
    original = FakeConfirmDialog("设置横封面 设置竖封面 封面确认", {"完成": [FakeDialogButton()]})
    page = FakeConfirmationPage([original])
    prompt, defer_buttons, _ = _recommendation_dialog(original, defer_count=2)
    original.buttons["完成"][0].on_click = lambda: _show_prompt(page, prompt)

    with pytest.raises(ValueError, match="暂不设置.*不唯一"):
        await editor._confirm_cover_dialog(page)

    assert all(button.click_count == 0 for button in defer_buttons)
    assert prompt.visible


class FakeImage:
    def __init__(self, source, background_image="none", visible=True, tag="IMG"):
        self.source = source
        self.background_image = background_image
        self.visible = visible
        self.tag = tag

    async def is_visible(self):
        return self.visible

    async def get_attribute(self, name):
        return self.source if name == "src" else None

    async def evaluate(self, _script):
        return self.background_image


class FakeImages:
    def __init__(self, source=None, elements=None):
        self.elements = list(elements) if elements is not None else [FakeImage(source)]

    async def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakeChooseButton:
    def __init__(self):
        self.clicked = False

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    async def click(self):
        self.clicked = True


class FakeCoverCard:
    def __init__(self, title, source, background_image="none", descendant_nodes=None):
        self.title = title
        self.source = source
        self.background_image = background_image
        self.image = FakeImage(source)
        self.descendant_nodes = (
            list(descendant_nodes) if descendant_nodes is not None else [self.image]
        )
        self.button = FakeChooseButton()
        self.button_label = "选择封面"
        self.extra_buttons = []
        self.visible = True
        self.hovered = False

    def locator(self, selector):
        assert selector in {"..", "img", "*"}
        if selector == "img":
            return FakeImages(
                elements=[node for node in self.descendant_nodes if node.tag == "IMG"]
            )
        if selector == "*":
            return FakeImages(elements=self.descendant_nodes)
        return self

    async def is_visible(self):
        return self.visible

    async def hover(self):
        self.hovered = True

    async def evaluate(self, script):
        if "tagName" in script:
            return "DIV"
        assert "backgroundImage" in script
        return self.background_image

    async def inner_text(self):
        return self.title

    def get_by_text(self, text, *, exact=None):
        assert exact is None
        assert isinstance(text, re.Pattern)
        assert text.pattern == r"^(?:选择封面|编辑封面)$"
        buttons = []
        if text.fullmatch(self.button_label):
            buttons.append(self.button)
        buttons.extend(
            button for label, button in self.extra_buttons if text.fullmatch(label)
        )
        return FakeLabels(buttons)


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
@pytest.mark.parametrize(
    "orientation,title",
    [("landscape", "横封面4:3"), ("portrait", "竖封面3:4")],
)
async def test_orientation_card_uses_unique_exact_choose_text_within_card(orientation, title):
    page = FakeCoverPage("old-landscape.jpg", "old-portrait.jpg")

    card, choose_text = await editor._orientation_card(page, orientation)

    assert card.title == title
    assert choose_text is card.button


@pytest.mark.asyncio
async def test_orientation_card_hovers_before_waiting_for_edit_text():
    class ChooseTextAfterHover(FakeChooseButton):
        def __init__(self, card):
            super().__init__()
            self.card = card

        async def count(self):
            return 1 if self.card.hovered else 0

        async def is_visible(self):
            return self.card.hovered

    page = FakeCoverPage("old-landscape.jpg", "old-portrait.jpg")
    card = page.cards["横封面4:3"]
    card.button_label = "编辑封面"
    card.button = ChooseTextAfterHover(card)

    selected_card, choose_text = await editor._orientation_card(page, "landscape")

    assert selected_card is card
    assert card.hovered
    assert choose_text is card.button


@pytest.mark.asyncio
async def test_orientation_card_rejects_two_visible_cover_actions():
    page = FakeCoverPage("old-landscape.jpg", "old-portrait.jpg")
    card = page.cards["横封面4:3"]
    card.extra_buttons = [("编辑封面", FakeChooseButton())]

    with pytest.raises(ValueError, match="操作不唯一"):
        await editor._orientation_card(page, "landscape")

    assert not card.hovered


@pytest.mark.asyncio
async def test_image_sources_reads_visible_css_backgrounds_and_deduplicates_layers():
    repeated_layers = (
        'url("https://cdn.test/shared.jpg"), url("https://cdn.test/shared.jpg")'
    )
    nodes = [
        FakeImage("old.jpg"),
        FakeImage(None, repeated_layers, tag="DIV"),
        FakeImage(None, repeated_layers, tag="DIV"),
        FakeImage("hidden.jpg", 'url("https://cdn.test/hidden.jpg")', visible=False),
    ]
    card = FakeCoverCard(
        "横封面4:3",
        "old.jpg",
        background_image=repeated_layers,
        descendant_nodes=nodes,
    )

    assert await editor._image_sources(card) == ["old.jpg", repeated_layers]


@pytest.mark.asyncio
async def test_image_sources_fails_closed_over_one_hundred_card_nodes():
    card = FakeCoverCard(
        "横封面4:3",
        "old.jpg",
        descendant_nodes=[FakeImage(None, tag="DIV") for _ in range(100)],
    )

    with pytest.raises(ValueError, match="节点数量超过 100"):
        await editor._image_sources(card)


class FakeUploadAnchor:
    def __init__(self):
        self.click_count = 0

    async def count(self):
        return 1

    async def is_visible(self):
        return True

    async def click(self):
        self.click_count += 1


class FakeChooserElement:
    def __init__(self, input_type="file", accept=editor._COVER_MODAL_ACCEPT):
        self.input_type = input_type
        self.accept = accept
        self.path = None

    async def get_attribute(self, name):
        return {"type": self.input_type, "accept": self.accept}.get(name)

    async def evaluate(self, _script):
        return self.path.name if self.path else ""


class FakeFileChooser:
    def __init__(self, input_type="file", accept=editor._COVER_MODAL_ACCEPT):
        self.element = FakeChooserElement(input_type, accept)

    async def set_files(self, path):
        self.element.path = Path(path)


class FakeFileChooserExpectation:
    def __init__(self, chooser, anchor):
        self.chooser = chooser
        self.anchor = anchor
        self.exited = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        self.exited = True
        if exc is None and (self.chooser is None or self.anchor.click_count != 1):
            raise TimeoutError("file chooser event missing")

    @property
    def value(self):
        async def resolve():
            assert self.exited
            if self.chooser is None:
                raise TimeoutError("file chooser event missing")
            return self.chooser

        return resolve()


class FakeUploadDialog:
    def __init__(self, short_anchors=None, full_anchors=None):
        self.short_anchors = short_anchors if short_anchors is not None else [FakeUploadAnchor()]
        self.full_anchors = full_anchors if full_anchors is not None else []
        self.requested_texts = []
        self.visible = True

    async def is_visible(self):
        return self.visible

    async def inner_text(self):
        return "封面 点击上传文件或拖拽文件到这里"

    def get_by_text(self, text, *, exact):
        assert exact is True
        self.requested_texts.append(text)
        anchors = {
            "点击上传文件": self.short_anchors,
            "点击上传文件或拖拽文件到这里": self.full_anchors,
        }.get(text, [])
        return FakeLabels(anchors)


@pytest.mark.asyncio
async def test_choose_cover_file_uses_unique_dialog_anchor_and_filechooser(tmp_path):
    path = _jpeg(tmp_path / "cover.jpg")
    dialog = FakeUploadDialog()
    chooser = FakeFileChooser()
    anchor = dialog.short_anchors[0]

    class Page:
        def expect_file_chooser(self, *, timeout):
            assert timeout == 10000
            return FakeFileChooserExpectation(chooser, anchor)

    await editor._choose_cover_file(Page(), dialog, path)

    assert anchor.click_count == 1
    assert dialog.requested_texts == ["点击上传文件"]
    assert chooser.element.path == path


@pytest.mark.asyncio
async def test_choose_cover_file_falls_back_to_exact_full_upload_instruction(tmp_path):
    path = _jpeg(tmp_path / "cover.jpg")
    anchor = FakeUploadAnchor()
    dialog = FakeUploadDialog(short_anchors=[], full_anchors=[anchor])
    chooser = FakeFileChooser()

    class Page:
        def expect_file_chooser(self, *, timeout):
            assert timeout == 10000
            return FakeFileChooserExpectation(chooser, anchor)

    await editor._choose_cover_file(Page(), dialog, path)

    assert dialog.requested_texts == ["点击上传文件", "点击上传文件或拖拽文件到这里"]
    assert anchor.click_count == 1
    assert chooser.element.path == path


@pytest.mark.asyncio
async def test_choose_cover_file_fails_closed_when_upload_target_is_not_unique(tmp_path):
    path = _jpeg(tmp_path / "cover.jpg")
    dialog = FakeUploadDialog(short_anchors=[FakeUploadAnchor(), FakeUploadAnchor()])

    class Page:
        def expect_file_chooser(self, *, timeout):
            pytest.fail("不唯一操作目标时不应等待文件选择器")

    with pytest.raises(ValueError, match="无法唯一定位"):
        await editor._choose_cover_file(Page(), dialog, path)


@pytest.mark.asyncio
async def test_choose_cover_file_rejects_unobserved_accept(tmp_path):
    path = _jpeg(tmp_path / "cover.jpg")
    dialog = FakeUploadDialog()
    chooser = FakeFileChooser(accept="image/png,image/jpeg")
    anchor = dialog.short_anchors[0]

    class Page:
        def expect_file_chooser(self, *, timeout):
            assert timeout == 10000
            return FakeFileChooserExpectation(chooser, anchor)

    with pytest.raises(ValueError, match="控件与已观察"):
        await editor._choose_cover_file(Page(), dialog, path)

    assert chooser.element.path is None


@pytest.mark.asyncio
async def test_choose_cover_file_fails_closed_without_filechooser_event(tmp_path):
    path = _jpeg(tmp_path / "cover.jpg")
    dialog = FakeUploadDialog()
    anchor = dialog.short_anchors[0]

    class Page:
        def expect_file_chooser(self, *, timeout):
            assert timeout == 10000
            return FakeFileChooserExpectation(None, anchor)

    with pytest.raises(ValueError, match="未能可靠触发"):
        await editor._choose_cover_file(Page(), dialog, path)


@pytest.mark.asyncio
async def test_apply_cover_orientation_does_not_use_page_wide_file_inputs(monkeypatch, tmp_path):
    path = _jpeg(tmp_path / "landscape.jpg")
    dialog = FakeUploadDialog()
    chooser = FakeFileChooser()
    anchor = dialog.short_anchors[0]
    card = FakeCoverCard("横封面4:3", "old.jpg")

    class PageWithoutGlobalLocator:
        def get_by_role(self, role):
            assert role == "dialog"
            return FakeLabels([dialog])

        def expect_file_chooser(self, *, timeout):
            assert timeout == 10000
            return FakeFileChooserExpectation(chooser, anchor)

    async def orientation_card(*_args):
        return card, card.button

    async def image_sources(*_args):
        return ["old.jpg"]

    async def confirm_dialog(*_args):
        return None

    async def changed_thumbnail(*_args):
        return "new.jpg"

    monkeypatch.setattr(editor, "_orientation_card", orientation_card)
    monkeypatch.setattr(editor, "_image_sources", image_sources)
    monkeypatch.setattr(editor, "_confirm_cover_dialog", confirm_dialog)
    monkeypatch.setattr(editor, "_wait_for_unique_thumbnail_change", changed_thumbnail)

    result = await editor._apply_cover_orientation(PageWithoutGlobalLocator(), "landscape", path)

    assert anchor.click_count == 1
    assert chooser.element.path == path
    assert result["orientation"] == "landscape"


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
    assert not any(card.hovered for card in page.cards.values())


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
        if selector == "*":
            return FakeImages(elements=[])
        assert selector == "img"
        return SequenceImageCollection(self)

    async def is_visible(self):
        return True

    async def evaluate(self, script):
        assert "backgroundImage" in script
        return "none"


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
