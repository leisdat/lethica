# Termux shell & terminal setup (zsh + p10k + productivity tools)

Full "make Termux enak" recipe — verified working on Android/Termux, aarch64.

## Install stack
```
pkg install -y zsh fzf zoxide eza bat nano
git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git ~/.oh-my-zsh
git clone --depth=1 https://github.com/romkatv/powerlevel10k.git ~/.oh-my-zsh/custom/themes/powerlevel10k
git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions ~/.oh-my-zsh/custom/plugins/zsh-autosuggestions
git clone --depth=1 https://github.com/zsh-users/zsh-syntax-highlighting ~/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting
```

## .zshrc essentials
- `ZSH_THEME="powerlevel10k/powerlevel10k"`, plugins: `git zsh-autosuggestions zsh-syntax-highlighting z`
- `POWERLEVEL9K_DISABLE_CONFIGURATION_WIZARD=true` — skip the interactive first-run wizard (it can't run headless; user can run `p10k configure` later)
- `POWERLEVEL9K_DISABLE_GITSTATUS=true` — REQUIRED on Termux, see gotcha below
- `eval "$(zoxide init zsh)"`
- `source <(fzf --zsh)` — fzf ≥0.73 ships a native `fzf --zsh` binding (replaces old ctrl-t/ctrl-r scripts)
- Aliases: `ls`/`ll`/`la`/`tree` → `eza --color=always --icons=auto ...`, `cat` → `bat`
- NOTE: do NOT `export SHELL=...` in .zshrc — chsh's symlink handles login shell; overriding SHELL confuses some tools.

## GOTCHA 1 — gitstatusd does NOT run on Termux (bionic vs glibc)
- p10k's `gitstatusd` official binaries are built for Linux **glibc**; Termux uses Android's **bionic** linker. Executing yields `Could not find a PHDR: broken executable?`.
- Do not waste time downloading `gitstatusd-linux-aarch64` from releases — it will not run.
- Fix: `POWERLEVEL9K_DISABLE_GITSTATUS=true`. Prompt falls back to plain `git status` detection — still shows branch/dirty/stash. Fine for normal repos; slower only on huge monorepos.
- Without this flag every shell start prints `[ERROR]: gitstatus failed to initialize.` — looks like a broken install but is expected on Termux.

## GOTCHA 2 — p10k gitstatus ./install silently fails
- `~/.oh-my-zsh/custom/themes/powerlevel10k/gitstatus/install` mktemp's under `/tmp`, which is NOT writable in Termux (known quirk — use `$HOME` for scratch). It prints nothing and exits non-zero with usrbin/ left empty.
- Same `/tmp` trap applies to any installer script that mktemp's under /tmp — set `TMPDIR=$HOME` or download artifacts manually.

## GOTCHA 3 — how chsh actually works in modern Termux
- There is NO `/etc/passwd` (and no `$PREFIX/etc/passwd`). `chsh -s zsh` writes a symlink `~/.termux/shell -> $PREFIX/bin/zsh`.
- Verify with `ls -la ~/.termux/shell`, NOT `grep $(whoami) /etc/passwd` (fails: no such file).
- `$SHELL` in an already-open bash session still shows bash until a fresh login — expected.

## Extra keys row + UI tweaks
- `~/.termux/termux.properties`:
  ```
  extra-keys = [['ESC','/','-','HOME','UP','END','PGUP'],['TAB','CTRL','ALT','LEFT','DOWN','RIGHT','PGDN']]
  bell-character = ignore
  cursor-blink = true
  cursor-style = bar
  font-size = 14
  use-black-ui = true
  ```
- Apply with `termux-reload-settings`. Most keys apply instantly; `use-black-ui`/`fullscreen` want a full app restart (swipe from recents).
- Nerd-font icons (p10k, eza icons): drop a `.ttf` at `~/.termux/font.ttf` + `termux-reload-settings`.

## Testing the setup headless
- `zsh -ic '...'` and `printf '...' | zsh -i` both emit benign `can't change option: zle` / `can't change option: monitor` warnings — these come from autosuggestions/highlighting plugins when zsh has no real TTY. NOT a real-session problem; grep them out when asserting prompt health.

## Verification checklist after setup
- `ls -la ~/.termux/shell` → points at zsh
- `printf 'alias ll | head -2; exit\n' | zsh -i` → alias resolves, no `gitstatus failed` line
- prompt shows `user@host  dir  git-branch` (git info present = p10k working without gitstatusd)
