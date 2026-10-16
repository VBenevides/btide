# Third-party notices

BTIDE is licensed under the MIT License; see [LICENSE](LICENSE). It configures, installs, and in some cases redistributes the software below. Each component keeps its own license and copyright. This file credits the authors and does not relicense their work.

Bootstrap uses current stable upstream releases or current Git branches, without repository version pins. Installed versions and commits are recorded locally. Distribution-managed components use packages available from configured distribution repositories. Components are not stored here unless the table says so.

## Credits

| Component | Authors | License | How BTIDE uses it |
| --- | --- | --- | --- |
| [PiG / pig-plugins](https://github.com/VBenevides/pig-plugins) | Vinicius Benevides and contributors | MIT | Existing executable reused, or installed lazily with its upstream installer on first tab selection. |
| [tmux](https://github.com/tmux/tmux) | Nicholas Marriott and contributors | ISC | Current system executable or latest stable upstream source build. |
| [lazygit](https://github.com/jesseduffield/lazygit) | Jesse Duffield and contributors | MIT | Latest stable release, running in the Git window. |
| [Ranger](https://github.com/ranger/ranger) | Roman Zimbelmann and contributors | GPL-3.0 | Installed from the system package manager. It runs in the Ranger window. BTIDE does not copy or modify its code. |
| [LazyVim](https://github.com/LazyVim/LazyVim) | Folke Lemaitre and contributors | Apache-2.0 | `config/nvim/` is based on the LazyVim starter template. The LazyVim plugin loads at runtime. |

## Also installed or bundled

| Component | License | Note |
| --- | --- | --- |
| [Neovim](https://github.com/neovim/neovim) | Apache-2.0 (with parts under Vim's license) | Current system executable or latest stable upstream release. |
| [Kitty](https://github.com/kovidgoyal/kitty) | GPL-3.0 | Optional: installed with `--include kitty`. BTIDE ships only a configuration file for it. |
| MesloLGS Nerd Font Mono Regular (`config/misc/`) | See below | Font file included in this repository; deployed only with `--include kitty`. |
| [Go](https://go.dev/) | BSD-3-Clause | Current system compiler or latest stable upstream toolchain. |
| [Node.js](https://github.com/nodejs/node) | MIT and bundled third-party licenses | Current system runtime or latest stable upstream release. |


## MesloLGS Nerd Font Mono

`config/misc/MesloLGSNerdFontMono-Regular.ttf` is a Nerd Font build of Meslo LG. The font file contains these copyright notices:

- Copyright (c) 2009 Apple Inc.
- Copyright (c) 2006 Tavmjong Bah.
- Copyright (c) 2003 Bitstream, Inc. All Rights Reserved.

The font file does not contain a license text, and this repository has not confirmed the license terms against the upstream distribution. Check the [Powerlevel10k font notes](https://github.com/romkatv/powerlevel10k#fonts) and the upstream Meslo LG license before you redistribute the font.

## License texts

The full license text of each component is in its upstream repository or in the installed copy. `config/nvim/LICENSE` is the Apache-2.0 text that accompanies the LazyVim starter template. The MIT copyright lines in the table above are taken from the upstream license files.
