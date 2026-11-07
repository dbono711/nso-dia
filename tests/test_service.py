import pytest
import ncs

CUSTOMER = 'pytest-customer'
PREFIX_LIST = 'CUSTOMER-STATIC'
PORT_DEVICE, PORT_INTF = 'ios-0', 'GigabitEthernet2/0'
SUB_DEVICE, SUB_INTF, SUB_VLAN = 'ios-0', 'GigabitEthernet2/1', 300


def _build(root, service_id, device=PORT_DEVICE, interface=PORT_INTF, ipv4_address='100.64.16.1/29',
           port_mode=True, vlan_id=None, description=None, static_routes=None):
    svc = root.services.dia.create(CUSTOMER, service_id)
    intf = svc.provider_edge.device.create(device).interface.create(interface)
    intf.ipv4_address = ipv4_address
    intf.port_mode = port_mode
    if vlan_id is not None:
        intf.vlan_id = vlan_id
    if description is not None:
        intf.description = description
    for prefix, next_hop in static_routes or []:
        intf.static.create()
        intf.static.ipv4_destination_prefix.create(prefix).ipv4_forwarding = next_hop
    return svc


def _build_sub(root, service_id, **kwargs):
    return _build(root, service_id, device=SUB_DEVICE, interface=SUB_INTF, ipv4_address='100.64.16.9/29',
                  port_mode=False, vlan_id=SUB_VLAN, **kwargs)


def _dry_run_native(maapi, *builds):
    """Apply each (build, service_id, kwargs) in one transaction and return {device-name: native CLI}
    from commit dry-run. Nothing is committed."""
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        for build, service_id, kwargs in builds:
            build(root, service_id, **kwargs)
        params = t.get_params()
        params.dry_run_native()
        result = t.apply_params(True, params)
    return result['device']


def _create(maapi, *builds):
    """Apply each (build, service_id, kwargs) in one transaction and commit it."""
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        for build, service_id, kwargs in builds:
            build(root, service_id, **kwargs)
        t.apply()


def _delete(maapi, service_id):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        if (CUSTOMER, service_id) in root.services.dia:
            del root.services.dia[CUSTOMER, service_id]
            t.apply()


def _passive_interfaces(root, device):
    return root.devices.device[device].config.ios__router.isis_container.isis['1'].passive_interface.interface


def _prefix_list(root, device):
    """{seq: permitted prefix} for CUSTOMER-STATIC on a device."""
    prefixes = root.devices.device[device].config.ios__ip.prefix_list.prefixes
    if PREFIX_LIST not in prefixes:
        return {}
    return {int(e.no): e.permit.ip for e in prefixes[PREFIX_LIST].seq}


def _expected_seqs(maapi, device, count):
    """The next free multiples of 10 in CUSTOMER-STATIC, so tests don't depend on lab contents."""
    with maapi.start_read_trans() as t:
        used = set(_prefix_list(ncs.maagic.get_root(t), device))
    seqs, seq = [], 10
    while len(seqs) < count:
        if seq not in used:
            seqs.append(seq)
        seq += 10
    return seqs


def _static_routes(root, device):
    return root.devices.device[device].config.ios__ip.route.ip_route_forwarding_list


def test_service_lifecycle(maapi):
    port = (_build, 'pytest-dia-01', {'description': 'testing'})
    sub = (_build_sub, 'pytest-dia-02', {})

    # DRY-RUN: the native CLI the service renders
    cli = _dry_run_native(maapi, port, sub)[PORT_DEVICE]
    # one assert per line: the NED adds its own defaults (no shutdown, no switchport) to new interfaces
    assert f'interface {PORT_INTF}' in cli
    assert ' description "testing"' in cli
    assert ' ip address 100.64.16.1 255.255.255.248' in cli
    assert f'interface {SUB_INTF}.{SUB_VLAN}' in cli
    assert ' description "NSO:pytest-customer:pytest-dia-02"' in cli
    assert f' encapsulation dot1Q {SUB_VLAN}' in cli
    assert ' ip address 100.64.16.9 255.255.255.248' in cli
    assert 'router isis 1' in cli
    assert f' passive-interface {PORT_INTF}' in cli
    assert f' passive-interface {SUB_INTF}.{SUB_VLAN}' in cli
    assert 'ip route' not in cli
    assert 'prefix-list' not in cli

    # CREATE
    _create(maapi, port, sub)

    try:
        # READ
        with maapi.start_read_trans() as t:
            root = ncs.maagic.get_root(t)
            gig = root.devices.device[PORT_DEVICE].config.ios__interface.GigabitEthernet
            assert gig['2/0'].description == 'testing'
            assert gig['2/0'].ip.address.primary.address == '100.64.16.1'
            assert gig[f'2/1.{SUB_VLAN}'].encapsulation.dot1Q.vlan_id == SUB_VLAN
            assert gig[f'2/1.{SUB_VLAN}'].description == 'NSO:pytest-customer:pytest-dia-02'
            assert PORT_INTF in _passive_interfaces(root, PORT_DEVICE)
            assert f'{SUB_INTF}.{SUB_VLAN}' in _passive_interfaces(root, SUB_DEVICE)

            # re-deploy must be a no-op (FASTMAP undoes our own config before the validations run)
            assert root.services.dia[CUSTOMER, 'pytest-dia-01'].check_sync().in_sync
            assert root.services.dia[CUSTOMER, 'pytest-dia-02'].check_sync().in_sync
    finally:
        # DELETE
        _delete(maapi, 'pytest-dia-01')
        _delete(maapi, 'pytest-dia-02')

    # VERIFY DELETE
    with maapi.start_read_trans() as t:
        root = ncs.maagic.get_root(t)
        assert (CUSTOMER, 'pytest-dia-01') not in root.services.dia
        assert (CUSTOMER, 'pytest-dia-02') not in root.services.dia
        gig = root.devices.device[PORT_DEVICE].config.ios__interface.GigabitEthernet
        assert gig['2/0'].ip.address.primary.address is None
        assert f'2/1.{SUB_VLAN}' not in gig
        assert PORT_INTF not in _passive_interfaces(root, PORT_DEVICE)
        assert f'{SUB_INTF}.{SUB_VLAN}' not in _passive_interfaces(root, SUB_DEVICE)


def test_static_route_lifecycle(maapi):
    key = (CUSTOMER, 'pytest-dia-03')
    seq1, seq2, seq3 = _expected_seqs(maapi, PORT_DEVICE, 3)
    svc = (_build, key[1], {'static_routes': [
        ('100.64.20.0/24', '100.64.16.2'),
        ('100.64.21.0/25', '100.64.16.3'),
    ]})

    # DRY-RUN: the native CLI the service renders
    cli = _dry_run_native(maapi, svc)[PORT_DEVICE]
    assert 'ip route 100.64.20.0 255.255.255.0 100.64.16.2' in cli
    assert 'ip route 100.64.21.0 255.255.255.128 100.64.16.3' in cli
    assert f'ip prefix-list {PREFIX_LIST} seq {seq1} permit 100.64.20.0/24' in cli
    assert f'ip prefix-list {PREFIX_LIST} seq {seq2} permit 100.64.21.0/25' in cli

    # CREATE
    _create(maapi, svc)

    try:
        # READ: sequence numbers allocated, device config present, re-deploy is a no-op
        with maapi.start_read_trans() as t:
            root = ncs.maagic.get_root(t)
            routes = root.services.dia[key].provider_edge.device[PORT_DEVICE].interface[PORT_INTF].static.ipv4_destination_prefix
            assert routes['100.64.20.0/24'].prefix_list_seq == seq1
            assert routes['100.64.21.0/25'].prefix_list_seq == seq2
            assert _prefix_list(root, PORT_DEVICE)[seq1] == '100.64.20.0/24'
            assert _prefix_list(root, PORT_DEVICE)[seq2] == '100.64.21.0/25'
            assert ('100.64.20.0', '255.255.255.0', '100.64.16.2') in _static_routes(root, PORT_DEVICE)
            assert ('100.64.21.0', '255.255.255.128', '100.64.16.3') in _static_routes(root, PORT_DEVICE)
            assert root.services.dia[key].check_sync().in_sync

        # UPDATE: add a route; existing sequence numbers must not move
        with maapi.start_write_trans() as t:
            root = ncs.maagic.get_root(t)
            intf = root.services.dia[key].provider_edge.device[PORT_DEVICE].interface[PORT_INTF]
            intf.static.ipv4_destination_prefix.create('100.64.22.0/24').ipv4_forwarding = '100.64.16.2'
            t.apply()

        with maapi.start_read_trans() as t:
            root = ncs.maagic.get_root(t)
            routes = root.services.dia[key].provider_edge.device[PORT_DEVICE].interface[PORT_INTF].static.ipv4_destination_prefix
            assert routes['100.64.20.0/24'].prefix_list_seq == seq1
            assert routes['100.64.21.0/25'].prefix_list_seq == seq2
            assert routes['100.64.22.0/24'].prefix_list_seq == seq3
            assert _prefix_list(root, PORT_DEVICE)[seq3] == '100.64.22.0/24'
            assert root.services.dia[key].check_sync().in_sync
    finally:
        # DELETE
        _delete(maapi, key[1])

    # VERIFY DELETE
    with maapi.start_read_trans() as t:
        root = ncs.maagic.get_root(t)
        entries = _prefix_list(root, PORT_DEVICE)
        for seq in (seq1, seq2, seq3):
            assert seq not in entries
        assert ('100.64.20.0', '255.255.255.0', '100.64.16.2') not in _static_routes(root, PORT_DEVICE)
        assert ('100.64.21.0', '255.255.255.128', '100.64.16.3') not in _static_routes(root, PORT_DEVICE)
        assert ('100.64.22.0', '255.255.255.0', '100.64.16.2') not in _static_routes(root, PORT_DEVICE)


def test_static_route_seqs_distinct_across_services(maapi):
    # two services on the same device in one transaction must not get the same sequence number
    seq1, seq2 = _expected_seqs(maapi, PORT_DEVICE, 2)
    cli = _dry_run_native(
        maapi,
        (_build, 'pytest-dia-04', {'static_routes': [('100.64.20.0/24', '100.64.16.2')]}),
        (_build_sub, 'pytest-dia-05', {'static_routes': [('100.64.30.0/24', '100.64.16.10')]}),
    )[PORT_DEVICE]

    assert f'seq {seq1} permit' in cli
    assert f'seq {seq2} permit' in cli


def test_vlan_required_when_not_port_mode(maapi):
    with maapi.start_write_trans() as t:
        _build(ncs.maagic.get_root(t), 'pytest-dia-06', port_mode=False)
        with pytest.raises(ncs.error.Error):
            t.apply()


def test_missing_isis_rejected(maapi):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        # removed in this transaction only; it's never applied
        del root.devices.device[PORT_DEVICE].config.ios__router.isis_container.isis['1']
        _build(root, 'pytest-dia-07')
        with pytest.raises(ncs.error.Error, match=f"router isis 1' is not configured on {PORT_DEVICE}"):
            t.apply()

def test_static_next_hop_rejected(maapi):
    with maapi.start_write_trans() as t:
        _build(ncs.maagic.get_root(t), 'pytest-dia-09', static_routes=[('100.64.20.0/24', '100.64.17.2')])
        with pytest.raises(ncs.error.Error, match='is not a host address in interface subnet 100.64.16.0/29'):
            t.apply()


def test_static_prefix_already_permitted_rejected(maapi):
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        # a hand-built entry for the same prefix, in this transaction only
        pl = root.devices.device[PORT_DEVICE].config.ios__ip.prefix_list.prefixes.create(PREFIX_LIST)
        pl.seq.create(5000).permit.ip = '100.64.20.0/24'
        _build(root, 'pytest-dia-10', static_routes=[('100.64.20.0/24', '100.64.16.2')])
        with pytest.raises(ncs.error.Error, match=f'already permitted by ip prefix-list {PREFIX_LIST} seq 5000'):
            t.apply()
