# -*- mode: python; python-indent: 4 -*-


from ncs.application import get_ned_id

from .context import ServiceContext


class Device:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx

    def get_device_ned_id(self, device_name: str) -> str:
        """Return the Network Element Driver (NED) ID for a given device

        Args:
            device_name (str): Network device hostname

        Returns:
            str: Network Element Driver (NED) ID
        """
        return get_ned_id(self.ctx.root.devices.device[device_name])

    def validate_ned(self, device_name: str) -> None:
        """Validate that a device uses a NED supported by this service

        Args:
            device_name (str): Network device hostname

        Raises:
            ValueError: The device NED is not supported
        """
        ned = self.get_device_ned_id(device_name)
        if "cisco-iosxr" in ned or "cisco-ios" not in ned:
            raise ValueError(f"Unsupported NED '{ned}' for device {device_name}, only Cisco IOS is supported")
