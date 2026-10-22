# Note Split

Note Split turns a lecture into an Obsidian study note, an Anki deck, or both. You can make a note, cards, or both. The note is for understanding. The cards are only facts that must be recalled word for word. It was built for the Yale Computer Society Catalyst sprint.

Obsidian is a notes app. It stores each note as a markdown file, which is plain text with simple marks such as `#` for a heading. Anki is a flashcard app. A deck is one set of cards, and an `.apkg` file is the deck file Anki imports.

## How it works

Note Split uses up to three model calls. A model call is one request to OpenAI. Each call has its own instructions, and the reply is text. The two checkboxes choose which calls run.

- Both checked: the summarizer, then the drafter, then the card-creator.
- Only Study note: the summarizer, then the drafter. The card-creator is not called, and there is no `.apkg`.
- Only Flashcards: the card-creator only. Cards only is not a fourth agent. It skips the summarizer and the drafter. It does not see the example notes. The cards come from the source and the optional instruction.

If you upload photos, the app transcribes them one page at a time before those calls. That transcription only reads the page. It is not a fourth agent. An agent, in this app, is one of the three calls below.

- The summarizer reads your example markdown notes and writes a style brief. The brief describes the length and the habits of those notes.
- The drafter writes the Obsidian note from the source, that brief, and an optional instruction.
- The card-creator returns only the recall cards. With both boxes checked, it reads the source and the finished note. With only Flashcards checked, it reads the source and the optional instruction.

## What you need

- Python.
- An OpenAI API key. The key is a secret string from your OpenAI account. The app sends it with each request, and those requests spend credits (the paid balance) on that account.
- The packages in `requirements.txt`: `streamlit`, `streamlit-sortables`, `pymupdf`, `genanki`, `python-dotenv`, and `openai`.

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
```

The real key stays on your computer. Pushing sends files to the shared copy of the project, so `.env` must not be pushed. `.env.example` is the file that is safe to share, because its key line is empty.

Start the page:

```bash
streamlit run app.py
```

Streamlit opens a page in the browser and reruns the Python file when a widget is clicked. A widget is something on the page you click or type in, such as a button, a file box, or a text box.

## How to use the page

The page has four steps.

1. **What to make.** Two checkboxes, both on at the start: Study note and Flashcards. Leave both on to make the note and the cards. Study note alone runs the summarizer and the drafter. Flashcards alone runs only the card-creator. When Flashcards is the only box checked, the example-notes upload disappears. The page says this run only reads the source, and that the example Obsidian files are not opened and are not sent. If neither box is checked, the page stops with "Choose a study note, flashcards, or both." That click does not call the model.
2. **Example notes.** Upload at least one `.md` file when a study note is being made. These are notes you already like. They set the length and the habits of the new note.
3. **Source.** Upload exactly one kind: several `.txt` files, or several PDFs, or photos (`png`, `jpg`, `jpeg`). Do not mix kinds in one run.
4. **Instruction.** This box is optional. Leaving it empty is fine.

The button label follows the boxes. Both boxes: **Make the note and cards**. Only Study note: **Make the note**. Only Flashcards: **Make the cards**.

When both are checked, download `note.md` and `cards.apkg`. The preview can show Note, Cards, and Style notes. Style notes starts closed. Style notes are not downloaded. A study note alone downloads `note.md` and does not make an `.apkg`. Flashcards alone downloads `cards.apkg`.

## Tips

- Choose only what you need. A study note alone skips the card-creator. Flashcards alone skip the summarizer and the drafter. Fewer calls spend fewer API credits.
- Cards only never reads the example markdown files. They are not opened, and they are not sent.
- Example notes decide the length and the habits of the new note. A few real notes of yours work better than one empty file.
- Use a lecture, a chapter section, or a few paper pages. There is an 80,000 character cap. A full textbook will be refused.
- One kind of source only. The page stops if photos are mixed with a txt or PDF, or if a PDF is mixed with a txt.
- iPhone HEIC photos must be exported as JPEG first. HEIC is the photo format an iPhone saves by default, and the page accepts png, jpg, and jpeg.
- Two or more files can be dragged. Photos start in filename order, so page-10 comes before page-2 unless the names are zero-padded (page-01, page-02) or you drag them.
- The optional instruction can change style and how many cards are made. It cannot make the app paste the source unchanged, and it cannot turn the whole note into cards. In a cards-only run, it cannot turn the whole source into cards.
- After a run that got past the upload check, the button waits 60 seconds. That wait is there so a second click does not spend API credits again. A click with no files does not start the wait. Neither box checked does not start the wait.
- Several photos can take about a minute.
- Math in the note uses `$` and `$$`. The deck download converts those to Anki's `\(\)` and `\[\]`.
- An empty card list can be a valid result. When the run makes cards, the `.apkg` is still created. A study note by itself does not make a package.
- Handwritten math in photos can be wrong.
- Typed PDFs only include text already stored in the file. If equations are missing, use photos of those pages instead.

## Project files

- `app.py` — the web page: the checkboxes, the uploads, the button, the preview, and the downloads.
- `models.py` — sends each request to OpenAI and returns the reply text.
- `prompts.py` — holds the instruction text for the summarizer, the drafter, the card-creator, a separate cards-only instruction, and photo transcription.
- `extract.py` — reads `.txt` files, PDFs, and photos, and turns them into one source string.
- `pipeline.py` — runs the model calls for the chosen mode and checks their replies.
- `anki_export.py` — turns the card list into the `.apkg` file.
- `.env.example` — a sample settings file with `PROVIDER=openai` and a blank `API_KEY`.
- `requirements.txt` — the list of packages to install.
