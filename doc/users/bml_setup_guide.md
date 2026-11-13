# Setting up BMLibrarian with `bml setup`

`bml setup` checks that your computer has everything BMLibrarian needs and
installs only what is missing. It is safe to run as often as you like: steps
that are already done are left alone, and an interrupted download carries on
where it stopped.

## What it checks and installs

| Step | What it does |
|---|---|
| Hardware check | Warns if the computer has less than 16 GB of memory, too little free disk space for the downloads, or a disk whose free space it cannot read. It never stops setup, and the summary repeats its warnings. When Ollama runs on another computer, its disk is not checked. |
| Database | Sets up the PostgreSQL database BMLibrarian stores its literature in (see "Choosing a database" below). |
| Start at login | Starts the private database automatically when you log in. |
| Ollama | Installs or starts Ollama, the program that runs the AI models on your computer. An Ollama you installed yourself (also with Homebrew) is used rather than installed again; if it is a command rather than an app, setup tells you how to start it. |
| Language models | Downloads the two approved models: `gpt-oss:20b` (about 14 GB) and `medgemma4B_it_q8:latest` (about 5 GB). Other models are never substituted. |
| Embedding model | Downloads the search model (about 1.2 GB) into `models/` inside the BMLibrarian folder and checks it is intact. |

The BMLibrarian folder is `~/.bmlibrarian` unless you give `--config-dir` or
set `BML_CONFIG_DIR`. `bml setup` never reads or changes the files of the
Python program (`.env`, `config.json`).

## Running it

```
bml setup
```

You see one line when each step starts and ends (a skipped step only gets
the end line), a progress line about every
five seconds during downloads, and a summary table at the end. Warnings start
with `Warning:`. Warnings and failed steps are written to standard error,
everything else to standard output; the summary at the end (standard output)
repeats every failure and warning. Setup exits with 0 when no step failed, 1
otherwise. Only one setup at a time can download into a BMLibrarian folder; a
second one stops its download steps with a message saying so.

Useful options:

- `--skip STEP` leaves a step out; repeat it for several. Steps:
  `database`, `autostart`, `ollama`, `models`, `embedding-model`. The
  hardware check cannot be skipped. Skipping `database` also skips
  `autostart`; skipping `ollama` also skips `models`.
- `--ollama-host URL` (or the `OLLAMA_HOST` variable) says where Ollama is.
  The default is `http://127.0.0.1:11434`.
- `--config-dir PATH` uses another BMLibrarian folder (put it before `setup`).

## Choosing a database

**A private database (default).** With no database options, setup
downloads BMLibrarian's own PostgreSQL 18 (with the `vector` extension, and
`pg_search` on Apple-silicon Macs and Linux) and creates a database for
BMLibrarian only, in `<BMLibrarian folder>/pgdata` or the folder given with
`--data-dir`. It listens on this computer only. The program files go into
`<BMLibrarian folder>/pgdist/18.6-r1/` (up to about 360 MB); the download (31–32 MB on
Intel Macs and Windows, 105–115 MB elsewhere) is checked against a fixed checksum before anything is unpacked. On
Intel Macs and Windows there is no `pg_search`, so setup warns that the BM25
search index is missing; BMLibrarian will fall back to PostgreSQL's built-in
text search there.

The ready-made database needs macOS 15 or later on a Mac, and on Linux a
system with glibc 2.36 or later (Debian 12, Ubuntu 23.04, Fedora 37, RHEL 10
or newer; not Ubuntu 22.04 or RHEL 9). Setup checks this before it
downloads anything: on an older system the Database step fails at once,
naming the version found and the one needed. Use `--pg-bindir` with a
PostgreSQL 18 of your own, or `--existing-server`, instead.

If you already set up a database with an earlier `bml setup`, a later run
continues with that one and downloads nothing. Passing `--data-dir` then is
only allowed with that database's own folder; setup refuses a different one
rather than ignore it.

To use a PostgreSQL 18 installation of your own instead, point `--pg-bindir`
at its bin folder (the one with `initdb`); add `--extension-dir FOLDER` for a
`pg_search` kept in its own folder (repeat for more folders).
`--extension-dir` only works together with `--pg-bindir`.

If no ready-made database exists for your computer (for example Windows on
ARM), the Database step fails with a message saying so; use `--pg-bindir` or
`--existing-server`.

**A PostgreSQL you already have.** Use it instead with:

```
BML_PG_SUPERUSER_PASSWORD=... bml setup --existing-server 127.0.0.1:5432 --pg-superuser postgres
```

- The server must run **on this computer** (`127.0.0.1`, `::1` or
  `localhost`; write IPv6 as `[::1]:5432`). The connection is not encrypted,
  so setup refuses any other address.
- It needs PostgreSQL 18 or newer, a superuser, the `vector` extension
  (0.8.1 or newer) and, on macOS and Linux, `pg_search` listed in
  `shared_preload_libraries`.
- The password is never taken from the command line. Set
  `BML_PG_SUPERUSER_PASSWORD` without echoing it
  (`read -s BML_PG_SUPERUSER_PASSWORD && export BML_PG_SUPERUSER_PASSWORD`),
  or add `--password-stdin` and pipe the password in from a password manager.
  Do not type it at a prompt that shows it.
- Setup only adds a role `bml_app` and a database `bmlibrarian`. It
  refuses if those names already exist and are not BMLibrarian's, and never
  touches your other data. `bml server start/stop/autostart` do not manage an
  existing server.

## If a step fails

The summary says which step failed and what to do. Fix the cause (network,
disk space, a missing program) and run `bml setup` again. An interrupted language-model pull resumes where it
stopped (Ollama keeps the partial data); an interrupted embedding-model or
Ollama-installer download starts again from the beginning on the next run.
Later steps still run when an earlier one failed, except those that depend on
it (start at login needs the database; the models need Ollama). If one
language model fails, setup still tries the other one.

An `--existing-server` on another computer, or a password or superuser name
that cannot be used (empty, or starting or ending with a space), stops setup
before any step runs, so nothing is downloaded first; a remote server is
refused before the password is even read. A wrong port or password is only
found by the Database step.

## Linux notes

Installing Ollama runs its official `install.sh`, which uses `sudo`; setup
says so before it runs. The script itself is checked against a pinned
checksum, but the program files that script downloads are not checked by
BMLibrarian (Ollama publishes no checksum we can verify). If that is not
acceptable, install Ollama yourself and run setup again: it will find it.
The macOS and Windows installers are checked against pinned checksums.
Installing on Windows and Linux has not yet been tried on real machines.

## Where to find things

- Database settings for BMLibrarian: `bml.env` (and `bml-admin.env`) in the
  BMLibrarian folder.
- Private database status: `bml server status`.
