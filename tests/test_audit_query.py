import csv
from datetime import UTC, datetime, timedelta
from io import StringIO
from uuid import uuid4

import pytest
from pydantic import ValidationError

from atep.audit.models import AuditRecord
from atep.audit.schemas import AuditSearch
from atep.audit.service import audit_records_csv


def test_audit_search_requires_timezone_and_ordered_window() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        AuditSearch(created_from=datetime(2026, 7, 15, 10, 0))

    end = datetime.now(UTC)
    with pytest.raises(ValidationError, match="created_from"):
        AuditSearch(created_from=end, created_to=end - timedelta(seconds=1))


def test_audit_search_strips_bounded_text_filters() -> None:
    search = AuditSearch(
        action="  identity.user.created ",
        resource_type=" user ",
        outcome=" success ",
    )
    assert search.action == "identity.user.created"
    assert search.resource_type == "user"
    assert search.outcome == "success"


def test_audit_csv_is_stable_and_spreadsheet_formula_safe() -> None:
    record = AuditRecord(
        id=uuid4(),
        actor_user_id=uuid4(),
        action="=unsafe-formula",
        resource_type="user",
        resource_id=uuid4(),
        outcome="success",
        correlation_id=uuid4(),
        details={"email": "engineer@example.com"},
        created_at=datetime(2026, 7, 15, 12, 0, tzinfo=UTC),
    )

    document = audit_records_csv([record])
    assert document.startswith("\ufeff")
    rows = list(csv.DictReader(StringIO(document.removeprefix("\ufeff"))))
    assert rows[0]["action"] == "'=unsafe-formula"
    assert rows[0]["details_json"] == '{"email":"engineer@example.com"}'
