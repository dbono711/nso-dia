# YANG service model

## Boilerplate (NSO 6.x)

```yang
module l3vpn {
  yang-version 1.1;
  namespace "http://example.com/l3vpn";
  prefix l3vpn;

  import ietf-inet-types { prefix inet; }
  import tailf-common    { prefix tailf; }
  import tailf-ncs       { prefix ncs; }

  description "L3VPN service";

  revision 2026-01-01 {
    description "Initial revision.";
  }

  list l3vpn {
    description "L3VPN service instances";
    key name;
    leaf name {
      tailf:info "Unique service id";
      tailf:cli-allow-range;
      type string;
    }

    uses ncs:service-data;
    ncs:servicepoint l3vpn-servicepoint;

    list endpoint {
      key "device interface";
      leaf device {
        type leafref { path "/ncs:devices/ncs:device/ncs:name"; }
      }
      leaf interface { type string; }
      leaf ip-address { type inet:ipv4-address; mandatory true; }
      leaf prefix-length {
        type uint8 { range "1..32"; }
        default 30;
      }
    }

    leaf vrf-name { type string { length "1..32"; } mandatory true; }
    leaf rd       { type string { pattern '[0-9]+:[0-9]+'; } }
  }
}
```

Conventions:
- The boilerplate above shows generic mechanics. For this user, follow `house-conventions.md` instead: `augment /ncs:services`, keys `"customer-name service-id"`, the `provider-edge/device/interface` shape, and namespace `http://dbono711/<pkg>`. Use a bare top-level list with `key name` only when the user explicitly wants something minimal or outside their house style.
- Add a `revision` statement; bump it on updates with a description of the change.
- Prefer `inet:` types for addresses, enumerations for small closed sets, `uint16 { range ... }` for VLAN/IDs.
- Use `mandatory true` or `default` — don't leave inputs undefined that the template depends on.
- `tailf:info` on leaves shows help in the CLI; nice-to-have.

## Device references

- Single device: `leaf device { type leafref { path "/ncs:devices/ncs:device/ncs:name"; } }`
- Several: `leaf-list device { type leafref { ... } }` or a keyed list when per-device params are needed.
- Interface pick-lists that depend on NED are rarely worth it; use `string` plus a `pattern` hint, and validate in Python if needed.

## Validation

- `must` for cross-leaf rules, with an `error-message`.
- `when` to hide platform-only leaves, e.g.:
  ```yang
  leaf bundle-id {
    when "deref(../device)/../ncs:platform/ncs:name = 'ios-xr'";
    type uint16;
  }
  ```
  (Only if it truly helps; `deref` on device platform is fragile — Python-side validation is often clearer.)

## Common compile breakers

- Missing `import tailf-ncs { prefix ncs; }` while using `ncs:service-data`.
- `ncs:servicepoint` outside the list.
- Leafref path without prefixes (`/devices/device/name` instead of `/ncs:devices/ncs:device/ncs:name`).
- Using `yang-version 1.1` features without declaring it.
- `pattern` regex in double quotes with backslashes — use single quotes.
- Key leaf with `default` (illegal) or key leaf that is a leafref to something not existing.

## Updates & upgrades

- Adding optional leaves / leaves with defaults: safe.
- Adding mandatory leaves: existing instances fail validation on next commit → give it a default or note a data migration.
- Renaming/removing/type-changing leaves: requires CDB upgrade logic (`upgrade` component in package-meta-data with a Python upgrade class) — flag this to the user rather than doing it silently.
