"""Chat service D-Bus interface: questions, chats and streaming signals."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from komin_terminal.constants import get_dbus_chat_namespace, get_dbus_object_path_chat
from komin_terminal.daemon.database import (
    ChatModel,
    ChatRepository,
    DatabaseManager,
    HistoryRepository,
    InteractionRepository,
)
from komin_terminal.daemon.http import ChatQuery, QueryExecutor, build_messages
from komin_terminal.daemon.session import UserSessionManager
from komin_terminal.dbus.bus import BusAbstraction, InterfaceSpec, MethodSpec, SignalSpec
from komin_terminal.dbus.interfaces.authorization import Authorization
from komin_terminal.dbus.structures import ChatInfo
from komin_terminal.exceptions import AccessDeniedError, BackendError, KominError
from komin_terminal.logger import get_logger

_LOGGER = get_logger("komin.dbus.chat")

MAX_ATTACHMENT_BYTES: int = 1024 * 1024
_SUMMARY_MAX_ROUNDS: int = 20
_SUMMARY_QUESTION_CHARS: int = 1000
_SUMMARY_RESPONSE_CHARS: int = 1000
_SUMMARY_PROMPT: str = (
    "请总结以下对话历史，保留关键事实、结论与未解决的问题，"
    "输出简洁的摘要，不要添加新信息：\n\n"
)
_LIST_LIMIT: int = 10_000


def _readable_error(error: BaseException) -> str:
    """Convert an exception into a human-readable StreamError message.

    Args:
        error: The exception raised inside the streaming thread.

    Returns:
        A readable message derived from the komin exception hierarchy.
    """
    if isinstance(error, KominError):
        return error.message
    return str(error)


class ChatInterface:
    """Server-side chat service published on the D-Bus system bus.

    Every public method starts with a caller authorization check and all
    data access is filtered by the caller's user id.

    Args:
        auth: Caller authorizer.
        sessions: User identity manager.
        db: Database manager.
        executor_factory: Factory producing a fresh QueryExecutor.
        bus: Bus abstraction used to emit streaming signals.
        default_model: Model used when a chat does not pin one.
    """

    def __init__(
        self,
        *,
        auth: Authorization,
        sessions: UserSessionManager,
        db: DatabaseManager,
        executor_factory: Callable[[], QueryExecutor],
        bus: BusAbstraction,
        default_model: str,
    ) -> None:
        """Initialize the chat service."""
        self._auth = auth
        self._sessions = sessions
        self._db = db
        self._executor_factory = executor_factory
        self._bus = bus
        self._default_model = default_model
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def get_dbus_spec(self) -> InterfaceSpec:
        """Return the declarative D-Bus specification of this service."""
        return InterfaceSpec(
            interface_name=get_dbus_chat_namespace(),
            methods=(
                MethodSpec("AskQuestion", "ask_question", ("s", "s", "as", "s"), "s"),
                MethodSpec("CreateChat", "create_chat", ("s", "s", "s"), "s"),
                MethodSpec("DeleteChat", "delete_chat", ("s",), "b"),
                MethodSpec("ListChats", "list_chats", (), "aa{sv}"),
                MethodSpec("GetChat", "get_chat", ("s",), "a{sv}"),
            ),
            signals=(
                SignalSpec("StreamChunk", ("s", "s")),
                SignalSpec("StreamEnd", ("s",)),
                SignalSpec("StreamError", ("s", "s")),
            ),
        )

    def ask_question(
        self, question: str, chat_id: str, attachments: list[str], model: str, caller: str
    ) -> str:
        """Start a streamed question and return its answer id immediately.

        The stream runs on a background thread: chunks are emitted as
        StreamChunk signals, completion as StreamEnd (after persisting the
        exchange) and any failure as StreamError.

        Args:
            question: The user's question text.
            chat_id: Chat to attach the exchange to; empty for one-shot.
            attachments: Paths of text files attached as context.
            model: Optional model override for this call; empty falls back
                to the chat-pinned model, then the daemon default.
            caller: D-Bus connection name of the caller.

        Returns:
            The answer id used by every streaming signal.

        Raises:
            AccessDeniedError: When the chat belongs to another user.
            KeyError: When the chat id is malformed or does not exist.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        chat = self._resolve_chat(user_id, chat_id)
        model = model or (
            chat.model if chat is not None and chat.model else self._default_model
        )
        answer_id = str(uuid.uuid4())
        thread = threading.Thread(
            target=self._run_stream,
            args=(answer_id, question, chat, model, list(attachments), user_id),
            name=f"komin-stream-{answer_id}",
            daemon=True,
        )
        with self._lock:
            self._threads[answer_id] = thread
        thread.start()
        return answer_id

    def create_chat(self, name: str, description: str, model: str, caller: str) -> str:
        """Create a chat owned by the caller.

        Args:
            name: Chat name.
            description: Free-form description.
            model: Optional model pinned to the chat; empty means unset.
            caller: D-Bus connection name of the caller.

        Returns:
            The new chat id.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        chat = ChatRepository(self._db, user_id).add(
            name=name, description=description, model=model
        )
        return str(chat.id)

    def delete_chat(self, chat_id: str, caller: str) -> bool:
        """Soft-delete a chat owned by the caller.

        Args:
            chat_id: Chat to delete.
            caller: D-Bus connection name of the caller.

        Returns:
            ``True`` when a live chat was deleted.

        Raises:
            KeyError: When the chat id is malformed.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        parsed = self._parse_chat_id(chat_id)
        return ChatRepository(self._db, user_id).soft_delete(parsed)

    def list_chats(self, caller: str) -> list[dict[str, Any]]:
        """List every live chat of the caller.

        Args:
            caller: D-Bus connection name of the caller.

        Returns:
            ChatInfo structures as dicts.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        repo = ChatRepository(self._db, user_id)
        total = repo.count()
        chats = repo.list(limit=max(total, 1)) if total else []
        return [self._chat_info(chat).to_structure() for chat in chats]

    def get_chat(self, chat_id: str, caller: str) -> dict[str, Any]:
        """Fetch one chat of the caller.

        Args:
            chat_id: Chat to fetch.
            caller: D-Bus connection name of the caller.

        Returns:
            The ChatInfo structure as a dict.

        Raises:
            AccessDeniedError: When the chat belongs to another user.
            KeyError: When the chat id is malformed or does not exist.
        """
        uid = self._auth.check_access(caller)
        user_id = self._sessions.get_user_id(uid)
        chat = self._resolve_chat(user_id, chat_id)
        assert chat is not None
        return self._chat_info(chat).to_structure()

    def _parse_chat_id(self, chat_id: str) -> uuid.UUID:
        """Parse a chat id string.

        Args:
            chat_id: Chat id as transmitted over D-Bus.

        Returns:
            The parsed UUID.

        Raises:
            KeyError: When the string is not a valid UUID.
        """
        try:
            return uuid.UUID(chat_id)
        except ValueError as exc:
            raise KeyError(f"invalid chat id {chat_id!r}") from exc

    def _resolve_chat(self, user_id: uuid.UUID, chat_id: str) -> ChatModel | None:
        """Resolve a chat id to a live chat owned by ``user_id``.

        Args:
            user_id: Owning user.
            chat_id: Chat id; empty selects no chat (one-shot).

        Returns:
            The chat, or ``None`` for one-shot questions.

        Raises:
            AccessDeniedError: When the chat exists but belongs to another user.
            KeyError: When the chat id is malformed or does not exist.
        """
        if not chat_id:
            return None
        parsed = self._parse_chat_id(chat_id)
        repo = ChatRepository(self._db, user_id)
        chat = repo.get(parsed)
        if chat is None:
            if repo.get_owner(parsed) is not None:
                raise AccessDeniedError(f"chat {chat_id} belongs to another user")
            raise KeyError(f"chat {chat_id} not found")
        return chat

    def _chat_info(self, chat: ChatModel) -> ChatInfo:
        """Convert an ORM chat into its D-Bus structure."""
        return ChatInfo(
            id=chat.id,
            user_id=chat.user_id,
            name=chat.name,
            description=chat.description,
            model=chat.model,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    def _emit(self, member: str, args: tuple[Any, ...]) -> None:
        """Emit a chat signal from the chat object path."""
        self._bus.emit_signal(get_dbus_object_path_chat(), get_dbus_chat_namespace(), member, args)

    def _run_stream(
        self,
        answer_id: str,
        question: str,
        chat: ChatModel | None,
        model: str,
        attachments: list[str],
        user_id: uuid.UUID,
    ) -> None:
        """Execute the streamed question on a background thread.

        Args:
            answer_id: Id correlating every emitted signal.
            question: The user's question text.
            chat: Resolved chat, or ``None`` for one-shot.
            model: Model to query.
            attachments: Attachment paths.
            user_id: Owning user.
        """
        try:
            executor = self._executor_factory()
            attachment_texts = self._read_attachments(attachments)
            summary = self._summarize_history(executor, chat, model, user_id)
            context = self._compose_context(summary, attachment_texts)
            query = ChatQuery(
                messages=build_messages(question, context=context or None),
                model=model,
                stream=True,
            )
            chunks: list[str] = []
            for event in executor.ask_stream(query):
                if event.kind == "chunk":
                    chunks.append(event.content)
                    self._emit("StreamChunk", (answer_id, event.content))
                elif event.kind == "error":
                    raise BackendError(event.content or "backend reported a stream error")
                else:
                    break
            response = "".join(chunks)
            self._persist(user_id, chat, question, summary, response, model)
            self._emit("StreamEnd", (answer_id,))
        except Exception as exc:  # noqa: BLE001 - every failure becomes StreamError
            _LOGGER.warning("stream %s failed: %s", answer_id, exc)
            self._emit("StreamError", (answer_id, _readable_error(exc)))
        finally:
            with self._lock:
                self._threads.pop(answer_id, None)

    def _read_attachments(self, attachments: list[str]) -> list[str]:
        """Read attachment files on the daemon side.

        Args:
            attachments: Paths transmitted by the client.

        Returns:
            The file contents decoded as UTF-8 (replacement on errors).

        Raises:
            KominError: When a path is missing, not a regular file or larger
                than 1 MiB.
        """
        texts: list[str] = []
        for raw in attachments:
            path = Path(raw)
            if not path.is_file():
                raise KominError(f"attachment is not an existing regular file: {raw}")
            if path.stat().st_size > MAX_ATTACHMENT_BYTES:
                raise KominError(f"attachment exceeds the 1 MiB limit: {raw}")
            texts.append(path.read_text(encoding="utf-8", errors="replace"))
        return texts

    def _summarize_history(
        self,
        executor: QueryExecutor,
        chat: ChatModel | None,
        model: str,
        user_id: uuid.UUID,
    ) -> str:
        """Summarize the chat history with one extra LLM call.

        Args:
            executor: Executor used for the summarization call.
            chat: The chat whose history is summarized; ``None`` skips it.
            model: Model to query.
            user_id: Owning user.

        Returns:
            The summary text, or an empty string when there is no history.
        """
        if chat is None:
            return ""
        rounds = InteractionRepository(self._db, user_id).list_by_chat(
            chat.id, limit=_SUMMARY_MAX_ROUNDS
        )
        if not rounds:
            return ""
        lines = [
            f"用户: {item.question[:_SUMMARY_QUESTION_CHARS]}\n"
            f"助手: {item.response[:_SUMMARY_RESPONSE_CHARS]}"
            for item in reversed(rounds)
        ]
        prompt = _SUMMARY_PROMPT + "\n".join(lines)
        summary_query = ChatQuery(
            messages=[{"role": "user", "content": prompt}], model=model, stream=False
        )
        return executor.ask(summary_query).strip()

    def _compose_context(self, summary: str, attachment_texts: list[str]) -> str:
        """Compose the context block appended to the user message.

        Args:
            summary: Conversation history summary (may be empty).
            attachment_texts: Full attachment contents.

        Returns:
            The combined context, or an empty string when there is none.
        """
        parts: list[str] = []
        if summary:
            parts.append(f"[对话历史摘要]\n{summary}")
        if attachment_texts:
            parts.append("[附件内容]\n" + "\n\n".join(attachment_texts))
        return "\n\n".join(parts)

    def _persist(
        self,
        user_id: uuid.UUID,
        chat: ChatModel | None,
        question: str,
        summary: str,
        response: str,
        model: str,
    ) -> None:
        """Persist the finished exchange as history plus interaction.

        Args:
            user_id: Owning user.
            chat: Parent chat, or ``None`` for one-shot.
            question: The user's question text.
            summary: History summary included in the stored question.
            response: The full assistant response.
            model: Model that answered.
        """
        history = HistoryRepository(self._db, user_id).add(
            chat_id=chat.id if chat is not None else None
        )
        stored_question = (
            f"{question}\n\n[对话历史摘要]\n{summary}" if summary else question
        )
        InteractionRepository(self._db, user_id).append_interaction(
            history.id, stored_question, response, model, 0
        )
