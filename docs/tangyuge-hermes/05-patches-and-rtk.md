# Patches And RTK

常用叫法："patch记录"、"二开patch"、"/new和/reset"、"/view"、"/context"、
"关闭自动记忆"、"自动总结skills"、"RTK"、"provider"、"模型路由"、
"Tavily"、"OpenAI-compatible image"、"CPA生图旁路"、"新旧行为差异"。

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
should be narrow and documented by commit, test evidence, and `main` deployment evidence.

## Built-In Patch Behaviors

These QianYan patches are now normal Tangyuge-Hermes source behavior, not
external patch files to replay:

- `/new` and `/reset` are distinct gateway commands in `gateway/run.py`.
  `/new` starts a fresh session and returns model settings to global defaults;
  `/reset` starts a fresh session while preserving the current session model
  configuration. `/new` also deletes the previous session DB row/transcript so
  the old conversation is no longer resumable; `/reset` keeps the old session
  record. Both commands bypass the running-agent queue path, interrupt active
  work first, clear pending queued text, and then dispatch the reset handler so
  stale slash-command text is not fed back to the agent. Gateway `/new` and
  `/reset` replies do not append random `hermes_cli.tips` discovery tips, so
  irrelevant platform hints such as Telegram webhook setup do not appear in QQ
  new-session replies.
- Manual reset state is tracked with `SessionEntry.is_fresh_reset` in
  `gateway/session.py`. The next turn can re-inject session/topic skills
  without falsely showing the idle/daily auto-reset notice.
- `/status` and `/view` remain available while an agent is running. The
  running-agent fast path in `gateway/run.py` routes them to dedicated handlers
  before normal queueing so users can inspect session and live-run state without
  interrupting work.
- `/auxmodel`, QQ `/model` provider selection, custom provider routing, and
  model/provider filtering are retained as source behavior around gateway
  command handling, runtime provider resolution, and auxiliary client routing.
  The 81 deployment currently uses the built-in `minimax-cn` provider for the
  main model (`minimax-m3`). The older main-model custom providers
  `openrouter`, `siliconflow`, `deepseek-direct`, and `xiaomi-token-plan-cn`
  are removed from server runtime config; auxiliary/vision, image generation,
  and TTS settings are separate and must be preserved.
- Inbound QQ images still respect the explicit auxiliary vision backend
  (`custom:ollama_vision`) when `agent.image_input_mode` is `auto`; images are
  summarized before reaching the main model. Inbound QQ videos are separate:
  for `minimax-cn` + `minimax-m3`, cached local video files are attached as
  native Anthropic-compatible `video` blocks when small enough for inline
  base64. The inline budget is 45 MiB per file and 45 MiB total per turn;
  unsupported or oversized videos fall back to the cached-path text marker.
- Built-in API-key provider discovery from generic env vars is disabled by
  default. `HERMES_BUILTIN_ENV_PROVIDER_DISCOVERY=1` is required to restore
  legacy auto-discovery of built-in providers from env names such as
  `MINIMAX_CN_API_KEY` or `DEEPSEEK_API_KEY`; explicit provider selection and user-defined
  `providers:` entries continue to work without that flag.
- `/context` is a native CLI/gateway command for showing or setting
  `model.context_length`. `/context <size> --global` persists the context
  window to config; `/context auto --global` probes the active model and falls
  back to 256k if detection cannot resolve a stronger value. `/model` switches
  also auto-probe and persist the current model context window so providers do
  not need static default context values.
- Automatic memory and skill-review loops are disabled for the Tangyuge Codex
  runtime path. `agent/codex_runtime.py` explicitly sets
  `should_review_memory = False` and `should_review_skills = False`; memory
  writes remain available through explicit user/tool action only.
- Tangyuge identity prompt hardening is built in. `agent/system_prompt.py`
  injects `# Tangyuge Identity` before SOUL, skills, context, memory, and
  platform hints; `agent/prompt_builder.py` treats SOUL as style-only overlay,
  rewrites legacy upstream default SOUL identity text to the style overlay, and
  labels Hermes docs/runtime guidance as non-identity guidance.
- Delegated child agents inherit active runtime/toolset configuration, but child
  tool access is constrained. `tools/delegate_tool.py` documents that leaf
  subagents cannot call `delegate_task`, `clarify`, `memory`, `send_message`,
  or `execute_code`; orchestrator subagents can delegate within configured depth
  but still cannot call `clarify`, `memory`, `send_message`, or `execute_code`.
- Async subagent delegation is available with `delegate_task(background=true)`.
  It is single-task only: a background call returns a `delegation_id`
  immediately, runs the child through `tools/async_delegation.py`, and pushes an
  `async_delegation` completion event through `tools.process_registry` so
  `gateway/run.py` can inject the result back into the originating session as a
  new turn. `delegation.max_async_children` caps concurrent background
  subagents; excess dispatches are rejected rather than queued.
- API-key rotation, Tavily multi-key failover, OpenAI-compatible image backend
  behavior, mail-vps-ops, hermes-md-locator, and tangyuge-roleplay are retained
  as built-in repo behavior or built-in skills. Image backend secrets remain
  server-local in runtime environment variables and are never stored in repo
  docs.

## Verification

```bash
pytest tests/plugins/test_rtk_rewrite_plugin.py -q
python -m compileall -q plugins/rtk-rewrite hermes_cli/plugins.py
```

These tests prove fail-open behavior for absent/error paths. They do not prove a
real RTK rewrite success without an installed `rtk` binary, and docs/status must
not claim that live rewrite success was verified unless that binary is present
and tested.
