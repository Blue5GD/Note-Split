"""Save style briefs and the last finished run on this computer.

Two files live in DATA_DIR, which is .note-split next to this file
unless NOTE_SPLIT_DATA_DIR says otherwise. style_profiles.json holds
named style briefs, so a brief that was already paid for can be used
again. last_run.json holds the last finished result, so a browser
reload can show the note and the cards without another paid run.

A style profile keeps only the brief and its measured summary. The
last run keeps only the result the pipeline made. Source text and
example notes are never written to either file.

Both files can hold private note text. A write goes to a temporary
file in the same folder, then replaces the old file, and the final
file is set to 0o600, so only this user can read it. A missing or
corrupt file reads as empty, because a bad cache must not stop the
page.

The names below are used by app.py. Keep them stable.
"""

import base64
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# NOTE_SPLIT_DATA_DIR is for a shell check or for a different folder.
# The default sits beside this file and is ignored by Git.
DATA_DIR = Path(
    os.environ.get(
        "NOTE_SPLIT_DATA_DIR",
        Path(__file__).resolve().parent / ".note-split",
    )
)

PROFILES_FILE = DATA_DIR / "style_profiles.json"
LAST_RUN_FILE = DATA_DIR / "last_run.json"

# Bump this only if the stored shape changes in a way old code cannot read.
VERSION = 1


@dataclass(frozen=True)
class StyleProfile:
    """One saved style brief and the numbers it was measured from."""

    name: str
    brief: str
    measured_text: str = ""
    median_words: float = 0.0
    longest_words: int = 0
    saved_at: str = ""


def _now() -> str:
    """The current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path) -> dict | None:
    """Read one JSON object. Missing or corrupt reads as None."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_json(path: Path, data: dict) -> None:
    """Write one JSON object without leaving a half-written file.

    The temporary file is in the same folder, so os.replace stays on
    one disk. Flush and fsync finish the bytes before the replace.
    A failure removes the temporary file and leaves the old file
    alone. The final file is readable only by this user.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        handle, temporary = tempfile.mkstemp(
            dir=path.parent,
            prefix=path.name + ".",
            suffix=".tmp",
        )
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
    os.chmod(path, 0o600)


def _stored_profile(name: str, stored: object) -> StyleProfile | None:
    """Build a profile from one stored entry, or None if it is unusable.

    A hand-edited file may have a missing or wrong type. One bad entry
    is skipped instead of stopping the list.
    """
    if not isinstance(stored, dict):
        return None
    brief = stored.get("brief")
    if not isinstance(brief, str):
        return None
    measured_text = stored.get("measured_text", "")
    if not isinstance(measured_text, str):
        measured_text = ""
    median_words = stored.get("median_words", 0.0)
    if isinstance(median_words, bool) or not isinstance(median_words, (int, float)):
        median_words = 0.0
    longest_words = stored.get("longest_words", 0)
    if isinstance(longest_words, bool) or not isinstance(longest_words, int):
        longest_words = 0
    saved_at = stored.get("saved_at", "")
    if not isinstance(saved_at, str):
        saved_at = ""
    return StyleProfile(
        name=name,
        brief=brief,
        measured_text=measured_text,
        median_words=float(median_words),
        longest_words=longest_words,
        saved_at=saved_at,
    )


def _profile_entries() -> dict:
    """The stored name-to-profile mapping, or an empty dict."""
    data = _read_json(PROFILES_FILE)
    if data is None:
        return {}
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        return {}
    return profiles


def list_profiles() -> list[StyleProfile]:
    """Every saved profile, sorted by name without regard to case.

    Entries that do not have the stored shape are left out.
    """
    profiles = []
    for name, stored in _profile_entries().items():
        if not isinstance(name, str):
            continue
        profile = _stored_profile(name, stored)
        if profile is not None:
            profiles.append(profile)
    profiles.sort(key=lambda profile: profile.name.casefold())
    return profiles


def get_profile(name: str) -> StyleProfile | None:
    """The profile with this exact name, or None when it is not saved."""
    stored = _profile_entries().get(name)
    if stored is None:
        return None
    return _stored_profile(name, stored)


def save_profile(
    name: str,
    brief: str,
    measured_text: str = "",
    median_words: float = 0.0,
    longest_words: int = 0,
) -> StyleProfile:
    """Save a style brief under a name and return the new profile.

    A name that is already saved is replaced, so saving the same name
    twice does not make a duplicate. The name and the brief are
    stripped. Either one being empty raises ValueError. saved_at is
    written here, not passed in by the caller.
    """
    name = name.strip()
    brief = brief.strip()
    if name == "":
        raise ValueError("A style profile needs a name.")
    if brief == "":
        raise ValueError("A style profile needs a brief.")

    saved_at = _now()
    entries = dict(_profile_entries())
    entries[name] = {
        "brief": brief,
        "measured_text": measured_text,
        "median_words": float(median_words),
        "longest_words": int(longest_words),
        "saved_at": saved_at,
    }
    _write_json(PROFILES_FILE, {"version": VERSION, "profiles": entries})
    return StyleProfile(
        name=name,
        brief=brief,
        measured_text=measured_text,
        median_words=float(median_words),
        longest_words=int(longest_words),
        saved_at=saved_at,
    )


def delete_profile(name: str) -> bool:
    """Remove a saved profile. True means one was removed."""
    entries = _profile_entries()
    if name not in entries:
        return False
    del entries[name]
    _write_json(PROFILES_FILE, {"version": VERSION, "profiles": entries})
    return True


def _result_has_usable_text(result: dict) -> bool:
    """True when Preview can draw the stored note, cards, and brief.

    A hand-edited or older file can parse as JSON yet still hold the
    wrong types. Preview indexes each card, so a card that is not a
    dict with string fields would stop the page before Clear is drawn.
    A bad value reads as no saved result instead.
    """
    for key in ("note", "brief"):
        value = result.get(key)
        if value is not None and not isinstance(value, str):
            return False
    cards = result.get("cards")
    if cards is None:
        return True
    if not isinstance(cards, list):
        return False
    for card in cards:
        if not isinstance(card, dict):
            return False
        if not isinstance(card.get("front"), str):
            return False
        if not isinstance(card.get("back"), str):
            return False
    return True


def load_last_run() -> dict | None:
    """The last finished result, or None when there is no usable one.

    The stored package is base64 text. It is turned back into bytes
    here. A missing package stays None. A file that is missing, corrupt,
    or the wrong shape reads as None, so the page can simply run again.
    """
    data = _read_json(LAST_RUN_FILE)
    if data is None:
        return None
    result = data.get("result")
    if not isinstance(result, dict):
        return None
    if not _result_has_usable_text(result):
        return None

    result = dict(result)
    package = result.get("apkg_bytes")
    if package is None:
        result["apkg_bytes"] = None
    elif isinstance(package, str):
        try:
            result["apkg_bytes"] = base64.b64decode(package, validate=True)
        except ValueError:
            return None
    else:
        return None
    return result


def save_last_run(result: dict) -> None:
    """Save the last finished result, with its package as base64.

    The caller's dict is not changed. saved_at goes in the envelope,
    not in the result. The package bytes are replaced on a copy, so
    the next browser reload can use them without another paid run.
    """
    stored = dict(result)
    package = stored.get("apkg_bytes")
    if package is None:
        stored["apkg_bytes"] = None
    elif isinstance(package, (bytes, bytearray)):
        stored["apkg_bytes"] = base64.b64encode(package).decode("ascii")
    else:
        raise TypeError("apkg_bytes must be bytes or None.")

    _write_json(
        LAST_RUN_FILE,
        {"version": VERSION, "saved_at": _now(), "result": stored},
    )


def clear_last_run() -> None:
    """Remove the saved run. A missing file is already clear."""
    try:
        LAST_RUN_FILE.unlink()
    except FileNotFoundError:
        pass
