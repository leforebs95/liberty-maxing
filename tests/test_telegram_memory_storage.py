"""Tests for per-user Telegram memory storage.

Verifies that:
- MemoryStore creates isolated per-user directories when a namespace is given
- Two different Telegram users do NOT share MEMORY.md / HISTORY.md
- ContextBuilder injects per-session memory into the system prompt
- AgentLoop._consolidate_memory writes to the correct per-user namespace
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from liberty_max.agent.context import ContextBuilder, _session_namespace
from liberty_max.agent.memory import MemoryStore
from liberty_max.providers.base import LLMResponse, ToolCallRequest


# ---------------------------------------------------------------------------
# _session_namespace helper
# ---------------------------------------------------------------------------

class TestSessionNamespace:
    def test_telegram_key(self) -> None:
        assert _session_namespace("telegram:123456789") == "telegram_123456789"

    def test_discord_key(self) -> None:
        assert _session_namespace("discord:987654321") == "discord_987654321"

    def test_cli_key(self) -> None:
        assert _session_namespace("cli:direct") == "cli_direct"


# ---------------------------------------------------------------------------
# MemoryStore namespace isolation
# ---------------------------------------------------------------------------

class TestMemoryStoreNamespace:
    def test_default_uses_root_memory_dir(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path)
        assert store.memory_dir == tmp_path / "memory"
        assert store.memory_file == tmp_path / "memory" / "MEMORY.md"
        assert store.history_file == tmp_path / "memory" / "HISTORY.md"

    def test_namespace_creates_subdirectory(self, tmp_path: Path) -> None:
        store = MemoryStore(tmp_path, namespace="telegram_123456789")
        assert store.memory_dir == tmp_path / "memory" / "telegram_123456789"
        assert store.memory_file == tmp_path / "memory" / "telegram_123456789" / "MEMORY.md"
        assert store.history_file == tmp_path / "memory" / "telegram_123456789" / "HISTORY.md"

    def test_two_users_isolated(self, tmp_path: Path) -> None:
        alice = MemoryStore(tmp_path, namespace="telegram_111")
        bob = MemoryStore(tmp_path, namespace="telegram_222")

        alice.write_long_term("# Alice\nAlice prefers Python.")
        bob.write_long_term("# Bob\nBob prefers Rust.")

        assert "Alice" in alice.read_long_term()
        assert "Bob" not in alice.read_long_term()
        assert "Bob" in bob.read_long_term()
        assert "Alice" not in bob.read_long_term()

    def test_history_isolation(self, tmp_path: Path) -> None:
        alice = MemoryStore(tmp_path, namespace="telegram_111")
        bob = MemoryStore(tmp_path, namespace="telegram_222")

        alice.append_history("[2026-01-01 10:00] Alice said hello.")
        bob.append_history("[2026-01-01 10:01] Bob said goodbye.")

        alice_hist = alice.history_file.read_text()
        bob_hist = bob.history_file.read_text()

        assert "Alice said hello" in alice_hist
        assert "Bob said goodbye" not in alice_hist
        assert "Bob said goodbye" in bob_hist
        assert "Alice said hello" not in bob_hist

    def test_namespace_directory_created_on_init(self, tmp_path: Path) -> None:
        MemoryStore(tmp_path, namespace="telegram_999")
        assert (tmp_path / "memory" / "telegram_999").is_dir()

    @pytest.mark.asyncio
    async def test_consolidation_writes_to_namespace(self, tmp_path: Path) -> None:
        """Consolidation must write to the per-user namespace directory."""
        store = MemoryStore(tmp_path, namespace="telegram_42")
        provider = AsyncMock()
        provider.chat = AsyncMock(
            return_value=LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="save_memory",
                        arguments={
                            "history_entry": "[2026-01-01 12:00] User 42 asked about Python.",
                            "memory_update": "# Memory\nUser 42 likes Python.",
                        },
                    )
                ],
            )
        )

        session = MagicMock()
        session.messages = [
            {"role": "user", "content": f"msg{i}", "timestamp": "2026-01-01 00:00"}
            for i in range(60)
        ]
        session.last_consolidated = 0

        result = await store.consolidate(session, provider, "test-model", memory_window=50)

        assert result is True
        assert store.memory_file.parent == tmp_path / "memory" / "telegram_42"
        assert "User 42 likes Python" in store.memory_file.read_text()
        assert "User 42 asked about Python" in store.history_file.read_text()

        # Root memory directory must NOT have been created with data
        root_memory = tmp_path / "memory" / "MEMORY.md"
        assert not root_memory.exists()


# ---------------------------------------------------------------------------
# ContextBuilder per-session memory integration
# ---------------------------------------------------------------------------

class TestContextBuilderPerSessionMemory:
    def test_system_prompt_without_session_key_uses_root(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        builder = ContextBuilder(workspace)
        prompt = builder.build_system_prompt()
        mem_root = str((workspace / "memory").resolve())
        assert mem_root in prompt

    def test_system_prompt_with_session_key_uses_namespace(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        builder = ContextBuilder(workspace)
        prompt = builder.build_system_prompt(session_key="telegram:999")
        ns_dir = str((workspace / "memory" / "telegram_999").resolve())
        assert ns_dir in prompt
        # The global root path must NOT appear as the memory path
        root_mem = str((workspace / "memory").resolve()) + "/MEMORY.md"
        assert root_mem not in prompt

    def test_two_users_get_different_memory_paths(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()
        builder = ContextBuilder(workspace)

        prompt_alice = builder.build_system_prompt(session_key="telegram:111")
        prompt_bob = builder.build_system_prompt(session_key="telegram:222")

        assert "telegram_111" in prompt_alice
        assert "telegram_222" not in prompt_alice
        assert "telegram_222" in prompt_bob
        assert "telegram_111" not in prompt_bob

    def test_per_user_memory_content_loaded_into_prompt(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()

        # Pre-seed Alice's memory
        alice_store = MemoryStore(workspace, namespace="telegram_111")
        alice_store.write_long_term("# Alice Memory\nAlice's birthday is in July.")

        builder = ContextBuilder(workspace)

        prompt_alice = builder.build_system_prompt(session_key="telegram:111")
        prompt_bob = builder.build_system_prompt(session_key="telegram:222")

        assert "Alice's birthday is in July" in prompt_alice
        assert "Alice's birthday is in July" not in prompt_bob

    def test_build_messages_passes_session_key(self, tmp_path: Path) -> None:
        workspace = tmp_path / "ws"
        workspace.mkdir()

        alice_store = MemoryStore(workspace, namespace="telegram_111")
        alice_store.write_long_term("# Facts\nAlice uses vim.")

        builder = ContextBuilder(workspace)
        messages = builder.build_messages(
            history=[],
            current_message="Hello",
            channel="telegram",
            chat_id="111",
            session_key="telegram:111",
        )

        system_content = messages[0]["content"]
        assert "Alice uses vim" in system_content
        assert "telegram_111" in system_content
