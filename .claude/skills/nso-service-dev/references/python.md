# Python service code, package-meta-data.xml, Makefile

The single-file example below shows the NSO API mechanics. For real packages, use the **house module split** from `house-conventions.md`: a thin `main.py`, `context.py`, a `<pkg>.py` service class, and `device.py` / `network.py` / `premod.py` / `completion.py`. Only go single-file when the user asks for something minimal.

## main.py (NSO 6.x), API mechanics

```python
# -*- mode: python; python-indent: 4 -*-
import ipaddress

import ncs
from ncs.application import Service


class ServiceCallbacks(Service):

    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info('Service create(service=', service._path, ')')

        for ep in service.endpoint:
            iface = ipaddress.ip_interface(f'{ep.ip_address}/{ep.prefix_length}')
            if_type, if_id = split_interface(ep.interface)

            tvars = ncs.template.Variables()
            tvars.add('DEVICE', ep.device)
            tvars.add('IF_TYPE', if_type)
            tvars.add('IF_ID', if_id)
            tvars.add('IP', str(iface.ip))
            tvars.add('MASK', str(iface.netmask))
            tvars.add('PLEN', iface.network.prefixlen)
            template = ncs.template.Template(service)
            template.apply('l3vpn-template', tvars)


def split_interface(name):
    """'GigabitEthernet0/1' -> ('GigabitEthernet', '0/1')."""
    for i, ch in enumerate(name):
        if ch.isdigit():
            return name[:i], name[i:]
    raise ValueError(f'Cannot parse interface name {name!r}')


class Main(ncs.application.Application):
    def setup(self):
        self.log.info('Main RUNNING')
        self.register_service('l3vpn-servicepoint', ServiceCallbacks)

    def teardown(self):
        self.log.info('Main FINISHED')
```

Rules:
- Keep pure helpers (parsing, IP math, ID derivation) as **module-level functions** with no `ncs` dependency so they're unit-testable without NSO. In house-layout packages they go in `network.py` (see `house-conventions.md`); only a single-file minimal package keeps them in `main.py`.
- Leaf names with `-` become `_` in Python (`ip-address` → `ep.ip_address`).
- Access other config: `root.devices.device[name].platform.name`, or `ncs.maagic.get_root(service)`.
- Raise errors to abort the commit: `raise ValueError('...')` — NSO shows the message to the operator. Validate early, before applying templates.
- Never write to CDB outside the service's transaction in `cb_create` (no `ncs.maapi.single_write_trans` inside create) — it breaks FASTMAP idempotency. Same for side effects (REST calls, IPAM allocations): use Resource Manager / nano services for those.
- `cb_create` must be deterministic: same input → same output.
- `@Service.pre_modification(self, tctx, op, kp, root, proplist)` runs before create in the same transaction. `op` is 0 for create, 1 for update and 2 for delete; return early on 2. Get the service with `ncs.maagic.cd(root, kp)`. It may write to the service's own hidden leaves (house pattern: allocate `efp-id`), because those writes aren't part of the FASTMAP diff the way writes in `cb_create` are. Keep it idempotent: only fill a leaf that's still empty.
- `@Service.post_modification`: only when it's truly needed.
- CLI completion for a leaf with `tailf:cli-completion-actionpoint X`: subclass `ncs.dp.Action`, implement `cb_completion(self, uinfo, cli_style, token, completion_char, kp, cmdpath, cmdparam_id, simpleType, extra)`, reply with `_ncs.dp.action_reply_completion(uinfo, [(0, value, " "), ...])`, and register it with `self.register_action('X', Cls)`. Get a root with `Maapi().attach(uinfo.actx_thandle, usid=uinfo.usid)` → `get_root(trans)`. Use `kp.dup_len(n)` to keep the part of the keypath leading to the device entry.
- Resource-manager ID allocation (house: RM 5.x fluent API): `Allocator(service).id(request_id=service.vpn_id).pool('<pool>').allocate(<request-key>)`. It returns the id once ready. Store it in an oper leaf, not the config input (see house-conventions overrides).
- Logging: `self.log.info/debug`. Log lands in `logs/ncs-python-vm-<pkg>.log`.

## Actions (if the service needs one)

```python
from ncs.dp import Action

class CheckAction(Action):
    @Action.action
    def cb_action(self, uinfo, name, kp, input, output, trans):
        output.result = 'ok'
# in Main.setup: self.register_action('l3vpn-check', CheckAction)
```
YANG: `tailf:action check { tailf:actionpoint l3vpn-check; output { leaf result { type string; } } }` inside the list.

## package-meta-data.xml

```xml
<ncs-package xmlns="http://tail-f.com/ns/ncs-packages">
  <name>l3vpn</name>
  <package-version>1.0</package-version>
  <description>L3VPN service</description>
  <ncs-min-version>6.0</ncs-min-version>

  <component>
    <name>main</name>
    <application>
      <python-class-name>l3vpn.main.Main</python-class-name>
    </application>
  </component>
</ncs-package>
```
- Template-only packages: no `<component>` for Python.
- If the service depends on another package (e.g., resource-manager): `<required-package><name>resource-manager</name></required-package>`.
- Bump `package-version` on updates.

## src/Makefile

Use what `ncs-make-package` generates; core of it:

```make
all: fxs
include $(NCS_DIR)/src/ncs/build/include.ncs.mk

YANGPATH += ../../*/src/yang
NCSCPATH  = $(YANGPATH:%=--yangpath %)
YANG      = $(wildcard yang/*.yang)
FXS       = $(YANG:yang/%.yang=../load-dir/%.fxs)

fxs: $(FXS)

../load-dir/%.fxs: yang/%.yang
	$(NCSC) `ls $*-ann.yang > /dev/null 2>&1 && echo "-a $*-ann.yang"` \
	        $(NCSCPATH) -c -o $@ $<

clean:
	rm -rf ../load-dir/*
```
- Recipe lines are **tabs**. Say so if you emit a Makefile.
- If the YANG imports NED models (rare for services), add the NED's `src/ncsc-out/modules/yang` to `YANGPATH`.
