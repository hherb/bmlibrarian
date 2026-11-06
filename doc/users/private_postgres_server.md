# The private PostgreSQL server

BMLibrarian keeps its literature database in PostgreSQL. If your computer has
no suitable PostgreSQL, BMLibrarian sets up its own **private** server. It
belongs to you alone:

- It runs as your user. No administrator rights are needed.
- It listens only on your own computer (`127.0.0.1`), never on the network.
- It uses its own port, **5418** by default, or the next free one. Other
  PostgreSQL servers commonly use 5432, so it won't collide with one you, or
  another program, install later.
- It never changes any other PostgreSQL on your computer, and never changes
  the configuration of the older Python BMLibrarian (`~/.bmlibrarian/.env`).

The one-click installer will set this up for you. The commands below are for
setting it up by hand, and for checking on it.

## Commands

All commands take an optional `--config-dir <folder>`. It defaults to the
`BML_CONFIG_DIR` environment variable, and otherwise to `~/.bmlibrarian`.

| Command | What it does |
|---|---|
| `bml server init --bindir <PostgreSQL 18 bin folder> --data-dir <folder> [--extension-dir <folder>]...` | Sets up the server and starts it. Safe to run again: it carries on where an interrupted run stopped, and changes nothing if setup is complete. |
| `bml server status` | Shows whether the server is running, where its data is, and which extensions the database has. |
| `bml server start` / `stop` / `restart` | Starts or stops the server. Starting a running server, or stopping a stopped one, does nothing. |
| `bml server autostart enable` / `disable` | Starts the server once each time you log in, or stops doing so. Disabling leaves a running server alone. |

`bml server status` exits with code **0** when the server is running and
healthy, **1** when it is stopped or unhealthy, and **2** when no server has
been set up yet.

### Choosing the data folder

The data folder must be new or empty. `init` refuses a folder that already
holds other files, and leaves those files untouched. A full PubMed mirror needs
a lot of space, so an external disk is fine.

## Where things are kept

In the configuration folder:

| File | Contents |
|---|---|
| `bml.env` | How BMLibrarian connects to its database: the everyday, unprivileged account. |
| `bml-admin.env` | The server's administrator password. **Keep it.** Without it the server can't be managed, and `init` stops rather than overwrite anything. |
| `bml-pgserver.json` | Where the server's programs and data are, and its port. |

Only your user account can read these files. The passwords are generated for
you, and you never need to type them.

The server's log is `bml-server.log` in the data folder.

## Autostart, per system

| System | How it starts at login |
|---|---|
| macOS | a LaunchAgent, `~/Library/LaunchAgents/org.bmlibrarian.pgserver.plist` |
| Linux | a user service, `~/.config/systemd/user/bml-pgserver.service` |
| Windows | the `BMLibrarianPgServer` entry under your user's "Run at login" registry key |

In each case the server is started once at login. Nothing restarts it if you
stop it.

## Problems

- **"admin credentials file … is missing"**: `bml-admin.env` was deleted.
  Restore it from a backup. BMLibrarian won't re-create the server over your
  data.
- **"… is not empty and is not a PostgreSQL data folder"**: choose a new or
  empty folder.
- **"PostgreSQL 16 found; version 18 or newer is required"**: point
  `--bindir` at a PostgreSQL 18 installation.
