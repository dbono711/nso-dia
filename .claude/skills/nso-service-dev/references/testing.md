# Netsim, sample payloads, Python unit tests

Include all of these in every new package. For updates, add or adjust payloads and tests that cover the change. Use netsim device names in the house style: `ios-0`, `ios-1`, `iosxr-0`, `iosxr-1`, `junos-0`. Create them with `ncs-netsim create-network <ned> 2 ios-` (the prefix includes the trailing dash).

## Netsim + local NSO

Put this in `README.md` inside the package (adjust NED package names to what the user has under `$NCS_DIR/packages/neds` or their own NED dir):

```bash
# from a fresh project dir
ncs-netsim create-network <path-to>/cisco-ios-cli-6.x      2 ios-
ncs-netsim add-to-network  <path-to>/cisco-iosxr-cli-7.x    2 iosxr-
ncs-netsim add-to-network  <path-to>/juniper-junos-nc-4.x   1 junos-
ncs-setup --netsim-dir ./netsim --dest .
cp -r /path/to/<pkg> packages/
make -C packages/<pkg>/src clean all
ncs-netsim start
ncs
ncs_cli -C -u admin
```
```
devices fetch-ssh-host-keys
devices sync-from
packages reload
```
NED version numbers vary per install; say to substitute theirs.

Troubleshooting: if `sync-from` fails with `Could not verify ssh-rsa host key ... in new state`, the netsims were regenerated and the stored key is stale. Fix it with `devices device <d> ssh fetch-host-keys` (or `devices fetch-ssh-host-keys` for all), then `sync-from` again.

## Sample payloads

Provide a CLI payload (and optionally XML for `ncs_load -lm`):

```
config
 l3vpn acme
  vrf-name ACME
  endpoint ios0 GigabitEthernet0/1
   ip-address 10.1.1.1
  !
 !
commit dry-run outformat native
commit
```

XML (`payloads/acme.xml`, load with `ncs_load -lm payloads/acme.xml` or `load merge` in CLI):
```xml
<config xmlns="http://tail-f.com/ns/config/1.0">
  <l3vpn xmlns="http://example.com/l3vpn">
    <name>acme</name>
    ...
  </l3vpn>
</config>
```
Include one payload per NED family the service supports, plus one for an update scenario if relevant. Also mention verifying with `l3vpn acme get-modifications`, `check-sync`, and `re-deploy dry-run`.

## Integration tests against a live NSO (house default)

Put these in the repo-root `tests/` dir, in the shape described in `house-conventions.md`: a `conftest.py` with the session `maapi` fixture and the autouse `test_customer` fixture, and a `test_service.py` that runs the lifecycle. Go one step further than the reference packages and **assert on the device config the service generates**, not just that the instance exists in CDB:

```python
import ncs

KEY = ('pytest-customer', 'pytest-<pkg>-01')


def _build(root):
    svc = root.services.<pkg_underscored>.create(*KEY)
    # ... set the minimum inputs ...
    return svc


def test_create_dry_run_generates_device_config(maapi):
    with maapi.start_write_trans() as t:
        _build(ncs.maagic.get_root(t))
        params = t.get_params()
        params.dry_run_native()
        result = t.apply_params(True, params)
    native = result['device']           # {device-name: native config text}
    assert 'ios-0' in native
    assert 'encapsulation dot1Q 100' in native['ios-0']


def test_service_lifecycle(maapi):
    # create -> read -> delete -> verify delete, as in the reference packages
    ...
```

`apply_params(True, params)` with `dry_run_native()` returns a dict keyed by device name with the native CLI that would be sent. For NETCONF NEDs (Junos), the native output is XML, so assert on element text there.

Native output is the NED's rendering, not what you'd type by hand. Known quirk: cisco-ios-cli quotes descriptions (`description "to_client3"`), so assert `' description "to_client3"'`. When an assert on native text fails, print the full `native[dev]` before you suspect the template.

### Inspect the lab before choosing test devices and interfaces

Netsims are often seeded with real lab config, so don't assume they're empty. Before writing tests, run:

```
show running-config devices device <d> config interface
show running-config devices device <d> config <any shared parent the service needs, e.g. router isis>
```

Then pick interfaces that **exist** and are **free**: no IP, no sub-interface with the test VLAN, not already used by hand-built config. Put them in module-level constants (`PORT_DEVICE, PORT_INTF = 'ios-1', 'GigabitEthernet2/1'`) with a comment saying why those were chosen. Never let a test create a physical interface. Netsims may reject unknown ones (`% Invalid input detected`), and a real device always will. Sub-interfaces are fine to create.

### Prerequisite fixtures: create only what's missing, remove only what you created

When the service validates that shared config already exists (and doesn't own it), use a session-scoped autouse fixture that creates it where missing and tears down only those entries:

```python
@pytest.fixture(scope='session', autouse=True)
def isis_instance(maapi):
    created = []
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        for name in PE_DEVICES:
            isis = root.devices.device[name].config.ios__router.isis_container.isis
            if '1' not in isis:
                isis.create('1')
                created.append(name)
        if created:
            t.apply()
    yield
    if created:
        with maapi.start_write_trans() as t:
            root = ncs.maagic.get_root(t)
            for name in created:
                del root.devices.device[name].config.ios__router.isis_container.isis['1']
            t.apply()
```

### Negative tests that never commit

To test a Python validation, break its precondition **in the same transaction** that creates the service, then expect `apply()` to fail. The transaction aborts, so nothing reaches CDB or the device and there's nothing to clean up:

```python
def test_missing_isis_rejected(maapi):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        del root.devices.device['ios-1'].config.ios__router.isis_container.isis['1']  # never applied
        _build(root, 'pytest-<pkg>-05')
        with pytest.raises(ncs.error.Error, match="router isis 1' is not configured on ios-1"):
            t.apply()
```

The same pattern covers "interface already in use" (set an IP on the interface in the transaction) and YANG `mandatory`/`when`/`must` failures (just leave the leaf out). Match on the operator-facing message, so the test also pins the error text.

### Lifecycle: assert re-deploy is a no-op

After create, assert `root.services.<pkg>[KEY].check_sync().in_sync` inside the READ block. It proves the service output is stable, and that validations reading device config don't trip on the service's own config (see the FASTMAP note in `house-conventions.md`). After delete, assert the device config the service created is gone (sub-interface removed, passive-interface entry removed), not just the service instance.

## Offline unit tests (pure helpers)

Goal: test the logic without a running NSO. Two layers:

1. **Pure helpers** (interface parsing, IP math, ID derivation): plain pytest, no mocks.
2. **cb_create** with mocks: patch `ncs.template.Template` and `ncs.template.Variables`, feed a fake service object, assert which variables were passed.

`test/unit/test_<pkg>.py`:
```python
import sys
import types
from unittest import mock

import pytest

# Allow import without an NSO install: stub the ncs modules if missing.
try:
    import ncs  # noqa: F401
except ImportError:
    ncs = types.ModuleType('ncs')
    ncs.application = types.ModuleType('ncs.application')
    ncs.template = types.ModuleType('ncs.template')

    class _Service:
        def __init__(self, *a, **kw):
            self.log = mock.MagicMock()
        @staticmethod
        def create(fn):
            return fn
    ncs.application.Service = _Service
    ncs.application.Application = object
    ncs.template.Template = mock.MagicMock()
    ncs.template.Variables = mock.MagicMock()
    sys.modules.update({'ncs': ncs,
                        'ncs.application': ncs.application,
                        'ncs.template': ncs.template})

sys.path.insert(0, 'python')
from l3vpn import main  # noqa: E402


@pytest.mark.parametrize('name,expected', [
    ('GigabitEthernet0/1', ('GigabitEthernet', '0/1')),
    ('TenGigE0/0/0/1', ('TenGigE', '0/0/0/1')),
])
def test_split_interface(name, expected):
    assert main.split_interface(name) == expected


def test_split_interface_bad():
    with pytest.raises(ValueError):
        main.split_interface('bogus')


def test_cb_create_applies_template_per_endpoint():
    ep = types.SimpleNamespace(device='ios0', interface='GigabitEthernet0/1',
                               ip_address='10.0.0.1', prefix_length=30)
    service = types.SimpleNamespace(_path='/l3vpn{a}', endpoint=[ep])
    with mock.patch.object(main.ncs.template, 'Template') as tmpl, \
         mock.patch.object(main.ncs.template, 'Variables') as tv:
        cb = main.ServiceCallbacks.__new__(main.ServiceCallbacks)
        cb.log = mock.MagicMock()
        cb.cb_create(None, None, service, None)
        tmpl.return_value.apply.assert_called_once()
        tv.return_value.add.assert_any_call('MASK', '255.255.255.252')
```

Run from the package root: `python -m pytest test/unit -q`.

In house-layout repos, put these offline tests under `tests/unit/` next to the integration tests. Mark the integration tests so CI without NSO can skip them: in `conftest.py`, skip when `import ncs` fails or no NSO is listening. With the house helper classes (`Network`, `Device`), test them by building a `ServiceContext` from `MagicMock`s. Give `Device.get_device_ned_id` a fake via `mock.patch.object` so the NED branching in `Network` gets exercised for IOS, XR and Junos.

Adapt the stub block to what the package imports (e.g., add `ncs.maagic` if used). Keep `Variables`/`Template` assertions focused on the values that matter (computed ones), not every variable.
