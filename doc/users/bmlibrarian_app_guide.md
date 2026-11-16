# The BMLibrarian app

The BMLibrarian app is a single window. It sets up BMLibrarian on your Mac,
downloads a library of medical research on a topic you choose, and lets you
search it by meaning. Everything runs on your computer; the only network
traffic is the downloads.

## First start

1. **Welcome.** What will happen. No administrator password is needed.
2. **Where your library lives.** Your papers and their database go into
   `BMLibrarian` in your home folder. The screen shows the free space there
   and roughly how much a topic library needs (about 10 GB for the largest).
3. **Setting up.** Each step has a line that shows what it is doing: checking
   this Mac, the private database, starting it when you log in, the AI engine
   (Ollama), the language models and the search model. A step that fails says
   why; fix that and press **Try again**. Warnings appear in a corner and go
   away by themselves.
4. **Your library.** Choose a topic:
   - Depression & anxiety
   - Heart failure & cardiology
   - Obesity & GLP-1 drugs
   - Stroke

   Each topic is peer-reviewed, open-access randomised trials, systematic
   reviews and meta-analyses from 2021 to 2026, with their full text. The
   paper counts come from Europe PMC; "(as last counted)" means the app
   could not reach it just now. Choose how often to keep the library up to
   date, then press **Start downloading**.
5. **Building your library.** Counts of papers found, full texts downloaded,
   and papers ready to search, with a time estimate. The newest papers come
   first and are searchable within minutes. You can **Pause**, close the
   window or quit; the app finishes the paper in hand first, and the next
   time it carries on where it stopped. A topic takes about a day in all.
6. **Search.** Ask in plain words, for example *does exercise help
   depression?* The results show the paper, its journal and year, and the
   passage that matched. Click a result to read the paper. Search works
   while the library is still downloading.

After the first start, the app opens straight on Search (or on **Your
library**, if it was closed before a topic was chosen).

## If the internet drops out

The download says *"Waiting for the internet. Downloading carries on when
it's back."* and stops. Nothing is lost: the app tries again by itself about
every minute while the window is open, and carries on once the internet is
back. Meanwhile, **Search what is ready** works as usual.

## Good to know

- One library holds one topic. For another topic, use another library.
- Reference lists and funding statements are never shown as matches.
- A paper whose full text Europe PMC does not hold is searchable by its
  abstract.
