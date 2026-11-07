# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Cisco NSO 6.4 service package, `dia` (Direct Internet Access). The repo wraps the package: `dia/` is the NSO package itself (it's what gets tarred and loaded); everything else is build, test and release tooling.

**Current state:** v1.1.0, Cisco IOS only. `/ncs:services/dia{customer-name service-id}/provider-edge/device{name}/interface{name}` with:

- `description`, `ipv4-address` (CIDR), `port-mode`, `vlan-id` (sub-interface `<intf>.<vlan-id>` when `port-mode false`) → interface description/IP (+ `encapsulation dot1Q`) and `router isis 1 / passive-interface` (template `dia-template.xml`). `router isis 1` must pre-exist (validated in `network.py`; template uses `tags="nocreate"`).
- Optional `static/ipv4-destination-prefix{ipv4-prefix}` with `ipv4-forwarding` → `ip route` + `ip prefix-list CUSTOMER-STATIC seq N permit <prefix>` (template `dia-static.xml`). `premod.py` allocates N (lowest free multiple of 10 across the device's prefix-list **and** all DIA instances in the transaction) into hidden leaf `prefix-list-seq`; it's never reallocated. `cb_create` validates next-hop in the interface subnet and that no foreign CUSTOMER-STATIC entry already uses the seq or permits the prefix.

Netsim lab quirks: The IOS NED quotes descriptions in native dry-run output (`description "x"`) and adds its own defaults (`no shutdown`, `no switchport`) to new interfaces, so assert one CLI line at a time. ios-0 gets regenerated from time to time, sometimes from real lab config with different interfaces (new SSH host key → `devices device ios-0 ssh fetch-host-keys`). Check its interfaces before running tests. Tests currently use ios-0 `GigabitEthernet2/0` (port) and `GigabitEthernet2/1.300` (sub); `conftest.py` creates `router isis 1` on ios-0 if missing.

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
- `dia/python/dia/main.py`: `Main.setup()` registers `ServiceCallbacks` on `dia-servicepoint` and the `dia-interface-name` completion action. `cb_pre_modification` (skipped on delete) runs `PreMod.fill()` to allocate prefix-list sequence numbers. `cb_create` runs inside FASTMAP and calls `Dia.configure()` (`dia.py`), which applies `dia-template` per interface and `dia-static` per static route. Component class wired in `dia/package-meta-data.xml` (`dia.main.Main`).
- `network.py`: pure helpers (interface/IP parsing, next-hop check, `get_next_seq`) are module-level; `Network` methods read device config (IS-IS, interface-in-use, prefix-list checks).
- After changing YANG: `make all`, then `packages reload` in NSO. Python/template-only changes need just `packages reload` (or `redeploy` of the package).

## Release

Conventional Commits on `main` drive release-please (`.release-please-config.json`, type `simple`, `v`-prefixed tags), which writes `CHANGELOG.md` (never hand-edit) and on release dispatches `package-artifact.yml`, which tars the **contents** of `dia/` into `dia-<version>.tar.gz` + sha256 and attaches them to the GitHub release. Bump `<package-version>` in `dia/package-meta-data.xml` in the same change, matching the commit's semver level.
