import pytest
import ncs

CUSTOMER = 'pytest-customer'
PORT_DEVICE, PORT_INTF = 'ios-0', 'GigabitEthernet2/0'
SUB_DEVICE, SUB_INTF, SUB_VLAN = 'ios-1', 'GigabitEthernet2/0', 300


def _build(root, service_id, device=PORT_DEVICE, interface=PORT_INTF, ipv4_address='100.64.16.1/29',
           port_mode=True, vlan_id=None, description=None):
    svc = root.services.dia.create(CUSTOMER, service_id)
    intf = svc.provider_edge.device.create(device).interface.create(interface)
    intf.ipv4_address = ipv4_address
    intf.port_mode = port_mode
    if vlan_id is not None:
        intf.vlan_id = vlan_id
    if description is not None:
        intf.description = description
    return svc


def _build_sub(root, service_id, **kwargs):
    return _build(root, service_id, device=SUB_DEVICE, interface=SUB_INTF, ipv4_address='100.64.16.9/29',
                  port_mode=False, vlan_id=SUB_VLAN, **kwargs)


def _dry_run_native(maapi, build, service_id, **kwargs):
    """Build a service instance and return {device-name: native CLI} from commit dry-run."""
    with maapi.start_write_trans() as t:
        build(ncs.maagic.get_root(t), service_id, **kwargs)
        params = t.get_params()
        params.dry_run_native()
        result = t.apply_params(True, params)
    return result['device']


def _delete(maapi, service_id):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        if (CUSTOMER, service_id) in root.services.dia:
            del root.services.dia[CUSTOMER, service_id]
            t.apply()


def _passive_interfaces(root, device):
    return root.devices.device[device].config.ios__router.isis_container.isis['1'].passive_interface.interface


def test_port_mode_dry_run(maapi):
    native = _dry_run_native(maapi, _build, 'pytest-dia-01', description='testing')

    cli = native[PORT_DEVICE]
    assert f'interface {PORT_INTF}' in cli
    assert ' description "testing"' in cli
    assert ' ip address 100.64.16.1 255.255.255.248' in cli
    assert 'router isis 1' in cli
    assert f' passive-interface {PORT_INTF}' in cli
    assert 'encapsulation' not in cli


def test_subinterface_dry_run(maapi):
    native = _dry_run_native(maapi, _build_sub, 'pytest-dia-02', description='to_client4')

    cli = native[SUB_DEVICE]
    assert f'interface {SUB_INTF}.{SUB_VLAN}' in cli
    assert f' encapsulation dot1Q {SUB_VLAN}' in cli
    assert ' ip address 100.64.16.9 255.255.255.248' in cli
    assert f' passive-interface {SUB_INTF}.{SUB_VLAN}' in cli


def test_vlan_required_when_not_port_mode(maapi):
    with maapi.start_write_trans() as t:
        _build(ncs.maagic.get_root(t), 'pytest-dia-04', port_mode=False)
        with pytest.raises(ncs.error.Error):
            t.apply()


def test_missing_isis_rejected(maapi):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        # removed in this transaction only; it's never applied
        del root.devices.device[PORT_DEVICE].config.ios__router.isis_container.isis['1']
        _build(root, 'pytest-dia-05')
        with pytest.raises(ncs.error.Error, match=f"router isis 1' is not configured on {PORT_DEVICE}"):
            t.apply()


def test_interface_in_use_rejected(maapi):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        # give the interface an address in this transaction only, as if someone else owned it
        intf_type, intf_id = 'GigabitEthernet', PORT_INTF.removeprefix('GigabitEthernet')
        intf = getattr(root.devices.device[PORT_DEVICE].config.ios__interface, intf_type)[intf_id]
        intf.ip.address.primary.address = '192.0.2.1'
        intf.ip.address.primary.mask = '255.255.255.0'
        _build(root, 'pytest-dia-06')
        with pytest.raises(ncs.error.Error, match='already has an IPv4 address configured'):
            t.apply()


def test_service_lifecycle(maapi):
    # CREATE
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        _build(root, 'pytest-dia-07', description='testing')
        _build_sub(root, 'pytest-dia-08')
        t.apply()

    try:
        # READ
        with maapi.start_read_trans() as t:
            root = ncs.maagic.get_root(t)
            assert (CUSTOMER, 'pytest-dia-07') in root.services.dia
            assert (CUSTOMER, 'pytest-dia-08') in root.services.dia

            port = root.devices.device[PORT_DEVICE].config.ios__interface.GigabitEthernet['2/0']
            assert port.description == 'testing'
            assert port.ip.address.primary.address == '100.64.16.1'
            assert PORT_INTF in _passive_interfaces(root, PORT_DEVICE)

            sub = root.devices.device[SUB_DEVICE].config.ios__interface.GigabitEthernet[f'2/0.{SUB_VLAN}']
            assert sub.encapsulation.dot1Q.vlan_id == SUB_VLAN
            assert sub.description == 'NSO:pytest-customer:pytest-dia-08'
            assert f'{SUB_INTF}.{SUB_VLAN}' in _passive_interfaces(root, SUB_DEVICE)

            # re-deploy must be a no-op (FASTMAP undoes our own config before the validations run)
            out = root.services.dia[CUSTOMER, 'pytest-dia-07'].check_sync()
            assert out.in_sync
    finally:
        # DELETE
        _delete(maapi, 'pytest-dia-07')
        _delete(maapi, 'pytest-dia-08')

    # VERIFY DELETE
    with maapi.start_read_trans() as t:
        root = ncs.maagic.get_root(t)
        assert (CUSTOMER, 'pytest-dia-07') not in root.services.dia
        assert (CUSTOMER, 'pytest-dia-08') not in root.services.dia
        assert root.devices.device[PORT_DEVICE].config.ios__interface.GigabitEthernet['2/0'].ip.address.primary.address is None
        assert PORT_INTF not in _passive_interfaces(root, PORT_DEVICE)
        assert f'2/0.{SUB_VLAN}' not in root.devices.device[SUB_DEVICE].config.ios__interface.Ethernet
        assert f'{SUB_INTF}.{SUB_VLAN}' not in _passive_interfaces(root, SUB_DEVICE)
