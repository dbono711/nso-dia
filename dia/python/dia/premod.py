# -*- mode: python; python-indent: 4 -*-


from .context import ServiceContext
from .network import Network, get_next_seq

PREFIX_LIST_NAME = "CUSTOMER-STATIC"


class PreMod:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.network = Network(ctx)

    def fill(self) -> None:
        """Allocate a CUSTOMER-STATIC prefix-list sequence number to every static route that
        doesn't have one yet. Allocated numbers are kept, so re-deploys stay stable"""
        for device in self.ctx.service.provider_edge.device:
            used = None
            for intf in device.interface:
                if not intf.static.exists():
                    continue
                for route in intf.static.ipv4_destination_prefix:
                    if route.prefix_list_seq is not None:
                        continue
                    if used is None:
                        used = self.network.get_used_prefix_list_seqs(device.name, PREFIX_LIST_NAME)
                    seq = get_next_seq(used)
                    used.add(seq)
                    route.prefix_list_seq = seq
                    self.ctx.log.info(
                        f"Allocated ip prefix-list {PREFIX_LIST_NAME} seq {seq} for {route.ipv4_prefix} on {device.name}"
                    )
