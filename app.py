"""The one Streamlit page.

Uploads stay on the page until the button is clicked. The pipeline, including
the example-note check and any photo reading, starts only inside that
click. A later click, such as a download, an expander, or a checkbox,
reruns this script from the top and does not start the pipeline again.

Two boxes choose a study note, flashcards, or both. Cards only does
not read the example notes. A click with neither box checked is a
local stop, like a missing file, and does not start a wait. Once a
click gets past that check, the finish time is kept for this browser
tab. Another click is refused for 60 seconds after the attempt ends.
The note under the button counts those seconds down on its own.

The stored result is written only after run_pipeline returns. A notes
run has no card package. A failed later run does not replace the
stored dict. When a note was written, that dict includes the style
brief. The Style notes expander draws that brief. It is not a
download.

Two or more txt files, PDFs, or photos can be dragged into the order
they should be read. Streamlit reruns this file on every widget
change and forgets a normal variable, so that order lives in
st.session_state.
"""

import math
import time

import streamlit as st

# A missing package must not stop the page from opening. Up and Down
# buttons stand in for dragging when the import fails.
try:
    from streamlit_sortables import sort_items
except ImportError:
    sort_items = None

from extract import extract_photos, extract_sources
from models import ProviderError, Stop
from pipeline import check_example_notes, join_example_notes, run_pipeline

# This stop is only for a source file plus photos. Several .txt files,
# or several PDFs, are one kind and are allowed. A .txt mixed with a
# PDF uses a different sentence, below.
ONE_KIND = "Upload one kind of source: .txt files, PDFs, or photos."

# A rerun forgets a normal variable. These hold the dragged labels,
# one list for txt/PDF files and one list for photos.
SOURCE_ORDER_KEY = "source_order"
PHOTO_ORDER_KEY = "photo_order"

# How long a finished attempt blocks the next one. The clock starts
# when the attempt ends, not when the button is clicked.
COOLDOWN_SECONDS = 60
# session_state key for that finish time. A missing key means no wait.
RUN_FINISHED_KEY = "run_finished_at"


def _seconds_left() -> int:
    """Seconds of the wait still left, or 0 when a click may run.

    No stored finish time means 0. A finish time that is already a
    minute old is removed, so a missing key again means the wait is over.
    """
    finished = st.session_state.get(RUN_FINISHED_KEY)
    if finished is None:
        return 0
    remaining = COOLDOWN_SECONDS - (time.monotonic() - finished)
    if remaining <= 0:
        del st.session_state[RUN_FINISHED_KEY]
        return 0
    # Round up, so the note says 1 second until the minute is actually over.
    return math.ceil(remaining)


def _reject_bad_upload(examples, sources, photos, mode) -> None:
    """Stop if Run was clicked without a usable choice or upload.

    This runs before example notes are read and before the source is
    read. It looks at which kinds of files were chosen, not at their
    bytes. Several .txt files are fine. Several PDFs are fine.

    A notes run, or a run that makes both, still needs at least one
    example note. A cards run does not: it only reads the source.
    Neither box checked is the same kind of stop as a missing file.
    It is raised here, outside the wait.
    """
    if mode not in ("both", "notes", "cards"):
        raise Stop("Choose a study note, flashcards, or both.")
    if mode != "cards" and not examples:
        raise Stop("Upload at least one example note.")
    if not sources and not photos:
        raise Stop(
            "Upload a source: one or more .txt files, one or more PDFs, or photos."
        )
    if sources and photos:
        raise Stop(ONE_KIND)
    if sources and _mixes_pdf_and_txt(sources):
        raise Stop("Use only PDF files, or only .txt files, not both.")


def _example_text(examples) -> tuple[list[str], str]:
    """Decode each example note, and join them into one string.

    getvalue() returns the whole file on every Run. read() would leave
    the pointer at the end, so a second Run could see an empty file.
    The list is each file on its own, so the word-count median is per
    note. The joined string is what the empty and too-long checks read.
    """
    notes = []
    for example in examples:
        notes.append(example.getvalue().decode("utf-8"))
    return notes, join_example_notes(notes)


def _mixes_pdf_and_txt(sources) -> bool:
    """True when the source box has a PDF and a file that is not a PDF.

    The uploader only allows txt and pdf, so a name that does not end
    in .pdf is a txt.
    """
    pdf_count = 0
    for source in sources:
        if source.name.lower().endswith(".pdf"):
            pdf_count += 1
    return pdf_count > 0 and pdf_count < len(sources)


def _source_text(sources, photos) -> str:
    """Read the source files and return one string.

    Call this only after check_example_notes has returned. Photos go
    in as (filename, bytes) pairs. Every txt or PDF goes in the same
    way. Both lists already follow the order chosen above the Run
    button. This function does not sort.
    """
    if photos:
        pairs = []
        for photo in photos:
            pairs.append((photo.name, photo.getvalue()))
        return extract_photos(pairs)
    # getvalue() returns the whole file on every Run. read() would leave
    # the pointer at the end, so a second Run could see an empty file.
    pairs = []
    for source in sources:
        pairs.append((source.name, source.getvalue()))
    return extract_sources(pairs)


def _labels_for_names(names: list[str]) -> list[str]:
    """One label per filename, in this list's order.

    A filename that appears once is its own label. Two files with the
    same name would be one drag item, so copies are numbered
    "name (1)", "name (2)", and so on. Pass the default order. A drag
    must not renumber them.
    """
    copies = {}
    for name in names:
        copies[name] = copies.get(name, 0) + 1

    used = {}
    labels = []
    for name in names:
        if copies[name] == 1:
            labels.append(name)
            continue
        used[name] = used.get(name, 0) + 1
        labels.append(f"{name} ({used[name]})")
    return labels


def _photos_in_filename_order(photos) -> list:
    """The starting order for photos, before anyone drags.

    Ordinary string order puts page-10.jpg before page-2.jpg, which
    is how photos were read before dragging. Python keeps the old
    order when two names are equal, so the numbers stay put.
    """
    if not photos:
        return []
    return sorted(list(photos), key=lambda photo: photo.name)


def _sources_in_upload_order(sources) -> list:
    """The starting order for txt and PDF files.

    The uploader already has an order. Sorting by name would change
    it before the user has dragged anything.
    """
    if not sources:
        return []
    return list(sources)


def _kept_order(saved, default_labels: list[str]) -> list[str]:
    """Keep a drag when the files are still the same ones.

    sorted() lines both lists up, so position does not matter. The
    same names in a new uploader order still match, and the drag
    stays. A new or missing name does not match, so the order goes
    back to the default.
    """
    if isinstance(saved, list) and sorted(saved) == sorted(default_labels):
        return list(saved)
    return list(default_labels)


def _accept_drag(returned, labels: list[str]) -> list[str] | None:
    """Return the widget's list when it is these labels rearranged.

    None means the widget has no answer yet. A list that adds or
    drops a name is not a drag of the files on the page.
    """
    if not isinstance(returned, list):
        return None
    if not all(isinstance(item, str) for item in returned):
        return None
    if sorted(returned) != sorted(labels):
        return None
    return list(returned)


def _labels_this_run(saved, default_labels: list[str], widget_result) -> list[str]:
    """The label order for this run.

    The widget's list is used when it is a permutation of the current
    labels. None, or any other list, leaves the saved order in place.
    That saved order is the default when a file was added or removed.
    """
    order = _kept_order(saved, default_labels)
    accepted = _accept_drag(widget_result, default_labels)
    if accepted is None:
        return order
    return accepted


def _files_for_labels(files_in_default_order, label_order: list[str]) -> list:
    """Line the file objects up with the dragged labels.

    The numbers were assigned on files_in_default_order, so each
    label belongs to one file. Walking the dragged labels is the
    read order. Names only: the bytes stay unread until Run.
    """
    labels = _labels_for_names([item.name for item in files_in_default_order])
    by_label = {}
    for label, item in zip(labels, files_in_default_order):
        by_label[label] = item
    ordered = []
    for label in label_order:
        ordered.append(by_label[label])
    return ordered


def _drag_widget_key(prefix: str, labels: list[str]) -> str:
    """Same files, same key. A new file, a new key.

    The drag widget remembers the first list it showed. If a file is
    added and the key stays, the old names stay on screen, and a drag
    of those old names is ignored. Sorting the labels means a drag,
    which only changes positions, does not change the key.
    """
    return prefix + ":" + repr(sorted(labels))


def _swap(items: list[str], i: int, j: int) -> list[str]:
    moved = list(items)
    moved[i], moved[j] = moved[j], moved[i]
    return moved


def _up_down_buttons(labels: list[str], key_prefix: str) -> list[str]:
    """Move one label with Up and Down.

    Used only when streamlit-sortables cannot be imported. A button
    is True only on the rerun its click caused, so the swapped list
    is this run's order.
    """
    order = list(labels)
    for index, label in enumerate(labels):
        up_col, down_col, name_col = st.columns([1, 1, 6])
        if up_col.button(
            "Up",
            key=f"{key_prefix}:up:{label}",
            disabled=index == 0,
            icon=":material/arrow_upward:",
        ):
            order = _swap(labels, index, index - 1)
        if down_col.button(
            "Down",
            key=f"{key_prefix}:down:{label}",
            disabled=index == len(labels) - 1,
            icon=":material/arrow_downward:",
        ):
            order = _swap(labels, index, index + 1)
        name_col.write(label)
    return order


def _drag_list(labels: list[str], widget_key: str, button_prefix: str):
    """Ask for a new order. A vertical list of the labels.

    sort_items can come back with no answer. None, and the TypeError
    the package raises when its answer is None, both mean keep the
    previous order.
    """
    if sort_items is None:
        return _up_down_buttons(labels, button_prefix)
    try:
        # A copy, so the widget cannot share the list we stored.
        return sort_items(list(labels), direction="vertical", key=widget_key)
    except TypeError:
        return None


def _show_order(files_in_default_order, state_key: str, drag_prefix: str, sentence: str) -> list:
    """Draw the drag list and return the files in this run's order.

    This runs on every rerun, above the button, so the click sees the order
    from this run. Fewer than two files draws nothing. The saved
    labels are reset when a file is added or removed.
    """
    default_labels = _labels_for_names(
        [item.name for item in files_in_default_order]
    )
    returned = None
    # Two files are the smallest list worth dragging. One file is
    # already in order, so it gets no widget.
    if len(default_labels) >= 2:
        # Same sentence as before, in caption type, so the drag list
        # does not look like another heading.
        st.caption(":material/swap_vert: " + sentence)
        returned = _drag_list(
            _kept_order(st.session_state.get(state_key), default_labels),
            _drag_widget_key(drag_prefix, default_labels),
            drag_prefix,
        )
    order = _labels_this_run(
        st.session_state.get(state_key), default_labels, returned
    )
    # Labels, not the file objects. The next rerun brings new objects
    # for the same names. The bytes are read later, inside Run.
    st.session_state[state_key] = order
    return _files_for_labels(files_in_default_order, order)


def _preview_caption(mode: str, note, apkg_bytes, brief) -> str:
    """The line under Preview.

    It names only the downloads that are actually there. Style notes
    are never a file, so that sentence is added only when the brief
    is shown. mode is "both" when an older result has no mode key.
    """
    has_note = note is not None
    has_deck = apkg_bytes is not None
    if has_note and has_deck:
        line = "Download the note and the deck, or read them here."
    elif has_note:
        line = "Download the note, or read it here."
    elif has_deck:
        line = "Download the deck, or read the cards here."
    elif mode == "cards":
        line = "Read the cards here."
    else:
        line = "Read the result here."
    if brief is not None and brief != "":
        line += " Style notes are not a download."
    return line


# set_page_config has to be the first Streamlit call. "centered" keeps
# the form at a reading width. A wide layout is for dashboards.
st.set_page_config(
    page_title="Note Split",
    page_icon=":material/menu_book:",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Redraws only the wait note, once a second. run_every=1 means one
# second. The uploaders, the button, and the pipeline stay outside
# this function, so a tick cannot start a run.
@st.fragment(run_every=1)
def _show_cooldown() -> None:
    """The wait note under the button."""
    left = _seconds_left()
    if left <= 0:
        # The minute is over. One full rerun leaves this note
        # unregistered, so it does not keep ticking. That rerun is
        # not a button click, so the model is not called.
        st.rerun()
    if left == 1:
        amount = "1 second"
    else:
        amount = f"{left} seconds"
    with st.container(border=True):
        st.markdown(
            ":material/hourglass_top: This run uses API credits. "
            f"You can start another in {amount}."
        )


# The title and the boxes below are layout only. Choosing a file,
# dragging, checking a box, or opening a section reruns this script
# and does not call the model. That call stays inside the button.
st.title("Note Split", icon=":material/menu_book:")
st.markdown(
    "Upload notes you already like, plus one lecture or a set of paper pages. "
    "The study note is for understanding, and the cards are only the facts "
    "you need word for word. You can make a study note, flashcards, or both, "
    "and cards only uses the source, not the example notes."
)

# These two boxes only pick the mode. A narrow window stacks the
# columns. A wide window keeps them side by side. Unchecking one
# reruns the page and does not call the model.
with st.container(border=True):
    st.subheader("1. What to make", icon=":material/checklist:")
    note_col, card_col = st.columns(2, gap="medium")
    with note_col:
        # The icon is the heading, same as the typed-files heading.
        # The checkbox label is the choice itself, so the words are
        # not written twice.
        make_note = st.checkbox(
            ":material/article: **Study note**",
            value=True,
            key="make_note",
        )
        st.caption(
            "The study note uses the example Obsidian files to copy their length and habits. "
            "Unchecking it skips that work."
        )
    with card_col:
        make_cards = st.checkbox(
            ":material/style: **Flashcards**",
            value=True,
            key="make_cards",
        )
        st.caption(
            "Flashcards are only the word-for-word facts. "
            "Cards only does not read the example Obsidian files. It only reads the source."
        )

with st.container(border=True):
    st.subheader("2. Example notes", icon=":material/description:")
    # Cards only must not create the uploader. A later read of that
    # widget would open the files. examples is an empty list instead,
    # so the click below has nothing to decode.
    if make_cards and not make_note:
        examples = []
        with st.container(border=True):
            st.markdown(
                "This run only reads the source. Example Obsidian markdown files "
                "are not opened and are not sent to the model."
            )
    else:
        st.caption(
            "One or more Obsidian markdown files. These set the length and the habits of the new note."
        )
        examples = st.file_uploader(
            "Example markdown notes",
            type=["md"],
            accept_multiple_files=True,
            help="At least one .md file.",
        )

with st.container(border=True):
    st.subheader("3. Source", icon=":material/upload_file:")
    st.caption("Exactly one kind. Use typed files or photos, not both.")
    # Two columns, because these boxes are alternatives. The page still
    # refuses a run that fills both.
    text_col, photo_col = st.columns(2, gap="medium")
    with text_col:
        st.markdown(":material/article: **Typed files**")
        sources = st.file_uploader(
            "Source text",
            type=["txt", "pdf"],
            accept_multiple_files=True,
            help="Several .txt files, or several PDFs. Not a PDF mixed with a .txt.",
        )
        st.caption("Several .txt files, or several PDFs. Not a mix of the two.")
        # Under the uploader, on every rerun, so the button sees this run's order.
        sources_to_read = _show_order(
            _sources_in_upload_order(sources),
            SOURCE_ORDER_KEY,
            "source_drag",
            "Drag files into the order they should be read.",
        )
    with photo_col:
        st.markdown(":material/photo_camera: **Paper photos**")
        photos = st.file_uploader(
            "Photos of paper notes",
            type=["png", "jpg", "jpeg"],
            accept_multiple_files=True,
            help="png, jpg, or jpeg.",
        )
        st.caption("HEIC photos need to be exported as JPEG first.")
        photos_to_read = _show_order(
            _photos_in_filename_order(photos),
            PHOTO_ORDER_KEY,
            "photo_drag",
            "Drag photos into page order.",
        )

with st.container(border=True):
    st.subheader("4. Instruction", icon=":material/edit_note:")
    st.caption(
        "Optional. Empty is fine. Use this when the new note should differ from the examples."
    )
    instruction = st.text_area(
        "Optional instruction",
        placeholder="For example: keep it shorter than the examples, or use my wording for definitions.",
        height=120,
    )

# The boxes map to the pipeline's mode string. Neither box is not a
# mode. That click is stopped with the missing-file check, before the
# wait. A run that includes a note uses the book icon. Cards only uses
# the card icon.
if make_note and make_cards:
    run_mode = "both"
    button_label = "Make the note and cards"
    button_icon = ":material/auto_stories:"
    spinner_text = "Writing the note and the cards. Several photos can take about a minute."
elif make_note:
    run_mode = "notes"
    button_label = "Make the note"
    button_icon = ":material/auto_stories:"
    spinner_text = "Writing the note. Several photos can take about a minute."
elif make_cards:
    run_mode = "cards"
    button_label = "Make the cards"
    button_icon = ":material/style:"
    spinner_text = "Writing the cards. Several photos can take about a minute."
else:
    run_mode = None
    button_label = "Make the note and cards"
    button_icon = ":material/auto_stories:"
    spinner_text = "Writing the note and the cards. Several photos can take about a minute."

# The button stays clickable during the wait. A disabled button does
# not rerun the page by itself, so the wait would never end. The click
# is refused in code while seconds are left.
if st.button(
    button_label,
    type="primary",
    icon=button_icon,
    width="stretch",
):
    # A click during the wait must not read the notes or call the model.
    # The note under the button says how many seconds are left.
    if _seconds_left() == 0:
        try:
            _reject_bad_upload(examples, sources, photos, run_mode)
            # Past the upload check, this attempt may call the model.
            # finally records the finish time on every way out, so the
            # wait does not depend on a crash. A missing file, or neither
            # box checked, never reaches this try, so it does not start
            # the wait.
            try:
                with st.spinner(spinner_text):
                    if run_mode == "cards":
                        # Skip _example_text on this branch. A normal read
                        # would still open those files, because getvalue()
                        # reads each upload. Cards only must not open them,
                        # and it must not call check_example_notes. The
                        # empty string and None are placeholders. The
                        # pipeline does not read example notes in this mode.
                        source = _source_text(sources_to_read, photos_to_read)
                        st.session_state["result"] = run_pipeline(
                            "", source, instruction, None, mode="cards"
                        )
                    else:
                        example_files, example_notes = _example_text(examples)
                        # Before the source is read, and before any photo is sent.
                        check_example_notes(example_notes)
                        # The lists above are already in the dragged order.
                        source = _source_text(sources_to_read, photos_to_read)
                        # run_pipeline returns when the note is done. A both
                        # run also waits for the .apkg bytes. Assigning that
                        # dict here is the first time a result is stored.
                        # example_files is each upload, measured before the notes are joined.
                        # run_mode is "notes" or "both" in this branch.
                        st.session_state["result"] = run_pipeline(
                            example_notes,
                            source,
                            instruction,
                            example_files,
                            mode=run_mode,
                        )
            finally:
                # A normal variable is forgotten on every rerun. Streamlit
                # starts this file over from the top on a click, so the
                # finish time has to live in st.session_state. That dict
                # stays with this browser tab.
                #
                # The wait starts here, after the attempt, not at the click.
                # Clicks during the spinner are handled only on the next
                # rerun, once this file has returned. Those queued clicks
                # still need a full minute, or they would start a second paid run.
                st.session_state[RUN_FINISHED_KEY] = time.monotonic()
        except Stop as error:
            st.error(str(error))
        except ProviderError as error:
            st.error(str(error))

# Only while a wait is stored. An idle page does not register the
# once-a-second note, so opening the app does not keep rerunning.
if _seconds_left() > 0:
    _show_cooldown()

# A download or an expander reruns this file. The block above is skipped
# on that rerun. The previous result stays until a later click finishes.
if "result" in st.session_state:
    result = st.session_state["result"]
    # A result saved before modes existed has no "mode" key. That run
    # made a note and cards, so a missing mode counts as "both". A
    # section is still skipped when its value is missing: no note
    # download for cards only, no deck download for a note only.
    mode = result.get("mode", "both")
    note = result.get("note")
    cards = result.get("cards")
    brief = result.get("brief")
    apkg_bytes = result.get("apkg_bytes")
    st.header("Preview", icon=":material/visibility:")
    st.caption(_preview_caption(mode, note, apkg_bytes, brief))
    # A horizontal container keeps the downloads on one row. A missing
    # file is left out, so the caption does not promise it either.
    if note is not None or apkg_bytes is not None:
        with st.container(horizontal=True, gap="small"):
            if note is not None:
                st.download_button(
                    "Download note.md",
                    data=note,
                    file_name="note.md",
                    mime="text/markdown",
                    key="download_note",
                    icon=":material/download:",
                )
            if apkg_bytes is not None:
                st.download_button(
                    "Download cards.apkg",
                    data=apkg_bytes,
                    file_name="cards.apkg",
                    mime="application/octet-stream",
                    key="download_apkg",
                    icon=":material/download:",
                )
    if note is not None:
        with st.expander("Note", expanded=True, icon=":material/article:"):
            st.markdown(note)
    if cards is not None:
        with st.expander("Cards", expanded=True, icon=":material/style:"):
            for index, card in enumerate(cards):
                if index > 0:
                    st.divider()
                st.markdown(card["front"])
                st.markdown(card["back"])
    if brief is not None and brief != "":
        with st.expander("Style notes", expanded=False, icon=":material/ink_pen:"):
            st.markdown(brief)
