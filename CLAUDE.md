# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Cisco NSO 6.4 service package, `dia` (Direct Internet Access). The repo wraps the package: `dia/` is the NSO package itself (it's what gets tarred and loaded); everything else is build, test and release tooling.

**Current state:** v1.0.0, Cisco IOS only. `/ncs:services/dia{customer-name service-id}/provider-edge/device{name}/interface{name}` with `description`, `ipv4-address` (CIDR), `port-mode`, `vlan-id` (sub-interface `<intf>.<vlan-id>` when `port-mode false`). Renders interface description/IP (+ `encapsulation dot1Q`) and `router isis 1 / passive-interface`. `router isis 1` must pre-exist (validated in `network.py`; template uses `tags="nocreate"`). Single template `dia-template.xml`; no premod.

Netsim lab quirk: The IOS NED quotes descriptions in native dry-run output (`description "x"`).

For any YANG/template/Python/test work, use the project skill `nso-service-dev` (`.claude/skills/nso-service-dev/`). Its `references/house-conventions.md` defines the expected package structure (thin `main.py` + `context.py`/`device.py`/`network.py`/`premod.py`/`completion.py`, `augment /ncs:services`, `customer-name service-id` keys, one template per feature, UPPER-KEBAB-CASE template vars, etc.) and lists reference-package anti-patterns not to copy.

## Commands

Requires a sourced NSO install (`$NCS_DIR`; local is 6.4.11, see `pyrightconfig.json`).

```sh
make all        # compile YANG -> dia/load-dir/*.fxs (via dia/src/Makefile, ncsc --fail-on-warnings)
make clean      # remove dia/load-dir
make test       # create tests/.venv, pip install, pytest tests/ -v, delete venv
```

Tests are integration tests against a **running NSO** over MAAPI (user `admin`, context `python`), with the package loaded and netsim devices `ios-0`/`ios-1` present. `conftest.py` auto-creates/removes customer `pytest-customer`. Single test, reusing a venv:

```sh
python3 -m venv tests/.venv && tests/.venv/bin/pip install -r tests/requirements.txt
tests/.venv/bin/pytest tests/test_service.py::test_service_lifecycle -v
```

The `ncs` Python module must be importable (`$NCS_DIR/src/ncs/pyapi` on `PYTHONPATH`, normally set by `ncsrc`).

`dia/test/internal/lux/` is skeleton lux scaffolding; not used.

## Architecture

- `dia/src/yang/dia.yang` declares `ncs:servicepoint dia-servicepoint`.
- `dia/python/dia/main.py`: `Main.setup()` registers `ServiceCallbacks` on `dia-servicepoint`; `cb_create` runs inside FASTMAP and applies `dia-template` (`dia/templates/dia-template.xml`) with variables. Component class wired in `dia/package-meta-data.xml` (`dia.main.Main`).
- After changing YANG: `make all`, then `packages reload` in NSO. Python/template-only changes need just `packages reload` (or `redeploy` of the package).

## Release

Conventional Commits on `main` drive release-please (`.release-please-config.json`, type `simple`, `v`-prefixed tags), which writes `CHANGELOG.md` (never hand-edit) and on release dispatches `package-artifact.yml`, which tars the **contents** of `dia/` into `dia-<version>.tar.gz` + sha256 and attaches them to the GitHub release. Bump `<package-version>` in `dia/package-meta-data.xml` in the same change, matching the commit's semver level.
