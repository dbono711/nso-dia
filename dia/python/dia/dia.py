# -*- mode: python; python-indent: 4 -*-


from ncs.template import Template, Variables

from .context import ServiceContext
from .device import Device
from .network import Network, get_intf_type_and_id, get_ip_and_mask

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
