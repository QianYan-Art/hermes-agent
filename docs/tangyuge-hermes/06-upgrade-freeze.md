# Upgrade Freeze

Tangyuge-Hermes is frozen on Hermes Agent v0.16.0 (2026-06-05) and the
the 2026-06-12 81-server snapshot baseline. It should not automatically follow
upstream Hermes feature churn.

## Allowed Changes

Allowed changes are limited to:

- fixes needed for 81 server QQBot/API-server operation
- Tangyuge identity correctness
- retained skill/tool/platform maintenance
- security fixes that apply to the retained scope
- RTK plugin maintenance
- deployment and documentation fixes

## Upgrade Review

Before accepting upstream changes:

1. Compare against the retained scope.
2. Reject restored UI/web/desktop/TUI surfaces unless explicitly requested.
3. Reject restored non-retained toolsets/platforms/plugins.
4. Verify Tangyuge identity still injects first and excludes scenario/openers.
5. Verify `hermes tools list`, `hermes skills list --enabled-only`, focused tests,
   and 81 deployment after the change.

## Release Rule

Validated releases are carried on `main` until a future explicit versioning
decision changes the release process. Historical Tangyuge release tags are not
the server deployment target.
