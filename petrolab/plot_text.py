from __future__ import annotations


SUBSCRIPT_MAP = {
    "₀": "0", "₁": "1", "₂": "2", "₃": "3", "₄": "4",
    "₅": "5", "₆": "6", "₇": "7", "₈": "8", "₉": "9",
    "ₜ": "t",
}


def matplotlib_label(text: str) -> str:
    """Convert Unicode subscripts to Matplotlib MathText without changing UI text."""
    source = str(text)
    output: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            output.append("$_{" + "".join(buffer) + "}$")
            buffer.clear()

    for char in source:
        if char in SUBSCRIPT_MAP:
            buffer.append(SUBSCRIPT_MAP[char])
        else:
            flush()
            output.append(char)
    flush()
    return "".join(output)
