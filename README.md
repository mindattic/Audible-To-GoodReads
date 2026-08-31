# Audible → Goodreads

Converts an Audible library export into a Goodreads-compatible import CSV.
There's no official integration between the two services, so this tool
handles the format conversion — you handle the two logins (Audible and
Goodreads), since credentials never leave your machine or get typed
anywhere but the real login pages.

## Quick start (recommended)

1. Double-click **`Start.bat`** in this folder.
2. A console window opens (installs dependencies on first run — takes a
   minute), then your browser opens automatically to a step-by-step wizard.
3. Follow the 5 steps on the page:
   1. **Connect your Audible account** — opens a separate terminal window
      running `audible quickstart`. Log in there (2FA included); the wizard
      page never sees your password.
   2. **Export your library**
   3. **Convert to Goodreads format** (with automatic ISBN lookup for
      better match rates)
   4. **Test import** — upload a 5-title sample to Goodreads first
   5. **Full import** — upload everything once the test looks right
4. When you're done, close the console window (or press `Ctrl+C` in it) to
   stop the app.

Requires [Python 3.10+](https://www.python.org/downloads/) — `Start.bat`
will tell you if it's missing. Everything else (Flask, audible-cli,
requests) installs itself on first run.

## Advanced: command line only

The wizard is a UI wrapper around a standalone CLI script — you can skip
the browser entirely and run each step by hand:

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

## Before you commit to the full import

Goodreads imports are hard to cleanly undo. Test with a handful of rows
first — the wizard generates `test_import.csv` (first 5 rows) automatically;
on the CLI path, copy the header plus a few rows out of the full CSV by hand.
Upload the small file, check the results in your Goodreads library, then run
the full import once you're happy with the mapping.

## Known limitations

- Audible Originals, podcasts, and some exclusives often have no ISBN
  anywhere — those rows import with title/author only, and Goodreads
  will either fuzzy-match them or create a new, sparse book entry.
- `audible-cli` uses a reverse-engineered private API; if Audible changes
  something, exports can break until the tool is updated.
- The `Exclusive Shelf` column is set from Audible's finished/in-progress
  state (`read` / `currently-reading` / `to-read`) — check this looks
  right for a few titles before the full import.
