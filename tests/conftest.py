import pytest

import app as lendease


class FakeDB:
    """Stands in for MySQL: records every SQL call and returns canned rows."""

    def __init__(self):
        self.queries = []
        self.executed = []
        self.query_result = []
        self.one_result = None

    def query(self, sql, params=None, one=False):
        self.queries.append((" ".join(sql.split()), list(params or [])))
        return self.one_result if one else self.query_result

    def execute(self, sql, params=None, lastrowid=False):
        self.executed.append((" ".join(sql.split()), list(params or [])))
        return 1


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(lendease, "query", fake.query)
    monkeypatch.setattr(lendease, "execute", fake.execute)
    return fake


@pytest.fixture
def client(fake_db, monkeypatch):
    monkeypatch.setitem(lendease.app.config, "TESTING", True)
    return lendease.app.test_client()


def login_session(client, user_id=7, is_admin=False):
    with client.session_transaction() as s:
        s["user_id"] = user_id
        s["user_name"] = "Test User"
        s["is_admin"] = is_admin
        s["csrf_token"] = "tok"


CSRF = {"X-CSRF-Token": "tok"}
