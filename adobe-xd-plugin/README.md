# Adobe XD MCP Bridge

This folder contains the Adobe XD UXP-side bridge for `MCP_adobe`.

## Why writes require approval

Adobe XD only allows `application.editDocument()` to start from an explicit plugin UI action such as a button click. A WebSocket callback cannot legally start a document edit. For that reason the bridge uses this flow:

1. MCP queues a requested mutation over `ws://127.0.0.1:8765`.
2. The XD panel displays the pending count.
3. The user clicks **Apply pending**.
4. The plugin applies the entire pending batch inside one `application.editDocument()` operation.
5. XD atomically rolls back the edit batch if the operation throws.

Read operations use the latest selection/document snapshot supplied to the panel's XD lifecycle callback.

## Windows development location

Adobe documents the XD development plugin root as:

```text
%LOCALAPPDATA%\Packages\Adobe.CC.XD_adky2gkssdxte\LocalState\develop
```

The supported UI route is also available inside XD:

```text
Plugins > Development > Show Develop Folder
```

After placing the plugin under the `develop` folder, use:

```text
Plugins > Development > Reload Plugins
```

or on Windows press `Ctrl+Shift+R`.

## Development plugin ID

The checked-in manifest uses the local-development ID `MCPADB01`. Before Marketplace/distributed packaging, replace this with the plugin ID registered in Adobe's Developer Distribution portal and keep that ID stable for updates.

## Bridge surface

Read:

- `xd.health`
- `xd.document.info`
- `xd.selection.get`
- `xd.queue.status`

Approval-queued writes:

- `xd.queue.rectangle_create`
- `xd.queue.text_create`
- `xd.queue.selection_resize`
- `xd.queue.selection_fill`

The Python bridge binds to loopback only. It does not expose XD control on the LAN.
