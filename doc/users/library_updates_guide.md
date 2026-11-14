# Keeping your library up to date (`bml library`)

Once `bml setup` has set up your database and library folder, `bml library
update` downloads medRxiv into it and makes every paper searchable:

1. **Paper details** (title, authors, abstract, every version) from medRxiv,
   day by day.
2. **Full text** for each paper: its JATS XML, or its PDF when the JATS has
   no article text. Files go into the `documents` folder of your library.
3. **Search index**: every paper's title and abstract, and its full text
   where held, cut into passages and turned into vectors by the embedding
   model that `bml setup` downloaded.

## Running an update

```bash
bml library update                     # everything since medRxiv began (2019)
bml library update --from 2026-01-01   # paper details from this day on
bml library update --skip fulltext     # details and index only
```

The day you give with `--from` is remembered: later updates, scheduled ones
too, start from it. Give an earlier `--from` to widen the library.

New papers become searchable by their title and abstract first, within the
hour; their full text is added to the search as it arrives.

You can stop an update at any time with Ctrl-C. It finishes the paper it is
working on and stops. Running it again carries on where it left off: nothing
already downloaded or indexed is done twice. A crash or a power cut loses at
most the paper in flight.

Only one update runs at a time. If another one is already running, for
example a scheduled one, a second `bml library update` says so and stops.

Exit codes, for scripts: `0` done, `1` something failed (the messages say
what; running again retries it), `2` no library or database is set up yet
(run `bml setup`), `4` stopped early (Ctrl-C, or medRxiv asked us to slow
down). `bml library update --if-older-than 7` does nothing (exit 0) if the
library was brought fully up to date less than 7 days ago; this is what a
scheduled update runs.

## Why full text is slow

medRxiv limits how fast one computer may download from it. BMLibrarian waits
30 seconds between requests (`MEDRXIV_REQUEST_DELAY`), the rate measured as
safe. A paper costs one request when its JATS XML holds the article, two when
the PDF is needed. That is at most about 2,880 papers a day. A weekly update
(a few hundred new postings) takes a few hours, mostly waiting. Downloading
the whole medRxiv backlog this way takes weeks. A faster bulk route through
medRxiv's archive on Amazon S3, with your own AWS account, is planned.

If medRxiv answers "too many requests" anyway, the update stops fetching full
text for an hour and tells you when it will resume. Paper details and the
search index carry on.

## Abstract only

A paper whose full text could not be fetched is kept **abstract only**: it is
still searchable by its title and abstract. This is never final. The paper is
tried again later: after an hour (doubling each time, up to a week) for
problems that may pass, such as a timeout or a server error; after 30 days
for refusals that usually last, such as a PDF blocked by medRxiv's firewall
or a file that does not exist. `bml library status` lists the reasons.

When a paper gets its full text later, or medRxiv posts a new version, the
paper is indexed again. A new version replaces the old one, its file and its
passages. If the new version cannot be fetched, the old version's full text
stays.

## What the library holds

```bash
bml library status
```

shows how many papers there are, how many have JATS or PDF full text, how
many are abstract only (with the most common reasons), how many are indexed,
when the last complete update finished, and whether full text is paused
after medRxiv asked us to slow down. Files in the documents folder that no
paper uses are only counted, never deleted for that alone.

## Updating automatically

```bash
bml library schedule weekly     # the default: once a week
bml library schedule every 3    # every 3 days (1 = daily, up to 365)
bml library schedule manual     # only when you run `bml library update`
```

This adds an entry to your computer's own scheduler, for your user only and
without administrator rights: a launch agent on macOS, a `systemd --user`
timer on Linux, a scheduled task on Windows. Running the command again with
another choice replaces it. The entry checks once a day, at noon, and
updates when the last complete update is as old as your choice. An update
that did not finish (the backlog, a pause after medRxiv asked us to slow
down, an error) carries on the next day. On macOS and Linux the output of
each scheduled update goes to `bml-library-update.log` in your BMLibrarian
configuration folder; Windows keeps no log, so use `bml library status`.

Notes:

- The entry runs the `bml` program you scheduled it with, so schedule from
  the installed `bml`, not from a development build that may move.
- macOS also checks when you log in (and right after you schedule), and
  runs a missed check when the Mac wakes from sleep.
- On Linux the timer runs while you are logged in; a missed check runs at
  your next login.
- On Windows a check missed while the computer is off waits for the next
  day. Windows scheduling has not been tried on a real machine yet.

## Where things are

- Your library folder (default `~/BMLibrarian`): `documents/` holds the
  downloaded files, `database/` the private database (if `bml setup` made
  one).
- Update log of scheduled runs: `bml-library-update.log` in the
  configuration folder (`~/.bmlibrarian` unless you chose another).
