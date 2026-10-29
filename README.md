# Note Split

Note Split turns a lecture into an Obsidian study note, an Anki deck, or both. The note is for understanding, patterns, and quick reference. The cards are only facts that must be recalled word for word. This is based on Justin Sung's approach to note-making and recall. See his [YouTube channel](https://www.youtube.com/@JustinSung). It was built for the Yale Computer Society Catalyst sprint.

Note Split reads text only. Upload `.txt` files or typed PDFs. If your source is handwritten, transcribe it first with a tool such as Gemini, save the text as a `.txt` file, and upload that. The app makes no vision calls, so reading images does not cost extra.

## What it makes

- `note.md` — an Obsidian markdown note in the style of your example notes or a saved style. Math uses `$...$` inline and `$$...$$` for display.
- `cards.apkg` — an Anki deck of the facts the card-creator judged must be recalled word for word. Math uses Anki's `\(...\)` and `\[...\]` delimiters in the deck.

When your example notes use images or embeds repeatedly, the style brief records them, but the drafter can only leave a suggestion in the note; it cannot add the asset. The note can carry over Obsidian formatting from the example style, including color markup, callouts, links, and tags.

A notes-only run downloads `note.md` and does not build a deck. A cards-only run downloads `cards.apkg` and does not write a note. A both run downloads both.

## How it works

Note Split has three agents. An agent is one job with its own instructions. One agent run is one paid model call.

1. **Summarizer** reads your example notes and writes a compact style brief. It does not run when you choose a saved style, and it does not run in cards-only mode.
2. **Drafter** writes the Obsidian note from the source, the style brief, the measured length, and the optional instruction.
3. **Card-creator** selects the recall cards. On a both run it reads the source, the finished note, and the instruction. On a cards-only run it reads only the source and the instruction.

The source is read before those calls. `.txt` files and PDFs are read locally by the app, not by the model. The source is capped at 80,000 characters.

| Run | Style source | Base calls | Possible retries |
| --- | --- | --- | --- |
| Both | Example notes | 3 | Drafter length retry, card retry |
| Both | Saved style | 2 | Drafter length retry, card retry |
| Study note only | Example notes | 2 | Drafter length retry |
| Study note only | Saved style | 1 | Drafter length retry |
| Flashcards only | Not used | 1 | Card retry |

The page shows **Up to N paid model calls** above Run. That number includes the retries the current choices can make. A saved style with no typical word count cannot make the length retry, so its maximum is one lower.

## What you need

- Python.
- An OpenAI API key. Requests spend credits on that account.
- The packages in `requirements.txt`: `streamlit`, `streamlit-sortables`, `pymupdf`, `genanki`, `python-dotenv`, and `openai`.

Open the finished note in Obsidian. Import the `.apkg` in Anki. The app can build the deck without Anki running.

## Setup

Open a terminal in this project folder.

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows, activate it with `.venv\Scripts\activate`.

Install the packages:

```bash
pip install -r requirements.txt
```

Copy the example settings file and add your key:

```bash
cp .env.example .env
```

The file should look like this:

```dotenv
PROVIDER=openai
API_KEY=sk-your-key-here

# Optional: USD prices per million tokens. Uncomment both to show
# an estimated cost. Set both or neither.
# INPUT_PRICE_PER_MTOK=
# OUTPUT_PRICE_PER_MTOK=
```

The two price lines are optional. When both are set, Preview shows an estimated cost after a run. The app does not hardcode prices, and the estimate is not a bill.

Start the page:

```bash
streamlit run app.py
```

Streamlit opens the page in your browser. Changing a widget, opening a preview, or downloading a file does not call the model. Only the Run button starts the pipeline.

## How to use the page

The page has four steps.

1. **What to make.** Both checkboxes start on. Leave both on to make the note and the cards. Study note alone makes the note. Flashcards alone makes the cards. If neither is checked, Run stops before any model call.
2. **Style source.** A note run needs a style. Choose one:
   - **Upload example notes.** Upload one or more `.md` files that already look the way you want. They set the length and habits of the new note.
   - **Saved style.** Pick a style you saved earlier. View it, delete it, or add a new one from this section. A saved style skips the summarizer, which saves one paid call.
   Cards-only runs do not use example notes or saved styles, so the style controls are hidden and the section says so.
3. **Source.** Upload several `.txt` files, or several typed PDFs. Do not mix the two. Handwritten pages are not accepted directly: transcribe them first and save the text as a `.txt` file.
4. **Instruction.** Optional. Use it when the new note or deck should differ from the style source. Examples: a shorter note, more cards, or focus on one section.

Above Run, the page shows the maximum paid calls for the current choices. After an attempt that gets past the upload check, Run waits 60 seconds. A click with no files, or with neither box checked, does not start the wait.

## Source files

- `.txt` files must be UTF-8.
- PDFs must already contain a text layer. A scanned PDF with no text stops with a message; transcribe it and upload a `.txt` file.
- Use one lecture, one chapter section, or a few pages of text. The combined source must be 80,000 characters or fewer.
- Several `.txt` files, or several PDFs, can be dragged into the order they should be read. One file has no drag list.
- Do not mix `.txt` and PDFs in one run.
- A corrupt or password-protected PDF stops with a clear message.

## Saved styles

A saved style is a named style summary stored on this computer. It holds the style brief and any measured word counts, not the original example notes. A saved-style run reads no example notes.

There are two ways to make one:

- After a successful note or both run, open **Save this style for later** in Preview, enter a name, and save.
- In step 2, open **Add a style summary**, enter a name, paste a summary, and optionally give a typical word count.

To use one, choose **Saved style** in step 2. Saving a name that already exists replaces the old summary. You can view or delete a saved style from the same section. Deleting affects only the copy on this computer.

A saved style skips the summarizer, so a both run makes two agent calls instead of three, and a notes-only run makes one instead of two. It does not skip the drafter. A cards-only run ignores saved styles.

## Tokens, cost, and guards

A finished run shows a compact line such as:

```text
2 model calls · 1,200 input tokens · 300 output tokens
```

The app counts every paid call, including the card retry and the drafter length retry. If an attempt fails after one or more paid calls, the page still shows that attempt's counts, labeled **This attempt used**. A failed attempt does not replace the last successful result.

A dollar estimate appears only when both `INPUT_PRICE_PER_MTOK` and `OUTPUT_PRICE_PER_MTOK` are set in `.env`. Restart the app after changing `.env`. The estimate is not a bill.

The last successful result is saved on this computer. A reload or new tab restores it without spending credits. A failed later run leaves the previous preview in place. **Clear saved result** removes the local copy after you confirm; files you already downloaded are not affected.

## Where your data lives

The app stores local data in `.note-split/`, next to the app. That folder is gitignored. It holds:

- `style_profiles.json` — your saved styles.
- `last_run.json` — the last successful result.

Both files are written with `0o600` permissions, so only your operating-system user can read them. `NOTE_SPLIT_DATA_DIR` can point the app at a different folder.

Requests use `store=False`, so the Responses API does not keep the response for later retrieval. OpenAI's own retention and account policies still apply.

Source files and example note files are not stored. A generated style brief can quote a few short lines from your examples, because the summarizer uses them as style illustrations. The last run stores the generated note, cards, deck bytes, brief, measured counts, token counts, and finish time, when those pieces exist.

## Tips

- Use one lecture or one chapter section per run. Split longer material instead of testing the 80,000-character cap.
- Start with two or three real notes that already look like what you want. They make a better style sample than one short file.
- Save a style as soon as a run produces a note you like. Reusing it skips the summarizer next time.
- Match the mode to the material: Flashcards for memorization-heavy topics, both when you also need the explanation.
- Transcribe handwritten pages carefully, and keep the math in the text so the drafter and card-creator can use it.
- Write an instruction for one specific exception, such as a shorter note or a denser deck.
- Review the deck before importing. The app does not edit or approve cards for you.

## Project files

- `app.py` — the Streamlit page: checkboxes, style controls, source upload, Run button, preview, and saved-result controls.
- `models.py` — the single model-call function, token counting, and optional cost estimate.
- `prompts.py` — instructions for the summarizer, drafter, both-mode card-creator, and cards-only card-creator.
- `extract.py` — reads `.txt` files and typed PDFs, applies the 80,000-character cap, and returns one source string.
- `pipeline.py` — runs the selected agents, checks replies, parses card JSON, and swaps math delimiters for Anki.
- `anki_export.py` — builds the `.apkg` file.
- `storage.py` — saves and loads styles and the last result in `.note-split/`.
- `.streamlit/config.toml` — the light and dark theme.
- `.env.example` — sample settings with a blank API key and optional price variables.
- `requirements.txt` — pinned package versions.
