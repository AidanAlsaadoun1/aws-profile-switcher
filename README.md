# aws-profile-switcher

> Interactive terminal AWS profile switcher written in Python.

Reads from `~/.aws/config` and updates `AWS_PROFILE` in your `~/.zshrc` — with live profile previews, region/account details, and automatic backups.

---

## Features

- **Active profile display** — shows your current `AWS_PROFILE` on launch
- **Interactive TUI** — navigate with `↑ ↓` arrow keys (or `j` / `k`), no mouse required
- **Profile preview** — region, output format, SSO URL, role ARN, and live AWS account ID before you commit
- **Safe `.zshrc` updates** — updates `export AWS_PROFILE=` in place, or appends if missing
- **Automatic backup** — saves `~/.zshrc.bak` before every write
- **SSO & role-aware** — tags profiles that use SSO or role assumption
- **Zero dependencies** — uses only the Python standard library

---

## Requirements

| Requirement      | Notes                                             |
| ---------------- | ------------------------------------------------- |
| Python 3.10+     | Pre-installed on macOS 12+                        |
| `curses`         | Included in the Python standard library           |
| `~/.aws/config`  | Must exist with at least one profile              |
| `aws` CLI        | Optional — only needed for live account ID lookup |
| Zsh + `~/.zshrc` | Created automatically if missing                  |

---

## Installation

```bash
git clone https://github.com/<your-username>/aws-profile-switcher.git
cd aws-profile-switcher

mkdir -p ~/scripts
cp aws-profile-switcher.py ~/scripts/
chmod +x ~/scripts/aws-profile-switcher.py
```

Optionally install globally:

```bash
sudo cp ~/scripts/aws-profile-switcher.py /usr/local/bin/aws-switch
```

---

## Recommended Setup

A child process can't export variables back into the parent shell, so wrap the script in a zsh function that `source`s `~/.zshrc` automatically when it exits cleanly:

```zsh
# Add to ~/.zshrc
aws-switch() {
  python3 ~/scripts/aws-profile-switcher.py && source ~/.zshrc
}
```

Then just run:

```bash
aws-switch
```

> If you also installed the script globally as `/usr/local/bin/aws-switch`, pick one or the other — the shell function and the binary share a name, and the function will win.

---

## Usage

```bash
python3 ~/scripts/aws-profile-switcher.py
# or, if installed globally:
aws-switch
```

### Controls

| Key                    | Action                     |
| ---------------------- | -------------------------- |
| `↑` / `↓` or `k` / `j` | Navigate the profile list  |
| `Enter`                | Select highlighted profile |
| `q` / `Ctrl+C`         | Cancel — no changes made   |

---

## How It Works

1. **Profile discovery** — parses `~/.aws/config` for `[profile <name>]` and `[default]` blocks. `default` is listed first; the rest are sorted alphabetically.
2. **Active profile display** — checks `$AWS_PROFILE` first, then falls back to reading `~/.zshrc`.
3. **Interactive TUI** — profiles are listed with their region and tagged `[SSO]` or `[role]` where applicable.
4. **Detail preview** — after you pick a profile, the script shows region, output, SSO/role, and live account ID via `aws sts get-caller-identity`.
5. **Confirmation** — you must confirm with `y` before anything is written.
6. **`.zshrc` update** — either updates the existing `export AWS_PROFILE=` line in place, or appends a new one with a comment header. A backup is written to `~/.zshrc.bak` first.

---

## File Locations

| File            | Purpose                                             |
| --------------- | --------------------------------------------------- |
| `~/.aws/config` | Source of all profiles (names, regions, SSO, roles) |
| `~/.zshrc`      | Modified to persist `AWS_PROFILE`                   |
| `~/.zshrc.bak`  | Backup taken before each modification               |

Override the config path with the standard AWS environment variable:

```bash
export AWS_CONFIG_FILE=~/.aws/config
```

---

## Security Notes

- The script **never reads or logs credentials** — only profile names and non-secret config values.
- Account ID lookup uses `aws sts get-caller-identity`, a read-only API call.
- `.zshrc.bak` is overwritten on every run. Copy it elsewhere if you want history.

---

## Troubleshooting

**No profiles found**

```bash
aws configure --profile profile-test
```

**`No such file or directory` when running `aws-switch`**

The wrapper function expects the script at `~/scripts/aws-profile-switcher.py`. Re-run the installation steps, or edit the path inside the `aws-switch()` function.

**Arrow keys not working**

Ensure your terminal sends standard ANSI escape codes (default in iTerm2, Terminal.app, GNOME Terminal, etc.).

**Account ID shows `n/a`**

Either the `aws` CLI isn't installed or the profile has no valid credentials. Everything else still works normally.

---

## Development

> Only relevant if you're contributing or modifying the script. The script itself has **no runtime dependencies** — everything below is for tests only.

### Repo layout

```
aws-profile-switcher/
├── aws-profile-switcher.py     # the script (stdlib only)
├── tests/
│   ├── conftest.py             # loads the hyphenated script as a module
│   └── test_aws_profile_switcher.py
├── requirements-dev.txt        # pytest, for tests
├── README.md
└── .gitignore
```

### Setup

Use a virtualenv so dev tools don't leak into your global Python:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Run the tests

```bash
pytest
```

Expected output:

```
============================== 30 passed in 0.03s ==============================
```

### What's covered

- Profile discovery and sort order (`default` first, rest alphabetical)
- Profile metadata extraction (region, output, SSO URL, role ARN)
- Active-profile detection from `$AWS_PROFILE` and from `~/.zshrc` (quoted and unquoted forms)
- `.zshrc` updates: in-place replace, append-when-missing, create-when-absent, and the trailing-newline edge case
- Backup file creation
- Account ID lookup with the `aws` CLI **mocked** — no real AWS calls or credentials needed
- Export-line regex against valid and invalid forms

All tests are sandboxed into pytest's `tmp_path`, so they never touch your real `~/.aws/config` or `~/.zshrc`.

---

## License

MIT — see [LICENSE](LICENSE).
