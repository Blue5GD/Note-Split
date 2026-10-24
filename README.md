# Note Split

Note Split turns a lecture into an Obsidian study note, an Anki deck, or both. You can make a note, cards, or both. The note is for understanding. The cards are only facts that must be recalled word for word. It was built for the Yale Computer Society Catalyst sprint.

You can give the note a style by uploading example notes, or by choosing a saved style. A saved style is a style summary you already have on this computer. It skips the summarizer, so it saves one paid model call. You do not need to upload example notes to use one.

Obsidian is a notes app. It stores each note as a markdown file, which is plain text with simple marks such as `#` for a heading. Anki is a flashcard app. A deck is one set of cards, and an `.apkg` file is the deck file Anki imports.

## How it works

Note Split has three agents: a summarizer, a drafter, and a card-creator. An agent is one job, with its own instructions. When an agent runs, that is one model call, meaning one request to OpenAI. The two checkboxes choose which agents run.

A note needs a style source. You upload one or more example notes, or you choose a saved style. A saved style holds a style summary from an earlier run, or one you added by hand. It replaces what the summarizer would write for this run, so the summarizer is not called. No example notes are opened or sent on a saved-style run.

- Both checked, example notes: the summarizer, then the drafter, then the card-creator. Three calls.
- Both checked, saved style: the drafter, then the card-creator. Two calls. The summarizer is skipped.
- Only Study note, example notes: the summarizer, then the drafter. Two calls.
- Only Study note, saved style: the drafter only. One call.
- Only Flashcards: the card-creator only. One call. Cards only is not a fourth agent. It skips the summarizer and the drafter, and it ignores both example notes and saved styles. The cards come from the source and the optional instruction.

If you upload photos, the app transcribes them one page at a time before those calls. That is one vision call per photo page. It only reads the page. It is not a fourth agent. It adds to the paid calls for the run.

Some runs make more calls than the lists above. The drafter may be called once more when the note comes out much longer than the measured target, or than the typical word count saved with a style. The card-creator may be called once more when its reply has no usable cards. The page shows "Up to N paid model calls" above Run, and that number includes those possible retries and one call per photo page. The actual number depends on the replies.

- The summarizer reads your example markdown notes and writes a dense 300-450 word style contract. It covers length, headings, paragraph shape, lists and callouts, voice, math and notation, Obsidian markup, recurring patterns, and a short "do not" list. It also copies 2-4 short lines from your notes. It does not run when you choose a saved style, and it does not run in cards-only mode.
- The drafter writes the Obsidian note from the source, the style brief, and an optional instruction. When the app measured example notes, the drafter uses the median word count as its target. A saved style with no measurements follows the length in the brief instead of inventing a median.
- The card-creator returns only the recall cards. With both boxes checked, it reads the source and the finished note. With only Flashcards checked, it reads the source and the optional instruction. It asks the Responses API for strict JSON with a schema (`text.format` / `json_schema`), not Chat Completions `response_format`. The app still checks the reply and retries once if it has no usable cards, such as an empty front or back. That check is a safeguard, not a sign that JSON errors are expected.

## What you need

- Python.
- An OpenAI API key. The key is a secret string from your OpenAI account. The app sends it with each request, and those requests spend credits (the paid balance) on that account.
- The packages in `requirements.txt`: `streamlit`, `streamlit-sortables`, `pymupdf`, `genanki`, `python-dotenv`, and `openai`. The file pins the exact installed versions.

Open the finished note in Obsidian. Import the `.apkg` in Anki. The app can build that deck file without Anki running.

## Setup

Open a terminal in this project folder, then run these commands.

Create a virtual environment. That is a folder of packages used only by this project, so they stay separate from other Python work:

```bash
python -m venv .venv
```

Turn that environment on. You do this again in each new terminal before you run the app. On Linux:

```bash
source .venv/bin/activate
```

Windows uses a different activate path (`.venv\Scripts\activate`).

Install the packages named above:

```bash
pip install -r requirements.txt
```

Copy the example settings file, then open `.env` and put your OpenAI key on the `API_KEY` line. `PROVIDER` must stay `openai`.

```bash
cp .env.example .env
```

The file should look like this, with your key after the equals sign:

```
PROVIDER=openai
API_KEY=sk-your-key-here

# Optional: prices in USD per million tokens. Uncomment both to show
# an estimated dollar cost. Set both or neither.
# INPUT_PRICE_PER_MTOK=
# OUTPUT_PRICE_PER_MTOK=
```

The two price lines are optional. Each is a price in US dollars per million tokens. Uncomment both and set both to show an estimated dollar cost for a finished run. Leave them commented out, or blank, to show token counts only. The app does not hardcode prices. The estimate is not a bill.

The real key stays on your computer. Pushing sends files to the shared copy of the project, so `.env` must not be pushed. `.env.example` is the file that is safe to share, because its key line is empty.

Start the page:

```bash
streamlit run app.py
```

Streamlit opens a page in the browser and reruns the Python file when a widget is clicked. A widget is something on the page you click or type in, such as a button, a file box, or a text box. A widget click never calls the model. Only the Run button starts the pipeline.

## How to use the page

The page has four steps.

1. **What to make.** Two checkboxes, both on at the start: Study note and Flashcards. Leave both on to make the note and the cards. Study note alone makes the note. Flashcards alone makes the cards. When Flashcards is the only box checked, step 2 changes: the style controls disappear, and the page says the run only reads the source. Example notes and saved styles are not used and are not sent. If neither box is checked, the page stops with "Choose a study note, flashcards, or both." That click does not call the model.
2. **Style source.** For a note or both run, choose one:
   - **Upload example notes.** Upload one or more `.md` files. These are notes you already like. They set the length and the habits of the new note.
   - **Saved style.** Choose a name from the **Saved style** list. **View style summary** opens the saved brief. **Delete style** asks for confirmation before it removes the saved copy. **Add a style summary** opens a form for a name, a pasted style summary, and an optional typical word count. Use it when you have no saved styles yet, or when you want to add another. Saving a name that already exists replaces it.

   On a cards-only run, step 2 says the run only reads the source, and that example notes and saved styles are not used and are not sent.

3. **Source.** Upload exactly one kind: several `.txt` files, or several PDFs, or photos (`png`, `jpg`, `jpeg`). Do not mix kinds in one run.
4. **Instruction.** This box is optional. Leaving it empty is fine.

The button label follows the boxes. Both boxes: **Make the note and cards**. Only Study note: **Make the note**. Only Flashcards: **Make the cards**. Above the button, a caption shows "Up to N paid model calls" for the current choices.

When both are checked, download `note.md` and `cards.apkg`. The preview can show Note, Cards, and Style notes. Style notes starts closed. Style notes are not downloaded. A study note alone downloads `note.md` and does not make an `.apkg`. Flashcards alone downloads `cards.apkg`.

For a note or both run, Preview also has **Save this style for later**. It saves the run's style brief and measured word counts under a name. The control is not shown in cards-only mode, because that mode has no style.

## Saved styles

A saved style is a named style summary stored on this computer. It holds the style brief and any measured word counts, not the original example notes. A saved-style run does not read or send any example notes.

There are two ways to make one:

- After a successful note or both run, open **Save this style for later** in Preview, type a name, then click **Save style**. This stores that run's style brief and measured word counts.
- In step 2, open **Add a style summary**, type a name, paste a style summary, and optionally give a typical word count. Use the count when you know the length you want; the drafter treats it as the target. With no count, the drafter follows the length described in the summary and does not invent a median.

To use one, choose **Saved style** in step 2 and pick it from the list. You can view the summary before a run, or delete it after checking the confirmation box. Deleting removes only the saved copy on this computer. Saving a name that already exists replaces the old summary.

A saved style skips the summarizer entirely. That saves one paid model call. It does not skip the drafter. On a both run it is two agent calls (drafter and card-creator) instead of three. On a notes-only run it is one instead of two. A cards-only run does not use a saved style: it still makes one card call, plus its possible retry.

## Tokens, cost, and spend guards

A finished run shows a compact line such as:

```
2 model calls · 1,200 input tokens · 300 output tokens
```

The app records input tokens, output tokens, and the model-call count from the API response for every paid call. That includes photo vision calls and retries.

A dollar estimate appears only when both `INPUT_PRICE_PER_MTOK` and `OUTPUT_PRICE_PER_MTOK` are set in `.env`. Each is a price in US dollars per million tokens. The app does not hardcode prices. Without both, the line shows tokens only, and its help tooltip explains the two variables. The estimate is not a bill.

The caption above Run shows "Up to N paid model calls" for the current mode, style source, and source files. It includes the retries that mode can make (the drafter length retry, the card retry, or both) and one vision call per photo page. It is a spending guard, not an estimate from the API. A run may make fewer calls.

After an attempt that gets past the upload check, the Run button waits 60 seconds. That wait is there so a second click does not spend API credits again. A click with no files, or with neither box checked, does not start the wait. The cooldown stores epoch time, and for the last successful run it survives a browser reload.

The last successful result is saved on this computer. A browser reload or a new tab restores it, with the caption "Restored from the last run on this computer. No credits were spent." Whatever the run made — note, cards, deck, or style brief — is kept, along with token counts and the finish time. A failed later run does not replace the stored result.

**Clear saved result** removes the local copy after you check the confirmation box. Files you already downloaded are not affected.

## Where your data lives

The app stores local data in `.note-split/`, next to the app. That folder is gitignored. It holds:

- `style_profiles.json` — the saved styles.
- `last_run.json` — the last successful result.

Both files are written with `0o600` permissions, so only your operating-system user can read them. `NOTE_SPLIT_DATA_DIR` can point the app at a different folder.

Source text and example notes are not stored. A saved style stores only its brief and measured summary. The last run stores the generated note and card content, the deck bytes, the style brief, token counts, and the finish time, when those pieces exist.

## Tips

- Choose only what you need. A study note alone skips the card-creator. Flashcards alone skip the summarizer and the drafter. Fewer calls spend fewer API credits.
- A saved style skips the summarizer and saves one paid call. It does not skip the drafter. Cards only ignores both example notes and saved styles.
- Cards only never reads example markdown files or a saved style. They are not opened, and they are not sent.
- Example notes decide the length and the habits of the new note. A few real notes of yours work better than one empty file. If you use a saved style with no measurements, add a typical word count when you create it, or expect the drafter to follow the length described in the summary.
- Use a lecture, a chapter section, or a few paper pages. There is an 80,000 character cap. A full textbook will be refused.
- One kind of source only. The page stops if photos are mixed with a txt or PDF, or if a PDF is mixed with a txt.
- iPhone HEIC photos must be exported as JPEG first. HEIC is the photo format an iPhone saves by default, and the page accepts png, jpg, and jpeg.
- At most 20 photos. Two or more source files can be dragged. Photos start in filename order, so page-10 comes before page-2 unless the names are zero-padded (page-01, page-02) or you drag them.
- The optional instruction can change style and how many cards are made. It cannot make the app paste the source unchanged, and it cannot turn the whole note into cards. In a cards-only run, it cannot turn the whole source into cards.
- After a run that got past the upload check, the button waits 60 seconds. A click with no files does not start the wait. Neither box checked does not start the wait.
- Several photos can take about a minute.
- Math in the note uses `$` and `$$`. The deck download converts those to Anki's `\(\)` and `\[\]`.
- The conversion leaves common spaced dollar amounts alone, such as `$5 and $10` or `$3.50 to $4.25`. Tight inline math such as `$a$` still converts. A tight currency range such as `$5-$10` can still be mistaken for math. The app does not fully detect currency.
- An empty card list can be a valid result. When the run makes cards, the `.apkg` is still created. A study note by itself does not make a package.
- Handwritten math in photos can be wrong.
- Typed PDFs only include text already stored in the file. If equations are missing, use photos of those pages instead.
- `.txt` files and example `.md` files must be UTF-8. If one is not, the page shows a clear message instead of a traceback.
- The last successful result restores after a reload. **Clear saved result** removes that local copy; files you already downloaded stay.
- There is no card-editing screen, no revision loop, no model picker, no chunking, and no automated test suite.

## Project files

- `app.py` — the web page: the checkboxes, the style source, the uploads, the Run button, the preview, the saved-style controls, the token line, and the saved-result restore and clear controls.
- `models.py` — sends each request to OpenAI, asks for a JSON schema when a call needs one, returns the reply text, and counts tokens. It also estimates a cost when both price variables are set.
- `prompts.py` — holds the instruction text for the summarizer, the drafter, the card-creator, a separate cards-only instruction, and photo transcription.
- `extract.py` — reads `.txt` files, PDFs, and photos, and turns them into one source string. It also handles photo transcription.
- `pipeline.py` — runs the model calls for the chosen mode, reuses a saved style instead of calling the summarizer, checks the replies, parses the card JSON, and swaps math delimiters on a copy for the deck.
- `anki_export.py` — turns the card list into the `.apkg` file.
- `storage.py` — saves and loads style profiles and the last run in `.note-split/`.
- `.env.example` — a sample settings file with `PROVIDER=openai`, a blank `API_KEY`, and optional price variables.
- `requirements.txt` — the list of packages to install, pinned to exact versions.
