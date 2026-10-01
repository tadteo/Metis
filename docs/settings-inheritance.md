# Model settings and inheritance

Settings preserves Appearance and presents **Available to Metis**, a compact model
inventory with Configure/Add model. **System 1 → Laya** is a separate section.
The inventory selector chooses global or workspace settings. To restrict a project,
open **New research → Project settings → Model permissions** after selecting
its folder; Return to inquiry preserves the preparation form. All available models
continues inheriting later inventory additions. Only selected models stores stable
model IDs. These permissions apply to future runs.

Advanced model settings opens the explicit routing and inheritance editor. Its
scopes remain:

1. **Global defaults** apply across this user's local Metis workspaces and connected
   managed SSH workspaces.
2. **This workspace** overrides selected groups for this private state directory.
3. **A project** overrides selected groups for a canonical absolute source directory
   within this workspace. A project on another host is a separate project.

A workspace is the Store/state directory, not a Git branch or the browser tab.
Global defaults are per operating-system user on the originating host; there is no
cloud account sync. They are stored privately under `~/.local/state/metis-settings`
(or `METIS_SETTINGS_HOME`). Workspace/project layers live in that workspace's private
SQLite database. No project commands, execution permissions, paths or research data
are included in global model defaults.

In the advanced editor, unchecked **Override model routing** / **Override Laya** groups inherit from the
parent. Check a group to edit it. **Use inherited settings**, then **Save settings**,
removes that scope's overrides. Provider objects and role maps are replaced as
complete configuration sections; selected UI groups pin their displayed sections.
Advanced model JSON can edit individual model sections and prices. Apply JSON,
then save; unapplied JSON is never silently saved. Unsaved scope drafts survive
navigation. Reload saved values explicitly discards the selected scope's draft.

Existing saved workspace and global choices without inventory remain explicit legacy routing. Reset those
choices to inheritance when you want global defaults to apply. Unrelated budget or
project saves do not create model overrides. Optimistic revision checks cover parent
changes as well as local edits; stale editors must reload. Revision numbers are
opaque JavaScript-safe integers, not counters clients should increment.

New inquiries resolve project settings when the source folder changes. Editing a
model in the inquiry overrides it only for that run. Explicit launch/config files
and reused run configurations take precedence. Existing runs retain the exact
recorded configuration; changing settings never starts or rewrites research.
CLI and TUI new-run defaults use the same resolution rules. An open TUI resolves
current defaults for each new inquiry unless launched with an explicit config.

## SSH and credentials

The originating local console synchronizes only model configuration over the
existing authenticated SSH tunnel on connection and while connected. Unchanged
snapshots are not resent. Disconnected hosts receive the latest defaults on reconnect.
The save result and connection status report synchronization failures as pending;
update an old remote runtime before retrying. A remote controller retains its last
received defaults while disconnected. Its Global view is read-only; workspace and
project overrides remain editable. Remote deployments need the matching runtime.

Global settings can be saved without any connected SSH controller. This is not a
claim that disconnected hosts have received them. No new SSH connection is started
by saving defaults. One originating local settings store is the authority for a
managed remote workspace; avoid connecting the same workspace from competing local
settings stores.

API keys stay in each execution host's vault/session/environment. Only variable
names travel with model defaults. Use a distinct variable name for different keys
within the same host. A loopback Laya URL refers to the execution host, so each host
must provide its own service or override the address. Laya remains optional advice;
no cost-saving or scientific-quality result is implied.

## CLI

```bash
metis settings --scope global profile google-flash
metis settings --scope workspace set provider.model '"chosen-model"'
metis settings --scope project --project /path/to/project set laya.enabled true
metis settings --scope project --project /path/to/project inherit
metis settings --scope workspace show
```

Scoped `import` accepts only model-routing/inventory/permission/Laya JSON sections. Unscoped setup and
settings commands retain their full workspace configuration interface; explicit
model edits there create only the changed section overrides. Project commands and
runtime permissions remain local. Use [the routing guide](model-routing.md) for
the Google recipe and [Laya's contract](laya.md) for its advisory boundary.

Compact saves submit only inventory, project permissions or Laya changes and retain
other scope overrides. A model edit also updates its matching primary reference.
Advanced explicit routing edits disable inventory selection. To use project model
permissions, retain inventory and configure models through the compact list.
Credential saves use a separate endpoint and never enter configuration snapshots.
