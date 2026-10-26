#!/usr/bin/env python3
"""Build the public agent-hub snapshot from allowlisted local files."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
ROOT = Path(__file__).resolve().parent
README = ROOT / "README.md"
INVENTORY = ROOT / "inventory.json"

SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|auth|token|secret|password|passwd|webhook|deviceid|credential)",
    re.I,
)
IPV4_RE = re.compile(r"\b(?!127\.)\d{1,3}(?:\.\d{1,3}){3}\b")
TAILSCALE_RE = re.compile(r"\b[\w.-]+\.ts\.net\b", re.I)
KEYISH_RE = re.compile(
    r"\b(?:sk-|ghp_|github_pat_|xai-|xoxb-|AIza)[A-Za-z0-9_\-]{8,}\b"
)


def sh(args: list[str], timeout: int = 8) -> str | None:
    try:
        p = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    out = (p.stdout or "").strip() or (p.stderr or "").strip()
    return out or None


def version(bin_name: str, extra: list[str] | None = None) -> str | None:
    out = sh([bin_name, *(extra or ["--version"])])
    if not out:
        return None
    return sanitize(out.splitlines()[0])[:120]


def which(bin_name: str) -> str | None:
    p = sh(["which", bin_name])
    return tidy_path(p) if p else None


def tidy_path(value: str | Path | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    try:
        text = str(Path(text).expanduser())
        if text.startswith(str(HOME)):
            text = "~" + text[len(str(HOME)) :]
    except Exception:
        pass
    return sanitize(text)


def sanitize(text: str | None) -> str | None:
    if text is None:
        return None
    text = IPV4_RE.sub("<redacted-ip>", text)
    text = TAILSCALE_RE.sub("<redacted-tailnet>", text)
    text = KEYISH_RE.sub("<redacted-key>", text)
    return text


def read_text(path: Path, limit: int = 20000) -> str | None:
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw) > limit:
        raw = raw[:limit] + "\n\n<!-- truncated -->\n"
    return sanitize(raw)


def read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def skill_entry(skill_dir: Path) -> dict | None:
    skill = skill_dir / "SKILL.md"
    if not skill.is_file():
        return None
    text = skill.read_text(encoding="utf-8", errors="replace")
    name = skill_dir.name
    description = None
    if text.startswith("---"):
        end = text.find("\n---", 3)
        fm = text[3:end] if end != -1 else ""
        for line in fm.splitlines():
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"')
    return {
        "name": sanitize(name),
        "description": sanitize(description)[:400] if description else None,
        "path": tidy_path(skill_dir),
    }


def list_skills(*dirs: Path) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for base in dirs:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir():
                continue
            entry = skill_entry(child)
            if not entry or entry["name"] in seen:
                continue
            seen.add(entry["name"])
            out.append(entry)
    return out


def list_md_names(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    return sorted(p.name for p in directory.glob("*.md"))


def pick(d: dict, keys: list[str]) -> dict:
    out = {}
    for key in keys:
        if key not in d:
            continue
        if SECRET_KEY_RE.search(key):
            continue
        val = d[key]
        if isinstance(val, (str, int, float, bool)) or val is None:
            out[key] = sanitize(val) if isinstance(val, str) else val
        elif isinstance(val, list) and all(isinstance(x, str) for x in val):
            out[key] = [sanitize(x) for x in val]
    return out


def normalize_pi_package(spec: str) -> str:
    spec = spec.replace(str(HOME), "~")
    spec = spec.replace("../../.local/share/pi-packages/", "~/.local/share/pi-packages/")
    return sanitize(spec) or spec


def collect_pi() -> dict:
    settings = read_json(HOME / ".pi/agent/settings.json") or {}
    packages = [normalize_pi_package(p) for p in settings.get("packages") or []]
    return {
        "id": "pi",
        "name": "Pi",
        "binary": which("pi"),
        "version": version("pi"),
        "config_dir": "~/.pi/agent",
        "default_model": sanitize(settings.get("defaultModel")),
        "default_provider": sanitize(settings.get("defaultProvider")),
        "enabled_models": [sanitize(m) for m in settings.get("enabledModels") or []],
        "packages": packages,
        "instruction_files": [
            {
                "path": "~/.agents/AGENTS.md",
                "via": "symlink ~/.pi/agent/AGENTS.md",
            },
            {
                "path": "~/.pi/agent/APPEND_SYSTEM.md",
                "via": "Pi append-system",
            },
        ],
        "subagents": list_md_names(HOME / ".pi/agent/agents"),
        "extensions": sorted(p.name for p in (HOME / ".pi/agent/extensions").glob("*.ts"))
        if (HOME / ".pi/agent/extensions").is_dir()
        else [],
        "skills": list_skills(HOME / ".pi/agent/skills"),
        "instruction_text": {
            "APPEND_SYSTEM.md": read_text(HOME / ".pi/agent/APPEND_SYSTEM.md"),
        },
    }


def load_jsonc(path: Path) -> dict:
    if not path.is_file():
        return {}
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        stripped = re.sub(r"^\s*//.*$", "", raw, flags=re.M)
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def collect_opencode() -> dict:
    cfg = load_jsonc(HOME / ".config/opencode/opencode.jsonc")
    instructions = []
    skills = []
    if isinstance(cfg, dict):
        instructions = [tidy_path(x) for x in cfg.get("instructions") or []]
        skills = [tidy_path(x) for x in cfg.get("skills") or []]
        agents = {
            name: pick(body, ["model"])
            for name, body in (cfg.get("agents") or {}).items()
            if isinstance(body, dict)
        }
        mcp_names = list((cfg.get("mcp") or {}).keys())
    else:
        agents, mcp_names = {}, []
    return {
        "id": "opencode",
        "name": "OpenCode",
        "binary": which("opencode"),
        "version": version("opencode"),
        "config_dir": "~/.config/opencode",
        "instruction_files": instructions,
        "config_skills": skills,
        "agents": agents,
        "mcp_server_names": mcp_names,
        "instruction_text": {
            "opencode.md": read_text(HOME / ".config/opencode/opencode.md"),
        },
        "skills": list_skills(HOME / ".config/opencode/skills"),
    }


def collect_delta() -> dict:
    return {
        "id": "delta",
        "name": "Delta",
        "binary": which("delta"),
        "version": version("delta"),
        "config_dir": "~/.config/delta",
        "instruction_files": ["~/.config/delta/AGENTS.md"],
        "instruction_text": {
            "AGENTS.md": read_text(HOME / ".config/delta/AGENTS.md"),
        },
        "note": "Personal AGENTS.md is not the shared ~/.agents/AGENTS.md.",
    }


def collect_claude() -> dict:
    settings = read_json(HOME / ".claude/settings.json") or {}
    return {
        "id": "claude",
        "name": "Claude Code",
        "binary": which("claude"),
        "version": version("claude"),
        "config_dir": "~/.claude",
        "model": sanitize(str(settings.get("model"))) if settings.get("model") else None,
        "instruction_files": ["~/.claude/CLAUDE.md (imports ~/.agents/AGENTS.md)"],
        "instruction_text": {
            "CLAUDE.md": read_text(HOME / ".claude/CLAUDE.md", limit=2000),
        },
        "skills": list_skills(HOME / ".claude/skills", HOME / ".agents/skills"),
    }


def collect_codex() -> dict:
    model = None
    effort = None
    cfg = HOME / ".codex/config.toml"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model ") or line.startswith("model="):
                model = sanitize(line.split("=", 1)[-1].strip().strip('"'))
            elif "model_reasoning_effort" in line:
                effort = sanitize(line.split("=", 1)[-1].strip().strip('"'))
    return {
        "id": "codex",
        "name": "Codex",
        "binary": which("codex"),
        "version": version("codex"),
        "config_dir": "~/.codex",
        "model": model,
        "reasoning_effort": effort,
        "instruction_files": ["~/.codex/AGENTS.md -> ~/.agents/AGENTS.md"],
        "skills": list_skills(HOME / ".codex/skills", HOME / ".agents/skills"),
    }


def collect() -> dict:
    shared_text = read_text(HOME / ".agents/AGENTS.md")
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "purpose": (
            "Public snapshot of Fatih's coding-agent stack. "
            "Generated on the desktop. Not live config."
        ),
        "shared": {
            "repo": "https://github.com/Fatih0234/agents",
            "path": "~/.agents",
            "AGENTS.md": shared_text,
            "skills": list_skills(HOME / ".agents/skills"),
        },
        "harnesses": [
            collect_pi(),
            collect_opencode(),
            collect_delta(),
            collect_claude(),
            collect_codex(),
        ],
    }


def md_escape(text: str | None) -> str:
    if not text:
        return ""
    return text.replace("\r\n", "\n")


def render(data: dict) -> str:
    lines = [
        "<!-- generated by generate.py. Do not edit this file. -->",
        "",
        "# Agent hub",
        "",
        f"Generated: `{data['generated_at']}` (UTC).",
        "",
        data["purpose"],
        "",
        "If you are an AI helping Fatih: this page is the current agent stack.",
        "Do not assume a harness, package, or skill that is not listed.",
        "Do not ask him to restate this. Private notes stay in `my-brain`.",
        "",
        "Live files stay on the machine. This repo is only the published view.",
        "",
        "## Harnesses",
        "",
        "| Harness | Version | Config | Standing instructions | Default model |",
        "|---|---|---|---|---|",
    ]
    models = {
        "pi": lambda h: h.get("default_model"),
        "opencode": lambda h: (h.get("agents") or {}).get("general", {}).get("model"),
        "delta": lambda h: None,
        "claude": lambda h: h.get("model"),
        "codex": lambda h: h.get("model"),
    }
    for h in data["harnesses"]:
        instr = h.get("instruction_files") or []
        if instr and isinstance(instr[0], dict):
            instr_s = "; ".join(i.get("path", "") for i in instr)
        else:
            instr_s = "; ".join(str(x) for x in instr)
        model = models.get(h["id"], lambda _h: None)(h) or "—"
        lines.append(
            f"| {h['name']} | {h.get('version') or '—'} | `{h.get('config_dir')}` | {instr_s} | `{model}` |"
        )

    shared = data["shared"]
    lines += [
        "",
        "## Shared layer (`~/.agents`)",
        "",
        f"Source repo (private): {shared['repo']}",
        "",
        "Skills visible to every harness that reads `~/.agents/skills`:",
        "",
    ]
    if shared["skills"]:
        lines.append("| Skill | Description |")
        lines.append("|---|---|")
        for s in shared["skills"]:
            desc = (s.get("description") or "").replace("|", "/")
            lines.append(f"| `{s['name']}` | {desc} |")
    else:
        lines.append("_No shared skills found._")

    lines += [
        "",
        "### Shared `AGENTS.md`",
        "",
        "```markdown",
        md_escape(shared.get("AGENTS.md") or ""),
        "```",
        "",
    ]

    for h in data["harnesses"]:
        lines += [f"## {h['name']}", ""]
        lines.append(f"- Binary: `{h.get('binary') or 'missing'}`")
        lines.append(f"- Version: `{h.get('version') or 'unknown'}`")
        lines.append(f"- Config: `{h.get('config_dir')}`")
        if h["id"] == "pi":
            lines.append(f"- Provider: `{h.get('default_provider') or '—'}`")
            if h.get("enabled_models"):
                lines.append("- Enabled models: " + ", ".join(f"`{m}`" for m in h["enabled_models"]))
            if h.get("packages"):
                lines.append("- Packages:")
                for p in h["packages"]:
                    lines.append(f"  - `{p}`")
            if h.get("subagents"):
                lines.append("- Subagents: " + ", ".join(f"`{n}`" for n in h["subagents"]))
            if h.get("extensions"):
                lines.append("- Extensions: " + ", ".join(f"`{n}`" for n in h["extensions"]))
        if h["id"] == "opencode":
            if h.get("agents"):
                for name, body in h["agents"].items():
                    lines.append(f"- Agent `{name}` model: `{body.get('model') or '—'}`")
            if h.get("mcp_server_names"):
                lines.append("- MCP servers (names only): " + ", ".join(f"`{n}`" for n in h["mcp_server_names"]))
            if h.get("config_skills"):
                lines.append("- Config skill paths:")
                for p in h["config_skills"]:
                    lines.append(f"  - `{p}`")
        if h.get("note"):
            lines.append(f"- {h['note']}")
        local_skills = h.get("skills") or []
        # Shared skills already listed; only extra names for this harness.
        shared_names = {s["name"] for s in shared["skills"]}
        extra = [s for s in local_skills if s["name"] not in shared_names]
        if extra:
            lines.append("- Extra skills:")
            for s in extra:
                lines.append(f"  - `{s['name']}`: {s.get('description') or ''}")
        texts = h.get("instruction_text") or {}
        for name, body in texts.items():
            if not body:
                continue
            lines += ["", f"### {h['name']}: `{name}`", "", "```markdown", md_escape(body), "```", ""]

    lines += [
        "## How this file is updated",
        "",
        "On the desktop, `generate.py` reads allowlisted paths and CLI `--version` output.",
        "A systemd user timer commits and pushes when the snapshot changes.",
        "See `SECURITY.md` for what is never included.",
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def without_time(data: dict) -> dict:
    copy = json.loads(json.dumps(data))
    copy.pop("generated_at", None)
    return copy


def git_push_if_changed() -> None:
    def git(args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args],
            check=False,
            capture_output=True,
            text=True,
        )

    git(["add", "README.md", "inventory.json"])
    diff = git(["diff", "--cached", "--quiet"])
    if diff.returncode == 0:
        return
    msg = f"Refresh snapshot {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}"
    c = git(["commit", "-m", msg])
    if c.returncode != 0:
        print(c.stderr or c.stdout, file=sys.stderr)
        sys.exit(c.returncode)
    p = git(["push", "origin", "HEAD"])
    if p.returncode != 0:
        print(p.stderr or p.stdout, file=sys.stderr)
        sys.exit(p.returncode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--push", action="store_true", help="commit and push if changed")
    args = parser.parse_args()
    os.chdir(ROOT)
    data = collect()
    previous = {}
    if INVENTORY.is_file():
        try:
            previous = without_time(json.loads(INVENTORY.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            previous = {}
    if without_time(data) == previous:
        return
    README.write_text(render(data), encoding="utf-8")
    INVENTORY.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.push:
        git_push_if_changed()


if __name__ == "__main__":
    main()
