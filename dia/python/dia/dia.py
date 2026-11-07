# -*- mode: python; python-indent: 4 -*-


from ncs.template import Template, Variables

from .context import ServiceContext
from .device import Device
from .network import (
    Network,
    get_intf_type_and_id,
    get_ip_and_mask,
    get_network_mask_and_length,
    validate_next_hop,
)
from .premod import PREFIX_LIST_NAME

ISIS_AREA_TAG = "1"


class Dia:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.network = Network(ctx)
        self.device = Device(ctx)

    def configure(self) -> None:
        """Apply the DIA configuration to every Provider Edge interface in the service"""
        template = Template(self.ctx.service)
        vars = Variables()
        customer_name = self.ctx.service.customer_name
        service_id = self.ctx.service.service_id
        vars.add("CUSTOMER-NAME", customer_name)
        vars.add("SERVICE-ID", service_id)
        vars.add("ISIS-AREA-TAG", ISIS_AREA_TAG)
        vars.add("PREFIX-LIST-NAME", PREFIX_LIST_NAME)

        for device in self.ctx.service.provider_edge.device:
            self.ctx.log.info(f"Configuring device: {device.name}")
            self.device.validate_ned(device.name)
            self.network.validate_isis_instance(device.name, ISIS_AREA_TAG)
            vars.add("DEVICE-NAME", device.name)

            for intf in device.interface:
                intf_type, intf_id = get_intf_type_and_id(intf.name)
                vlan_id = None if intf.port_mode else intf.vlan_id
                self.network.validate_interface(device.name, intf_type, intf_id, vlan_id)

                if vlan_id is not None:
                    intf_id = f"{intf_id}.{vlan_id}"
                ip_address, ip_mask = get_ip_and_mask(intf.ipv4_address)

                vars.add("INTERFACE-TYPE", intf_type)
                vars.add("INTERFACE-ID", intf_id)
                vars.add("VLAN-ID", "" if vlan_id is None else vlan_id)
                vars.add("DESCRIPTION", intf.description or f"NSO:{customer_name}:{service_id}")
                vars.add("IPV4-ADDRESS", ip_address)
                vars.add("IPV4-MASK", ip_mask)
                vars.add("PASSIVE-INTERFACE", f"{intf_type}{intf_id}")

                self.ctx.log.info(f"Applying dia-template to {intf_type}{intf_id} on {device.name}")
                template.apply("dia-template", vars)

                if intf.static.exists():
                    self._setup_static(template, vars, device.name, intf)

    def _setup_static(self, template: Template, vars: Variables, device_name: str, intf) -> None:
        """Apply a static route and CUSTOMER-STATIC prefix-list entry for every destination
        prefix on an interface

        Args:
            template (Template): Service template
            vars (Variables): Template variables, already set for the device and interface
            device_name (str): Network device hostname
            intf: The service interface list entry

        Raises:
            ValueError: A route failed validation, or has no prefix-list sequence number
        """
        for route in intf.static.ipv4_destination_prefix:
            network, mask, length = get_network_mask_and_length(route.ipv4_prefix)
            validate_next_hop(intf.ipv4_address, route.ipv4_forwarding)
            if route.prefix_list_seq is None:
                raise ValueError(f"Static route {route.ipv4_prefix} on {device_name} has no prefix-list sequence number")
            seq = int(route.prefix_list_seq)
            self.network.validate_prefix_list_entry(device_name, PREFIX_LIST_NAME, seq, f"{network}/{length}")

            vars.add("STATIC-PREFIX", network)
            vars.add("STATIC-MASK", mask)
            vars.add("STATIC-PREFIX-LENGTH", length)
            vars.add("STATIC-NEXT-HOP", route.ipv4_forwarding)
            vars.add("PREFIX-LIST-SEQ", seq)

            self.ctx.log.info(
                f"Applying dia-static for {network}/{length} via {route.ipv4_forwarding} (seq {seq}) on {device_name}"
            )
            template.apply("dia-static", vars)
