# Historical BTIDE implementation evidence

This records the original import, not the current PiG installer or its validation. See README.md for current behavior.

State: complete.

Implementation commit: `86d9ab3e7bcb31b3ed9412078f38cfc1d864170e`

## Completed items

- [x] Copy relevant portable IDE source and configuration into BTIDE without generated archives, installed dependencies, or private runtime state.
- [x] Update README, third-party notices, license links, and upstream attribution.
- [x] Replace private vendor snapshots with upstream Ouro, smart-approve-lancet, and pi-curator integration.
- [x] Update launcher tests to exercise the `btide` command.
- [x] Track `main` for all three source integrations.
- [x] Resolve current stable software releases and refresh dependencies, retaining minimum-only BTIDE version requirements rather than repository release/lock snapshots.
- [x] Add `VERSION` containing `0.1.0` and use it in the executable `install.sh` entry point.
- [x] Add executable `uninstall.sh` for safe removal of the managed `btide` launcher, preserving tools, configuration, user data, and running sessions.
- [x] Document quick installation with curl, a permanent checkout, prerequisites, and existing-directory protection.

## Checks and results

- `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v`: **81 tests passed** before the implementation commit. Includes actual tmux launcher interaction, runtime integrity, minimum-version boundaries, release discovery, safe archive handling, reverse synchronization, and isolated-home uninstallation.
- `bash -n bootstrap.sh install.sh uninstall.sh config/btide.sh`: passed.
- `zsh -n config/btide.sh`, `zsh -n config/zsh/zshrc`, and `zsh -n config/zsh/p10k.zsh`: passed.
- `git diff --cached --check`: passed before commit after removing two whitespace defects in the imported zsh templates.
- `./install.sh --version`: printed `0.1.0`; installer and uninstaller help paths executed successfully.
- Real entry-point smoke in an isolated home: loaded the launcher, removed it through `uninstall.sh`, confirmed a fresh shell starts successfully without `btide`, and repeated uninstallation successfully.
- Earlier in that session, full Linux x86_64 isolated-home provisioning passed with actual upstream runtime downloads, a tmux source build, the legacy agent stack, all three original source integrations with updated libraries, shell frameworks, editor plugins/Mason tools/Tree-sitter parsers, and the final offline integrity check. Unchanged runtime archives were reused on a second pass.
- Curl README recipe smoke: shell syntax, downloading/extracting a real local archive of the project, invoking the extracted version entry point, archive cleanup, and refusing an existing destination all passed. The smoke used a local archive and `--version`, not a live GitHub download or system package installation.
- Implementation commit message verified with `git log -1 --format=%B`; full SHA recorded above.

## Result and limits

The implementation and its tests are committed together. BTIDE-managed releases use current stable upstream versions; distro-managed applications use configured package repositories and upstream dependency compatibility constraints still apply. No nightly policy or automatic host-wide upgrade was added.

Uninstallation is launcher-only. Already-loaded shell functions require a new shell or `unset -f btide btide_reload btide_close`. Foreign launcher files, unsafe environment paths, and unrecognized edited environment references are refused rather than deleted.

Authenticated model calls, external quality services, real distribution package transactions, and aarch64 execution were not verified. The full provisioning smoke preceded the final whitespace-only zsh cleanup; final template syntax checks passed afterward.
