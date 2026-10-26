# What this repo must never contain

This repository is public. The generator allowlists fields. If a file
is not on the list, it is not published.

Never publish:

- `auth.json`, credentials, OAuth, webhooks, `.env`
- sessions, history, caches, logs, sqlite databases
- `deviceId`, installation ids, trusted hashes
- environment variables, Claude `autoMode`, Codex `hooks.state`
- API keys, tokens, passwords
- non-loopback IP addresses, Tailscale names, homelab hostnames

Live config stays on the machine. This repo is a generated view.
