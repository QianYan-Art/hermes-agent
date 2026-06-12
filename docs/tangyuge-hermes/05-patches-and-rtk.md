# Patches And RTK

Tangyuge-Hermes keeps QianYan server patches from the frozen baseline and
vendors the RTK rewrite plugin as a bundled plugin.

## RTK Plugin

- Bundled path: `plugins/rtk-rewrite/`
- Server-local historical path: `/home/hermes/.hermes/plugins/rtk-rewrite/`
- The RTK binary is not vendored by default.
- No real secrets are stored in the repo.
- The plugin must fail open: missing binary, timeout, or rewrite failure must
  continue with the original tool call/command rather than blocking execution.

## Patch Policy

Server behavior that existed at the frozen snapshot is treated as baseline unless
it conflicts with Tangyuge-Hermes trimming or identity requirements. New changes
should be narrow and documented by commit, test evidence, and deployment tag.

## Verification

```bash
pytest tests/plugins/test_rtk_rewrite_plugin.py -q
python -m compileall -q plugins/rtk-rewrite hermes_cli/plugins.py
```

These tests prove fail-open behavior for absent/error paths. They do not prove a
real RTK rewrite success without an installed `rtk` binary, and docs/status must
not claim that live rewrite success was verified unless that binary is present
and tested.
