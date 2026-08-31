# Audible → Goodreads

Converts your Audible audiobook library into a file Goodreads can import,
so you don't have to add hundreds of titles by hand. There's no official
integration between the two services (despite both being owned by Amazon),
so this tool bridges the gap: it talks to Audible and reformats the data
for Goodreads, but **you** log into both — your passwords never touch
this tool, only the real Audible and Goodreads login pages.

---

## What you need

- A Windows PC (this is what `Start.bat` targets; see [Advanced](#advanced-command-line-only--other-platforms) if you're on Mac/Linux)
- An internet connection
- Your Audible account login (2FA is fine)
- Your Goodreads account login
- **Nothing else.** You do not need Python, pip, or any dev tools installed
  beforehand — `Start.bat` sets all of that up for you automatically.

---

## Quick start

1. **Get the files.** If you haven't already:
   [download this repository as a ZIP](https://github.com/mindattic/Audible-To-GoodReads)
   (Code → Download ZIP on GitHub) and extract it anywhere, e.g. your
   Desktop. If you already have it cloned with `git`, just make sure it's
   up to date (`git pull`).

2. **Double-click `Start.bat`.**
   A black console window opens. First run only, it will:
   - Check whether Python is installed. If not, it installs it
     automatically (via Windows' built-in `winget` tool, or by downloading
     the official installer from python.org if `winget` isn't available)
     — no admin rights needed, and it only installs for your user account.
   - Install the few Python packages this tool needs (Flask, requests,
     audible-cli).

   This first run can take a couple of minutes. Every run after that is
   fast (a few seconds) since everything is already installed.

3. **Your browser opens automatically** to a local page (`127.0.0.1:5151`
   — this only exists on your own computer, nothing is exposed to the
   internet). You'll see 5 numbered steps. Work through them top to
   bottom — each one unlocks after the previous is done:

   **Step 1 — Connect your Audible account.**
   Click **Open Audible Login**. This opens a *separate* real terminal
   window running `audible quickstart`. Log in there — email, password,
   2FA code if you use it. This window is a normal Windows terminal
   talking directly to Audible; the wizard page in your browser cannot
   see anything you type here.
   When you're done, go back to the browser tab and click
   **"I've logged in — check again."**

   **Step 2 — Export your library.**
   Click **Export Library**. This pulls your titles, authors, ratings,
   and listening progress into a file called `library.json` in this
   folder. Takes a few seconds.

   **Step 3 — Convert to Goodreads format.**
   Click **Convert**. Leave "Look up ISBNs" checked (recommended) — it
   queries the free Open Library database for each title to find a
   matching ISBN, which makes Goodreads far more likely to recognize the
   book. This takes about half a second per title (a library of 250
   books takes roughly 2 minutes) — you'll see a live progress bar.
   When it finishes you'll see totals: how many titles matched an ISBN,
   and how many landed on each shelf (read / currently-reading / to-read,
   pulled from your actual Audible listening progress).

   **Step 4 — Test import.**
   Click **Download test_import.csv** (just 5 titles), then
   **Open Goodreads Import Page**. On Goodreads:
   **My Books → Import and export → Import books**, upload the file you
   just downloaded. Check those 5 titles show up correctly in your
   Goodreads library before doing the full import — bulk imports are
   hard to cleanly undo, so this is worth the extra minute.

   **Step 5 — Full import.**
   Once the test batch looks right, click **Download goodreads_import.csv**
   and upload that on the same Goodreads import page. This one has your
   entire library.

4. **When you're done**, close the browser tab and press any key in (or
   close) the black console window to stop the app.

---

## Troubleshooting

**A handful of titles didn't import.**
Expected for some titles, especially self-published or Audible-exclusive
audiobooks and audio dramas that never had a traditional ISBN — Goodreads'
bulk importer can't match them on title/author alone. Fix: on Goodreads,
use the normal search box to add those titles by hand — Goodreads' live
search is more forgiving than its CSV importer. A very recently released
book can also fail even with a correct ISBN, simply because Goodreads
hasn't indexed that ISBN into its import-matching database yet; try again
in a week or two, or add it manually.

**Start.bat flashes and closes immediately.**
Right-click `Start.bat` → **Edit** to confirm it wasn't corrupted by the
download, or run it once from inside a terminal (`cmd /c Start.bat`) to
see the error before the window closes.

**"Python was not found" and the automatic install didn't work.**
Some locked-down/corporate machines block both `winget` and direct
downloads. In that case, install Python yourself from
[python.org/downloads](https://www.python.org/downloads/) (check
"Add python.exe to PATH" during setup), then run `Start.bat` again.

**The browser didn't open, or shows nothing at `127.0.0.1:5151`.**
Another copy of the app might already be running (only one can use that
port at a time) — check for an existing console window, close it, and
try again. Otherwise, open `http://127.0.0.1:5151` manually in your
browser while the console window is running.

**Audible login keeps failing / asks for 2FA repeatedly.**
This happens in the separate `audible quickstart` terminal window, and is
between you and Audible directly — try again, and make sure you're using
a current 2FA code (they expire in ~30 seconds).

---

## Privacy notes

- `library.json`, `goodreads_import.csv`, and `test_import.csv` (your
  actual book data) are created locally and are excluded from this
  repository (`.gitignore`) — they never get committed or pushed.
- Your Audible login is stored locally by `audible-cli` in its own config
  directory (outside this project folder), the same as if you'd run it
  yourself from a terminal.
- This tool makes exactly one kind of outbound call with your data: a
  title/author lookup per book to the free, public Open Library API (to
  find ISBNs). No other service ever sees your library.

---

## Advanced: command line only / other platforms

The wizard is a thin UI wrapper around a standalone CLI script — you can
skip the browser entirely and run each step by hand (this also works on
macOS/Linux, where `Start.bat` doesn't apply):

### 1. Install audible-cli

```
pip install audible-cli
```

### 2. Authenticate with Audible (interactive, your credentials)

```
audible quickstart
```

Follow the prompts (Amazon/Audible login, 2FA if enabled, marketplace
selection). This only needs to be done once; it stores an auth profile
locally.

### 3. Export your library

```
audible library export -f json -o library.json
```

### 4. Install this project's dependencies

```
pip install -r requirements.txt
```

### 5. Convert to a Goodreads-ready CSV

```
python audible_to_goodreads.py library.json -o goodreads_import.csv
```

This looks up each title on the free Open Library API to backfill
ISBN/ISBN13 (most audiobooks don't carry one natively), which improves
how well Goodreads matches each row to an existing book. Skip this with
`--no-isbn-lookup` if you want a faster, offline-only conversion.

### 6. Import into Goodreads

Go to **Goodreads → My Books → Import and export → Import books**, and
upload `goodreads_import.csv`.

Test with a handful of rows first — copy the header plus a few rows out
of the full CSV by hand into a separate file, upload that, check the
results, then run the full import.

---

## Known limitations

- Audible Originals, podcasts, and some exclusives often have no ISBN
  anywhere — those rows import with title/author only, and Goodreads
  will either fuzzy-match them or create a new, sparse book entry (or
  fail to import at all — see Troubleshooting above).
- `audible-cli` uses a reverse-engineered private API; if Audible changes
  something, exports can break until the tool is updated.
- The `Exclusive Shelf` column is set from Audible's finished/in-progress
  state (`read` / `currently-reading` / `to-read`) — check this looks
  right for a few titles before the full import.
- A correct ISBN doesn't guarantee a Goodreads match for very recently
  released books; Goodreads' own catalog can lag behind new releases.
