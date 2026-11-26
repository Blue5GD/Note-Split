# Note Split

Note Split turns a lecture into an Obsidian study note, an Anki deck, or both. The note is for understanding, patterns, and quick reference. The cards are only facts that must be recalled word for word. This is based on Justin Sung's approach to note-making and recall. See his [YouTube channel](https://www.youtube.com/@JustinSung). It was built for the Yale Computer Society Catalyst sprint.

Note Split reads text only. Upload `.txt` files or typed PDFs. If your source is handwritten, transcribe it first with a tool such as Gemini, save the text as a `.txt` file, and upload that. The app makes no vision calls, so reading images does not cost extra.

## What it makes

- `note.md` — an Obsidian markdown note in the style of a saved style. Math uses `$...$` inline and `$$...$$` for display.
- `cards.apkg` — an Anki deck of the facts the card-creator judged must be recalled word for word. Math uses Anki's `\(...\)` and `\[...\]` delimiters in the deck.

When your example notes use images or embeds repeatedly, the style brief records them, but the drafter can only leave a suggestion in the note; it cannot add the asset. The note can carry over Obsidian formatting from the saved style, including color markup, callouts, links, and tags.

A notes-only run downloads `note.md` and does not build a deck. A cards-only run downloads `cards.apkg` and does not write a note. A both run downloads both.

## How it works

Note Split has three agents. An agent is one job with its own instructions. One agent run is one paid model call.

1. **Summarizer** runs on its own in the **Styles** tab. It reads your example `.md` notes and writes a compact style brief, then saves it with the measured word counts. It never runs during a **Generate** run.
2. **Drafter** writes the Obsidian note from the source, the chosen saved style brief, its word-count targets, and the optional instruction.
3. **Card-creator** selects the recall cards. On a both run it reads the source, the finished note, and the instruction. On a cards-only run it reads only the source and the instruction.

The source is read before those calls. `.txt` files and PDFs are read locally by the app, not by the model. The source is capped at 80,000 characters.

| Tab | Run | Base calls | Possible retries |
| --- | --- | --- | --- |
| Styles | Generate style from example notes | 1 | None |
| Generate | Study note + Flashcards | 2 | Drafter length retry, card retry |
| Generate | Study note only | 1 | Drafter length retry |
| Generate | Flashcards only | 1 | Card retry |

The **Generate** tab shows **Up to N paid model calls** above the Run button. That number includes the retries the current choices can make. A saved style with word counts set to `0` skips the length retry, so its maximum is one lower.

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

Streamlit opens the page in your browser. Changing a widget, opening a preview, or downloading a file does not call the model. Only the Run buttons start a paid call.

## How to use the page

The page has two tabs: **Styles** and **Generate**.

### Styles tab (set up your styles first)

1. **Generate a style from example notes.** Give the style a name, upload one or more `.md` notes that already look the way you want, and click **Generate and save style**. This runs only the summarizer (1 paid call) and saves the brief along with the measured median and longest word counts.
2. **Saved styles.** Pick any saved style to view its summary, edit its text or word counts (**Median words** and **Longest words**), or delete it.
3. **Add a style manually.** Write or paste a style summary yourself with 0 paid calls.

### Generate tab (make notes and cards)

1. **What to make.** Choose **Study note**, **Flashcards**, or both. If neither is checked, Run stops before any model call.
2. **Saved style.** Pick a saved style from the dropdown. (Cards-only runs do not use a saved style.)
3. **Source.** Upload several `.txt` files, or several typed PDFs. Do not mix the two. Handwritten pages are not accepted directly: transcribe them first and save the text as a `.txt` file.
4. **Instruction.** Optional. Sent to the drafter and card-creator for lecture-specific requests (for example, focusing on one section or treating uploaded practice problems as reference).

Above Run, the page shows the maximum paid calls for the current choices. After any paid attempt on either tab that gets past the local upload check, the app waits 60 seconds before allowing another paid run.

## Source files

- `.txt` files must be UTF-8.
- PDFs must already contain a text layer. A scanned PDF with no text stops with a message; transcribe it and upload a `.txt` file.
- Use one lecture, one chapter section, or a few pages of text. The combined source must be 80,000 characters or fewer.
- Several `.txt` files, or several PDFs, can be dragged into the order they should be read. One file has no drag list.
- Do not mix `.txt` and PDFs in one run.
- A corrupt or password-protected PDF stops with a clear message.

## Saved styles

A saved style is a named style summary stored on this computer. It holds the style brief and its word-count targets (**Median words** and **Longest words**), not the original example notes.

- **Median words** is the target length the drafter aims for.
- **Longest words** is the ceiling used alongside `1.5 × median`: a draft is shortened once only if it exceeds **both** `1.5 × median` and `longest`.
- **Median words** cannot be larger than **Longest words**. Setting both to `0` disables the length retry.
- Saving a name that already exists replaces the old style. Deleting affects only the copy on this computer.

## Tokens, cost, and guards

A finished run shows a compact line such as:

```text
2 model calls · 1,200 input tokens · 300 output tokens
```

The app counts every paid call, including the card retry and the drafter length retry. If an attempt fails after one or more paid calls, the page still shows that attempt's counts, labeled **This attempt used**. A failed attempt does not replace the last successful result.

A dollar estimate appears only when both `INPUT_PRICE_PER_MTOK` and `OUTPUT_PRICE_PER_MTOK` are set in `.env`. Restart the app after changing `.env`. The estimate is not a bill.

The last successful Generate result is saved on this computer. A reload or new tab restores it without spending credits. A failed later run leaves the previous preview in place. **Clear saved result** removes the local copy after you confirm; files you already downloaded are not affected.

## Where your data lives

The app stores local data in `.note-split/`, next to the app. That folder is gitignored. It holds:

- `style_profiles.json` — your saved styles.
- `last_run.json` — the last successful result.

Both files are written with `0o600` permissions, so only your operating-system user can read them. `NOTE_SPLIT_DATA_DIR` can point the app at a different folder.

Requests use `store=False`, so the Responses API does not keep the response for later retrieval. OpenAI's own retention and account policies still apply.

Source files and example note files are not stored. A generated style brief can quote a few short lines from your examples, because the summarizer uses them as style illustrations. The last run stores the generated note, cards, deck bytes, brief, measured counts, token counts, and finish time, when those pieces exist.

## Tips

- Start in the **Styles** tab with two or three real notes that already look like what you want. They make a better style sample than one short file.
- After generating a style, open **Edit style summary** to add any permanent rules the summarizer couldn't guess (like custom color meanings or sections to leave blank). That way you don't have to repeat them in **Instruction** every run.
- Tweak **Median words** and **Longest words** in the **Styles** tab if you want longer notes or more room before a length retry triggers.
- Use one lecture or one chapter section per run. Split longer material instead of testing the 80,000-character cap.
- Match the mode to the material: Flashcards for memorization-heavy topics, both when you also need the explanation.
- Transcribe handwritten pages carefully, and keep the math in the text so the drafter and card-creator can use it.
- Keep **Instruction** for lecture-specific requests (such as focusing on a section, or using uploaded practice problems as reference).
- Review the deck before importing. The app does not edit or approve cards for you.

## Project files

- `app.py` — the Streamlit page: Generate and Styles tabs, style management, source upload, Run buttons, preview, and saved-result controls.
- `models.py` — the single model-call function, token counting, and optional cost estimate.
- `prompts.py` — instructions for the summarizer, drafter, both-mode card-creator, and cards-only card-creator.
- `extract.py` — reads `.txt` files and typed PDFs, applies the 80,000-character cap, and returns one source string.
- `pipeline.py` — runs the summarizer or the generate pipeline, checks replies, parses card JSON, and swaps math delimiters for Anki.
- `anki_export.py` — builds the `.apkg` file.
- `storage.py` — saves and loads styles and the last result in `.note-split/`.
- `.streamlit/config.toml` — the light and dark theme.
- `.env.example` — sample settings with a blank API key and optional price variables.
- `requirements.txt` — pinned package versions.
