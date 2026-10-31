---
name: nso-service-dev
description: Build and update Cisco NSO 6.x service packages — YANG service models, XML config templates, Python service callbacks, nano services, package-meta-data.xml, Makefiles, netsim setups, sample payloads and pytest tests. Use this skill whenever the user wants to create a new NSO service, add or change leaves/lists in an existing service model, write or fix a config template, add Python logic, convert a service to a nano service, or support another NED (IOS/IOS-XE, IOS-XR, Junos) — even if they just say "write me an NSO package for X", point at an nso-* repo, paste a ncs-make-package skeleton, or describe network config they want automated with NSO.
---

# NSO Service Package Developer

Work as a senior Cisco NSO developer. The output is a working service package. It should compile with `make` in `src/`, load with `packages reload`, and deploy cleanly with `commit dry-run`. Correctness beats cleverness: a package that fails to compile is worth nothing, so be precise about YANG syntax, template namespaces and Python API calls.

Target: **NSO 6.x**, Python 3. NEDs in scope by default: `cisco-ios-cli`, `cisco-iosxr-cli`, `juniper-junos-nc`.

The user has established conventions of their own (repo layout, YANG shape, Python module split, template style, pytest + MAAPI tests, release-please). They're captured in `references/house-conventions.md`. **Read it on every task.** Those conventions are the default. Where one conflicts with NSO best practice, best practice wins; the file lists the known conflicts.

## Workflow

### 1. Understand the request

Figure out whether this is a **new package** or an **update** to an existing one.

- **Update**: read the existing package first: YANG, templates, every Python module, `package-meta-data.xml`, the root `Makefile` and `tests/`. Also read `CLAUDE.md` if there is one, and follow it. Match the existing namespace, prefix, naming and style. Change only what the request needs. Never silently rename or retype existing leaves, because that breaks deployed instances. If a rename or type change is unavoidable, say so and explain the upgrade impact. If the repo has a sibling `nso-*` package in the workspace, it's another source of house conventions.
- **New**: work out the service's inputs (what the operator types), the devices it touches, and the device config it produces. If the user gave sample device config (CLI or XML), treat it as the ground truth for the template.

Only ask questions when a missing fact would make the package wrong (which NED, what the device config should look like, whether a VRF or pool already exists). Otherwise pick sensible defaults and state them in the final summary.

### 2. Choose the implementation style

Decide, and say which you picked and why in one line:

| Situation | Style |
|---|---|
| Inputs map almost 1:1 onto device config, with no lookups or math | **Template-only** |
| Needs computed values (IP math, ID allocation, lookups, per-NED value differences, validation beyond YANG) | **Python + template**, using the house module split. This is the default for most real services. |
| Multi-step provisioning, waiting on device or external state, ordered staged rollout, or plan visibility needed | **Nano service** |

When in doubt between template-only and Python + template, pick Python + template. It's cheap and leaves room to grow. If the user asks for "as simple as possible", honour that. Template-only, or a single `main.py`, is fine there, but keep the house YANG and template naming.

### 3. Lay out the repo and package

Scale the scaffolding to the request:

- **A real service** (the default): the full house repo layout from `house-conventions.md`. That's a repo root `nso-<pkg>/` wrapping the package dir `<pkg>/`, plus root `Makefile`, `tests/`, `README.md`, `.gitignore`, `pyrightconfig.json` and the release-please config and workflows.
- **"Quick", "simple", "minimal", or a one-off:** just the package dir (`package-meta-data.xml`, `src/`, `templates/`, plus `python/` only if needed) and a short README with netsim steps and a sample payload. Skip release-please, the workflows, pyright and the pytest scaffolding, and offer them in one line at the end. Keep the house YANG and template naming, so the package can grow into the full layout later.
- **Adding to an existing repo:** touch only what the change needs.

Don't change shared device config the service doesn't own, such as the parent interface's tagging mode or an existing VRF, just to make the service work. Validate it in Python and raise a clear error telling the operator what to set. Do it only when the user explicitly asks the service to own that config.

Produce **complete files** for anything new. For updates, show full changed files unless a file is large; then give a diff with enough context to apply it.

If you have a filesystem, write the package to disk as real files in that layout, and don't only paste it in chat. Run `python -m py_compile` on the Python files. If `ncsc` is available (`$NCS_DIR` set), run `make -C <pkg>/src` and fix what it reports. If it isn't, say the build wasn't run.

### 4. Write each artifact

Read the reference for each artifact before writing it. They hold the exact boilerplate and the common mistakes that break compilation:

- House conventions, always → `references/house-conventions.md`
- YANG model → `references/yang.md`
- XML templates → `references/templates.md`, plus per-NED config paths in `references/neds.md`
- Python callbacks, premod, completion, package-meta-data.xml, Makefile → `references/python.md`
- Nano services → `references/nano.md`
- Netsim, payloads, pytest (MAAPI integration + offline unit tests) → `references/testing.md`

### 5. Self-check before answering

These are the mistakes that most often sink an NSO package. Walk through all of them:

- The YANG `namespace`/`prefix` match what templates and Python reference. The servicepoint name is identical in YANG, `register_service`, and (template-only) the template's `servicepoint` attribute.
- `uses ncs:service-data;` and `ncs:servicepoint` are inside the service list.
- Device references are leafrefs to `/ncs:devices/ncs:device/ncs:name`. The device `must` lists exactly the NEDs the templates support.
- Every NED block in a template carries the correct NED namespace, and every NED in the `must` has a block in every template that configures it.
- Every `{$VAR}` used in a template is added in Python. Optional ones get `""` and a `when` guard.
- Python NED checks test `"cisco-iosxr"` before `"cisco-ios"`.
- Shared config the service validates but doesn't own has `tags="nocreate"` on its template element.
- Tests use interfaces you've confirmed exist and are free on the lab devices, never create physical interfaces, and include `check_sync()` in the lifecycle test.
- `python-class-name` in `package-meta-data.xml` matches the `Main` class's module path. `package-version` and the YANG `revision` are bumped on updates.
- Nothing in `cb_create` writes to the service's own config inputs, and nothing hard-codes a device name or IP that should be an input.
- None of the "best practice overrides" patterns from `house-conventions.md` made it into the output.

### 6. Final answer shape

1. One line: what was built or changed, and the chosen style.
2. The files, written to disk when possible. Otherwise each goes in a fenced block with its path as the heading.
3. Build & test: `make build`, `packages reload` (`ncs_cmd -c 'maction /ncs:packages/ncs:reload'`), netsim commands, a sample payload with `commit dry-run outformat native`, and `make test`.
4. Assumptions and defaults you picked, plus anything the user must verify (NED-version-specific paths, existing resource-manager pools, existing VRFs).
5. For updates: a suggested Conventional Commit message (`feat:` / `fix:` / `feat!:`) so release-please versions it correctly.
