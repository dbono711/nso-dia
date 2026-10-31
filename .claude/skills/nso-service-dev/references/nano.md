# Nano services (NSO 6.x)

Use when provisioning has stages that depend on state (wait for device reachable, wait for an IPAM allocation, order across devices) or when operators need a `plan` showing progress.

## YANG pieces

```yang
import tailf-ncs { prefix ncs; }

identity vpn-endpoint { base ncs:plan-component-type; }
identity config-pushed { base ncs:plan-state; }
identity verified      { base ncs:plan-state; }

list l3vpn {
  key name;
  leaf name { type string; }
  uses ncs:service-data;
  uses ncs:nano-plan-data;
  ncs:servicepoint l3vpn-servicepoint;
  // inputs...
}

ncs:plan-outline l3vpn-plan {
  ncs:component-type "ncs:self" {
    ncs:state "ncs:init";
    ncs:state "ncs:ready";
  }
  ncs:component-type "l3vpn:vpn-endpoint" {
    ncs:state "ncs:init";
    ncs:state "l3vpn:config-pushed" {
      ncs:create {
        ncs:nano-callback;               // Python cb_nano_create for this state
      }
    }
    ncs:state "l3vpn:verified" {
      ncs:create {
        ncs:pre-condition {
          ncs:monitor "$SERVICE/endpoint[device=$NAME]" {
            ncs:trigger-expr "verified = 'true'";
          }
        }
      }
    }
    ncs:state "ncs:ready";
  }
}

ncs:service-behavior-tree l3vpn-servicepoint {
  ncs:plan-outline-ref "l3vpn:l3vpn-plan";
  ncs:selector {
    ncs:create-component "'self'" { ncs:component-type-ref "ncs:self"; }
    ncs:multiplier {
      ncs:foreach "endpoint" {
        ncs:variable "NAME" { ncs:value-expr "device"; }
        ncs:create-component "$NAME" { ncs:component-type-ref "l3vpn:vpn-endpoint"; }
      }
    }
  }
}
```

Notes:
- `plan-outline` and `service-behavior-tree` are top-level statements (outside the list).
- `$SERVICE` is the service instance; variables set with `ncs:variable` are available in XPath and as template vars.
- A state can apply a template directly: `ncs:create { ncs:nano-callback; }` *or* the template's `componenttype`/`state` attributes; simplest robust path is Python `nano_create`.

## Python

```python
from ncs.application import NanoService

class EndpointConfig(NanoService):
    @NanoService.create
    def cb_nano_create(self, tctx, root, service, plan, component, state,
                       proplist, component_proplist):
        dev = component[1] if isinstance(component, tuple) else component
        tvars = ncs.template.Variables()
        tvars.add('DEVICE', dev)
        ncs.template.Template(service).apply('l3vpn-template', tvars)
        return proplist

# Main.setup:
self.register_nano_service('l3vpn-servicepoint',   # servicepoint
                           'l3vpn:vpn-endpoint',   # component type
                           'l3vpn:config-pushed',  # state
                           EndpointConfig)
```

- One `register_nano_service` per (component-type, state) that has `ncs:nano-callback`.
- Check progress: `show l3vpn <name> plan`; re-deploy with `re-deploy reconcile` if needed.
- Delete is staged in reverse; add `ncs:delete { ... }` blocks only when teardown needs ordering.
