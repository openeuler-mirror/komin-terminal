"""Rendering layer: ANSI colors, themes, width handling, Markdown and streaming.

Public surface: :class:`Color`, :class:`Style`, :class:`Theme`,
:class:`MarkdownRenderer`, :class:`StreamRenderer`, :class:`Renderers`,
:class:`Spinner`, :func:`get_terminal_width`, :func:`wrap_to_width` and
:func:`truncate`.
"""

from komin_terminal.rendering.animation import Spinner
from komin_terminal.rendering.colors import Color, Style
from komin_terminal.rendering.formatting import get_terminal_width, truncate, wrap_to_width
from komin_terminal.rendering.markdown import MarkdownRenderer
from komin_terminal.rendering.renderers import Renderers
from komin_terminal.rendering.stream import StreamRenderer
from komin_terminal.rendering.theme import Theme

__all__ = [
    "Color",
    "MarkdownRenderer",
    "Renderers",
    "Spinner",
    "StreamRenderer",
    "Style",
    "Theme",
    "get_terminal_width",
    "truncate",
    "wrap_to_width",
]
