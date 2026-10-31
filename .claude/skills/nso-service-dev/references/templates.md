# XML config templates

## Skeleton

```xml
<config-template xmlns="http://tail-f.com/ns/config/1.0"
                 servicepoint="l3vpn-servicepoint">   <!-- servicepoint attr ONLY for template-only packages -->
  <devices xmlns="http://tail-f.com/ns/ncs">
    <device>
      <name>{/endpoint/device}</name>
      <config>
        <!-- one block per NED; NSO applies only the block whose namespace the device's NED loads -->
        <vrf xmlns="urn:ios">...</vrf>
        <vrf xmlns="http://tail-f.com/ned/cisco-ios-xr">...</vrf>
        <configuration xmlns="http://xml.juniper.net/xnm/1.1/xnm">...</configuration>
      </config>
    </device>
  </devices>
</config-template>
```

- Python+template packages: **no** `servicepoint` attribute; the template is applied from Python via `ncs.template.Template(service).apply('<name>-template', tvars)`. The template name is the file name without `.xml`.
- Template-only packages: `servicepoint="<servicepoint-name>"` on the root, must match YANG.

## Expressions

- `{/leaf}` — XPath from the service instance (context node). `{endpoint/ip-address}` relative to current context.
- `{$VAR}` — variable passed from Python (`tvars.add('VAR', value)`) or set via `<?set VAR=...?>`.
- Iterating a list: an XPath that returns several nodes in `<name>{/endpoint/device}</name>` makes the *context* move to each endpoint, so sibling expressions inside become relative to that endpoint. Use `{device}` style relative paths after that, or use `<?foreach {/endpoint}?> ... <?end?>` for clarity (preferred — explicit is easier to read).
- Conditionals, house style: a `when="{...}"` attribute on the element (`<TenGigE when="{$INTERFACE-TYPE = 'TenGigE' and $PORT-MODE = 'true'}">`). The element and its subtree are skipped when the expression is false. Prefer this to processing instructions. Use `<?if {...}?> ... <?elif ...?> ... <?else?> ... <?end?>` only when one condition has to gate several sibling elements, and `when` would mean repeating it.
- Unset optional leaves arrive as the string `'None'` when Python passes `None`, so guard them with `when="{$MTU != 'None'}"`. Better still, add `""` in Python and guard with `!= ''`.
- Per-NED branching without namespaces: `<?if-ned-id cisco-ios-cli-6.100:cisco-ios-cli-6.100?>` — fragile (pinned NED-ID). Prefer namespace blocks; use `if-ned-id` only when two NED versions share a namespace but differ.
- `<?macro?>` / `<?expand?>` exist for reuse; use sparingly.
- Tags: `tags="merge"` (default), `replace`, `create`, `nocreate`, `delete`. Use `tags="nocreate"` when touching config the service must not own (e.g., existing interface descriptions on a shared interface). Use `delete` only with clear intent.

## Pitfalls

- Wrong NED namespace → config silently not applied (shows empty dry-run). Check `references/neds.md`.
- Leaf ordering must follow the NED YANG — mostly forgiving, but list keys must appear before other children.
- Mixing context-moving XPath and `$VAR`s set per-iteration in Python: if Python loops over endpoints and applies the template per endpoint, use `$DEVICE`-style vars and **don't** also iterate in the template.
- Booleans/empty leaves: `<shutdown tags="delete"/>` for "no shutdown" on IOS; Junos uses `<disable tags="delete"/>`.
- Empty-string variables produce invalid config — guard with `<?if {$VAR != ''}?>`.

## Getting the template right from device config

Best practice the user can run: configure the device (or netsim) by hand, then
```
show running-config devices device <dev> config <path> | display xml-template
```
This prints a ready-made template fragment with the correct namespaces. Mention this to the user whenever you weren't given exact device XML, since NED paths vary by NED version.
