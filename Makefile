.DEFAULT_GOAL := install

INSTALL_ARGS ?=
# Keep options literal through Make and parse them as arguments, not shell code.
override INSTALL_ARGS := $(value INSTALL_ARGS)
export INSTALL_ARGS

.PHONY: install
install:
	@python3 -c 'import os, shlex; os.execvp("bash", ["bash", "./install.sh", *shlex.split(os.environ.get("INSTALL_ARGS", ""))])'
