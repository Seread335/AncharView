from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ancharview.audit import write_audit_event
from ancharview.server import ActionApproval, _confirmed_action


class FakeConsentContext:
    def __init__(self, action: str, approved: bool = False) -> None:
        self.action = action
        self.approved = approved
        self.message = ""

    async def elicit(self, message: str, schema: type[ActionApproval]) -> SimpleNamespace:
        self.message = message
        return SimpleNamespace(action=self.action, data=schema(approved=self.approved) if self.action == "accept" else None)


class ActionConsentTests(unittest.IsolatedAsyncioTestCase):
    async def test_approved_action_is_audited_without_logging_result_or_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "audit.jsonl"
            secret_text = "private text must not appear in the audit"
            context = FakeConsentContext("accept", approved=True)

            with patch.dict(os.environ, {"ANCHARVIEW_AUDIT_PATH": str(audit_path)}):
                result = await _confirmed_action(context, "set_text", "e1", 'Edit named "recipient"', lambda: secret_text)
                audit_contents = audit_path.read_text(encoding="utf-8")
                records = [json.loads(line) for line in audit_contents.splitlines()]

        self.assertEqual(result, secret_text)
        self.assertIn('Edit named "recipient"', context.message)
        self.assertNotIn(secret_text, context.message)
        self.assertEqual([record["status"] for record in records], ["pending", "approved", "started", "succeeded"])
        self.assertNotIn(secret_text, audit_contents)

    async def test_declined_action_never_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            context = FakeConsentContext("decline")
            action_ran = False

            def operation() -> str:
                nonlocal action_ran
                action_ran = True
                return "done"

            with patch.dict(os.environ, {"ANCHARVIEW_AUDIT_PATH": str(Path(directory) / "audit.jsonl")}):
                with self.assertRaisesRegex(PermissionError, "not approved"):
                    await _confirmed_action(context, "click", "e2", "Button named \"Delete\"", operation)

        self.assertFalse(action_ran)

    async def test_client_without_consent_support_fails_closed(self) -> None:
        class UnsupportedContext:
            async def elicit(self, **kwargs: object) -> None:
                raise NotImplementedError

        with tempfile.TemporaryDirectory() as directory:
            action_ran = False

            def operation() -> str:
                nonlocal action_ran
                action_ran = True
                return "done"

            with patch.dict(os.environ, {"ANCHARVIEW_AUDIT_PATH": str(Path(directory) / "audit.jsonl")}):
                with self.assertRaisesRegex(PermissionError, "could not complete a consent request"):
                    await _confirmed_action(UnsupportedContext(), "click", "e3", "Button named \"Delete\"", operation)

        self.assertFalse(action_ran)


class AuditLogTests(unittest.TestCase):
    def test_audit_record_contains_only_allowlisted_action_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            audit_path = Path(directory) / "nested" / "audit.jsonl"
            with patch.dict(os.environ, {"ANCHARVIEW_AUDIT_PATH": str(audit_path)}):
                write_audit_event("action", "click", "e4", "succeeded")
            record = json.loads(audit_path.read_text(encoding="utf-8"))

        self.assertEqual(record["action"], "click")
        self.assertEqual(record["element_id"], "e4")
        self.assertEqual(record["status"], "succeeded")
        self.assertNotIn("text", record)
        self.assertNotIn("window_title", record)


if __name__ == "__main__":
    unittest.main()