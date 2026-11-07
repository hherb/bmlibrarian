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
healthy, **3** when it is stopped, **2** when no server has been set up yet,
and **1** when it is unhealthy, its data folder is missing, or something went
wrong. `start`, `stop`, `restart` and
`autostart enable` also exit with **2** when nothing is set up.

### Choosing the data folder

The first time, the data folder must be new or empty. `init` refuses a folder
that already holds other files, or another PostgreSQL server's data, and
leaves those files untouched. Later runs of `init` must name the same data
folder and PostgreSQL bin folder.

On macOS and Linux the bin and data folder names may not contain `"`, `$`, a
backtick or `\` (PostgreSQL's own tools cannot handle them). Spaces, accents
and `'` are fine.

A full PubMed mirror needs a lot of space, so an external disk is fine. If the
disk isn't mounted, `status` says the data folder is missing, and `init`
refuses to create a new, empty server in its place.

## Where things are kept

In the configuration folder:

| File | Contents |
|---|---|
| `bml.env` | How BMLibrarian connects to its database: the everyday, unprivileged account. If it is lost, or no longer matches the database (for example a data folder moved from another computer together with its `bml-admin.env`), running `init` again repairs it, and says so: other copies of the old password then stop working. |
| `bml-admin.env` | The server's administrator password. **Keep it.** Without it `init` can no longer repair or finish the setup, and stops rather than overwrite anything (starting, stopping and status still work). |
| `bml-pgserver.json` | Where the server's programs and data are, and its port. |
| `bml-external.json` | Instead of the file above, when you use a PostgreSQL you already have: its address and the administrator account's name. |

Only your user account can read these files. The passwords are generated for
you, and you never need to type them.

The server's log is `bml-server.log` in the data folder. When the server
fails to start, the error message quotes its last lines.

## Using a PostgreSQL you already have

If PostgreSQL 18 is already running on this computer, BMLibrarian can use it
instead of a private one. It adds one account (`bml_app`) and one database
(`bmlibrarian`) and changes nothing else. To do that you give it an
administrator account of that PostgreSQL (usually `postgres`) and its
password. BMLibrarian keeps that password in `bml-admin.env`, readable only by
you.

BMLibrarian checks first, and tells you everything that is missing in one go:

- it must be PostgreSQL 18 or newer, on this computer;
- the account you give must be an administrator;
- the pgvector extension (0.8.1 or newer) must be installed;
- except on Windows, the pg_search extension must be installed and listed in
  that PostgreSQL's `shared_preload_libraries` setting. BMLibrarian never
  changes that setting or restarts your PostgreSQL; you do it.

If an account named `bml_app` or a database named `bmlibrarian` is already
there and BMLibrarian did not make it, it stops and leaves them alone. A
configuration folder uses either a private server or an existing one, not
both.

## Autostart, per system

| System | How it starts at login | When it stops |
|---|---|---|
| macOS | a LaunchAgent, `~/Library/LaunchAgents/org.bmlibrarian.pgserver.plist`. Enabling it also starts the server now. Messages go to `bml-autostart.log` in the configuration folder. | only when you stop it |
| Linux | a user service, `~/.config/systemd/user/bml-pgserver.service`. Messages go to the journal (`journalctl --user -u bml-pgserver`). | when you stop it, or at logout |
| Windows | the `BMLibrarianPgServer` entry under your user's "Run at login" registry key | only when you stop it |

In each case the server is started once at login. Nothing restarts it if you
stop it. There is one login entry per user: enabling it for another
configuration folder replaces the old one. Enable it from an installed `bml`,
because the entry remembers where that program is.

## Problems

- **"admin credentials file … is missing"**: `bml-admin.env` was deleted.
  Restore it from a backup. BMLibrarian won't re-create the server over your
  data.
- **"… is not empty and is not a PostgreSQL data folder"**: choose a new or
  empty folder.
- **"… is another PostgreSQL server's data folder"**: choose a new or empty
  folder; the other server's data is left alone.
- **"the server's data folder … is missing or empty (is its disk mounted?)"**:
  connect the disk and run the command again. If you deleted the data on
  purpose and want a new server, delete `bml-pgserver.json` as the message
  says.
- **"… was left half set up by an interrupted first init"**: setup was cut off
  while the database was being created. If you haven't stored anything in
  that folder, delete it and run `init` again.
- **"this configuration folder already manages a server with data folder …"**:
  use the folder named in the message, or a different `--config-dir`. A first
  `init` that failed early also records its folder; delete `bml-pgserver.json`
  to choose another.
- **"… contains the character …"**: choose a folder whose name doesn't contain
  it.
- **"the PostgreSQL extension vector is not available"**: install pgvector for
  this PostgreSQL, or pass its folder with `--extension-dir`.
- **"extension folder …"**: the folder doesn't exist or isn't laid out as
  `lib/postgresql` and `share/postgresql`.
- **Starting fails after the port was taken by another program**: the server
  keeps the port it was set up with. Free that port.
- **"PostgreSQL 16 found; version 18 or newer is required"**: point
  `--bindir` at a PostgreSQL 18 installation.
