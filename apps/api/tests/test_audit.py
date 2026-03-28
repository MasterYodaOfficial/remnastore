import unittest

from app.core.audit import log_audit_event


class AuditLoggingTests(unittest.TestCase):
    def test_log_audit_event_renames_reserved_logrecord_fields(self) -> None:
        with self.assertLogs("app.audit", level="INFO") as captured:
            log_audit_event(
                "referral.claim",
                outcome="success",
                category="business",
                created=True,
                message="reserved message payload",
                account_id="account-1",
            )

        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertEqual(getattr(record, "audit_created"), True)
        self.assertEqual(getattr(record, "audit_message"), "reserved message payload")
        self.assertEqual(getattr(record, "account_id"), "account-1")
        self.assertIn("created=True", captured.output[0])
        self.assertIn('message="reserved message payload"', captured.output[0])
