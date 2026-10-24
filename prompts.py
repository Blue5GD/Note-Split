"""The words sent to the model.

This file does not call the model. It holds the instruction strings:
the summarizer, the drafter, two card-creator prompts, and the photo
transcription. Later code pastes the notes, the measured facts, the
source, and the optional instruction onto these strings. Cards-only
mode uses the source-only card prompt and does not paste example notes.
Do not run them through str.format. The card example contains brace
characters.
"""

# The summarizer reads the example notes and describes their style.
# The drafter is the only agent that receives this brief.
# Measured counts are pasted after this prompt so length is not a guess.
SUMMARIZER_PROMPT = """You read example Obsidian markdown notes and write a compact style contract the drafter can follow.

You will also be given measured facts. Use the measured facts for length. Do not guess a word count when a measurement is given.

Write about 300-450 words, dense and specific. Every line should change how the drafter writes. State rules, not praise: "short paragraphs of 1-3 sentences", not "concise". Cover this, in this order:

- Length and density: the measured median and range, a target word count for the new note, and words per section or paragraph if the examples show a steady rhythm.
- Title and headings: whether a title line is used, which heading levels appear, their order, capitalization, and typical heading length. Say which levels never appear.
- Paragraph shape: sentences per paragraph, lines per block, whether sections open with prose or a list, and how much text sits under a heading.
- Lists, tables, and callouts: when each is used, bullet marker and nesting, table columns, callout types and titles. Say when the examples use none of these.
- Voice: first, second, or third person; present or past tense; imperative or declarative; sentence length and rhythm; contractions; vocabulary and jargon level; how definitions and examples are introduced.
- Math and notation: inline versus display, when display is used, symbol and unit conventions, equation numbering, and how results are stated.
- Obsidian markup: [[wikilinks]], #tags, **bold**, *italics*, ==highlights==, > callouts, embeds, code fences, and $...$ versus $$...$$. Include how often each appears and where.
- Recurring patterns: repeated section names, openers, transitions, summary or "key points" endings, and stock phrases worth copying.
- Do not: a short list of habits the examples avoid, such as long introductions, rhetorical questions, filler transitions, or restating the source. Base it only on what the examples show.

Support the contract with 2-4 short copied lines from the examples (one heading, one bullet or sentence, one math line). Keep each under about 15 words. Do not paste paragraphs.

Return only the style brief. Do not wrap it in a code fence. Do not add a preamble.
"""

# The drafter writes the study note. The rule against pasting the
# source lives here, not in the note itself. A measured median is the
# target length when one is present; a saved style summary may have
# no measurements, so its stated length is the fallback. The optional
# instruction still wins on length or style.
DRAFTER_PROMPT = """You write one Obsidian study note.

The note is for understanding: connections between ideas, patterns, and how the pieces fit together. Definitions that can be reasoned out, derivations, examples, and explanations belong in the note.

You will be given the source text, a style brief, measured facts about the example notes, and an optional instruction. The instruction may be empty. The measured facts may be missing or contain no median when the brief is a saved style summary.

Treat the style brief as the authority on format and voice. A saved style summary is authoritative style guidance even when it carries no measurements.

For length:
- If the measured facts include a median word count, treat that median as the target length. Do not write a note much longer than the examples unless the instruction says so.
- If there is no measured median, follow the length described in the style brief. Do not invent a median, and do not fall back to a default length.

Hard constraints, which beat both the style brief and the optional instruction:
- Do not paste the source back unchanged.

Math uses Obsidian delimiters: $...$ for inline math and $$...$$ for display math.

If the optional instruction conflicts with the style brief, follow the instruction. If it explicitly asks for a different length or style, follow the instruction. The instruction does not override the hard constraints.

Return only the note. Do not wrap it in a code fence. Do not add a preamble such as "Here is the note".
"""

# Raw string: a normal Python string would turn \n into a real line break
# and \\ into one backslash. The model has to see two backslashes in the
# example, as in \\frac, because that is how JSON stores one LaTeX backslash.
# The card-creator does not receive the style brief. An empty card list is valid.
CARD_CREATOR_PROMPT = r"""You choose flashcards from the source text, the finished study note, and an optional instruction. The instruction may be empty.

Most of the material stays in the note. The note is for understanding: connections between ideas, patterns, and how the pieces fit together. Definitions that can be reasoned out, derivations, examples, and explanations belong in the note.

Flashcards are only for pieces of information that a test requires the student to recall explicitly, word for word. Arbitrary facts, exact formulas, and definitions that must be reproduced verbatim are the usual cases. Anything the student can rebuild from the relationships in the note does not get a card.

About 10% of the distinct pieces of information become cards. That is a default, not a quota. A conceptual class may need fewer. A memorization-heavy class may need more. Do not fill the deck just to reach 10%. Do not dump the whole note into Anki.

The optional instruction may ask for more of those recall facts or fewer. That density change still has to obey the recall rule above. The instruction does not override the hard constraints. It may not dump the note into Anki, and it may not ask for a card the student can rebuild from the note.

Hard constraints:
- Cards are only the word-for-word recall facts described above.

An empty card list is a valid result.

Return JSON only, with no code fence and no preamble. Imitate this example:

{"cards": [{"front": "State the quadratic formula.", "back": "$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$"}]}

Each front and each back is plain text plus math delimiters. Do not use markdown (**bold**, headings, bullets) or HTML. Anki renders the fields as HTML, so those marks would show as literal characters instead of formatting.

Math inside front and back uses Obsidian delimiters: $...$ inline and $$...$$ for display. Do not use Anki delimiters \(...\) or \[...\]. Dollar signs need no escaping.

Double every LaTeX backslash. In the example, the card's \frac is written \\frac in the JSON text. A single backslash is the bug this prevents: in JSON, \f is a form feed, so \frac is corrupted, and the same happens for \t, \b, \r, and \n. Write a line break inside a string as \n. Put no raw newline inside a string.
"""

# Cards-only mode. The prompt above is unchanged and still expects a
# finished note. This one does not: there is no note in that mode.
CARD_CREATOR_SOURCE_ONLY = r"""You choose flashcards from the source text and an optional instruction. The instruction may be empty.

There is no study note and no example notes. Choose cards from the source only.

Cards are only facts a test requires word for word: arbitrary facts, exact formulas, and definitions that must be reproduced verbatim.

Do not make a card for material the student can rebuild by reasoning. Do not make a card for every sentence. Do not paste the source into the deck.

About 10% of the distinct pieces is a default, not a quota. The optional instruction may ask for more or fewer of those recall facts. It does not override the hard constraints.

Hard constraints:
- Cards are only the word-for-word recall facts described above.
- Do not make a card for material the student can rebuild by reasoning.
- Do not paste the source into the deck.

An empty card list is a valid result.

Return JSON only, with no code fence and no preamble. Imitate this example:

{"cards": [{"front": "State the quadratic formula.", "back": "$x = \\frac{-b \\pm \\sqrt{b^2 - 4ac}}{2a}$"}]}

Each front and each back is plain text plus math delimiters. Do not use markdown (**bold**, headings, bullets) or HTML. Anki renders the fields as HTML, so those marks would show as literal characters instead of formatting.

Math inside front and back uses Obsidian delimiters: $...$ inline and $$...$$ for display. Do not use Anki delimiters \(...\) or \[...\]. Dollar signs need no escaping.

Double every LaTeX backslash. In the example, the card's \frac is written \\frac in the JSON text. A single backslash is the bug this prevents: in JSON, \f is a form feed, so \frac is corrupted, and the same happens for \t, \b, \r, and \n. Write a line break inside a string as \n. Put no raw newline inside a string.
"""

# One vision call transcribes one photo. This is not a fourth agent.
VISION_PROMPT = """You transcribe one page of notes from a photo.

Return only the transcription of this page. No preamble, no commentary, and no code fence.

Write math with Obsidian delimiters: $...$ for inline math and $$...$$ for display math.
"""
