"""Run the three agents, and check their replies.

check_example_notes runs before the summarizer and before the source
is read. Empty notes, or notes past the character cap, raise Stop.
That check does not call the model.

measure_example_notes counts words, headings, and bullets. It does
not call the model. Those numbers go to the summarizer and the drafter.

run_pipeline then calls the summarizer, the drafter, and the
card-creator, in that order. If the drafted note is much longer than
the examples, the drafter is asked once to shorten it. The pipeline
parses the card JSON, retries that call once if the JSON is bad,
swaps math delimiters on a copy, and writes the .apkg. The cards it
returns still use $ and $$.

swap_math_delimiters and parse_cards are the helpers those steps use.
parse_cards does not call the model, and it does not write card text.
"""

import json
import re

from anki_export import export_apkg
from extract import MAX_SOURCE_CHARS
from models import Stop, call_model
from prompts import CARD_CREATOR_PROMPT, DRAFTER_PROMPT, SUMMARIZER_PROMPT


def _display_math(match: re.Match[str]) -> str:
    # Return the two characters \ and [, then the math, then \ and ].
    # re.sub inserts this text as-is. A replacement string would treat
    # \1 as "the captured math", so writing \[ by hand there is easy to get wrong.
    return "\\[" + match.group(1) + "\\]"


def _inline_math(match: re.Match[str]) -> str:
    # Same idea: the two characters \ and (, then the math, then \ and ).
    return "\\(" + match.group(1) + "\\)"


def swap_math_delimiters(text: str) -> str:
    """Turn $...$ and $$...$$ into Anki MathJax delimiters.

    Display math is first, left to right, and it may span lines.
    Inline math is second. An inline span stays on one line, so
    $a$ and $b$ becomes two spans. A string that already uses
    \\(...\\) and \\[...\\] is unchanged, because these passes only
    look for $ signs. A single leftover $ stays. The input string
    itself is not edited; the swapped text is a new string.
    """
    # $$...$$ first, so the inline pass cannot cut a display block in half.
    # .*? is the math between one opening $$ and the next $$. DOTALL lets
    # that math include newlines.
    swapped = re.sub(r"\$\$(.*?)\$\$", _display_math, text, flags=re.DOTALL)
    # $...$ second. [^$\n] stops the span at a dollar or a newline, so
    # $a$ and $b$ is two spans, and a span never crosses a line.
    swapped = re.sub(r"\$([^$\n]+?)\$", _inline_math, swapped)
    return swapped


class CardParseError(Exception):
    """The card-creator reply was not usable card JSON.

    A later step can catch this and ask the model once more. This is
    not a Stop: the page shows a stop only after that retry also fails.
    """


def parse_cards(reply: str) -> list[dict[str, str]]:
    """Turn the card-creator reply into a list of cards.

    Drops one code fence if it wraps the whole reply. Then requires a
    JSON object with a cards list. Each card needs a string front and
    a string back, and each of those strings must contain a
    non-whitespace character. Extra keys are ignored. An empty cards
    list is valid.

    Raises CardParseError when the reply does not match that shape.
    """
    # The model was told not to use a fence. If it wraps the whole
    # reply in one anyway, drop that fence. A fence in the middle stays.
    text = _strip_one_fence(reply)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CardParseError("The card reply was not valid JSON.") from exc

    if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
        raise CardParseError("The card reply needs an object with a cards list.")

    cards: list[dict[str, str]] = []
    for item in data["cards"]:
        if not isinstance(item, dict):
            raise CardParseError("Each card must be an object with front and back.")
        front = item.get("front")
        back = item.get("back")
        if not isinstance(front, str) or not isinstance(back, str):
            raise CardParseError("Each card needs a string front and a string back.")
        # "" and "   " both fail. A card with only spaces is not a card.
        if front.strip() == "" or back.strip() == "":
            raise CardParseError("Each card front and back must contain text.")
        # Keep the strings as the model wrote them. Drop any other keys.
        cards.append({"front": front, "back": back})
    return cards


def _strip_one_fence(text: str) -> str:
    """Drop one code fence that wraps the whole reply.

    A fence that sits in the middle of the reply stays.
    """
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return text
    if not _is_opening_fence(lines[0].strip()):
        return text
    if lines[-1].strip() != "```":
        return text
    return "\n".join(lines[1:-1])


def _is_opening_fence(line: str) -> bool:
    # ``` or ```json. A line that only mentions a fence does not count.
    if not line.startswith("```"):
        return False
    tag = line[3:].strip()
    if tag == "":
        return True
    return tag.replace("-", "").replace("_", "").isalnum()


# The second card-creator call adds this. The first call does not.
# The example JSON is already in the prompt above this line.
_CARD_RETRY_REMINDER = (
    "Reminder: double every LaTeX backslash, use \\n for a line break, "
    "put no raw newline inside a string, return JSON only, and follow "
    "the example above."
)


def join_example_notes(notes: list[str]) -> str:
    """Join example markdown notes into one string.

    A blank line goes between notes. Pass the result to
    check_example_notes before reading the source.
    """
    return "\n\n".join(notes)


def check_example_notes(example_notes: str) -> None:
    """Stop if the joined example notes cannot be used.

    Call this before reading the source and before the summarizer.
    It does not call the model. Notes that are empty or only spaces
    are the empty stop. Notes longer than MAX_SOURCE_CHARS are the
    too-long stop. That cap is the constant in extract.py.
    """
    if example_notes.strip() == "":
        raise Stop("The example notes were empty.")
    if len(example_notes) > MAX_SOURCE_CHARS:
        raise Stop(
            f"The example notes are longer than {MAX_SOURCE_CHARS:,} characters. "
            "Upload fewer or shorter notes."
        )


def _median_words(counts: list[int]) -> float:
    """Middle word count, or the average of the two middle counts.

    counts is non-empty. An even count uses a float average.
    """
    ordered = sorted(counts)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def _heading_level(stripped: str) -> int | None:
    """Heading level, or None when the line is not a heading.

    After strip, one to six # characters, then a space or the end of
    the line. "#Title" is not a heading. Seven hashes is not a heading.
    """
    match = re.match(r"^(#{1,6})(?: |$)", stripped)
    if match is None:
        return None
    return len(match.group(1))


def _is_bullet(stripped: str) -> bool:
    """True for "- ", "* ", "+ ", or a numbered item like "1. ".

    "-item" and "1.item" are ordinary lines. The line is already stripped.
    """
    if stripped.startswith(("- ", "* ", "+ ")):
        return True
    return re.match(r"^\d+\. ", stripped) is not None


def _format_number(value: float) -> str:
    # 20.0 is easier to read as 20. 15.5 stays 15.5.
    if value == int(value):
        return str(int(value))
    return str(value)


def _measured_text(
    word_counts: list[int],
    char_counts: list[int],
    median: float,
    longest: int,
    heading_counts: list[int],
    bullet_lines: int,
    nonempty_lines: int,
) -> str:
    lines = []
    for index, (words, chars) in enumerate(zip(word_counts, char_counts), start=1):
        lines.append(f"Note {index}: {words} words, {chars} characters")
    lines.append(f"Median word count: {_format_number(median)}")
    lines.append(f"Longest word count: {longest}")
    for level, count in enumerate(heading_counts, start=1):
        lines.append(f"Heading level {level}: {count}")
    # "3 of 10" states the share without a separate fraction.
    lines.append(f"Bullets: {bullet_lines} of {nonempty_lines} non-empty lines")
    return "\n".join(lines)


def measure_example_notes(notes: list[str]) -> dict:
    """Count words, headings, and bullets in the example notes.

    This does not call the model. The text field is pasted into the
    summarizer and the drafter so they use these numbers for length.
    An empty list does not crash. run_pipeline does not hit that case,
    because check_example_notes stops on empty notes first.
    """
    if not notes:
        return {
            "text": "There are no notes.",
            "word_counts": [],
            "median_words": 0.0,
            "longest_words": 0,
        }

    word_counts: list[int] = []
    char_counts: list[int] = []
    # Index 0 is heading level 1. Levels that never appear stay 0.
    heading_counts = [0, 0, 0, 0, 0, 0]
    bullet_lines = 0
    nonempty_lines = 0

    for text in notes:
        word_counts.append(len(text.split()))
        char_counts.append(len(text))
        for line in text.splitlines():
            stripped = line.strip()
            if stripped == "":
                continue
            nonempty_lines += 1
            level = _heading_level(stripped)
            if level is not None:
                heading_counts[level - 1] += 1
            if _is_bullet(stripped):
                bullet_lines += 1

    median = _median_words(word_counts)
    longest = max(word_counts)
    return {
        "text": _measured_text(
            word_counts,
            char_counts,
            median,
            longest,
            heading_counts,
            bullet_lines,
            nonempty_lines,
        ),
        "word_counts": word_counts,
        "median_words": median,
        "longest_words": longest,
    }


def draft_is_too_long(
    draft_words: int, median_words: float, longest_words: int
) -> bool:
    """True when the draft is much longer than the example notes.

    Both comparisons are strict greater-than. A draft of exactly 1.5
    times the median stays as it is. A shorter draft stays as it is.
    This does not read the optional instruction. The rewrite prompt
    tells the model to keep a longer note when that instruction asked
    for one.
    """
    return draft_words > 1.5 * median_words and draft_words > longest_words


def run_pipeline(
    example_notes: str,
    source: str,
    instruction: str = "",
    example_files: list[str] | None = None,
) -> dict:
    """Run the summarizer, the drafter, and the card-creator.

    The example-note check is first. It runs before the summarizer
    and it does not read the source. The source argument is the
    string from extract.py. The page should call check_example_notes
    before it calls extract.py, then call this with that same string.

    example_files is each uploaded note, before they are joined.
    Those separate notes are what the word counts measure. When the
    argument is omitted or empty, example_notes is measured as one
    note, so the old three-argument call still works.

    If the drafted note is much longer than the examples, the drafter
    is called once more to shorten it. A provider error is not caught,
    so it propagates with no retry.

    Returns a dict with brief, note, cards, and apkg_bytes. cards
    still uses $ and $$. apkg_bytes is the package from a swapped copy.
    The brief is not written into the note.
    """
    check_example_notes(example_notes)

    # Joining inserts a blank line between notes. Measuring the files
    # themselves keeps one word count per upload.
    if not example_files:
        measured = measure_example_notes([example_notes])
    else:
        measured = measure_example_notes(example_files)

    brief = _style_brief(example_notes, measured["text"])
    note = _draft_note(source, brief, instruction, measured)
    cards = _recall_cards(source, note, instruction)

    # Preview cards keep $ and $$. The package gets a new list whose
    # fronts and backs use Anki delimiters. Nothing else changes.
    swapped: list[dict[str, str]] = []
    for card in cards:
        swapped.append(
            {
                "front": swap_math_delimiters(card["front"]),
                "back": swap_math_delimiters(card["back"]),
            }
        )
    return {
        "brief": brief,
        "note": note,
        "cards": cards,
        "apkg_bytes": export_apkg(swapped),
    }


def _style_brief(example_notes: str, measured_text: str) -> str:
    """Ask the summarizer for a style brief.

    The summarizer sees the example notes and the measured facts.
    A blank reply is a missing result, so the drafter is not called.
    """
    reply = call_model(_summarizer_text(example_notes, measured_text))
    if reply.strip() == "":
        raise Stop("The summarizer returned a blank reply.")
    return reply


def _draft_note(
    source: str, brief: str, instruction: str, measured: dict
) -> str:
    """Ask the drafter for the study note.

    One surrounding code fence is removed before the blank check.
    A fence inside the note stays. A preamble is left as the model
    wrote it. A blank note is a missing result, so the card-creator
    is not called.

    A note much longer than the examples is sent back once. The second
    reply is kept even if it is still long. A blank second reply stops.
    A provider error on that call is not a length problem, so it is
    not caught.
    """
    reply = call_model(
        _drafter_text(source, brief, instruction, measured["text"])
    )
    note = _strip_one_fence(reply)
    if note.strip() == "":
        raise Stop("The drafter returned a blank reply.")

    draft_words = len(note.split())
    if not draft_is_too_long(
        draft_words, measured["median_words"], measured["longest_words"]
    ):
        return note

    # One rewrite. Do not loop if this reply is still long.
    reply = call_model(
        _drafter_text(
            source,
            brief,
            instruction,
            measured["text"],
            too_long_note=note,
            length_retry=_length_retry_instruction(
                draft_words,
                measured["median_words"],
                measured["longest_words"],
            ),
        )
    )
    note = _strip_one_fence(reply)
    if note.strip() == "":
        raise Stop("The drafter returned a blank reply.")
    return note


def _recall_cards(
    source: str, note: str, instruction: str
) -> list[dict[str, str]]:
    """Ask the card-creator for recall cards and parse the JSON.

    The card-creator does not receive the style brief. If the reply
    does not parse, call once more with a reminder about backslashes.
    An empty reply fails the parse, so it uses that same one retry.
    A provider error is not a parse failure: it is not caught, so
    there is no retry. If the second reply also fails, raise Stop.
    """
    reply = call_model(
        _card_creator_text(source, note, instruction, remind=False)
    )
    try:
        return parse_cards(reply)
    except CardParseError:
        # The first reply was unusable. Ask once more. Do not invent cards.
        reply = call_model(
            _card_creator_text(source, note, instruction, remind=True)
        )

    try:
        return parse_cards(reply)
    except CardParseError as exc:
        raise Stop(str(exc)) from exc


def _summarizer_text(example_notes: str, measured_text: str) -> str:
    return (
        SUMMARIZER_PROMPT
        + "\nExample notes:\n"
        + example_notes
        + "\nMeasured facts:\n"
        + measured_text
    )


def _length_retry_instruction(
    draft_words: int, median_words: float, longest_words: int
) -> str:
    median_label = _format_number(median_words)
    return (
        f"This draft is {draft_words} words. The example notes are about "
        f"{median_label} words (median) and the longest example is "
        f"{longest_words} words. Rewrite the same note so it matches the "
        "style brief and lands near "
        f"{median_label} words. Do not add sections the examples would not "
        "have. If the optional instruction asked for a longer note, obey "
        "the instruction instead of shortening."
    )


def _drafter_text(
    source: str,
    brief: str,
    instruction: str,
    measured_text: str,
    too_long_note: str | None = None,
    length_retry: str | None = None,
) -> str:
    text = (
        DRAFTER_PROMPT
        + "\nSource:\n"
        + source
        + "\nStyle brief:\n"
        + brief
        + "\nMeasured facts:\n"
        + measured_text
        + "\nOptional instruction:\n"
        + instruction
    )
    if too_long_note is None:
        return text
    # The first draft was too long. Python does not scan the optional
    # instruction for phrases like "make it longer". The sentence below
    # tells the model to obey that instruction.
    text += "\nDraft that is too long:\n" + too_long_note
    if length_retry is not None:
        text += "\nLength rewrite:\n" + length_retry
    return text


def _card_creator_text(
    source: str, note: str, instruction: str, remind: bool
) -> str:
    text = (
        CARD_CREATOR_PROMPT
        + "\nSource:\n"
        + source
        + "\nFinished note:\n"
        + note
        + "\nOptional instruction:\n"
        + instruction
    )
    if remind:
        text += "\n" + _CARD_RETRY_REMINDER
    return text
