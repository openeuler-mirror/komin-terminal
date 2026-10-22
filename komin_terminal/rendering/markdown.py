"""Markdown to ANSI rendering.

Uses the ``markdown`` library to produce XHTML, then walks the element tree
and maps blocks and inline spans to themed ANSI output. Malformed input never
raises: internal failures degrade to the plain source text with a warning.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import markdown as markdown_lib
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor

from komin_terminal.exceptions import RenderingError
from komin_terminal.logger import get_logger
from komin_terminal.rendering.colors import RESET, Style, ansi
from komin_terminal.rendering.formatting import (
    display_width,
    resolve_width,
    visible_text,
    wrap_to_width,
)
from komin_terminal.rendering.theme import Theme

_logger = get_logger("komin.rendering.markdown")

_HEADING_TAGS: frozenset[str] = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_LIST_TAGS: frozenset[str] = frozenset({"ul", "ol"})
_WHITESPACE_AROUND_NEWLINE: re.Pattern[str] = re.compile(r"[ \t]*\n[ \t]*")


class _StrikethroughProcessor(InlineProcessor):
    """Inline processor mapping ``~~text~~`` to a ``del`` element."""

    def __init__(self) -> None:
        """Initialize the processor with the strikethrough pattern."""
        super().__init__(r"~~(.+?)~~")

    def handleMatch(  # type: ignore[override]
        self, m: re.Match[str], data: str
    ) -> tuple[ET.Element | str | None, int | None, int | None]:
        """Build the ``del`` element for a strikethrough match.

        Args:
            m: The regex match.
            data: The source line (unused).

        Returns:
            The element with the match span.
        """
        del data
        element = ET.Element("del")
        element.text = m.group(1)
        return element, m.start(0), m.end(0)


class _StrikethroughExtension(Extension):
    """Markdown extension registering the strikethrough inline processor."""

    def extendMarkdown(self, md: markdown_lib.Markdown) -> None:
        """Register the processor on the given Markdown instance.

        Args:
            md: The Markdown instance being configured.
        """
        md.inlinePatterns.register(_StrikethroughProcessor(), "strikethrough", 75)


def _collapse_whitespace(text: str) -> str:
    """Collapse whitespace runs around newlines into single spaces."""
    return _WHITESPACE_AROUND_NEWLINE.sub(" ", text)


def _fit_columns(widths: list[int], available: int) -> list[int]:
    """Shrink the widest columns until their sum fits ``available``."""
    result = list(widths)
    min_width = 3
    while sum(result) > available:
        widest = max(result)
        if widest <= min_width:
            break
        result[result.index(widest)] -= 1
    return result


class MarkdownRenderer:
    """Renders Markdown text to themed ANSI terminal output.

    Attributes:
        width: The concrete column width used for wrapping and tables.
    """

    def __init__(self, theme: Theme, width: int = 0) -> None:
        """Initialize the renderer.

        Args:
            theme: Theme providing the semantic ANSI styles.
            width: Render width; ``0`` auto-detects via
                :func:`~komin_terminal.rendering.formatting.resolve_width`.
        """
        self._theme = theme
        self._width = resolve_width(width)

    @property
    def width(self) -> int:
        """The concrete column width this renderer wraps to."""
        return self._width

    def render(self, markdown_text: str) -> str:
        """Render Markdown text to an ANSI string.

        Supported constructs: headings, fenced code blocks (with language
        annotation), inline code, bold, italic, strikethrough, nested
        unordered/ordered lists, tables (border-styled, width-adaptive),
        links (text plus dim URL) and blockquotes. Malformed input never
        raises; internal failures degrade to the plain source text.

        Args:
            markdown_text: The Markdown source.

        Returns:
            The rendered ANSI string (no trailing newline), or the source
            text unchanged when rendering fails internally.
        """
        if not markdown_text.strip():
            return ""
        try:
            return self._render_markdown(markdown_text)
        except RenderingError as exc:
            _logger.warning("Markdown rendering failed (%s); degrading to plain text", exc)
            return markdown_text
        except Exception as exc:  # noqa: BLE001 - rendering must never crash the CLI
            _logger.warning("Unexpected rendering error (%s); degrading to plain text", exc)
            return markdown_text

    def _render_markdown(self, text: str) -> str:
        """Convert Markdown to XHTML and walk it into ANSI blocks."""
        html = markdown_lib.markdown(
            text,
            extensions=["fenced_code", "tables", "sane_lists", _StrikethroughExtension()],
            output_format="xhtml",
        )
        try:
            root = ET.fromstring(f"<div>{html}</div>")
        except ET.ParseError as exc:
            raise RenderingError("Generated HTML could not be parsed", detail=str(exc)) from exc
        blocks = self._render_block_children(root)
        return "\n\n".join(block for block in blocks if visible_text(block).strip())

    def _render_block_children(self, element: ET.Element) -> list[str]:
        """Render every block-level child of ``element``."""
        blocks: list[str] = []
        for child in element:
            block = self._render_block(child)
            if block:
                blocks.append(block)
        return blocks

    def _render_block(self, element: ET.Element) -> str:
        """Dispatch a single block-level element."""
        tag = element.tag
        if tag in _HEADING_TAGS:
            return self._render_heading(element)
        if tag == "p":
            return self._render_paragraph(element)
        if tag == "pre":
            return self._render_code_block(element)
        if tag in _LIST_TAGS:
            return self._render_list(element)
        if tag == "blockquote":
            return self._render_blockquote(element)
        if tag == "table":
            return self._render_table(element)
        if tag == "hr":
            return ""
        return self._render_paragraph(element)

    def _render_heading(self, element: ET.Element) -> str:
        """Render a heading with ``#`` prefix in the heading style."""
        level = int(element.tag[1])
        content = self._inline(element).strip()
        line = f"{'#' * level} {content}"
        return wrap_to_width(self._theme_apply(line, "heading"), self._width)

    def _render_paragraph(self, element: ET.Element) -> str:
        """Render a paragraph wrapped to the render width."""
        content = self._inline(element).strip()
        if not visible_text(content).strip():
            return ""
        return wrap_to_width(content, self._width)

    def _render_code_block(self, pre: ET.Element) -> str:
        """Render a fenced code block with language annotation."""
        code = pre.find("code")
        language = ""
        if code is not None:
            for cls in (code.get("class") or "").split():
                if cls.startswith("language-"):
                    language = cls.removeprefix("language-")
                    break
            content = "".join(code.itertext())
        else:
            content = "".join(pre.itertext())
        if content.endswith("\n"):
            content = content[:-1]
        style = self._theme.get("code_block")
        lines = [self._apply(style, f"```{language}")]
        lines.extend(self._apply(style, line) for line in content.split("\n"))
        lines.append(self._apply(style, "```"))
        return "\n".join(lines)

    def _render_list(self, element: ET.Element, depth: int = 0) -> str:
        """Render a list with nested indentation."""
        lines: list[str] = []
        ordered = element.tag == "ol"
        index = 1
        if ordered:
            try:
                index = int(element.get("start") or "1")
            except ValueError:
                index = 1
        for item in element.findall("li"):
            bullet = f"{index}." if ordered else "•"
            indent = "  " * depth
            content = self._inline(item, skip_tags=_LIST_TAGS).strip()
            first_prefix = f"{indent}{bullet} "
            cont_prefix = indent + " " * (len(bullet) + 1)
            lines.append(self._wrap_prefixed(content, first_prefix, cont_prefix))
            for child in item:
                if child.tag in _LIST_TAGS:
                    lines.append(self._render_list(child, depth + 1))
            index += 1
        return "\n".join(lines)

    def _render_blockquote(self, element: ET.Element) -> str:
        """Render a blockquote with a styled vertical bar prefix."""
        blocks = self._render_block_children(element)
        if not blocks:
            return ""
        inner = "\n\n".join(blocks)
        bar = self._apply(self._theme.get("table_border"), "│")
        lines = [f"{bar} {line}" if line else bar for line in inner.split("\n")]
        return "\n".join(lines)

    def _render_table(self, element: ET.Element) -> str:
        """Render a table with themed borders and width-adaptive columns."""
        rows: list[tuple[list[str], bool]] = []
        for tr in element.iter("tr"):
            cells = [self._inline(cell).strip() for cell in tr if cell.tag in ("th", "td")]
            is_header = any(cell.tag == "th" for cell in tr)
            rows.append((cells, is_header))
        if not rows:
            return ""
        column_count = max(len(cells) for cells, _ in rows)
        if column_count == 0:
            return ""
        styled_rows: list[list[str]] = []
        for cells, is_header in rows:
            padded = cells + [""] * (column_count - len(cells))
            if is_header:
                padded = [self._theme_apply(cell, "strong") for cell in padded]
            styled_rows.append(padded)
        column_widths = [1] * column_count
        for cells in styled_rows:
            for index, cell in enumerate(cells):
                cell_width = max(
                    (display_width(line) for line in visible_text(cell).split("\n")), default=0
                )
                column_widths[index] = max(column_widths[index], cell_width)
        overhead = 3 * column_count + 1
        available = max(self._width - overhead, column_count)
        column_widths = _fit_columns(column_widths, available)
        border = self._theme.get("table_border")

        def rule(left: str, mid: str, right: str) -> str:
            return self._apply(
                border, left + mid.join("─" * (w + 2) for w in column_widths) + right
            )

        lines = [rule("┌", "┬", "┐")]
        for row_index, cells in enumerate(styled_rows):
            wrapped_cells = [
                wrap_to_width(cell, column_widths[index]).split("\n")
                for index, cell in enumerate(cells)
            ]
            height = max(len(wrapped) for wrapped in wrapped_cells)
            for line_index in range(height):
                parts: list[str] = []
                for index in range(column_count):
                    wrapped = wrapped_cells[index]
                    text = wrapped[line_index] if line_index < len(wrapped) else ""
                    padding = column_widths[index] - display_width(visible_text(text))
                    parts.append(self._apply(border, "│") + f" {text}{' ' * padding} ")
                parts.append(self._apply(border, "│"))
                lines.append("".join(parts))
            if row_index == 0 and rows[0][1] and len(styled_rows) > 1:
                lines.append(rule("├", "┼", "┤"))
        lines.append(rule("└", "┴", "┘"))
        return "\n".join(lines)

    def _wrap_prefixed(self, content: str, first_prefix: str, cont_prefix: str) -> str:
        """Wrap content and hang continuation lines under the first prefix."""
        prefix_width = max(
            display_width(visible_text(first_prefix)), display_width(visible_text(cont_prefix))
        )
        inner_width = self._width - prefix_width
        wrapped = wrap_to_width(content, inner_width) if inner_width > 0 else content
        lines = wrapped.split("\n")
        out = [first_prefix + lines[0]]
        out.extend(cont_prefix + line for line in lines[1:])
        return "\n".join(out)

    def _inline(self, element: ET.Element, skip_tags: frozenset[str] = frozenset()) -> str:
        """Render the inline content of an element (text, children, tails)."""
        parts: list[str] = []
        if element.text:
            parts.append(_collapse_whitespace(element.text))
        for child in element:
            if child.tag in skip_tags:
                if child.tail:
                    parts.append(_collapse_whitespace(child.tail))
                continue
            parts.append(self._inline_child(child))
        return "".join(parts)

    def _inline_child(self, child: ET.Element) -> str:
        """Render one inline child element plus its tail text."""
        tag = child.tag
        if tag == "code":
            rendered = self._apply(self._theme.get("inline_code"), f"`{''.join(child.itertext())}`")
        elif tag in ("strong", "b"):
            rendered = self._theme_apply(self._inline(child), "strong")
        elif tag in ("em", "i"):
            rendered = self._theme_apply(self._inline(child), "emphasis")
        elif tag in ("del", "s"):
            inner = self._inline(child)
            strike = ansi(Style.STRIKETHROUGH)
            rendered = self._apply(strike, inner)
        elif tag == "a":
            rendered = self._render_link(child)
        elif tag == "img":
            rendered = child.get("alt") or ""
        elif tag == "br":
            rendered = "\n"
        else:
            rendered = self._inline(child)
        tail = _collapse_whitespace(child.tail) if child.tail else ""
        return rendered + tail

    def _render_link(self, element: ET.Element) -> str:
        """Render a link as styled text plus a dim URL."""
        href = element.get("href") or ""
        text = self._inline(element).strip()
        if not visible_text(text):
            text = href
        styled = self._theme_apply(text, "link")
        if not href or href == visible_text(text):
            return styled
        return f"{styled} {ansi(Style.DIM)}({href}){RESET}"

    def _theme_apply(self, text: str, key: str) -> str:
        """Wrap ``text`` in the themed style for ``key``."""
        return self._apply(self._theme.get(key), text)

    def _apply(self, style: str, text: str) -> str:
        """Wrap ``text`` in ``style``, re-opening the style after inner resets."""
        if not style or not text:
            return text
        if RESET in text:
            text = text.replace(RESET, RESET + style)
        return f"{style}{text}{RESET}"
