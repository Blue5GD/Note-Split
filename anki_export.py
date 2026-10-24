"""Turn swapped cards into an Anki package.

The caller already swapped $...$ into Anki's \\(...\\) and \\[...\\].
This file escapes each field for HTML, then writes it into a .apkg and
returns the bytes. It does not change the math delimiters. Writing the
package does not require Anki to be installed.
"""

import html
import os
import tempfile

import genanki

# genanki rejects an id outside this range. The two ids are different,
# and they are fixed so the same deck stays the same deck on every run.
# 2**30 is 1073741824. 2**31 - 1 is 2147483647.
MODEL_ID = 1812345673
DECK_ID = 1912345674

DECK_NAME = "Study cards"

# Our own model. Do not use genanki's built-in basic model.
# Two fields, one template: the front is the question, the back is the answer.
# white-space: pre-wrap is on the template so a newline in a field stays
# a newline. Anki treats the field as HTML, so export_apkg escapes &, <,
# and > before writing. Text such as "x < 5" then stays literal instead
# of starting a tag or an entity.
_MODEL = genanki.Model(
    MODEL_ID,
    "Study card",
    fields=[
        {"name": "Front"},
        {"name": "Back"},
    ],
    templates=[
        {
            "name": "Card 1",
            "qfmt": '<div style="white-space: pre-wrap;">{{Front}}</div>',
            "afmt": (
                "{{FrontSide}}"
                '<hr id="answer">'
                '<div style="white-space: pre-wrap;">{{Back}}</div>'
            ),
        },
    ],
)


def export_apkg(cards: list[dict[str, str]]) -> bytes:
    """Write cards to an .apkg and return the file bytes.

    cards is a list of {"front": ..., "back": ...}. Each string is
    escaped for HTML: &, <, and > become entities. Quotes, backslashes,
    dollar signs, and every other character stay as they are. Anki
    renders a field as HTML, so this keeps comparisons and ampersands
    in math or text literal instead of turning them into tags. An empty
    list still returns a package.

    The file is written in a temporary directory and deleted before
    this returns, so the project folder does not keep an .apkg.
    """
    deck = genanki.Deck(DECK_ID, DECK_NAME)
    deck.add_model(_MODEL)
    for card in cards:
        # A new list, so this does not edit the caller's dict.
        # Only the escaped copies go into the package.
        note = genanki.Note(
            model=_MODEL,
            fields=[
                html.escape(card["front"], quote=False),
                html.escape(card["back"], quote=False),
            ],
        )
        deck.add_note(note)

    # The temp directory is outside the project. It is removed when
    # the block ends, including when writing the package fails.
    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "cards.apkg")
        genanki.Package(deck).write_to_file(path)
        with open(path, "rb") as handle:
            return handle.read()
