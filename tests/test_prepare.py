"""Unit tests for persona, campaign, and instruction preparation."""

import copy
import math
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from ingest.sqlite import connect
from pipeline.prepare import (
    _remove_empty_keys,
    create_instructions,
    create_state,
    fetch_personas,
    prepare_campaign_info,
    prepare_question_info,
)
from prompts.system_prompt import SYSTEM_PROMPT
from tests.helpers import query, write_table

PEOPLE_COLUMNS = ["persona_id", "persona_summary", "age", "region"]
PEOPLE = [
    (1, "alpha", 30, "West"),
    (2, "beta", 50, "East"),
    (3, "gamma", 40, "West"),
    (4, "delta", 25, "South"),
    (5, "epsilon", 45, "West"),
]


def selected_columns(other: list[str] | None = None) -> dict[str, object]:
    """Return a column selection, using age and region unless other is given."""
    return {
        "id": "persona_id",
        "persona_column": "persona_summary",
        "other_columns": ["age", "region"] if other is None else other,
    }


def insert_campaign(db_path: Path, campaign_id: int, name: str) -> None:
    """Insert one saved campaign."""
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO campaigns (id, name, description, is_saved)
            VALUES (?, ?, 'Desc', 1)
            """,
            (campaign_id, name),
        )


def insert_question(db_path: Path, question_id: int, name: str) -> None:
    """Insert one saved question."""
    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO questions (
                id, question_name, question_type, instructions, criteria, is_saved
            )
            VALUES (?, ?, 'score', 'Old instructions', '["x"]', 1)
            """,
            (question_id, name),
        )


@pytest.fixture
def people_db(tmp_path: Path) -> Path:
    """Return a database loaded with the standard persona rows."""
    path = tmp_path / "people.db"
    write_table(path, "people", PEOPLE_COLUMNS, PEOPLE)
    return path


class TestFetchPersonas:
    """Tests for fetch_personas."""

    def test_returns_persona_text_and_attribute_rows(self, people_db: Path) -> None:
        """Persona text is separate from the attribute row used for results."""
        personas, rows = fetch_personas(people_db, "people", [], selected_columns())

        assert personas == {
            1: "alpha",
            2: "beta",
            3: "gamma",
            4: "delta",
            5: "epsilon",
        }
        assert rows[1] == {"persona_id": 1, "age": 30, "region": "West"}
        assert "persona_summary" not in rows[1]
        assert set(rows) == set(personas)

    def test_rows_keep_table_order(self, people_db: Path) -> None:
        """Both mappings follow the order returned by the query."""
        personas, rows = fetch_personas(people_db, "people", None, selected_columns())

        assert list(personas) == [1, 2, 3, 4, 5]
        assert list(rows) == [1, 2, 3, 4, 5]

    def test_limit_returns_the_first_rows(self, people_db: Path) -> None:
        """A limit keeps that many rows from the start of the query."""
        personas, rows = fetch_personas(
            people_db, "people", [], selected_columns(), limit=2
        )

        assert list(personas) == [1, 2]
        assert list(rows) == [1, 2]

    def test_limit_applies_after_filters(self, people_db: Path) -> None:
        """Filters run first, then the limit keeps the first matches."""
        personas, _ = fetch_personas(
            people_db,
            "people",
            [{"columns": "region", "type": "single_select", "values": "West"}],
            selected_columns(),
            limit=2,
        )

        assert list(personas) == [1, 3]

    def test_limit_zero_returns_no_rows(self, people_db: Path) -> None:
        """A limit of zero returns no personas."""
        personas, rows = fetch_personas(
            people_db, "people", [], selected_columns(), limit=0
        )

        assert personas == {}
        assert rows == {}

    @pytest.mark.parametrize("limit", [-1, True, 1.5])
    def test_limit_must_be_a_non_negative_integer(
        self, people_db: Path, limit: object
    ) -> None:
        """A negative or non-integer limit is rejected."""
        with pytest.raises(ValueError, match="limit must be a non-negative integer"):
            fetch_personas(
                people_db,
                "people",
                [],
                selected_columns(),
                limit=limit,  # type: ignore[arg-type]
            )

    def test_empty_table_returns_empty_mappings(self, tmp_path: Path) -> None:
        """A table with no rows produces two empty mappings."""
        db_path = tmp_path / "people.db"
        write_table(db_path, "people", PEOPLE_COLUMNS, [])

        personas, rows = fetch_personas(db_path, "people", [], selected_columns())

        assert personas == {}
        assert rows == {}

    def test_does_not_mutate_filters_or_column_selection(self, people_db: Path) -> None:
        """Inputs are only read."""
        filters = [
            {"columns": "region", "type": "multi_select", "values": ["West", "East"]}
        ]
        columns = selected_columns()
        original_filters = copy.deepcopy(filters)
        original_columns = copy.deepcopy(columns)

        fetch_personas(people_db, "people", filters, columns)

        assert filters == original_filters
        assert columns == original_columns

    def test_other_columns_can_repeat_the_persona_column(self, people_db: Path) -> None:
        """The persona text is still removed from the attribute row."""
        _, rows = fetch_personas(
            people_db,
            "people",
            [],
            selected_columns(["age", "age", "persona_summary"]),
        )

        assert rows[1] == {"persona_id": 1, "age": 30}

    def test_other_columns_can_be_empty(self, people_db: Path) -> None:
        """Only the persona id remains when no extra columns are requested."""
        _, rows = fetch_personas(people_db, "people", [], selected_columns([]))

        assert rows[1] == {"persona_id": 1}

    def test_quoted_table_and_column_names(self, tmp_path: Path) -> None:
        """Names with spaces are quoted in the select list."""
        db_path = tmp_path / "people.db"
        write_table(
            db_path,
            "persona data",
            ["persona_id", "home region", "summary"],
            [(1, "CA", "alpha")],
        )

        personas, rows = fetch_personas(
            db_path,
            "persona data",
            [],
            {
                "id": "persona_id",
                "persona_column": "summary",
                "other_columns": ["home region"],
            },
        )

        assert personas == {1: "alpha"}
        assert rows[1] == {"persona_id": 1, "home region": "CA"}

    def test_filter_on_a_spaced_column_is_not_quoted(self, tmp_path: Path) -> None:
        """Filter column names are inserted into the SQL text."""
        db_path = tmp_path / "people.db"
        write_table(
            db_path,
            "persona data",
            ["persona_id", "home region", "summary"],
            [(1, "CA", "alpha")],
        )

        with pytest.raises(pd.errors.DatabaseError):
            fetch_personas(
                db_path,
                "persona data",
                [{"columns": "home region", "type": "single_select", "values": "CA"}],
                {
                    "id": "persona_id",
                    "persona_column": "summary",
                    "other_columns": ["home region"],
                },
            )

    def test_null_attributes_become_nan_or_none(self, tmp_path: Path) -> None:
        """SQL NULL stays missing in the attribute row."""
        db_path = tmp_path / "people.db"
        write_table(
            db_path,
            "people",
            PEOPLE_COLUMNS,
            [(1, "alpha", 30, "West"), (2, "beta", None, None)],
        )

        personas, rows = fetch_personas(db_path, "people", [], selected_columns())

        assert personas == {1: "alpha", 2: "beta"}
        assert rows[1]["age"] == 30.0
        assert rows[1]["region"] == "West"
        assert math.isnan(rows[2]["age"])
        assert rows[2]["region"] is None

    def test_duplicate_persona_ids_keep_the_last_row(self, tmp_path: Path) -> None:
        """A repeated id overwrites the earlier row."""
        db_path = tmp_path / "people.db"
        write_table(
            db_path,
            "people",
            PEOPLE_COLUMNS,
            [
                (1, "first", 20, "West"),
                (1, "second", 21, "East"),
                (2, "third", 22, "South"),
            ],
        )

        personas, rows = fetch_personas(db_path, "people", [], selected_columns())

        assert personas == {1: "second", 2: "third"}
        assert rows[1] == {"persona_id": 1, "age": 21, "region": "East"}

    def test_filter_values_are_bound_parameters(self, tmp_path: Path) -> None:
        """Quotes in a filter value do not change the query structure."""
        db_path = tmp_path / "people.db"
        write_table(
            db_path,
            "people",
            PEOPLE_COLUMNS,
            [(1, "O'Brien", 30, "O'West"), (2, "beta", 40, "West")],
        )
        columns = selected_columns()

        matched, _ = fetch_personas(
            db_path,
            "people",
            [{"columns": "region", "type": "single_select", "values": "O'West"}],
            columns,
        )
        injected, _ = fetch_personas(
            db_path,
            "people",
            [
                {
                    "columns": "region",
                    "type": "single_select",
                    "values": "West' OR '1'='1",
                }
            ],
            columns,
        )

        assert list(matched) == [1]
        assert injected == {}

    def test_zero_and_empty_filter_values_are_used(self, tmp_path: Path) -> None:
        """A zero or blank value is a real filter, not a missing one."""
        db_path = tmp_path / "people.db"
        write_table(
            db_path,
            "people",
            PEOPLE_COLUMNS,
            [(1, "zero", 0, ""), (2, "one", 1, "East")],
        )
        columns = selected_columns()

        by_age, _ = fetch_personas(
            db_path,
            "people",
            [{"columns": "age", "type": "single_select", "values": 0}],
            columns,
        )
        by_slider, _ = fetch_personas(
            db_path,
            "people",
            [{"columns": "age", "type": "slider", "values": [0, 0]}],
            columns,
        )
        by_region, _ = fetch_personas(
            db_path,
            "people",
            [{"columns": "region", "type": "multi_select", "values": [""]}],
            columns,
        )

        assert list(by_age) == [1]
        assert list(by_slider) == [1]
        assert list(by_region) == [1]

    @pytest.mark.parametrize(
        ("filters", "expected"),
        [
            pytest.param([], [1, 2, 3, 4, 5], id="empty-list"),
            pytest.param(None, [1, 2, 3, 4, 5], id="none"),
            pytest.param("", [1, 2, 3, 4, 5], id="empty-string"),
            pytest.param(
                [{"columns": "region", "type": "single_select", "values": "East"}],
                [2],
                id="single-scalar",
            ),
            pytest.param(
                [{"columns": "region", "type": "single_select", "values": "West"}],
                [1, 3, 5],
                id="single-west",
            ),
            pytest.param(
                [{"columns": "region", "type": "single_select", "values": "west"}],
                [],
                id="single-case-sensitive",
            ),
            pytest.param(
                [
                    {
                        "columns": "region",
                        "type": "single_select",
                        "values": ["East", "West"],
                    }
                ],
                [2],
                id="single-list-uses-first-value",
            ),
            pytest.param(
                [{"columns": "region", "type": "single_select", "values": ["West"]}],
                [1, 3, 5],
                id="single-list-of-one",
            ),
            pytest.param(
                [{"columns": "age", "type": "single_select", "values": 30}],
                [1],
                id="single-number",
            ),
            pytest.param(
                [{"columns": "age", "type": "single_select", "values": [50, 30]}],
                [2],
                id="single-number-list-uses-first-value",
            ),
            pytest.param(
                [{"columns": "region", "type": "multi_select", "values": ["West"]}],
                [1, 3, 5],
                id="multi-one",
            ),
            pytest.param(
                [
                    {
                        "columns": "region",
                        "type": "multi_select",
                        "values": ("West", "South"),
                    }
                ],
                [1, 3, 4, 5],
                id="multi-tuple",
            ),
            pytest.param(
                [{"columns": "region", "type": "multi_select", "values": ["North"]}],
                [],
                id="multi-no-match",
            ),
            pytest.param(
                [{"columns": "region", "type": "multi_select", "values": []}],
                [],
                id="multi-empty",
            ),
            pytest.param(
                [{"columns": "region", "type": "multi_select", "values": "West"}],
                [],
                id="multi-string-iterates-characters",
            ),
            pytest.param(
                [{"columns": "age", "type": "slider", "values": [25, 45]}],
                [1, 3, 4, 5],
                id="slider-inclusive",
            ),
            pytest.param(
                [{"columns": "age", "type": "slider", "values": [25, 25]}],
                [4],
                id="slider-single-point",
            ),
            pytest.param(
                [{"columns": "age", "type": "slider", "values": [45, 45]}],
                [5],
                id="slider-upper-bound",
            ),
            pytest.param(
                [{"columns": "age", "type": "slider", "values": [45, 25]}],
                [],
                id="slider-reversed",
            ),
            pytest.param(
                [{"columns": "age", "type": "slider", "values": (30, 40)}],
                [1, 3],
                id="slider-tuple",
            ),
            pytest.param(
                [{"columns": "region", "type": "range", "values": ["East"]}],
                [1, 2, 3, 4, 5],
                id="unknown-type",
            ),
            pytest.param(
                [{"columns": "region", "type": None, "values": ["East"]}],
                [1, 2, 3, 4, 5],
                id="none-type",
            ),
            pytest.param(
                [{"columns": "region", "type": " single_select", "values": "East"}],
                [1, 2, 3, 4, 5],
                id="type-must-match-exactly",
            ),
            pytest.param(
                [
                    {
                        "columns": "region",
                        "type": "single_select",
                        "values": "East",
                        "label": "ignored",
                    }
                ],
                [2],
                id="extra-filter-key",
            ),
            pytest.param(
                [
                    {"columns": "region", "type": "range", "values": ["East"]},
                    {"columns": "region", "type": "single_select", "values": "East"},
                ],
                [2],
                id="unknown-plus-single",
            ),
            pytest.param(
                [
                    {"columns": "age", "type": "slider", "values": [30, 40]},
                    {"columns": "region", "type": "multi_select", "values": ["West"]},
                ],
                [1, 3],
                id="slider-and-multi",
            ),
            pytest.param(
                [
                    {"columns": "age", "type": "slider", "values": [25, 45]},
                    {"columns": "region", "type": "single_select", "values": "South"},
                ],
                [4],
                id="slider-and-single",
            ),
            pytest.param(
                [
                    {"columns": "region", "type": "multi_select", "values": ["West"]},
                    {"columns": "region", "type": "multi_select", "values": ["East"]},
                ],
                [],
                id="contradictory-multi",
            ),
            pytest.param(
                [
                    {"columns": "age", "type": "slider", "values": [40, 50]},
                    {
                        "columns": "region",
                        "type": "multi_select",
                        "values": ["West", "East"],
                    },
                ],
                [2, 3, 5],
                id="two-filters",
            ),
            pytest.param(
                [
                    {"columns": "region", "type": "single_select", "values": "West"},
                    {"columns": "age", "type": "slider", "values": [50, 50]},
                ],
                [],
                id="contradictory-single-and-slider",
            ),
        ],
    )
    def test_filters(
        self,
        people_db: Path,
        filters: object,
        expected: list[int],
    ) -> None:
        """Each filter type, and combinations of them, keep the matching rows."""
        personas, rows = fetch_personas(
            people_db,
            "people",
            filters,  # type: ignore[arg-type]
            selected_columns(),
        )

        assert list(personas) == expected
        assert list(rows) == expected

    def test_missing_table_raises(self, people_db: Path) -> None:
        """A name that is not in the database is rejected."""
        with pytest.raises(ValueError, match="Table missing does not exist"):
            fetch_personas(people_db, "missing", [], selected_columns())

    def test_missing_database_file_raises(self, tmp_path: Path) -> None:
        """A path that has no file is treated as a missing table."""
        with pytest.raises(ValueError, match="Table people does not exist"):
            fetch_personas(tmp_path / "missing.db", "people", [], selected_columns())

    def test_directory_path_raises(self, tmp_path: Path) -> None:
        """A directory is not a database file."""
        with pytest.raises(ValueError, match="Table people does not exist"):
            fetch_personas(tmp_path, "people", [], selected_columns())

    def test_string_path_is_not_accepted(self, people_db: Path) -> None:
        """table_exists requires a path object."""
        with pytest.raises(AttributeError, match="is_file"):
            fetch_personas(str(people_db), "people", [], selected_columns())

    @pytest.mark.parametrize(
        "columns",
        [
            {},
            {"id": "persona_id"},
            {"persona_column": "persona_summary"},
            {"id": 1, "persona_column": "persona_summary", "other_columns": []},
            {"id": "persona_id", "persona_column": None, "other_columns": []},
            {"id": None, "persona_column": None, "other_columns": []},
            {
                "id": b"persona_id",
                "persona_column": "persona_summary",
                "other_columns": [],
            },
        ],
    )
    def test_selected_columns_require_string_names(
        self,
        people_db: Path,
        columns: dict[str, object],
    ) -> None:
        """id and persona_column both have to be strings."""
        with pytest.raises(
            TypeError, match="selected_columns needs id and persona_column"
        ):
            fetch_personas(people_db, "people", [], columns)

    def test_missing_other_columns_raises(self, people_db: Path) -> None:
        """other_columns is unpacked and cannot be missing."""
        with pytest.raises(TypeError, match="iterable"):
            fetch_personas(
                people_db,
                "people",
                [],
                {"id": "persona_id", "persona_column": "persona_summary"},
            )

    def test_string_other_columns_are_read_as_character_literals(
        self, people_db: Path
    ) -> None:
        """A string is unpacked into characters, and unknown quoted names are text literals."""
        _, rows = fetch_personas(
            people_db,
            "people",
            [],
            {
                "id": "persona_id",
                "persona_column": "persona_summary",
                "other_columns": "age",
            },
        )

        assert rows[1] == {"persona_id": 1, '"a"': "a", '"g"': "g", '"e"': "e"}

    def test_missing_quoted_column_is_a_string_literal(self, people_db: Path) -> None:
        """A quoted name that is not a column comes back as that text."""
        _, rows = fetch_personas(people_db, "people", [], selected_columns(["income"]))

        assert rows[1] == {"persona_id": 1, '"income"': "income"}

    def test_missing_filter_column_raises(self, people_db: Path) -> None:
        """A filter column that is not in the table fails the query."""
        with pytest.raises(pd.errors.DatabaseError):
            fetch_personas(
                people_db,
                "people",
                [{"columns": "income", "type": "single_select", "values": 1}],
                selected_columns(),
            )

    def test_empty_single_select_raises(self, people_db: Path) -> None:
        """A single-select list must contain the value to bind."""
        with pytest.raises(IndexError):
            fetch_personas(
                people_db,
                "people",
                [{"columns": "region", "type": "single_select", "values": []}],
                selected_columns(),
            )

    def test_slider_with_one_value_raises(self, people_db: Path) -> None:
        """A slider binds both ends of the range."""
        with pytest.raises(pd.errors.DatabaseError):
            fetch_personas(
                people_db,
                "people",
                [{"columns": "age", "type": "slider", "values": [30]}],
                selected_columns(),
            )

    def test_json_filter_string_is_not_parsed(self, people_db: Path) -> None:
        """A JSON string is iterated as text instead of being loaded."""
        filters = '[{"columns": "region", "type": "single_select", "values": "West"}]'

        with pytest.raises(TypeError):
            fetch_personas(people_db, "people", filters, selected_columns())

    @pytest.mark.parametrize("missing", ["columns", "type", "values"])
    def test_filter_requires_its_fields(self, people_db: Path, missing: str) -> None:
        """Each filter needs a column, a type, and values."""
        item = {"columns": "region", "type": "single_select", "values": "West"}
        del item[missing]

        with pytest.raises(KeyError):
            fetch_personas(people_db, "people", [item], selected_columns())


class TestPrepareCampaignInfo:
    """Tests for prepare_campaign_info."""

    def test_empty_input_has_the_campaign_columns(self, simulation_db: Path) -> None:
        """No campaigns still returns a frame with the campaign columns."""
        with connect(simulation_db) as conn:
            frame = prepare_campaign_info(conn, [])

        assert frame.empty
        assert list(frame.columns) == ["id", "name", "description", "is_saved"]

    def test_new_campaigns_start_at_one(self, simulation_db: Path) -> None:
        """The first unsaved campaign gets id 1."""
        campaigns = [
            {"name": "Launch", "description": "First", "is_saved": 0},
            {"name": "Follow up", "description": "Second", "is_saved": 0},
        ]

        with connect(simulation_db) as conn:
            frame = prepare_campaign_info(conn, campaigns)

        assert frame.to_dict(orient="records") == [
            {"id": 1, "name": "Launch", "description": "First", "is_saved": 0},
            {"id": 2, "name": "Follow up", "description": "Second", "is_saved": 0},
        ]

    def test_mixed_campaigns_keep_saved_ids_and_continue_after_max(
        self,
        simulation_db: Path,
    ) -> None:
        """Saved ids are copied. Unsaved ids start at one past the current maximum."""
        insert_campaign(simulation_db, 1, "Kept one")
        insert_campaign(simulation_db, 5, "Kept five")
        campaigns = [
            {"name": "A", "description": "a", "is_saved": 0},
            {"id": 5, "name": "B", "description": "b", "is_saved": 1},
            {"name": "C", "description": "c", "is_saved": 0},
            {"id": 1, "name": "D", "description": "d", "is_saved": 1},
        ]
        original = copy.deepcopy(campaigns)

        with connect(simulation_db) as conn:
            frame = prepare_campaign_info(conn, campaigns)

        assert frame.to_dict(orient="records") == [
            {"id": 6, "name": "A", "description": "a", "is_saved": 0},
            {"id": 5, "name": "B", "description": "b", "is_saved": 1},
            {"id": 7, "name": "C", "description": "c", "is_saved": 0},
            {"id": 1, "name": "D", "description": "d", "is_saved": 1},
        ]
        assert campaigns == original
        assert query(simulation_db, "SELECT id, name FROM campaigns ORDER BY id") == [
            (1, "Kept one"),
            (5, "Kept five"),
        ]

    def test_bool_saved_flag_uses_integer_comparison(self, simulation_db: Path) -> None:
        """True matches a saved campaign because True == 1. False gets a new id."""
        campaigns = [
            {"name": "New", "description": "n", "is_saved": False},
            {"id": 8, "name": "Old", "description": "o", "is_saved": True},
        ]

        with connect(simulation_db) as conn:
            frame = prepare_campaign_info(conn, campaigns)

        assert frame.to_dict(orient="records") == [
            {"id": 1, "name": "New", "description": "n", "is_saved": False},
            {"id": 8, "name": "Old", "description": "o", "is_saved": True},
        ]

    def test_other_saved_values_get_new_ids(self, simulation_db: Path) -> None:
        """Only the value 1 keeps an existing id."""
        campaigns = [{"name": "Other", "description": "o", "is_saved": 2}]

        with connect(simulation_db) as conn:
            frame = prepare_campaign_info(conn, campaigns)

        assert frame.to_dict(orient="records") == [
            {"id": 1, "name": "Other", "description": "o", "is_saved": 2}
        ]

    def test_blank_name_and_description_are_preserved(
        self, simulation_db: Path
    ) -> None:
        """Empty text is stored as given."""
        campaigns = [{"name": "", "description": None, "is_saved": 0}]

        with connect(simulation_db) as conn:
            frame = prepare_campaign_info(conn, campaigns)

        assert frame.to_dict(orient="records") == [
            {"id": 1, "name": "", "description": None, "is_saved": 0}
        ]

    def test_saved_campaign_without_an_id_raises(self, simulation_db: Path) -> None:
        """A saved campaign has to bring its own id."""
        campaigns = [{"name": "Old", "description": "o", "is_saved": 1}]

        with connect(simulation_db) as conn, pytest.raises(KeyError, match="id"):
            prepare_campaign_info(conn, campaigns)

    @pytest.mark.parametrize("missing", ["name", "description", "is_saved"])
    def test_required_campaign_fields(self, simulation_db: Path, missing: str) -> None:
        """Name, description, and the saved flag are read for every campaign."""
        campaign = {"name": "Launch", "description": "First", "is_saved": 0}
        del campaign[missing]

        with connect(simulation_db) as conn, pytest.raises(KeyError):
            prepare_campaign_info(conn, [campaign])

    def test_missing_campaigns_table_raises(self, tmp_path: Path) -> None:
        """The next id is read from the campaigns table."""
        db_path = tmp_path / "empty.db"
        with (
            connect(db_path) as conn,
            pytest.raises(sqlite3.OperationalError, match="campaigns"),
        ):
            prepare_campaign_info(conn, [])


class TestPrepareQuestionInfo:
    """Tests for prepare_question_info."""

    def test_empty_campaigns_have_the_question_columns(
        self, simulation_db: Path
    ) -> None:
        """No questions still returns a frame with the question columns."""
        with connect(simulation_db) as conn:
            frame = prepare_question_info(conn, [])

        assert frame.empty
        assert list(frame.columns) == [
            "id",
            "campaign_id",
            "question_name",
            "question_type",
            "instructions",
            "criteria",
            "is_saved",
        ]

    def test_campaigns_with_no_questions_are_skipped(self, simulation_db: Path) -> None:
        """A campaign that has an empty question list adds no rows."""
        campaigns = [{"id": 1, "questions": []}, {"id": 2, "questions": []}]

        with connect(simulation_db) as conn:
            frame = prepare_question_info(conn, campaigns)

        assert frame.empty

    def test_ids_follow_saved_flag_and_campaign_order(
        self, simulation_db: Path
    ) -> None:
        """Unsaved questions get new ids. The campaign id comes from the campaign."""
        insert_question(simulation_db, 10, "old")
        campaigns = [
            {
                "id": 3,
                "questions": [
                    {
                        "question_name": "a",
                        "question_type": "noul",
                        "instructions": "ia",
                        "criteria": {"true": "yes"},
                        "is_saved": 0,
                    },
                    {
                        "id": 4,
                        "question_name": "b",
                        "question_type": "choice",
                        "instructions": "ib",
                        "criteria": {"A": "first"},
                        "is_saved": 1,
                    },
                ],
            },
            {
                "id": 8,
                "questions": [
                    {
                        "question_name": "c",
                        "question_type": "score",
                        "instructions": "ic",
                        "criteria": ["low"],
                        "is_saved": False,
                    }
                ],
            },
        ]
        original = copy.deepcopy(campaigns)

        with connect(simulation_db) as conn:
            frame = prepare_question_info(conn, campaigns)

        assert frame.to_dict(orient="records") == [
            {
                "id": 11,
                "campaign_id": 3,
                "question_name": "a",
                "question_type": "noul",
                "instructions": "ia",
                "criteria": {"true": "yes"},
                "is_saved": 0,
            },
            {
                "id": 4,
                "campaign_id": 3,
                "question_name": "b",
                "question_type": "choice",
                "instructions": "ib",
                "criteria": {"A": "first"},
                "is_saved": 1,
            },
            {
                "id": 12,
                "campaign_id": 8,
                "question_name": "c",
                "question_type": "score",
                "instructions": "ic",
                "criteria": ["low"],
                "is_saved": False,
            },
        ]
        assert campaigns == original
        assert query(simulation_db, "SELECT id, question_name FROM questions") == [
            (10, "old")
        ]

    def test_saved_question_without_an_id_raises(self, simulation_db: Path) -> None:
        """A saved question has to bring its own id."""
        campaigns = [
            {
                "id": 1,
                "questions": [
                    {
                        "question_name": "a",
                        "question_type": "score",
                        "instructions": "i",
                        "criteria": ["x"],
                        "is_saved": 1,
                    }
                ],
            }
        ]

        with connect(simulation_db) as conn, pytest.raises(KeyError, match="id"):
            prepare_question_info(conn, campaigns)

    def test_campaign_without_an_id_raises(self, simulation_db: Path) -> None:
        """Each question row copies the campaign id already on the campaign."""
        campaigns = [
            {
                "questions": [
                    {
                        "question_name": "a",
                        "question_type": "score",
                        "instructions": "i",
                        "criteria": ["x"],
                        "is_saved": 0,
                    }
                ]
            }
        ]

        with connect(simulation_db) as conn, pytest.raises(KeyError, match="id"):
            prepare_question_info(conn, campaigns)

    def test_campaign_without_questions_raises(self, simulation_db: Path) -> None:
        """Every campaign needs a question list."""
        with connect(simulation_db) as conn, pytest.raises(KeyError, match="questions"):
            prepare_question_info(conn, [{"id": 1}])

    @pytest.mark.parametrize(
        "missing",
        ["question_name", "question_type", "instructions", "criteria", "is_saved"],
    )
    def test_required_question_fields(self, simulation_db: Path, missing: str) -> None:
        """Each question field is copied onto the frame."""
        question = {
            "question_name": "a",
            "question_type": "score",
            "instructions": "i",
            "criteria": ["x"],
            "is_saved": 0,
        }
        del question[missing]

        with connect(simulation_db) as conn, pytest.raises(KeyError):
            prepare_question_info(conn, [{"id": 1, "questions": [question]}])

    def test_missing_questions_table_raises(self, tmp_path: Path) -> None:
        """The next id is read from the questions table."""
        db_path = tmp_path / "empty.db"
        with (
            connect(db_path) as conn,
            pytest.raises(sqlite3.OperationalError, match="questions"),
        ):
            prepare_question_info(conn, [])


class TestCreateState:
    """Tests for create_state."""

    def test_returns_persona_and_campaign(self) -> None:
        """The state is the persona text and the campaign text."""
        assert create_state("alpha", "Ad A's launch") == {
            "persona": "alpha",
            "campaign": "Ad A's launch",
        }

    def test_keeps_empty_and_unicode_text(self) -> None:
        """Text is not trimmed or rewritten."""
        assert create_state("", "") == {"persona": "", "campaign": ""}
        assert create_state("José", "café") == {"persona": "José", "campaign": "café"}

    def test_returns_a_new_dict(self) -> None:
        """Callers can change one state without changing another."""
        first = create_state("alpha", "launch")
        second = create_state("alpha", "launch")

        first["persona"] = "changed"

        assert second == {"persona": "alpha", "campaign": "launch"}


class TestRemoveEmptyKeys:
    """Tests for _remove_empty_keys."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ({}, {}),
            ({"a": "x"}, {"a": "x"}),
            ({"a": ""}, {}),
            ({"a": None}, {}),
            ({"a": {}}, {}),
            ({"a": []}, {}),
            ({"a": 0}, {"a": 0}),
            ({"a": 0.0}, {"a": 0.0}),
            ({"a": False}, {"a": False}),
            ({"a": True}, {"a": True}),
            ({"a": " "}, {"a": " "}),
            ({"a": "\n"}, {"a": "\n"}),
            ({"a": "0"}, {"a": "0"}),
            ({"": "x"}, {"": "x"}),
            ({"": ""}, {}),
            ({1: "x"}, {1: "x"}),
            ({1: ""}, {}),
            ({"a": {"b": ""}}, {}),
            ({"a": {"b": "x", "c": None}}, {"a": {"b": "x"}}),
            ({"a": {"b": {"c": ""}}}, {}),
            ({"a": {"b": {"c": "x", "d": []}}}, {"a": {"b": {"c": "x"}}}),
            ({"a": {"b": {"c": ""}, "d": "y"}}, {"a": {"d": "y"}}),
            ({"a": [None, "", {}]}, {"a": [None, "", {}]}),
            ({"a": {"b": "x"}, "c": "", "d": []}, {"a": {"b": "x"}}),
        ],
    )
    def test_drops_empty_values(
        self, value: dict[object, object], expected: dict[object, object]
    ) -> None:
        """None, blank text, empty dicts, and empty lists are removed at every level."""
        assert _remove_empty_keys(value) == expected

    def test_does_not_mutate_nested_input(self) -> None:
        """Cleaning builds a new mapping and leaves the input alone."""
        nested = {"b": ""}
        value = {"a": nested, "c": "x"}

        assert _remove_empty_keys(value) == {"c": "x"}
        assert value == {"a": {"b": ""}, "c": "x"}
        assert nested == {"b": ""}

    def test_keeps_the_same_list_object(self) -> None:
        """Lists are not copied or filtered item by item."""
        items = [None, ""]
        cleaned = _remove_empty_keys({"a": items})

        assert cleaned["a"] is items


class TestCreateInstructions:
    """Tests for create_instructions."""

    def test_empty_questions(self) -> None:
        """No questions produce no instructions."""
        assert create_instructions(1, []) == []

    def test_builds_the_instruction_payload(self) -> None:
        """Each question becomes one instruction, in the same order."""
        questions = [
            {
                "id": 4,
                "question_name": "like",
                "question_type": "noul",
                "instructions": "Do you like it?",
                "focus": "tone",
                "criteria": {"true": "yes", "false": "no"},
                "notes": "ignored",
            },
            {
                "id": 5,
                "question_name": "rate",
                "question_type": "score",
                "instructions": "Rate it",
                "criteria": ["low", ""],
            },
        ]
        original = copy.deepcopy(questions)

        prepared = create_instructions(2, questions)

        assert prepared == [
            {
                "id": 4,
                "question_name": "like",
                "question_type": "noul",
                "question_column_name": "camp_2_ques4",
                "instructions": {
                    "question": f"{SYSTEM_PROMPT}\nDo you like it?",
                    "focus": "tone",
                    "inspect": "`campaign`",
                },
                "criteria": {"true": "yes", "false": "no"},
            },
            {
                "id": 5,
                "question_name": "rate",
                "question_type": "score",
                "question_column_name": "camp_2_ques5",
                "instructions": {
                    "question": f"{SYSTEM_PROMPT}\nRate it",
                    "inspect": "`campaign`",
                },
                "criteria": ["low", ""],
            },
        ]
        assert questions == original

    def test_column_name_has_no_extra_separator(self) -> None:
        """The column name is camp_<campaign>_ques<question>."""
        prepared = create_instructions(
            12,
            [
                {
                    "id": 34,
                    "question_name": "q",
                    "question_type": "score",
                    "instructions": "i",
                    "criteria": ["a"],
                }
            ],
        )

        assert prepared[0]["question_column_name"] == "camp_12_ques34"

    @pytest.mark.parametrize("focus", ["missing", None, ""])
    def test_blank_focus_is_omitted(self, focus: object) -> None:
        """Focus is included only when it has text."""
        question = {
            "id": 1,
            "question_name": "like",
            "question_type": "noul",
            "instructions": "Do you like it?",
            "criteria": {"true": "yes", "false": "no"},
        }
        if focus != "missing":
            question["focus"] = focus

        prepared = create_instructions(1, [question])

        assert "focus" not in prepared[0]["instructions"]

    @pytest.mark.parametrize(
        ("criteria", "expected"),
        [
            ({}, None),
            ([], None),
            (None, None),
            ("", None),
            ({"true": "yes", "false": ""}, {"true": "yes"}),
            (["low", ""], ["low", ""]),
            (
                {"true": {"text": "yes", "note": ""}, "false": "no"},
                {"true": {"text": "yes"}, "false": "no"},
            ),
        ],
    )
    def test_criteria_are_cleaned(self, criteria: object, expected: object) -> None:
        """Empty criteria are dropped. Nested empty values inside a dict are dropped too."""
        question = {
            "id": 1,
            "question_name": "like",
            "question_type": "noul",
            "instructions": "Do you like it?",
            "criteria": criteria,
        }

        prepared = create_instructions(1, [question])

        if expected is None:
            assert "criteria" not in prepared[0]
        else:
            assert prepared[0]["criteria"] == expected

    def test_empty_scalar_fields_are_dropped(self) -> None:
        """An empty name or type is removed. An id of zero stays."""
        blank = {
            "id": None,
            "question_name": "",
            "question_type": "",
            "instructions": "Answer",
            "criteria": {"a": "b"},
        }
        zero = {
            "id": 0,
            "question_name": "q",
            "question_type": "score",
            "instructions": "Answer",
            "criteria": ["a"],
        }

        prepared = create_instructions(1, [blank, zero])

        assert "id" not in prepared[0]
        assert "question_name" not in prepared[0]
        assert "question_type" not in prepared[0]
        assert prepared[0]["question_column_name"] == "camp_1_quesNone"
        assert prepared[1]["id"] == 0
        assert prepared[1]["question_column_name"] == "camp_1_ques0"

    def test_none_instructions_are_stringified(self) -> None:
        """A missing instruction is still placed after the system prompt."""
        question = {
            "id": 1,
            "question_name": "q",
            "question_type": "score",
            "instructions": None,
            "criteria": ["a"],
        }

        prepared = create_instructions(1, [question])

        assert prepared[0]["instructions"]["question"] == f"{SYSTEM_PROMPT}\nNone"

    def test_blank_instructions_keep_the_system_prompt(self) -> None:
        """The system prompt remains even when the question text is blank."""
        question = {
            "id": 1,
            "question_name": "q",
            "question_type": "score",
            "instructions": "",
            "criteria": ["a"],
        }

        prepared = create_instructions(1, [question])

        assert prepared[0]["instructions"]["question"] == f"{SYSTEM_PROMPT}\n"
        assert prepared[0]["instructions"]["inspect"] == "`campaign`"

    def test_instruction_dicts_are_independent(self) -> None:
        """Changing one prepared instruction does not change another."""
        questions = [
            {
                "id": 1,
                "question_name": "a",
                "question_type": "score",
                "instructions": "A",
                "focus": "tone",
                "criteria": ["a"],
            },
            {
                "id": 2,
                "question_name": "b",
                "question_type": "score",
                "instructions": "B",
                "criteria": ["b"],
            },
        ]

        prepared = create_instructions(1, questions)
        prepared[0]["instructions"]["focus"] = "changed"

        assert "focus" not in prepared[1]["instructions"]
        assert questions[0]["focus"] == "tone"

    @pytest.mark.parametrize(
        "missing",
        ["id", "question_name", "question_type", "instructions", "criteria"],
    )
    def test_required_question_fields(self, missing: str) -> None:
        """The payload reads each of these fields from the question."""
        question = {
            "id": 1,
            "question_name": "q",
            "question_type": "score",
            "instructions": "Answer",
            "criteria": ["a"],
        }
        del question[missing]

        with pytest.raises(KeyError):
            create_instructions(1, [question])
