# Managed SSH connections

Metis can manage a controller on an SSH host while its web or terminal console
runs on your laptop. The controller owns the research history and experiment paths;
Slurm still owns scheduled compute jobs. Closing the local console or disconnecting
its tunnel does not stop the remote controller or cancel Slurm jobs.

## Connect from an interface

In the local web console, choose the **Local workspace / Connected to localhost**
button at bottom left. Its compact picker lists saved connections and aliases from
your OpenSSH configuration. Search for a host and choose **Connect**. A saved host
uses your local SSH client and asks for host-key, password or MFA responses when
needed. The picker then offers **Open remote dashboard**. For a new host, choose
**Add SSH host** or an unsaved alias to open the full connection settings. In the
terminal, open **SSH connections** under **Connections** (also searchable with Ctrl+K).
You can enter a new `user@hostname`. Optional port and local identity-file settings support hosts
that are not already in your SSH configuration. Saving a Metis profile does
not rewrite your SSH configuration.
The research-storage path is saved in the local private connection profile, not
in Metis source files. Do not place the local Metis state directory inside a public
repository.

1. Save a profile with a unique name. Choose **Research files on remote host** to
   place experiment workspaces and artifacts under a dedicated project directory.
   If home space is limited, choose a dedicated **Remote installation directory** in
   project storage too; this holds the Metis Python environment and controller files.
2. Choose **Sign in**. Respond to OpenSSH's host-key, passphrase, password or MFA
   prompts inside the interface. Inspect a new host's fingerprint before answering
   its trust question. Cancel closes the pending authentication attempt.
3. Check the host. Choose a Python 3.11+ executable when its default Python is older.
4. Install the controller into the profile's private user environment. This explicit
   action copies the application package and installs its pinned dependencies. It
   does not copy your repository, research data, SSH keys or provider credentials.
5. Connect and open the remote dashboard. Existing healthy controllers are reused.
   New research paths and configuration refer to files on the remote host.

The web picker keeps the full connection form available through **Connection
settings**. Installation remains an explicit action in that form. Disconnecting a tunnel
from the picker or form leaves remote research running. On a remote dashboard, the
bottom-left status identifies the remote host; manage SSH connections from the local
console.

Authentication responses are passed to the local OpenSSH process and are not saved
in profile files or application logs. OpenSSH can save an explicitly accepted host
key in its normal known-hosts file. Authentication can require several responses.
New challenges after an expired connection must be completed again in the interface.

The CLI exposes the same profile, check, installation, login and connection operations
under `metis remote`; run `metis remote --help` for the command syntax.
The connect command owns its tunnel until interrupted. Copying a printed dashboard
URL grants access to that controller, so treat it as private.

## Runtime and storage

Managed connections require OpenSSH and a POSIX client for interactive authentication,
plus a POSIX SSH host with Python 3.11 or later and support for virtual environments.
The host needs access to the package index during installation; the controller needs
network access to the configured model and literature providers during live research.
Provider credentials are configured on that host, never copied from the laptop.

The remote directory contains the private environment, controller descriptor and log.
The **Research files on remote host** setting (`state_dir` in saved profiles) selects
research artifacts and experiment workspaces. Run checkpoints and history live in the
separate controller database. On Berzelius, a dedicated path
under `/proj/<project>/users/<username>/` is appropriate for these files. Leave it
blank to use the installation directory's `state` folder. Changing the setting does
not move existing research; keep the original location with its database until a
deliberate migration is complete.
For Slurm those workspaces must be visible to compute nodes at the same absolute path.
The separate **Controller database directory** selects SQLite run history and
checkpoints. If left blank, it defaults to the research-files path, including a
project path on NFS. Set it explicitly to persistent host-local storage for such a
profile. Its contents must be backed up with the research-files directory.
The same split is available with `AUTORESEARCH_DB_DIR` for other entry points.

SQLite WAL requires compatible local storage. Managed startup rejects known network
filesystems such as NFS for the database directory. A shared project directory can
hold experiment workspaces, but it does not solve the database requirement even when
the login node can access it. The database needs persistent storage local to the
controller host. Do not use temporary scratch for durable research history: its
cleanup can destroy checkpoints even if experiment outputs survive elsewhere.
Filesystem detection is best-effort; administrators must verify unknown filesystems.

Some clusters provide an old default Python even when a newer executable is available.
Set the Python field to the supported binary or an existing environment's Python.
Installation and lightweight controller activity must follow site policy; expensive
experiments belong in scheduler allocations. Managed startup is a detached process,
not a system service with automatic restart after reboot or allocation expiry.

## Reconnection and ownership

SSH uses the user's existing host-key checks, keys, proxy/jump configuration and
authentication methods. X11 and agent forwarding are unnecessary and disabled for
managed operations. The interface owns the SSH connections it creates and closes
those on exit; it does not terminate a pre-existing user SSH master.

On hosts behind a load-balanced SSH name, reconnect to the same physical host. The
controller records its hostname and refuses to start a duplicate on another host.
A changed state/database/configuration selection also cannot silently replace an
already-running controller. Resolve an unresponsive controller before starting a new
one; an uncertain health check is not evidence that it has stopped.

Only loopback ports are opened. The SSH tunnel can choose a free local port independently
of the controller's port. Managed controllers require the SSH-delivered capability even
for bootstrap; another account on the remote machine cannot obtain it by requesting
the bootstrap endpoint. The browser receives the capability in a URL fragment, removes
it from the visible URL, and uses it for authenticated requests. Nested SSH management
is disabled on a managed remote dashboard.

Pause, resume, intervention, budget and cancellation controls retain their existing
research semantics. Disconnecting is only a connection operation. It never means
"cancel experiment" or "pause research".

## Design references

The local-interface/remote-process split follows the approach documented by
[VS Code Remote-SSH](https://code.visualstudio.com/docs/remote/ssh). In contrast to a
browser relay, transport uses the user's existing SSH setup directly. The distinction
between a remote interface and the process that owns execution is also described in
[Claude Code Remote Control](https://code.claude.com/docs/en/remote-control).
For cluster deployment, consult the site's guidance; examples include
[NSC's login-node policy](https://nsc.liu.se/support/running-applications/) and
[Berzelius storage](https://nsc.liu.se/support/systems/berzelius-getting-started/).
