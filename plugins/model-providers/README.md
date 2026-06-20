# Model Provider Plugins

Tangyuge-Hermes keeps only the provider profiles needed by the 81 QQBot
runtime:

- `custom`
- `deepseek`
- `minimax`

`providers/__init__.py._discover_providers()` scans this directory and
`$HERMES_HOME/plugins/model-providers/` when provider profiles are first
requested. Each retained provider package owns an `__init__.py` that registers
its `ProviderProfile` plus a `plugin.yaml` manifest.

Non-retained upstream provider packages are not tracked in this fork. Add a new
provider only when it is intentionally added to the Tangyuge runtime boundary,
then update `tests/hermes_cli/test_tangyuge_trim_scope.py`,
`tests/trimmed_manifest.py`, and the docs under `docs/tangyuge-hermes/`.
