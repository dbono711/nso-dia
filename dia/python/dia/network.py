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
