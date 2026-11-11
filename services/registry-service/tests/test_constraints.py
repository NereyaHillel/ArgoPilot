import pytest
from support import FARM_DEMO, plot_payload

import repository
from db import connect, write_transaction
from errors import ConflictProblem, ValidationProblem


@pytest.fixture
def conn(seeded_db):
    connection = connect(seeded_db)
    yield connection
    connection.close()


def plot_row(**overrides):
    return {"id": "11111111-1111-4111-8111-111111111111", **plot_payload(**overrides)}


# The route checks run first. These tests reach the database constraints directly,
# to confirm they still stop bad writes if a check is ever bypassed.


def test_database_rejects_duplicate_plot_name_and_rolls_back(conn):
    with pytest.raises(ConflictProblem):
        with write_transaction(conn):
            repository.insert_plot(conn, plot_row(name="North block", farm_id=FARM_DEMO))

    assert len(repository.list_plots(conn, None)) == 4


def test_database_rejects_plot_with_unknown_reference(conn):
    with pytest.raises(ValidationProblem):
        with write_transaction(conn):
            repository.insert_plot(conn, plot_row(crop_id="ghost"))


def test_database_refuses_to_delete_a_farm_with_plots(conn):
    with pytest.raises(ConflictProblem):
        with write_transaction(conn):
            repository.delete_farm(conn, FARM_DEMO)

    assert repository.get_farm(conn, FARM_DEMO) is not None
