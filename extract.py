"""Turn uploaded source files into one string.

One .txt file or one typed PDF goes through extract_source. Several
.txt files, or several PDFs, go through extract_sources. Both paths
read the file bytes and do not call the model. Handwritten pages are
not read here. Transcribe them first and upload the text as a .txt
file.
"""

import pymupdf

from models import Stop

# About a long lecture. The example-note check uses this same cap.
# A longer string is a stop. Do not cut it down and keep going.
MAX_SOURCE_CHARS = 80_000


def extract_source(data: bytes, filename: str) -> str:
    """Return the text of one .txt file or one typed PDF.

    An empty or whitespace-only file raises Stop. A PDF with no text
    asks the user to upload a text transcription. A string longer than
    MAX_SOURCE_CHARS raises Stop.
    """
    if _is_pdf(filename):
        text = _read_pdf(data)
        if text.strip() == "":
            raise Stop(
                "This PDF has no text. Transcribe it and upload a .txt file instead."
            )
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
            raise Stop(
                "This PDF has no text. Transcribe it and upload a .txt file instead."
            )
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
    #
    # A user-supplied file can be empty, junk, or password-protected.
    # PyMuPDF raises its own errors for those, and the page does not
    # catch them. Turn them into Stop so the user sees a sentence
    # instead of a traceback. EmptyFileError is a FileDataError.
    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except (pymupdf.FileDataError, ValueError) as exc:
        raise Stop(
            "This PDF could not be read. Export it again or upload a .txt file."
        ) from exc

    try:
        if document.needs_pass:
            raise Stop(
                "This PDF is password-protected. Remove the password "
                "or upload a .txt file."
            )
        pages = []
        for page in document:
            pages.append(page.get_text())
        return "".join(pages)
    except ValueError as exc:
        raise Stop(
            "This PDF could not be read. Export it again or upload a .txt file."
        ) from exc
    finally:
        document.close()
