from . import database_stub as db


def test_execute_and_query_one() -> None:
    db.execute("DROP TABLE IF EXISTS stub_items")
    db.execute("CREATE TABLE stub_items (id INTEGER PRIMARY KEY, name TEXT)")
    db.execute("INSERT INTO stub_items (id, name) VALUES (:id, :name)", {"id": 1, "name": "sample"})

    row = db.query_one("SELECT id, name FROM stub_items WHERE id=:id", {"id": 1})

    assert row == {"id": 1, "name": "sample"}


def test_query_scalar() -> None:
    db.execute("DROP TABLE IF EXISTS stub_counts")
    db.execute("CREATE TABLE stub_counts (value INTEGER)")
    db.execute("INSERT INTO stub_counts (value) VALUES (2)")
    db.execute("INSERT INTO stub_counts (value) VALUES (3)")

    total = db.query_scalar("SELECT SUM(value) FROM stub_counts")

    assert total == 5
