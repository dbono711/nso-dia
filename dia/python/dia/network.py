# -*- mode: python; python-indent: 4 -*-


import ipaddress
import re

from .context import ServiceContext


def get_intf_type_and_id(intf_name: str) -> tuple[str, str]:
    """Splits a complete network interface into type and ID. For example, for Cisco interface
    'Ethernet0/3', this function will return ('Ethernet', '0/3')

    Args:
        intf_name (str): The complete network interface name

    Raises:
        ValueError: The interface name could not be parsed

    Returns:
        tuple[str, str]: A network interface split into type and ID
    """
    match = re.fullmatch(r"([A-Za-z-]+)([0-9].*)", intf_name)
    if match is None:
        raise ValueError(f"Could not parse interface name '{intf_name}'")

    return match.group(1), match.group(2)


def get_ip_and_mask(prefix: str) -> tuple[str, str]:
    """Returns the IP address and netmask for an IPv4 address in CIDR notation. For
    example, '100.64.16.1/29' returns ('100.64.16.1', '255.255.255.248')

    Args:
        prefix (str): IPv4 address in CIDR notation

    Returns:
        tuple[str, str]: IP address and netmask
    """
    intf = ipaddress.ip_interface(prefix)

    return str(intf.ip), str(intf.netmask)


def get_network_mask_and_length(prefix: str) -> tuple[str, str, int]:
    """Returns the network address, netmask and prefix length for an IPv4 prefix. For
    example, '100.64.20.0/24' returns ('100.64.20.0', '255.255.255.0', 24)

    Args:
        prefix (str): IPv4 prefix in CIDR notation. inet:ipv4-prefix already rejects host bits

    Returns:
        tuple[str, str, int]: Network address, netmask and prefix length
    """
    network = ipaddress.ip_network(prefix)

    return str(network.network_address), str(network.netmask), network.prefixlen


def validate_next_hop(intf_address: str, next_hop: str) -> None:
    """Validate that a static route next-hop is a usable host address in the interface
    subnet, other than the interface's own address

    Args:
        intf_address (str): Interface IPv4 address in CIDR notation (i.e., '100.64.16.1/29')
        next_hop (str): Static route next-hop (i.e., '100.64.16.2')

    Raises:
        ValueError: The next-hop is not reachable via the interface
    """
    intf = ipaddress.ip_interface(intf_address)
    hop = ipaddress.ip_address(next_hop)
    if hop not in intf.network or hop in (intf.network.network_address, intf.network.broadcast_address):
        raise ValueError(f"Static route next-hop {next_hop} is not a host address in interface subnet {intf.network}")
    if hop == intf.ip:
        raise ValueError(f"Static route next-hop {next_hop} is the interface's own address")


def get_next_seq(used: set[int], step: int = 10) -> int:
    """Return the lowest multiple of step that is not already used

    Args:
        used (set[int]): Sequence numbers already in use
        step (int): Sequence number increment

    Returns:
        int: Next free sequence number
    """
    seq = step
    while seq in used:
        seq += step

    return seq


class Network:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx

    def validate_isis_instance(self, device_name: str, area_tag: str) -> None:
        """Validate that an IS-IS instance already exists on a network device. The service
        only adds passive interfaces to it; it does not own the IS-IS process

        Args:
            device_name (str): Network device hostname
            area_tag (str): IS-IS area tag (i.e., '1')

        Raises:
            ValueError: The IS-IS instance does not exist on the network device
        """
        isis = self.ctx.root.devices.device[device_name].config.ios__router.isis_container.isis
        if area_tag not in isis:
            raise ValueError(
                f"'router isis {area_tag}' is not configured on {device_name}, configure it before creating the service"
            )

    def validate_interface(self, device_name: str, intf_type: str, intf_id: str, vlan_id: int | None) -> None:
        """Validate that the interface the service will configure is not already in use. In
        port-mode the interface must not have an IPv4 address; otherwise the sub-interface
        must not already exist. FASTMAP removes this service's own config before create runs,
        so re-deploys don't trip these checks

        Args:
            device_name (str): Network device hostname
            intf_type (str): The interface type (i.e., 'Ethernet')
            intf_id (str): The interface ID (i.e., '0/3')
            vlan_id (int | None): Sub-interface VLAN ID, None for port-mode

        Raises:
            ValueError: The interface is already in use
        """
        intf_list = getattr(self.ctx.root.devices.device[device_name].config.ios__interface, intf_type)
        if vlan_id is None:
            if intf_id in intf_list and intf_list[intf_id].ip.address.primary.address is not None:
                raise ValueError(
                    f"{intf_type}{intf_id} on {device_name} already has an IPv4 address configured. "
                    "Check to ensure it is not in use by another service"
                )
        elif f"{intf_id}.{vlan_id}" in intf_list:
            raise ValueError(
                f"{intf_type}{intf_id}.{vlan_id} on {device_name} already exists. "
                "Check to ensure it is not in use by another service"
            )

    def get_prefix_list_entries(self, device_name: str, name: str) -> dict[int, str | None]:
        """Return the entries of an IOS prefix-list on a network device

        Args:
            device_name (str): Network device hostname
            name (str): Prefix-list name (i.e., 'CUSTOMER-STATIC')

        Returns:
            dict[int, str | None]: Sequence number -> permitted prefix (None for deny entries)
        """
        prefixes = self.ctx.root.devices.device[device_name].config.ios__ip.prefix_list.prefixes
        if name not in prefixes:
            return {}

        return {int(entry.no): entry.permit.ip for entry in prefixes[name].seq}

    def get_used_prefix_list_seqs(self, device_name: str, name: str) -> set[int]:
        """Return the prefix-list sequence numbers that are taken on a network device: entries
        already on the device, plus sequence numbers held by any DIA service instance in
        this transaction (which may not have reached the device config yet)

        Args:
            device_name (str): Network device hostname
            name (str): Prefix-list name (i.e., 'CUSTOMER-STATIC')

        Returns:
            set[int]: Sequence numbers in use
        """
        used = set(self.get_prefix_list_entries(device_name, name))
        for service in self.ctx.root.services.dia:
            if device_name not in service.provider_edge.device:
                continue
            for intf in service.provider_edge.device[device_name].interface:
                if not intf.static.exists():
                    continue
                used.update(
                    int(route.prefix_list_seq)
                    for route in intf.static.ipv4_destination_prefix
                    if route.prefix_list_seq is not None
                )

        return used

    def validate_prefix_list_entry(self, device_name: str, name: str, seq: int, prefix: str) -> None:
        """Validate that the service's prefix-list entry doesn't collide with one it doesn't own.
        FASTMAP removes this service's own entries before create runs, so every entry seen
        here belongs to someone else

        Args:
            device_name (str): Network device hostname
            name (str): Prefix-list name (i.e., 'CUSTOMER-STATIC')
            seq (int): Sequence number allocated to this route
            prefix (str): Prefix to permit (i.e., '100.64.20.0/24')

        Raises:
            ValueError: The sequence number is taken, or the prefix is already permitted
        """
        entries = self.get_prefix_list_entries(device_name, name)
        if seq in entries:
            raise ValueError(f"ip prefix-list {name} seq {seq} on {device_name} is already in use by another entry")
        for other_seq, other_prefix in entries.items():
            if other_prefix == prefix:
                raise ValueError(
                    f"{prefix} is already permitted by ip prefix-list {name} seq {other_seq} on {device_name}. "
                    "Check to ensure it is not in use by another service"
                )
