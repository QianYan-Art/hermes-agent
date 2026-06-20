from pathlib import Path

from tests.trimmed_manifest import TRIMMED_TEST_TARGETS


REMOVED_SURFACE_TOKENS = {
    "discord",
    "telegram",
    "slack",
    "whatsapp",
    "feishu",
    "wecom",
    "weixin",
    "yuanbao",
    "google_chat",
    "homeassistant",
    "webhook",
    "signal",
    "matrix",
}

REQUIRED_TARGETS = {
    "tests/gateway/test_qqbot.py",
    "tests/gateway/test_approve_deny_commands.py",
    "tests/tools/test_image_generation.py",
    "tests/tools/test_image_generation_plugin_dispatch.py",
    "tests/plugins/image_gen/test_openai_provider.py",
    "tests/plugins/model_providers/test_minimax_profile.py",
    "tests/plugins/model_providers/test_deepseek_profile.py",
    "tests/hermes_cli/test_tangyuge_trim_scope.py",
}


def _path_part(target: str) -> Path:
    return Path(target.split("::", 1)[0])


def test_trimmed_profile_targets_exist():
    missing = [
        target for target in TRIMMED_TEST_TARGETS
        if not _path_part(target).exists()
    ]

    assert missing == []


def test_trimmed_profile_excludes_removed_platform_surfaces():
    leaked = [
        target for target in TRIMMED_TEST_TARGETS
        if any(token in target.lower() for token in REMOVED_SURFACE_TOKENS)
    ]

    assert leaked == []


def test_trimmed_profile_covers_current_runtime_edges():
    assert REQUIRED_TARGETS <= set(TRIMMED_TEST_TARGETS)


def test_trimmed_profile_has_no_duplicate_targets():
    assert len(TRIMMED_TEST_TARGETS) == len(set(TRIMMED_TEST_TARGETS))
