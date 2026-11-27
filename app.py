"""The one Streamlit page.

Two tabs split style setup from generation:
- Generate: pick a saved style (when making a note), upload lecture
  sources, choose study note / flashcards / both, add an optional
  instruction, and run. Never calls the summarizer.
- Styles: generate a saved style from example .md notes (1 summarizer
  call, no source needed), add a style manually, or view, edit, and
  delete saved styles.

Uploads stay on the page until a Run button is clicked. A later click,
such as a download, an expander, or a checkbox, reruns this script from
the top and does not call the model again.

Once a paid attempt gets past the local upload check, the finish time
is kept as epoch seconds in this browser tab and in the saved run.
Another paid click on either tab is refused for 60 seconds after the
attempt ends.

The last finished generate run and all saved styles are stored on this
computer. A reload restores the last generate result without spending
credits.

The page is text-only. A handwritten page is transcribed outside the
app and uploaded as a .txt file, so the page makes no vision calls.
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

from extract import extract_sources
from models import (
    ProviderError,
    Stop,
    TokenUsage,
    estimate_cost,
    format_cost,
)
from pipeline import join_example_notes, run_pipeline, run_summarizer
from storage import (
    StyleProfile,
    clear_last_run,
    delete_profile,
    get_profile,
    list_profiles,
    load_last_run,
    save_last_run,
    save_profile,
)

# A rerun forgets a normal variable. This holds the dragged labels for
# the source files.
SOURCE_ORDER_KEY = "source_order"

STYLE_NOTICE_KEY = "style_notice"
STYLE_USAGE_KEY = "style_usage"
# Changing these makes Streamlit build fresh text widgets, which clears
# the form after a successful save.
STYLE_FORM_NONCE_KEY = "style_form_nonce"
GEN_STYLE_FORM_NONCE_KEY = "gen_style_form_nonce"

# True only while Preview is showing the run restored from disk. A new
# successful run clears it.
RESTORED_KEY = "result_restored"

# How long a finished attempt blocks the next one. The clock starts
# when the attempt ends, not when the button is clicked.
COOLDOWN_SECONDS = 60
# session_state key for that finish time. It is epoch seconds, because
# the same number is saved with the last run. A missing key means no wait.
RUN_FINISHED_KEY = "run_finished_at"


def _seconds_left() -> int:
    """Seconds of the wait still left, or 0 when a click may run.

    No stored finish time means 0. A finish time that is already a
    minute old is removed, so a missing key again means the wait is over.
    The stored time is time.time(), matching the saved run, so a reload
    can keep the same wait.
    """
    finished = st.session_state.get(RUN_FINISHED_KEY)
    if finished is None:
        return 0
    remaining = COOLDOWN_SECONDS - (time.time() - finished)
    if remaining <= 0:
        del st.session_state[RUN_FINISHED_KEY]
        return 0
    # Round up, so the note says 1 second until the minute is actually over.
    return math.ceil(remaining)


def _restore_last_run() -> None:
    """Restore the saved run once, and keep its wait when it is fresh.

    A reload starts with an empty st.session_state. The restored dict
    is marked, so Preview can say that opening the page did not spend
    credits. When its epoch finish time is still inside the cooldown,
    the same time seeds the wait key, so an immediate click cannot
    start a second paid run.
    """
    if "result" in st.session_state:
        return
    restored = load_last_run()
    if restored is None:
        return
    st.session_state["result"] = restored
    st.session_state[RESTORED_KEY] = True

    finished = restored.get("finished_at_epoch")
    if isinstance(finished, bool) or not isinstance(finished, (int, float)):
        return
    remaining = COOLDOWN_SECONDS - (time.time() - float(finished))
    if 0 < remaining <= COOLDOWN_SECONDS:
        st.session_state[RUN_FINISHED_KEY] = float(finished)


def _reject_bad_generate(
    sources,
    mode,
    selected_profile: StyleProfile | None,
) -> None:
    """Stop if Generate was clicked without a usable choice or upload.

    This runs before the source is read. A notes or both run needs a
    saved style with a non-blank brief. Cards only ignores styles.
    """
    if mode not in ("both", "notes", "cards"):
        raise Stop("Choose a study note, flashcards, or both.")
    if mode != "cards":
        if selected_profile is None or selected_profile.brief.strip() == "":
            raise Stop(
                "Choose a saved style, or create one in the Styles tab first."
            )
    if not sources:
        raise Stop("Upload a source: one or more .txt files or one or more PDFs.")
    if _mixes_pdf_and_txt(sources):
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
        try:
            notes.append(example.getvalue().decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise Stop(
                f"The example note {example.name} is not UTF-8 text. "
                "Save it as UTF-8 and upload it again."
            ) from exc
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


def _source_text(sources) -> str:
    """Read the source files and return one string.

    Every .txt or PDF goes in the same way. The list already follows
    the order chosen above the Run button. This function does not sort.
    """
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
        if sort_items is None:
            st.caption(
                ":material/swap_vert: Use Up and Down to order these files."
            )
        else:
            st.caption(":material/swap_vert: " + sentence)
        returned = _drag_list(
            _kept_order(st.session_state.get(state_key), default_labels),
            _drag_widget_key(drag_prefix, default_labels),
            drag_prefix,
        )
    order = _labels_this_run(
        st.session_state.get(state_key), default_labels, returned
    )
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


def _word_count_caption(profile: StyleProfile) -> str:
    """Short summary of a saved style's word-count targets."""
    median = int(round(profile.median_words)) if profile.median_words > 0 else 0
    longest = int(profile.longest_words) if profile.longest_words > 0 else 0
    if median > 0 and longest > 0:
        return (
            f"Word-count targets: median {median:,} words · "
            f"longest {longest:,} words (length retry triggers above "
            f"1.5× median and longest)."
        )
    if median > 0:
        return f"Target median: {median:,} words (no length retry)."
    return "No word-count targets set (length retry is skipped)."


def _normalize_word_targets(median_input, longest_input) -> tuple[float, int]:
    """Validate and normalize median and longest word-count inputs."""
    median = int(median_input) if median_input is not None and median_input > 0 else 0
    longest = int(longest_input) if longest_input is not None and longest_input > 0 else 0
    if median > 0 and longest == 0:
        longest = median
    if median == 0 and longest > 0:
        raise ValueError(
            "Set a median word count too, or set both to 0 to disable word targets."
        )
    if median > longest:
        raise ValueError("Median words cannot be larger than longest words.")
    return float(median), longest


def _token_count(count: int, noun: str) -> str:
    """One count with a singular or plural noun."""
    word = noun if count == 1 else noun + "s"
    return f"{count:,} {word}"


def _show_usage(usage_data, prefix: str = "") -> None:
    """Draw the compact token and cost line for a finished run."""
    if not isinstance(usage_data, dict):
        return
    try:
        usage = TokenUsage.from_dict(usage_data)
    except (TypeError, ValueError, OverflowError):
        return
    if usage.calls <= 0:
        return
    call_word = "call" if usage.calls == 1 else "calls"
    line = prefix + (
        f"{usage.calls} model {call_word} · "
        f"{_token_count(usage.input_tokens, 'input token')} · "
        f"{_token_count(usage.output_tokens, 'output token')}"
    )
    cost_text = format_cost(estimate_cost(usage))
    help_text = None
    if cost_text == "":
        help_text = (
            "Add INPUT_PRICE_PER_MTOK and OUTPUT_PRICE_PER_MTOK to .env "
            "and restart the app to show an estimated dollar cost."
        )
    else:
        line += f" · est. {cost_text}"
    st.caption(":material/payments: " + line, help=help_text)


def _max_paid_calls(mode, length_retry: bool = True) -> int:
    """The most paid calls a Generate run can make.

    Generate always uses a saved style for notes, so the summarizer
    never runs here.
    """
    if mode == "cards":
        return 2
    if mode == "notes":
        return 2 if length_retry else 1
    if mode == "both":
        return 4 if length_retry else 3
    return 0


def _max_calls_help(mode, length_retry: bool = True) -> str:
    """The breakdown behind the maximum call caption on Generate."""
    if mode == "cards":
        return "Cards only: one card call and one retry."
    if mode == "notes":
        if length_retry:
            return (
                "Study note: one drafter call and one length retry. "
                "The summarizer is skipped because a saved style is used."
            )
        return (
            "Study note with no word-count targets: one drafter call. "
            "The summarizer and length retry are skipped."
        )
    if mode == "both":
        if length_retry:
            return (
                "Note and cards: one drafter call, one length retry, one "
                "card call, and one card retry. The summarizer is skipped."
            )
        return (
            "Note and cards with no word-count targets: one drafter call, "
            "one card call, and one card retry. The summarizer and length "
            "retry are skipped."
        )
    return "No mode is selected, so Run stops before any model call."


# set_page_config has to be the first Streamlit call. "centered" keeps
# the form at a reading width. A wide layout is for dashboards.
st.set_page_config(
    page_title="Note Split",
    page_icon=":material/menu_book:",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# A browser reload forgets session_state. Restore the last result before
# any widget is drawn, so Preview and the wait key both see it.
_restore_last_run()


# Redraws only the wait note, once a second. run_every=1 means one
# second. The uploaders, buttons, and pipeline stay outside this
# function, so a tick cannot start a run.
@st.fragment(run_every=1)
def _show_cooldown() -> None:
    """The wait note shown while the 60-second cooldown is active."""
    left = _seconds_left()
    if left <= 0:
        st.rerun()
    if left == 1:
        amount = "1 second"
    else:
        amount = f"{left} seconds"
    with st.container(border=True):
        st.markdown(
            ":material/hourglass_top: An attempt was just made. "
            f"You can start another in {amount}."
        )


st.title("Note Split", icon=":material/menu_book:")
st.markdown(
    "Create or edit a saved style in **Styles**, then turn lectures into "
    "Obsidian study notes and Anki recall cards in **Generate**."
)

style_notice = st.session_state.pop(STYLE_NOTICE_KEY, None)
if style_notice:
    st.caption(":material/check_circle: " + style_notice)
style_usage = st.session_state.pop(STYLE_USAGE_KEY, None)
if style_usage:
    _show_usage(style_usage)

# Only while a wait is stored. Shown above the tabs so it applies to
# both Generate and Styles runs.
if _seconds_left() > 0:
    _show_cooldown()

profiles = list_profiles()

generate_tab, styles_tab = st.tabs(
    [":material/auto_stories: Generate", ":material/palette: Styles"]
)

with generate_tab:
    with st.container(border=True):
        st.subheader("1. What to make", icon=":material/checklist:")
        note_col, card_col = st.columns(2, gap="medium")
        with note_col:
            make_note = st.checkbox(
                ":material/article: **Study note**",
                value=True,
                key="make_note",
            )
            st.caption(
                "The study note follows a saved style. Unchecking it skips "
                "writing a note."
            )
        with card_col:
            make_cards = st.checkbox(
                ":material/style: **Flashcards**",
                value=True,
                key="make_cards",
            )
            st.caption(
                "Flashcards are only the word-for-word facts. "
                "Cards only does not use a saved style. It only reads the source."
            )

    with st.container(border=True):
        st.subheader("2. Saved style", icon=":material/palette:")
        if make_cards and not make_note:
            selected_profile = None
            with st.container(border=True):
                st.markdown(
                    "This run only reads the source. Saved styles are not "
                    "used and are not sent to the model."
                )
        elif profiles:
            names = [profile.name for profile in profiles]
            chosen = st.selectbox(
                "Saved style",
                names,
                key="generate_style_select",
            )
            selected_profile = get_profile(chosen) if chosen is not None else None
            if selected_profile is not None:
                st.caption(_word_count_caption(selected_profile))
                with st.expander(
                    "View style summary",
                    expanded=False,
                    icon=":material/ink_pen:",
                ):
                    st.markdown(selected_profile.brief)
                    st.caption(
                        "Want to tweak this style or its word counts? Edit it "
                        "in the **Styles** tab."
                    )
        else:
            selected_profile = None
            st.info(
                "No saved styles yet. Open the **Styles** tab to generate a "
                "style from example notes or add one manually."
            )

    with st.container(border=True):
        st.subheader("3. Source", icon=":material/upload_file:")
        st.caption(
            "Text only: several .txt files, or several typed PDFs. Do not mix "
            "the two. Handwritten pages must be transcribed and saved as .txt "
            "first."
        )
        sources = st.file_uploader(
            "Source files",
            type=["txt", "pdf"],
            accept_multiple_files=True,
            help="Several .txt files, or several PDFs. Not a PDF mixed with a .txt.",
        )
        sources_to_read = _show_order(
            _sources_in_upload_order(sources),
            SOURCE_ORDER_KEY,
            "source_drag",
            "Drag files into the order they should be read.",
        )

    with st.container(border=True):
        st.subheader("4. Instruction", icon=":material/edit_note:")
        st.caption(
            "Optional. Empty is fine. Sent to the drafter and card-creator "
            "for lecture-specific requests."
        )
        instruction = st.text_area(
            "Optional instruction",
            placeholder="For example: focus on the last section, or make sure the note covers every homework problem.",
            height=120,
        )

    if make_note and make_cards:
        run_mode = "both"
        button_label = "Make the note and cards"
        button_icon = ":material/auto_stories:"
        spinner_text = "Writing the note and the cards."
    elif make_note:
        run_mode = "notes"
        button_label = "Make the note"
        button_icon = ":material/auto_stories:"
        spinner_text = "Writing the note."
    elif make_cards:
        run_mode = "cards"
        button_label = "Make the cards"
        button_icon = ":material/style:"
        spinner_text = "Writing the cards."
    else:
        run_mode = None
        button_label = "Make the note and cards"
        button_icon = ":material/auto_stories:"
        spinner_text = "Writing the note and the cards."

    if run_mode is not None:
        saved_has_target = (
            selected_profile is not None
            and float(selected_profile.median_words or 0.0) > 0
            and int(selected_profile.longest_words or 0) > 0
        )
        length_retry = run_mode != "cards" and saved_has_target
        max_calls = _max_paid_calls(run_mode, length_retry=length_retry)
        call_word = "call" if max_calls == 1 else "calls"
        st.caption(
            f":material/payments: Up to {max_calls} paid model {call_word} for this run.",
            help=_max_calls_help(run_mode, length_retry=length_retry),
        )

    if st.button(
        button_label,
        type="primary",
        icon=button_icon,
        width="stretch",
        key="run_generate",
    ):
        if _seconds_left() == 0:
            usage = TokenUsage()
            finished_at = None
            try:
                _reject_bad_generate(sources, run_mode, selected_profile)
                try:
                    with st.spinner(spinner_text):
                        source = _source_text(sources_to_read)
                        if run_mode == "cards":
                            result = run_pipeline(
                                "",
                                source,
                                instruction,
                                None,
                                mode="cards",
                                usage=usage,
                            )
                        else:
                            result = run_pipeline(
                                "",
                                source,
                                instruction,
                                None,
                                mode=run_mode,
                                usage=usage,
                                style_brief=selected_profile.brief,
                                style_measured_text=selected_profile.measured_text,
                                style_median_words=selected_profile.median_words,
                                style_longest_words=selected_profile.longest_words,
                            )

                        result["usage"] = usage.as_dict()
                        finished_at = time.time()
                        result["finished_at_epoch"] = finished_at
                        st.session_state["result"] = result
                        st.session_state.pop(RESTORED_KEY, None)
                        try:
                            save_last_run(result)
                        except (OSError, TypeError) as error:
                            st.warning(
                                "The result is on this page, but it could not be "
                                f"saved for a reload: {error}"
                            )
                finally:
                    st.session_state[RUN_FINISHED_KEY] = (
                        finished_at if finished_at is not None else time.time()
                    )
            except Stop as error:
                st.error(str(error))
                _show_usage(usage.as_dict(), prefix="This attempt used ")
            except ProviderError as error:
                st.error(str(error))
                _show_usage(usage.as_dict(), prefix="This attempt used ")

    if "result" in st.session_state:
        result = st.session_state["result"]
        mode = result.get("mode", "both")
        note = result.get("note")
        cards = result.get("cards")
        brief = result.get("brief")
        apkg_bytes = result.get("apkg_bytes")
        st.header("Preview", icon=":material/visibility:")
        st.caption(_preview_caption(mode, note, apkg_bytes, brief))
        if st.session_state.get(RESTORED_KEY):
            st.caption(
                ":material/history: Restored from the last run on this computer. "
                "No credits were spent."
            )
        _show_usage(result.get("usage"))
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
        clear_stamp = result.get("finished_at_epoch", "older")
        with st.popover("Clear saved result", icon=":material/delete_sweep:"):
            st.caption(
                "This removes the result from this page and the saved copy on "
                "this computer. Files you already downloaded are not affected."
            )
            confirmed = st.checkbox(
                "Confirm clear",
                key=f"confirm_clear_saved_result:{clear_stamp}",
            )
            if st.button(
                "Clear saved result",
                icon=":material/delete:",
                disabled=not confirmed,
                key=f"clear_saved_result:{clear_stamp}",
            ):
                try:
                    clear_last_run()
                except OSError as error:
                    st.error(f"Could not remove the saved result: {error}")
                else:
                    st.session_state.pop("result", None)
                    st.session_state.pop(RESTORED_KEY, None)
                    st.rerun()
        if note is not None:
            note_words = len(note.split())
            with st.expander(
                f"Note ({_token_count(note_words, 'word')})",
                expanded=True,
                icon=":material/article:",
            ):
                st.markdown(note)
        if cards is not None:
            with st.expander("Cards", expanded=True, icon=":material/style:"):
                if not cards:
                    st.caption(
                        "No cards were returned. The deck download is empty."
                    )
                for index, card in enumerate(cards):
                    if index > 0:
                        st.divider()
                    st.markdown(card["front"])
                    st.markdown(card["back"])
        if brief is not None and brief != "":
            with st.expander("Style notes", expanded=False, icon=":material/ink_pen:"):
                st.markdown(brief)

with styles_tab:
    with st.container(border=True):
        st.subheader("Generate a style from example notes", icon=":material/auto_awesome:")
        st.caption(
            "Runs only the summarizer on your example Obsidian notes and saves "
            "the result. You can edit the summary and word counts right after."
        )
        gen_nonce = st.session_state.get(GEN_STYLE_FORM_NONCE_KEY, 0)
        gen_style_name = st.text_input(
            "Style name",
            placeholder="For example: Multivariable calculus notes",
            key=f"gen_style_name:{gen_nonce}",
        )
        gen_examples = st.file_uploader(
            "Example markdown notes",
            type=["md"],
            accept_multiple_files=True,
            help="Upload one or more .md files that already look the way you want.",
            key=f"gen_style_examples:{gen_nonce}",
        )
        st.caption(
            ":material/payments: 1 paid model call to summarize these example notes. "
            "Saving a name that already exists replaces it."
        )
        if st.button(
            "Generate and save style",
            type="primary",
            icon=":material/auto_awesome:",
            width="stretch",
            key="run_summarizer",
        ):
            if _seconds_left() == 0:
                usage = TokenUsage()
                finished_at = None
                try:
                    if gen_style_name.strip() == "":
                        raise Stop("Enter a name for this style first.")
                    if not gen_examples:
                        raise Stop("Upload at least one example .md note.")
                    try:
                        with st.spinner("Summarizing your example notes."):
                            example_files, example_notes = _example_text(gen_examples)
                            summary = run_summarizer(
                                example_notes,
                                example_files,
                                usage=usage,
                            )
                            measured = summary["measured"]
                            saved = save_profile(
                                gen_style_name,
                                summary["brief"],
                                measured_text=measured["text"],
                                median_words=measured["median_words"],
                                longest_words=measured["longest_words"],
                            )
                            finished_at = time.time()
                    finally:
                        st.session_state[RUN_FINISHED_KEY] = (
                            finished_at if finished_at is not None else time.time()
                        )
                except (Stop, ValueError, OSError) as error:
                    st.error(str(error))
                    _show_usage(usage.as_dict(), prefix="This attempt used ")
                except ProviderError as error:
                    st.error(str(error))
                    _show_usage(usage.as_dict(), prefix="This attempt used ")
                else:
                    st.session_state[GEN_STYLE_FORM_NONCE_KEY] = gen_nonce + 1
                    st.session_state[STYLE_NOTICE_KEY] = (
                        f'Generated and saved the style "{saved.name}".'
                    )
                    st.session_state[STYLE_USAGE_KEY] = usage.as_dict()
                    st.rerun()

    with st.container(border=True):
        st.subheader("Saved styles", icon=":material/bookmarks:")
        if profiles:
            names = [profile.name for profile in profiles]
            chosen_manage = st.selectbox(
                "Saved style",
                names,
                key="manage_style_select",
            )
            selected_manage = (
                get_profile(chosen_manage) if chosen_manage is not None else None
            )
            if selected_manage is not None:
                st.caption(_word_count_caption(selected_manage))
                with st.expander(
                    "View style summary",
                    expanded=False,
                    icon=":material/ink_pen:",
                ):
                    st.markdown(selected_manage.brief)
                with st.expander(
                    "Edit style summary",
                    expanded=False,
                    icon=":material/edit:",
                ):
                    current_median = (
                        int(round(selected_manage.median_words))
                        if selected_manage.median_words > 0
                        else 0
                    )
                    current_longest = (
                        int(selected_manage.longest_words)
                        if selected_manage.longest_words > 0
                        else 0
                    )
                    with st.form(
                        f"edit_style_profile:{selected_manage.name}:{selected_manage.saved_at}"
                    ):
                        edited_brief = st.text_area(
                            "Style summary",
                            value=selected_manage.brief,
                            height=220,
                            key=(
                                f"edit_style_brief:"
                                f"{selected_manage.name}:{selected_manage.saved_at}"
                            ),
                        )
                        med_col, long_col = st.columns(2, gap="medium")
                        with med_col:
                            edited_median = st.number_input(
                                "Median words",
                                min_value=0,
                                step=50,
                                value=current_median,
                                help="Target length for the drafter. Set both to 0 to disable the length retry.",
                                key=(
                                    f"edit_style_median:"
                                    f"{selected_manage.name}:{selected_manage.saved_at}"
                                ),
                            )
                        with long_col:
                            edited_longest = st.number_input(
                                "Longest words",
                                min_value=0,
                                step=50,
                                value=current_longest,
                                help="Must be at least Median words. Length retry triggers above both 1.5× median and longest.",
                                key=(
                                    f"edit_style_longest:"
                                    f"{selected_manage.name}:{selected_manage.saved_at}"
                                ),
                            )
                        save_edits = st.form_submit_button(
                            "Save changes",
                            icon=":material/save:",
                        )
                        if save_edits:
                            try:
                                median_val, longest_val = _normalize_word_targets(
                                    edited_median, edited_longest
                                )
                                if (
                                    int(round(median_val)) == current_median
                                    and longest_val == current_longest
                                ):
                                    measured_text = selected_manage.measured_text
                                    median_words = selected_manage.median_words
                                    longest_words = selected_manage.longest_words
                                else:
                                    measured_text = ""
                                    median_words = median_val
                                    longest_words = longest_val
                                saved = save_profile(
                                    selected_manage.name,
                                    edited_brief,
                                    measured_text=measured_text,
                                    median_words=median_words,
                                    longest_words=longest_words,
                                )
                            except (ValueError, OSError) as error:
                                st.error(f"Could not save the style: {error}")
                            else:
                                st.session_state[STYLE_NOTICE_KEY] = (
                                    f'Updated the style "{saved.name}".'
                                )
                                st.rerun()
                with st.popover("Delete style", icon=":material/delete:"):
                    st.caption(
                        f'Delete "{selected_manage.name}" from this computer?'
                    )
                    confirmed = st.checkbox(
                        "Confirm delete",
                        key=(
                            f"confirm_delete_style:"
                            f"{selected_manage.name}:{selected_manage.saved_at}"
                        ),
                    )
                    if st.button(
                        "Delete style",
                        icon=":material/delete:",
                        disabled=not confirmed,
                        key=(
                            f"delete_style:"
                            f"{selected_manage.name}:{selected_manage.saved_at}"
                        ),
                    ):
                        try:
                            removed = delete_profile(selected_manage.name)
                        except OSError as error:
                            st.error(f"Could not delete the style: {error}")
                        else:
                            if removed:
                                st.session_state[STYLE_NOTICE_KEY] = (
                                    f'Deleted the style "{selected_manage.name}".'
                                )
                                st.rerun()
                            else:
                                st.error("That style was already removed.")
        else:
            st.info(
                "No saved styles yet. Generate one from example notes above, "
                "or add one manually below."
            )

        nonce = st.session_state.get(STYLE_FORM_NONCE_KEY, 0)
        with st.expander(
            "Add a style manually",
            expanded=False,
            icon=":material/add:",
        ):
            st.caption(
                "Saving a name that already exists replaces its summary and "
                "word counts. Set both word counts to 0 for no length retry."
            )
            with st.form("add_style_profile"):
                name = st.text_input(
                    "Name",
                    placeholder="For example: Biology lecture notes",
                    key=f"new_style_name:{nonce}",
                )
                brief = st.text_area(
                    "Style summary",
                    height=160,
                    placeholder=(
                        "Describe length, headings, math habits, and what the "
                        "notes avoid."
                    ),
                    key=f"new_style_brief:{nonce}",
                )
                add_med_col, add_long_col = st.columns(2, gap="medium")
                with add_med_col:
                    add_median = st.number_input(
                        "Median words",
                        min_value=0,
                        step=50,
                        value=0,
                        help="Optional target length for the drafter.",
                        key=f"new_style_median:{nonce}",
                    )
                with add_long_col:
                    add_longest = st.number_input(
                        "Longest words",
                        min_value=0,
                        step=50,
                        value=0,
                        help="Optional ceiling. Defaults to Median words if left at 0.",
                        key=f"new_style_longest:{nonce}",
                    )
                submitted = st.form_submit_button(
                    "Save style",
                    icon=":material/save:",
                )
                if submitted:
                    try:
                        median_val, longest_val = _normalize_word_targets(
                            add_median, add_longest
                        )
                        saved = save_profile(
                            name,
                            brief,
                            median_words=median_val,
                            longest_words=longest_val,
                        )
                    except (ValueError, OSError) as error:
                        st.error(f"Could not save the style: {error}")
                    else:
                        st.session_state[STYLE_FORM_NONCE_KEY] = nonce + 1
                        st.session_state[STYLE_NOTICE_KEY] = (
                            f'Saved the style "{saved.name}".'
                        )
                        st.rerun()
