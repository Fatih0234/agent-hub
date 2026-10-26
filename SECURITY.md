# What this repo must never contain

This repository is public. The generator publishes only the fields and
files listed below. Everything else on the machine stays off this repo.

The list lives in `generate.py` (`collect_*`, `pick`, `read_text`).
There is no separate file allowlist.

## What is published

Instruction file bodies, regex-sanitized, truncated:

- `~/.agents/AGENTS.md`
- `~/.pi/agent/APPEND_SYSTEM.md`
- `~/.config/opencode/opencode.md`
- `~/.config/delta/AGENTS.md`
- `~/.claude/CLAUDE.md` (first 2000 characters)

Metadata only:

- Pi `settings.json`: `defaultModel`, `defaultProvider`, `enabledModels`, `packages`
- OpenCode `opencode.jsonc`: instruction paths, skill paths, per-agent `model`, MCP **names**
- Claude `settings.json`: `model`
- Codex `config.toml`: `model`, `model_reasoning_effort`
- Skill names and SKILL.md `description` (first 400 characters)
- Pi subagent `*.md` names and extension `*.ts` names
- `which` path and `--version` stdout for `pi`, `opencode`, `delta`, `claude`, `codex`

## What is redacted

`sanitize()`:

- Redacts non-loopback IPv4
- Redacts `*.ts.net`
- Redacts token-like prefixes `sk-`, `ghp_`, `github_pat_`, `xai-`, `xoxb-`, `AIza`

`pick()` drops JSON keys whose names look like secrets.

`tidy_path` and `normalize_pi_package` rewrite `$HOME` to `~` on paths the
generator builds. Instruction file bodies only go through `sanitize()`,
so an absolute home path in those files is published as written.

CLI `--version` uses stdout and exit 0 only. Stderr is never published.

## What is not redacted

Homelab hostnames are not filtered. A secret that is only in an
instruction file body, and that does not match the regexes above, is
published. Do not put credentials in those files.

## Never publish

- `auth.json`, credentials, OAuth, webhooks, `.env`
- sessions, history, caches, logs, sqlite databases
- `deviceId`, installation ids, trusted hashes
- environment variables, Claude `autoMode`, Codex `hooks.state`
- API keys, tokens, passwords
- full `settings.json` / `opencode.jsonc` / `config.toml`

Live config stays on the machine. This repo is a generated view.
