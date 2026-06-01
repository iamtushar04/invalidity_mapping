# import re


# def normalize_text(text):

#     if text is None:
#         return ""

#     # HANDLE LIST INPUT
#     if isinstance(text, list):
#         text = " ".join(
#             str(t) for t in text
#         )

#     # FORCE STRING
#     text = str(text)

#     # Remove leading claim number
#     text = re.sub(
#         r"^\s*\d+\.\s*",
#         "",
#         text
#     )

#     # Normalize whitespace
#     text = " ".join(text.split())

#     return text

import re


def normalize_text(text):

    if not text:
        return ""

    # list -> string
    if isinstance(text, list):
        text = " ".join(text)

    # Remove claim numbering
    text = re.sub(
        r"^\s*\d+\.\s*",
        "",
        text
    )

    # Remove excessive spaces
    text = " ".join(text.split())

    # Normalize weird unicode
    text = text.replace("“", "\"")
    text = text.replace("”", "\"")
    text = text.replace("’", "'")

    # Normalize FIG spacing
    text = re.sub(
        r"FIG\.\s*",
        "FIG ",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()