# NED notes (IOS/IOS-XE, IOS-XR, Junos)

Namespaces and paths below are for the common NED families; paths can differ between NED versions. When unsure of a deep path, say so and give the `| display xml-template` tip.

| NED | ned-id style | Config namespace | Root element(s) |
|---|---|---|---|
| Cisco IOS / IOS-XE CLI | `cisco-ios-cli-6.x` | `urn:ios` | `interface`, `vrf`, `ip`, `router`, `vlan`, ... directly under `<config>` |
| Cisco IOS-XR CLI | `cisco-iosxr-cli-7.x` | `http://tail-f.com/ned/cisco-ios-xr` | `interface`, `vrf`, `router`, `policy-map`, ... |
| Juniper Junos NETCONF | `juniper-junos-nc-4.x` | `http://xml.juniper.net/xnm/1.1/xnm` | single `<configuration>` wrapper, then `interfaces`, `routing-instances`, `protocols`, ... |

## IOS / IOS-XE examples

Interface IP + VRF:
```xml
<interface xmlns="urn:ios">
  <GigabitEthernet>
    <name>{$IF_ID}</name>          <!-- "0/1", NOT "GigabitEthernet0/1" -->
    <description>{$DESC}</description>
    <vrf><forwarding>{$VRF}</forwarding></vrf>
    <ip><address><primary>
      <address>{$IP}</address><mask>{$MASK}</mask>
    </primary></address></ip>
    <shutdown tags="delete"/>
  </GigabitEthernet>
</interface>
<vrf xmlns="urn:ios">
  <definition>
    <name>{$VRF}</name>
    <rd>{$RD}</rd>
    <address-family><ipv4/></address-family>
  </definition>
</vrf>
```
- Interface lists are split by type (`Ethernet`, `GigabitEthernet`, `TenGigabitEthernet`, `Loopback`, `Port-channel`, `Vlan`). The key is `<name>` holding only the number, so split "GigabitEthernet0/1" into type + id in Python.
- **Subinterfaces live in the same list as their parent** on cisco-ios-cli: `<GigabitEthernet><name>0/1.100</name><encapsulation><dot1Q><vlan-id>100</vlan-id></dot1Q></encapsulation>...</GigabitEthernet>`. There's no `-subinterface` list on IOS; that's the XR NED.
- Mask is dotted-decimal on IOS. Convert the prefix length in Python with `ipaddress`.
- There are two VRF flavours, and they must match on the VRF and the interface:
  - `vrf definition` (multi-AF): `<vrf xmlns="urn:ios"><definition><name/>...` with interface `<vrf><forwarding>{$VRF}</forwarding></vrf>`
  - legacy `ip vrf`: `<ip xmlns="urn:ios"><vrf><name/><rd/>...</vrf></ip>` with interface `<ip-vrf><ip><vrf><forwarding>{$VRF}</forwarding></vrf></ip></ip-vrf>` (this is what the user's l3vpn package uses)
  - When the VRF already exists on the box, check which flavour it is before choosing the interface binding.
- Policy: `<service-policy><input>{$NAME}</input></service-policy>` (a plain leaf on IOS; on XR it's `<input><name>`).
- L2VPN protocol-based CLI (IOS-XE 3.7S+ / 15.3(1)S+): `<interface><pseudowire><name>{$VPN-ID}</name><encapsulation>mpls</encapsulation><neighbor><address>{$PEER}</address><vcid>{$VPN-ID}</vcid></neighbor></pseudowire></interface>` plus `<l2vpn-xconnect xmlns="urn:ios"><l2vpn><xconnect><context><name/><member><interface-list><name>pseudowire{$VPN-ID}</name></interface-list>...`.
- VLAN: `<vlan xmlns="urn:ios"><vlan-list><id>{$VLAN}</id><name>...</name></vlan-list></vlan>`.
- IS-IS passive interface (`router isis 1` / ` passive-interface Ethernet0/3`), verified on cisco-ios-cli-6.109. Note the `isis-container` wrapper and the `area-tag` key. The interface name here is the **full** name, not type + id:
  ```xml
  <router xmlns="urn:ios">
    <isis-container>
      <isis tags="nocreate">                <!-- service must not create the IS-IS process -->
        <area-tag>{$ISIS-AREA-TAG}</area-tag>
        <passive-interface tags="merge">
          <interface><name>{$PASSIVE-INTERFACE}</name></interface>   <!-- "Ethernet0/3.100" -->
        </passive-interface>
      </isis>
    </isis-container>
  </router>
  ```
  OSPF/RIP/EIGRP share the same `passive-interface/interface{name}` grouping under their own `router` lists.
- Maagic access to IOS device config uses the `ios__` prefix on the first node under `config`: `root.devices.device[d].config.ios__interface.GigabitEthernet['0/1']`, `...config.ios__router.isis_container.isis['1'].passive_interface.interface`. For a type held in a variable, use `getattr(config.ios__interface, intf_type)`. IP: `.ip.address.primary.address` / `.mask`; dot1Q: `.encapsulation.dot1Q.vlan_id`.

## IOS-XR examples

```xml
<vrf xmlns="http://tail-f.com/ned/cisco-ios-xr">
  <vrf-list>
    <name>{$VRF}</name>
    <address-family><ipv4><unicast/></ipv4></address-family>
  </vrf-list>
</vrf>
<interface xmlns="http://tail-f.com/ned/cisco-ios-xr">
  <GigabitEthernet>
    <id>{$IF_ID}</id>               <!-- XR uses <id>, e.g. "0/0/0/1" -->
    <description>{$DESC}</description>
    <vrf>{$VRF}</vrf>
    <ipv4><address><ip>{$IP}</ip><mask>{$MASK}</mask></address></ipv4>
    <shutdown tags="delete"/>
  </GigabitEthernet>
</interface>
```
- Interface types: `GigabitEthernet`, `TenGigE`, `HundredGigE`, `Bundle-Ether`, `Loopback`; subinterfaces under `GigabitEthernet-subinterface/GigabitEthernet` with `<id>0/0/0/1.100</id>`.
- RD lives under BGP on XR, not under the VRF: `<router><bgp><bgp-no-instance><id>{$ASN}</id><vrf><name>{$VRF}</name><rd>{$RD}</rd>...`.
- Route targets: `<vrf-list><address-family><ipv4><unicast><import><route-target><address-list><name>{$ASN}:{$ID}</name>` (same for `export`).
- Policy: `<policy-map xmlns="http://tail-f.com/ned/cisco-ios-xr"><name/><class><class-default><map>class-default</map><police-rate-unit><police><rate><cir/><cir-unit>mbps</cir-unit>...`. Interfaces bind it with `<service-policy><input><name>{$NAME}</name></input></service-policy>`.
- Python keypaths into XR device config use the `cisco-ios-xr:` prefix (`/devices/device{x}/config/cisco-ios-xr:interface/GigabitEthernet`). IOS uses `ios:`, and Junos `junos:configuration`.
- XR VRF names: replace `.`, `(`, `)`, `,` and spaces with `_`, and truncate to 32 chars.

## Junos examples

```xml
<configuration xmlns="http://xml.juniper.net/xnm/1.1/xnm">
  <interfaces>
    <interface>
      <name>{$IF_NAME}</name>       <!-- full name, e.g. ge-0/0/1 -->
      <description>{$DESC}</description>
      <unit>
        <name>{$UNIT}</name>
        <vlan-id>{$VLAN}</vlan-id>   <!-- only if vlan-tagging set on interface -->
        <family><inet><address><name>{$IP}/{$PLEN}</name></address></inet></family>
      </unit>
    </interface>
  </interfaces>
  <routing-instances>
    <instance>
      <name>{$VRF}</name>
      <instance-type>vrf</instance-type>
      <interface><name>{$IF_NAME}.{$UNIT}</name></interface>
      <route-distinguisher><rd-type>{$RD}</rd-type></route-distinguisher>
      <vrf-target><community>target:{$RT}</community></vrf-target>
    </instance>
  </routing-instances>
</configuration>
```
- Junos takes CIDR (`10.0.0.1/30`) rather than mask.
- Disable/enable: `<disable tags="delete"/>`.

## Detecting the NED in Python

```python
from ncs.application import get_ned_id
ned = get_ned_id(root.devices.device[dev])     # works for CLI and NETCONF NEDs
if "cisco-iosxr" in ned: ...                   # check XR FIRST: "cisco-ios" is a substring of "cisco-iosxr-cli-..."
elif "cisco-ios" in ned: ...
elif "junos" in ned: ...
```
Simpler and version-proof: branch on `root.devices.device[dev].platform.name` (`'ios'`, `'ios-xr'`, `'junos'`) after `sync-from`. But usually you don't need to branch at all — put all three namespace blocks in the template and let NSO apply the matching one. Branch only when *values* differ (interface naming, mask vs CIDR).
