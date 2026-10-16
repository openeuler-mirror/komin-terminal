"""Chat query construction and execution against an OpenAI-compatible API."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass

import httpx

from komin_terminal.constants import SYSTEM_PROMPT
from komin_terminal.daemon.http.adapters import RetryAdapter, map_http_error
from komin_terminal.daemon.http.stream import SSEParser, StreamEvent
from komin_terminal.exceptions import BackendError
from komin_terminal.logger import audit_log

_CHAT_COMPLETIONS_PATH: str = "/chat/completions"


@dataclass(frozen=True)
class ChatQuery:
    """A single chat completion request payload."""

    messages: Sequence[Mapping[str, str]]
    model: str
    stream: bool = True
    temperature: float = 0.7


def build_messages(
    question: str,
    *,
    system_prompt: str = SYSTEM_PROMPT,
    context: str | None = None,
) -> list[dict[str, str]]:
    """Build the OpenAI messages array for a user question.

    Args:
        question: The user's question text.
        system_prompt: System role prompt; defaults to the global constant.
        context: Optional terminal context; when non-empty it is appended to
            the user message as ``\\n\\n[上下文]\\n<context>``.

    Returns:
        A ``[{role: system, ...}, {role: user, ...}]`` message list.
    """
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    user_content = question
    if context:
        user_content = f"{question}\n\n[上下文]\n{context}"
    messages.append({"role": "user", "content": user_content})
    return messages


class QueryExecutor:
    """Execute :class:`ChatQuery` against a configured httpx client."""

    def __init__(self, client: httpx.Client, retry: RetryAdapter) -> None:
        """Initialize the executor.

        Args:
            client: Configured client for the backend.
            retry: Retry policy applied to every request.
        """
        self._client = client
        self._retry = retry

    def ask(self, query: ChatQuery) -> str:
        """Run a non-streaming chat completion and return the reply text.

        Args:
            query: The query to send.

        Returns:
            The content of ``choices[0].message.content``.

        Raises:
            BackendError: On transport failure, HTTP error or an invalid
                response body.
        """
        request = self._build_request(query)
        start = time.monotonic()
        try:
            response = self._retry.send(self._client, request)
        except BackendError as exc:
            self._audit(query, exc.status_code, time.monotonic() - start)
            raise
        self._audit(query, response.status_code, time.monotonic() - start)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise BackendError("Backend returned an invalid response body") from exc
        if not isinstance(content, str):
            raise BackendError("Backend response is missing message content")
        return content

    def ask_stream(self, query: ChatQuery) -> Iterator[StreamEvent]:
        """Run a streaming chat completion, yielding SSE events.

        The request goes through the retry adapter; once the response stream
        is being read, no further retries happen and mid-stream transport
        failures surface as :class:`BackendError` subclasses.

        Args:
            query: The query to send.

        Yields:
            Chunk, done and error events from the SSE parser.

        Raises:
            BackendError: On retry exhaustion, HTTP error or mid-stream
                transport failure.
        """
        request = self._build_request(query)
        start = time.monotonic()
        try:
            response = self._retry.send(self._client, request)
        except BackendError as exc:
            self._audit(query, exc.status_code, time.monotonic() - start)
            raise
        self._audit(query, response.status_code, time.monotonic() - start)
        parser = SSEParser()
        try:
            yield from parser.parse_response(response)
        except httpx.HTTPError as exc:
            raise map_http_error(exc) from exc

    def _build_request(self, query: ChatQuery) -> httpx.Request:
        """Build the POST request for a query.

        Args:
            query: The query to serialize.

        Returns:
            The built request with a JSON body of
            ``{model, messages, stream, temperature}``.
        """
        payload: dict[str, object] = {
            "model": query.model,
            "messages": [dict(message) for message in query.messages],
            "stream": query.stream,
            "temperature": query.temperature,
        }
        return self._client.build_request("POST", _CHAT_COMPLETIONS_PATH, json=payload)

    def _audit(self, query: ChatQuery, status: int | None, elapsed: float) -> None:
        """Emit an audit event with request metadata only.

        Args:
            query: The query that was executed.
            status: Final HTTP status, when one was received.
            elapsed: Wall-clock duration of the request in seconds.
        """
        audit_log(
            "backend.request",
            url=str(self._client.base_url),
            model=query.model,
            status=status,
            elapsed=round(elapsed, 3),
        )


__all__ = ["ChatQuery", "QueryExecutor", "build_messages"]
