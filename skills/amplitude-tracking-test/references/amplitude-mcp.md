# Amplitude MCP (optional server-side confirmation)

The local log proves what the app tried to send. Amplitude MCP proves it arrived, and is the only
way to check keys added by SDK plugins (`app theme`, `from background`) and backend events.

## Read-only rule

This skill only **reads** tracking data. The Amplitude OAuth grant also carries `mcp:write`, so the
same session could edit the shared taxonomy or charts by mistake. Do not:

- call any tool outside the allowlist below;
- create, update, delete, restore or share anything: taxonomy, events, properties, group types,
  charts, dashboards, notebooks, cohorts, flags, experiments, comments, guides/surveys;
- "fix" a plan/Amplitude mismatch yourself; report it and let the person decide;
- query `… Production` projects; pick the project whose key matches the build (Staging).

Allowed tools (read only):

- `get_amplitude_context` — projects the account can see; pick the one whose API key matches the
  build (`scripts/amplitude_key.py` prints the key prefix).
- `get_amp_user_data` — a device's event timeline (`deviceId` + `include: "timeline"`,
  `includeEventProperties: true`): confirm each locally captured event arrived, with its properties.
- `get_amp_taxonomy`, `search_amp_data_taxonomy` — the tracking plan straight from Amplitude
  (alternative to the xlsx).
- `query_amplitude_data` with the typed `chart` parameter — event counts in a time window. It
  returns an unsaved chart edit; do not pass a `chartId`, save, render-and-share, or add the chart
  to a dashboard.

Anything else (`manage_amp_*`, `create_*`, `update_*`, `delete_*`, `restore_*`, `share_*`,
`use_amp_*`, `use_amplitude_*`) is out of scope for this skill.

## Setup (once, by the person; OAuth only)

```
claude mcp add --transport http amplitude https://mcp.amplitude.com/mcp -s user   # EU: https://mcp.eu.amplitude.com/mcp
```

Restart Claude Code → `/mcp` → amplitude → Authenticate. Prefer an Amplitude account with the
**Viewer** role on the Staging project: then even a wrong call cannot change anything.

Enforce the rule in Claude Code too: add the write tools to `permissions.deny` in
`~/.claude/settings.json`, so they are refused even if called:

```json
{
  "permissions": {
    "deny": [
      "mcp__amplitude__create_group_types",
      "mcp__amplitude__create_properties",
      "mcp__amplitude__update_properties",
      "mcp__amplitude__delete_event_properties",
      "mcp__amplitude__delete_user_properties",
      "mcp__amplitude__restore_event_properties",
      "mcp__amplitude__restore_user_properties",
      "mcp__amplitude__manage_amp_entities",
      "mcp__amplitude__manage_amp_events",
      "mcp__amplitude__manage_amp_taxonomy",
      "mcp__amplitude__share_amp_entities"
    ]
  }
}
```

## How to confirm

Read the test device's `device_id` from the app container on the simulator:

```
plutil -p "$(xcrun simctl get_app_container <udid> <bundle id> data)/Library/Preferences/com.amplitude.storage.amplitude-swift-storage-<key>-\$default_instance.plist" | grep device_id
```

Before querying, relaunch the app and send it to the background for a few seconds: the SDK keeps
the last events of a run in its queue and only uploads them on the next launch/background. A fresh
install on the same simulator deletes that queue, so read the `device_id` and flush before the
next run reinstalls the app.

Ingestion takes ~10 s–1 min: query once after the run, retry with back-off; never once per event.
Use a fresh install per run so the test device is not merged with an older one.
