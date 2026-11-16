# Investor demo runbook (2026-11-23)

Two parts, both in the BMLibrarian app window:

1. **The prepared library**: depression & anxiety, about 8,400 peer-reviewed
   trials and reviews with full text, built in the days before.
2. **A live install**: the same app started fresh. It sets everything up, and
   papers arrive and become searchable while the audience watches.

The two never share a folder. The prepared library uses `~/.bml-demo` and
`~/BMLibrarian-demo`. The live install uses the defaults, `~/.bmlibrarian`
(which also holds the Python app's settings; leave those alone) and
`~/BMLibrarian`.

## By 2026-11-22: get ready

1. **The prepared library is complete.**

   ```bash
   ~/.bml-demo-bin/bml --config-dir ~/.bml-demo library status
   ```

   Look for "0 to do" in the Index line ("not tried yet" may stay at a
   handful: papers Europe PMC holds no full text for). If the build stopped (log:
   `~/.bml-demo/build.log`), run it again; it carries on:

   ```bash
   nohup caffeinate -i ~/.bml-demo-bin/bml --config-dir ~/.bml-demo library update \
     >> ~/.bml-demo/build.log 2>&1 &
   ```

2. **Build the app and `bml` together** (the app needs `bml` beside it for
   its login items):

   ```bash
   cd ~/src/bmlibrarian/rust
   cargo build --release -p bml-cli -p bml-app
   ```

3. **No live install left over.** None of these may exist:
   `~/BMLibrarian`, `~/.bmlibrarian/bml.env`, `~/.bmlibrarian/bml-admin.env`,
   `~/.bmlibrarian/bml-pgserver.json`, `~/.bmlibrarian/bml-library.json`. If a
   rehearsal left them, see "Afterwards" below.

4. **Pre-copy the two big downloads** into the live install's settings
   folder (the search model, 1.1 GB, and the bundled PostgreSQL, 0.3 GB), so a
   phone connection only has to carry the papers:

   ```bash
   mkdir -p ~/.bmlibrarian
   cp -R ~/.bml-demo/models ~/.bml-demo/pgdist ~/.bmlibrarian/
   ```

   Screen 3 then shows those steps as already in place. The database and
   library are still created fresh.

5. **Ollama is running** (`ollama list` answers). The two approved models are
   already on this Mac.

6. **Test the phone hotspot**: join it and run step 1's status command and
   one `bml search`.

7. **Rehearse once end to end** (below), then clean up as in "Afterwards" and
   repeat steps 3–4. During the rehearsal, check these on purpose (no
   automated test covers them):
   - Choose a topic with **Every week** and watch screen 5's counts move
     within a minute (a scheduled update starts at the same moment and must
     not freeze the screen).
   - Turn the hotspot off for a minute: screen 5 says it is waiting for the
     internet. Turn it back on: within a minute or so the download carries on
     by itself.
   - Press **Pause**, then **Resume**.
   - Search on the prepared library: the first search takes a few seconds
     while the search model loads; later ones are quick.

## On the day

Keep the Mac on power, and turn off notifications (Focus).

### 1. The prepared library (about 5 minutes)

Start with the prepared library, so its database is running before the live
install picks a port for its own.

```bash
BML_CONFIG_DIR=~/.bml-demo ~/src/bmlibrarian/rust/target/release/bml-app
```

It opens on **Search**. Questions that show it well:

- does exercise reduce depressive symptoms
- ketamine for treatment-resistant depression
- psilocybin depression trial
- digital mental health apps for anxiety
- postpartum depression screening
- mindfulness for anxiety in students

Click a result to show the full text. Point out that the matching passage is
found by meaning, not by the words. Then quit the app (⌘Q).

### 2. The live install (about 10 minutes)

```bash
~/src/bmlibrarian/rust/target/release/bml-app
```

1. **Welcome** → Start.
2. **Where your library lives** → Continue.
3. **Setting up**: the steps tick through; the downloads are already in
   place.
4. **Your library**: pick a different topic from the prepared one (for
   example *Obesity & GLP-1 drugs*) to show that it works for any field.
   Leave "Every week" → **Start downloading**.
5. **Building your library**: the counts start moving within a minute. The
   first week of papers is searchable by abstract within a minute or two,
   and by full text within about five.
6. **Search what is ready** → ask a question on the new topic.

## If something goes wrong

- **No internet**: screen 5 says it is waiting for the internet. Go back to
  the prepared library; it needs no network.
- **A setup step fails**: its line says why. Press **Try again**, or switch to
  the prepared library.
- **The app will not open on the prepared library**: start its database by
  hand, `~/.bml-demo-bin/bml --config-dir ~/.bml-demo server start`, and try
  again.

## Afterwards: remove the live install

```bash
~/src/bmlibrarian/rust/target/release/bml server stop
~/src/bmlibrarian/rust/target/release/bml server autostart disable
~/src/bmlibrarian/rust/target/release/bml library schedule manual
rm -rf ~/BMLibrarian
rm -f ~/.bmlibrarian/bml.env ~/.bmlibrarian/bml-admin.env \
      ~/.bmlibrarian/bml-pgserver.json ~/.bmlibrarian/bml-library.json
```

This leaves the Python app's files in `~/.bmlibrarian` and the prepared
library untouched. Keep `~/.bmlibrarian/models` and `pgdist` for the next
rehearsal, or delete them too.
