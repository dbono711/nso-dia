# -*- mode: python; python-indent: 4 -*-


from _ncs.dp import action_reply_completion
from ncs.dp import Action
from ncs.maagic import cd, get_root
from ncs.maapi import Maapi

IOS_INTERFACE_TYPES = ["Ethernet", "GigabitEthernet", "TenGigabitEthernet"]


def get_root_uinfo(uinfo):
    """Return a maagic root attached to the CLI user's transaction"""
    trans = Maapi().attach(uinfo.actx_thandle, usid=uinfo.usid)
    return get_root(trans)


def get_ios_intf_list(root, device_name: str) -> list[str]:
    """Return the physical (non sub-interface) interface names on a Cisco IOS device

    Args:
        root: maagic root
        device_name (str): Network device hostname

    Returns:
        list[str]: Interface names, i.e., ['Ethernet0/3', ...]
    """
    config = root.devices.device[device_name].config
    return [
        f"{intf_type}{intf.name}"
        for intf_type in IOS_INTERFACE_TYPES
        for intf in getattr(config.ios__interface, intf_type)
        if "." not in intf.name
    ]


class InterfaceCompletion(Action):
    def cb_completion(
        self,
        uinfo,
        cli_style,
        token,
        completion_char,
        kp,
        cmdpath,
        cmdparam_id,
        simpleType,
        extra,
    ):
        """Displays list of possible interface completions for a given device."""
        self.log.info(f"Completion-Actionpoint: {self.actionpoint} id: {cmdparam_id}")
        completion_list = []

        if cmdparam_id.startswith("provideredge-"):
            root = get_root_uinfo(uinfo)
            # kp is only borrowed for this callback; dup_len(6) copies the device entry part:
            # /ncs:services/dia:dia{c s}/provider-edge/device{d}
            device_name = str(cd(root, str(kp.dup_len(6))).name)
            completion_list = [(0, intf, " ") for intf in get_ios_intf_list(root, device_name)]
        else:
            self.log.info(f"No matching completion_id: {cmdparam_id}")

        action_reply_completion(uinfo, completion_list)
