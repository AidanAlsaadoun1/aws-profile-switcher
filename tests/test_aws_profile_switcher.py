"""Tests for aws-profile-switcher.

No live AWS calls or real `~/.zshrc` edits are made — everything is sandboxed
into `tmp_path` and the `aws` CLI is mocked.
"""

import subprocess
from unittest import mock

import pytest

import aws_profile_switcher as aps


# ── load_config / get_profiles ────────────────────────────────────────────────

def _write_config(tmp_path, monkeypatch, text):
    cfg = tmp_path / "config"
    cfg.write_text(text)
    monkeypatch.setattr(aps, "AWS_CONFIG", cfg)
    return cfg


def test_get_profiles_sorts_with_default_first(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, """
[default]
region = us-east-1

[profile zeta]
region = eu-west-1

[profile alpha]
region = us-west-2

[profile beta]
region = ap-south-1
""")
    cfg = aps.load_config()
    assert aps.get_profiles(cfg) == ["default", "alpha", "beta", "zeta"]


def test_get_profiles_no_default(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, """
[profile prod]
region = us-east-1

[profile dev]
region = us-west-2
""")
    cfg = aps.load_config()
    assert aps.get_profiles(cfg) == ["dev", "prod"]


def test_get_profiles_empty_config(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "")
    cfg = aps.load_config()
    assert aps.get_profiles(cfg) == []


# ── get_profile_meta ──────────────────────────────────────────────────────────

def test_get_profile_meta_full(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, """
[profile prod]
region = us-east-1
output = json
sso_start_url = https://example.awsapps.com/start
role_arn = arn:aws:iam::123456789012:role/Admin
""")
    cfg = aps.load_config()
    assert aps.get_profile_meta(cfg, "prod") == {
        "region": "us-east-1",
        "output": "json",
        "sso":    "https://example.awsapps.com/start",
        "role":   "arn:aws:iam::123456789012:role/Admin",
    }


def test_get_profile_meta_defaults_when_keys_missing(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "[profile bare]\n")
    cfg = aps.load_config()
    assert aps.get_profile_meta(cfg, "bare") == {
        "region": "n/a", "output": "n/a", "sso": "", "role": "",
    }


def test_get_profile_meta_default_profile(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "[default]\nregion = eu-west-1\n")
    cfg = aps.load_config()
    meta = aps.get_profile_meta(cfg, "default")
    assert meta["region"] == "eu-west-1"
    assert meta["output"] == "n/a"


def test_get_profile_meta_unknown_profile(tmp_path, monkeypatch):
    _write_config(tmp_path, monkeypatch, "")
    cfg = aps.load_config()
    assert aps.get_profile_meta(cfg, "ghost") == {
        "region": "n/a", "output": "n/a", "sso": "", "role": "",
    }


# ── get_current_profile ───────────────────────────────────────────────────────

def test_get_current_profile_prefers_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AWS_PROFILE", "from-env")
    monkeypatch.setattr(aps, "ZSHRC", tmp_path / "missing-zshrc")
    assert aps.get_current_profile() == "from-env"


def test_get_current_profile_from_zshrc_unquoted(monkeypatch, tmp_path):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    zshrc = tmp_path / "zshrc"
    zshrc.write_text("# header\nexport AWS_PROFILE=dev\nalias l=ls\n")
    monkeypatch.setattr(aps, "ZSHRC", zshrc)
    assert aps.get_current_profile() == "dev"


def test_get_current_profile_from_zshrc_double_quoted(monkeypatch, tmp_path):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    zshrc = tmp_path / "zshrc"
    zshrc.write_text('export AWS_PROFILE="staging"\n')
    monkeypatch.setattr(aps, "ZSHRC", zshrc)
    assert aps.get_current_profile() == "staging"


def test_get_current_profile_from_zshrc_single_quoted(monkeypatch, tmp_path):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    zshrc = tmp_path / "zshrc"
    zshrc.write_text("export AWS_PROFILE='qa-eu'\n")
    monkeypatch.setattr(aps, "ZSHRC", zshrc)
    assert aps.get_current_profile() == "qa-eu"


def test_get_current_profile_returns_none_when_nothing_set(monkeypatch, tmp_path):
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setattr(aps, "ZSHRC", tmp_path / "no-zshrc")
    assert aps.get_current_profile() == "none"


# ── update_zshrc ──────────────────────────────────────────────────────────────

@pytest.fixture
def zshrc_paths(tmp_path, monkeypatch):
    zshrc = tmp_path / "zshrc"
    bak   = tmp_path / "zshrc.bak"
    monkeypatch.setattr(aps, "ZSHRC", zshrc)
    monkeypatch.setattr(aps, "ZSHRC_BAK", bak)
    return zshrc, bak


def test_update_zshrc_replaces_existing_line(zshrc_paths):
    zshrc, _ = zshrc_paths
    zshrc.write_text("# top\nexport AWS_PROFILE=old\nalias l=ls\n")

    aps.update_zshrc("new")

    content = zshrc.read_text()
    assert "export AWS_PROFILE=new\n" in content
    assert "export AWS_PROFILE=old" not in content
    assert "alias l=ls" in content  # surrounding lines preserved


def test_update_zshrc_creates_backup_before_write(zshrc_paths):
    zshrc, bak = zshrc_paths
    original = "export AWS_PROFILE=old\n"
    zshrc.write_text(original)

    aps.update_zshrc("new")

    assert bak.exists()
    assert bak.read_text() == original


def test_update_zshrc_appends_when_no_existing_line(zshrc_paths):
    zshrc, _ = zshrc_paths
    zshrc.write_text("# existing config\nalias l=ls\n")

    aps.update_zshrc("dev")

    content = zshrc.read_text()
    assert "alias l=ls" in content
    assert "export AWS_PROFILE=dev\n" in content
    assert "# AWS Profile" in content


def test_update_zshrc_creates_file_when_missing(zshrc_paths):
    zshrc, bak = zshrc_paths
    assert not zshrc.exists()

    aps.update_zshrc("dev")

    assert zshrc.exists()
    assert "export AWS_PROFILE=dev\n" in zshrc.read_text()
    # No backup for a fresh file.
    assert not bak.exists()


def test_update_zshrc_handles_missing_trailing_newline(zshrc_paths):
    """Regression: appending must not glue the new header onto the last line."""
    zshrc, _ = zshrc_paths
    zshrc.write_text("alias l=ls")  # no trailing \n

    aps.update_zshrc("dev")

    content = zshrc.read_text()
    assert "alias l=ls\n" in content
    assert "# AWS Profile" in content
    assert "export AWS_PROFILE=dev\n" in content
    # The original line must be standalone, not concatenated with the header.
    assert "alias l=ls# AWS" not in content


# ── get_account_id (mocked — no real AWS calls) ───────────────────────────────

def test_get_account_id_returns_na_when_cli_missing(monkeypatch):
    monkeypatch.setattr(aps.shutil, "which", lambda _: None)
    assert aps.get_account_id("prod") == "n/a"


def test_get_account_id_parses_stdout(monkeypatch):
    monkeypatch.setattr(aps.shutil, "which", lambda _: "/usr/local/bin/aws")
    fake = mock.Mock(returncode=0, stdout="123456789012\n")
    monkeypatch.setattr(aps.subprocess, "run", lambda *a, **kw: fake)
    assert aps.get_account_id("prod") == "123456789012"


def test_get_account_id_handles_nonzero_exit(monkeypatch):
    monkeypatch.setattr(aps.shutil, "which", lambda _: "/usr/local/bin/aws")
    fake = mock.Mock(returncode=255, stdout="")
    monkeypatch.setattr(aps.subprocess, "run", lambda *a, **kw: fake)
    assert aps.get_account_id("prod") == "n/a"


def test_get_account_id_handles_timeout(monkeypatch):
    monkeypatch.setattr(aps.shutil, "which", lambda _: "/usr/local/bin/aws")

    def _timeout(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="aws", timeout=10)

    monkeypatch.setattr(aps.subprocess, "run", _timeout)
    assert aps.get_account_id("prod") == "n/a"


# ── Regex sanity ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("line,expected", [
    ("export AWS_PROFILE=prod",          "prod"),
    ('export AWS_PROFILE="prod"',        "prod"),
    ("export AWS_PROFILE='prod-eu'",     "prod-eu"),
    ("  export AWS_PROFILE=prod  ",      "prod"),
    ("export  AWS_PROFILE = prod",       "prod"),
])
def test_export_value_regex_matches(line, expected):
    m = aps.EXPORT_VALUE_RE.match(line)
    assert m is not None, f"expected match for: {line!r}"
    assert m.group(2) == expected


@pytest.mark.parametrize("line", [
    "# export AWS_PROFILE=prod",
    "alias aws=aws",
    "export OTHER=prod",
    "",
])
def test_export_value_regex_rejects(line):
    assert aps.EXPORT_VALUE_RE.match(line) is None