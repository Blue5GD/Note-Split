"""Turn uploaded source files into one string.

One .txt file or one typed PDF goes through extract_source. Several
.txt files, or several PDFs, go through extract_sources. Those paths
read the file bytes and do not call the model. Photos go through
extract_photos. Each photo is one page and one vision call. The pages
come back joined into one string.
"""

import pymupdf

from models import Stop, TokenUsage, call_model
from prompts import VISION_PROMPT

# About a long lecture. Later, the example-note check uses this same cap.
# A longer string is a stop. Do not cut it down and keep going.
MAX_SOURCE_CHARS = 80_000

# One photo is one page. More than this is a stop, before any vision call.
MAX_PHOTOS = 20


def extract_source(data: bytes, filename: str) -> str:
    """Return the text of one .txt file or one typed PDF.

    An empty or whitespace-only file raises Stop. A PDF with no text
    asks the user to upload photos. A string longer than
    MAX_SOURCE_CHARS raises Stop.
    """
    if _is_pdf(filename):
        text = _read_pdf(data)
        if text.strip() == "":
            raise Stop("This PDF has no text. Upload photos instead.")
    else:
        text = _read_txt(data)
        if text.strip() == "":
            raise Stop("The file was empty.")

    if len(text) > MAX_SOURCE_CHARS:
        raise Stop(
            f"The source is longer than {MAX_SOURCE_CHARS:,} characters. "
            "Upload a shorter source."
        )
    return text


def extract_sources(files: list[tuple[str, bytes]]) -> str:
    """Return the text of several .txt files or several typed PDFs.

    files is (filename, bytes) pairs in the order the caller gives.
    The pieces are joined with a blank line. One file stays that
    file's text. The empty check and the length cap look at the
    combined string, not each file. A blank file among files that
    do have text is kept.
    """
    # The caller already chose the order. Do not sort.
    pieces = []
    for filename, data in files:
        if _is_pdf(filename):
            pieces.append(_read_pdf(data))
        else:
            pieces.append(_read_txt(data))
    combined = "\n\n".join(pieces)

    if combined.strip() == "":
        # The caller already rejected a PDF mixed with a txt. The
        # first name only picks which empty sentence to show.
        if _is_pdf(files[0][0]):
            raise Stop("This PDF has no text. Upload photos instead.")
        raise Stop("The file was empty.")

    if len(combined) > MAX_SOURCE_CHARS:
        raise Stop(
            f"The source is longer than {MAX_SOURCE_CHARS:,} characters. "
            "Upload a shorter source."
        )
    return combined


def _is_pdf(filename: str) -> bool:
    return filename.lower().endswith(".pdf")


def _read_txt(data: bytes) -> str:
    """Return the text of one .txt file.

    The file must be UTF-8. Another encoding raises Stop with a message
    that says how to save it again.
    """
    # A .txt file is already text. Read the bytes as UTF-8 and return them.
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Stop(
            "The file is not UTF-8 text. Save it as UTF-8 and upload it again."
        ) from exc


def _read_pdf(data: bytes) -> str:
    # PyMuPDF reads text stored in the PDF. A drawn equation is not in
    # that text when the rest of the page is. This function does not try
    # to notice a missing equation.
    document = pymupdf.open(stream=data, filetype="pdf")
    try:
        pages = []
        for page in document:
            pages.append(page.get_text())
        return "".join(pages)
    finally:
        document.close()


def extract_photos(
    photos: list[tuple[str, bytes]],
    usage: TokenUsage | None = None,
) -> str:
    """Turn photo pages into one string.

    photos is a list of (filename, file_bytes) pairs. One pair is one
    page. The caller chooses the order. This function does not sort.

    usage, when given, collects the token counts from every vision
    call, including a call whose page later turns out to be blank.

    More than MAX_PHOTOS raises Stop before any vision call. Each page
    is one call. A blank page names that file and stops. Pages are
    joined with a blank line. If the text so far passes the cap, the
    remaining pages are not sent.
    """
    # The caller already chose the page order. Do not sort. The length
    # cap is still checked before any vision call.
    if len(photos) > MAX_PHOTOS:
        raise Stop(f"Upload at most {MAX_PHOTOS} photos.")

    pages: list[str] = []
    joined = ""
    for filename, data in photos:
        reply = call_model(
            VISION_PROMPT,
            [{"data": data, "media_type": _media_type(filename)}],
            usage=usage,
        )
        # The model was told not to use a fence. If it wraps the whole
        # page in one anyway, drop that fence, then check for a blank page.
        # A fence in the middle of the page stays.
        text = _strip_one_fence(reply)
        if text.strip() == "":
            raise Stop(f"The photo {filename} was blank.")
        pages.append(text)
        joined = "\n\n".join(pages)
        # Same stop as a txt or PDF that is too long. Do not send the rest.
        if len(joined) > MAX_SOURCE_CHARS:
            raise Stop(
                f"The source is longer than {MAX_SOURCE_CHARS:,} characters. "
                "Upload a shorter source."
            )
    return joined


def _media_type(filename: str) -> str:
    # png, jpg, and jpeg are the accepted types. HEIC is not.
    if filename.lower().endswith(".png"):
        return "image/png"
    return "image/jpeg"


def _strip_one_fence(text: str) -> str:
    """Drop one code fence that wraps the whole reply.

    A fence that sits in the middle of the transcription stays.
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
    # ``` or ```markdown. A line that only mentions a fence does not count.
    if not line.startswith("```"):
        return False
    tag = line[3:].strip()
    if tag == "":
        return True
    return tag.replace("-", "").replace("_", "").isalnum()
