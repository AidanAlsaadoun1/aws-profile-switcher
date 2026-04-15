#!/usr/bin/env python3
"""
aws-profile-switcher.py — Interactive AWS profile switcher.

Reads ~/.aws/config, lets the user pick a profile via a curses TUI,
and persists the choice to ~/.zshrc as `export AWS_PROFILE=<name>`.
"""

from __future__ import annotations

import configparser
import curses
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
AWS_CONFIG = Path(os.environ.get("AWS_CONFIG_FILE", "~/.aws/config")).expanduser()
ZSHRC      = Path("~/.zshrc").expanduser()
ZSHRC_BAK  = Path("~/.zshrc.bak").expanduser()

EXPORT_RE        = re.compile(r'^\s*export\s+AWS_PROFILE\s*=')
EXPORT_VALUE_RE  = re.compile(r'^\s*export\s+AWS_PROFILE\s*=\s*(["\']?)(.+?)\1\s*$')

# ── Curses colour pairs ───────────────────────────────────────────────────────
C_SELECTED = 1
C_DIM      = 2
C_WARN     = 3
C_TITLE    = 4


# ── AWS config parsing ────────────────────────────────────────────────────────
def load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    try:
        cfg.read(AWS_CONFIG)
    except configparser.Error as e:
        print(f"\033[31m  ✖  Failed to parse {AWS_CONFIG}: {e}\033[0m")
        sys.exit(1)
    return cfg


def get_profiles(cfg: configparser.ConfigParser) -> list[str]:
    profiles = sorted(
        section[len("profile "):].strip()
        for section in cfg.sections()
        if section.startswith("profile ")
    )
    if "default" in cfg:
        profiles.insert(0, "default")
    return profiles


def get_profile_meta(cfg: configparser.ConfigParser, profile: str) -> dict:
    section = "default" if profile == "default" else f"profile {profile}"
    s = cfg[section] if section in cfg else {}
    return {
        "region": s.get("region", "n/a"),
        "output": s.get("output", "n/a"),
        "sso":    s.get("sso_start_url", ""),
        "role":   s.get("role_arn", ""),
    }


# ── Current profile detection ─────────────────────────────────────────────────
def get_current_profile() -> str:
    if val := os.environ.get("AWS_PROFILE"):
        return val
    if ZSHRC.exists():
        for line in ZSHRC.read_text().splitlines():
            if m := EXPORT_VALUE_RE.match(line):
                return m.group(2)
    return "none"


# ── Account ID lookup (best-effort) ───────────────────────────────────────────
def get_account_id(profile: str) -> str:
    if not shutil.which("aws"):
        return "n/a"
    try:
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity",
             "--query", "Account", "--output", "text"],
            env={**os.environ, "AWS_PROFILE": profile},
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return "n/a"
    if result.returncode != 0:
        return "n/a"
    return result.stdout.strip() or "n/a"


# ── .zshrc updater ────────────────────────────────────────────────────────────
def update_zshrc(profile: str) -> None:
    new_line = f"export AWS_PROFILE={profile}\n"
    header   = "# AWS Profile — managed by aws-profile-switcher\n"

    if not ZSHRC.exists():
        ZSHRC.write_text(header + new_line)
        return

    shutil.copy(ZSHRC, ZSHRC_BAK)
    lines = ZSHRC.read_text().splitlines(keepends=True)

    for i, line in enumerate(lines):
        if EXPORT_RE.match(line):
            lines[i] = new_line
            ZSHRC.write_text("".join(lines))
            return

    # No existing export — append, ensuring a separating newline.
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.append(f"\n{header}{new_line}")
    ZSHRC.write_text("".join(lines))


# ── TUI selector ──────────────────────────────────────────────────────────────
def draw_selector(stdscr, profiles: list[str], metas: dict, current: str) -> str | None:
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(C_SELECTED, curses.COLOR_CYAN,   -1)
    curses.init_pair(C_DIM,      curses.COLOR_WHITE,  -1)
    curses.init_pair(C_WARN,     curses.COLOR_YELLOW, -1)
    curses.init_pair(C_TITLE,    curses.COLOR_CYAN,   -1)

    selected = profiles.index(current) if current in profiles else 0

    while True:
        stdscr.erase()
        h, w = stdscr.getmaxyx()
        row  = 0

        def put(r, c, text, attr=curses.A_NORMAL):
            if r >= h - 1 or c >= w - 1:
                return
            try:
                stdscr.addnstr(r, c, text, w - c - 1, attr)
            except curses.error:
                pass

        rule = "─" * min(w - 4, 44)

        # Banner
        banner = "AWS Profile Switcher"
        put(row, max((w - len(banner)) // 2, 0),
            banner, curses.color_pair(C_TITLE) | curses.A_BOLD)
        row += 1
        put(row, 2, rule, curses.color_pair(C_DIM)); row += 1

        # Active profile
        put(row, 2, "Active: ", curses.A_DIM)
        put(row, 10, current, curses.color_pair(C_WARN) | curses.A_BOLD)
        row += 2
        put(row, 2, rule, curses.color_pair(C_DIM)); row += 1

        # Profile list
        for i, profile in enumerate(profiles):
            if row >= h - 3:
                break
            meta = metas[profile]
            tag  = "[SSO]" if meta["sso"] else ("[role]" if meta["role"] else "")
            line_text = f"{profile:<28}  {meta['region']}"
            if tag:
                line_text += f"  {tag}"

            if i == selected:
                put(row, 2, "▶ ", curses.color_pair(C_SELECTED) | curses.A_BOLD)
                put(row, 4, line_text, curses.color_pair(C_SELECTED) | curses.A_BOLD)
            else:
                put(row, 4, line_text, curses.A_DIM)
            row += 1

        row += 1
        put(row, 2, rule, curses.color_pair(C_DIM)); row += 1
        put(row, 2, "↑↓ navigate  ·  Enter select  ·  q quit", curses.A_DIM)

        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_UP, ord('k')) and selected > 0:
            selected -= 1
        elif key in (curses.KEY_DOWN, ord('j')) and selected < len(profiles) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            return profiles[selected]
        elif key in (ord('q'), ord('Q')):
            return None


# ── Confirm screen ────────────────────────────────────────────────────────────
def confirm_profile(profile: str, meta: dict) -> bool:
    rule = "  " + "─" * 42
    print()
    print(rule)
    print(f"  \033[1mProfile:\033[0m  \033[36m{profile}\033[0m")
    print(f"  \033[1mRegion:\033[0m   {meta['region']}")
    print(f"  \033[1mOutput:\033[0m   {meta['output']}")
    if meta["sso"]:
        print(f"  \033[1mSSO:\033[0m      {meta['sso']}")
    if meta["role"]:
        print(f"  \033[1mRole:\033[0m     {meta['role']}")

    print("  \033[1mAccount:\033[0m  fetching…", end="\r", flush=True)
    acct = get_account_id(profile)
    print(f"  \033[1mAccount:\033[0m  {acct}          ")

    print(rule)
    print()
    try:
        ans = input(
            f"  \033[33mSwitch to '\033[1m{profile}\033[0m\033[33m'? [y/N]:\033[0m "
        ).strip().lower()
    except EOFError:
        return False
    return ans in ("y", "yes")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    if not AWS_CONFIG.exists():
        print(f"\033[31m  ✖  AWS config not found: {AWS_CONFIG}\033[0m")
        print( "  ✖  Create a profile first:  aws configure --profile <name>")
        sys.exit(1)

    cfg      = load_config()
    profiles = get_profiles(cfg)
    if not profiles:
        print(f"\033[31m  ✖  No profiles found in {AWS_CONFIG}\033[0m")
        sys.exit(1)

    metas   = {p: get_profile_meta(cfg, p) for p in profiles}
    current = get_current_profile()

    try:
        chosen = curses.wrapper(draw_selector, profiles, metas, current)
    except KeyboardInterrupt:
        chosen = None

    if not chosen:
        print("\n  \033[33m⚠  Aborted — no changes made.\033[0m\n")
        sys.exit(0)

    if not confirm_profile(chosen, metas[chosen]):
        print("\n  \033[33m⚠  Aborted — no changes made.\033[0m\n")
        sys.exit(0)

    update_zshrc(chosen)

    print(f"\n  \033[32m✔  AWS_PROFILE set to '\033[1m{chosen}\033[0m\033[32m' in {ZSHRC}\033[0m")
    if ZSHRC_BAK.exists():
        print(f"  \033[32m✔  Backup saved  →  {ZSHRC_BAK}\033[0m")
    print(f"\n  \033[33m⚠  Run \033[1msource ~/.zshrc\033[0m\033[33m to apply in your current shell.\033[0m\n")


if __name__ == "__main__":
    main()
