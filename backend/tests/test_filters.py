from datetime import date

import pytest
from fastapi import HTTPException

from services.filters import CASES_COLS, DAILY_COLS, HEX_MV_COLS, STATION_MV_COLS, CrimeFilter, crime_filter


def test_defaults_exclude_non_criminal():
    f = CrimeFilter()
    params = []
    sql = f.where("c", params, CASES_COLS)
    assert sql == "c.categoria_delito <> $1"
    assert params == ["HECHO NO DELICTIVO"]


def test_include_non_criminal_drops_predicate():
    f = CrimeFilter(include_non_criminal=True)
    params = []
    assert f.where("c", params, CASES_COLS) == "" and params == []


def test_categories_replace_default_exclusion():
    f = CrimeFilter(categories=["HOMICIDIO DOLOSO", "VIOLACIÓN"])
    params = []
    sql = f.where("c", params, CASES_COLS)
    assert sql == "c.categoria_delito = ANY($1::TEXT[])"
    assert params == [["HOMICIDIO DOLOSO", "VIOLACIÓN"]]


def test_param_numbering_is_sequential_and_bound():
    f = CrimeFilter(date_from=date(2023, 1, 1), date_to=date(2023, 12, 31),
                    categories=["HOMICIDIO DOLOSO"], delitos=["X"], transport_only=True,
                    modes=["METRO"], alcaldia_id=3, colonia_id=42, hours=(8, 10), dows=[6, 7])
    params = [999]  # pre-existing bound value keeps numbering honest
    sql = f.where("c", params, CASES_COLS)
    assert "$1" not in sql.replace("$10", "").replace("$11", "").replace("$12", "")
    assert sql.count("$") == len(params) - 1
    assert params[1] == date(2023, 1, 1) and params[2] == date(2023, 12, 31)
    assert "c.is_transport_related" in sql and "c.hour BETWEEN" in sql and "c.dow = ANY" in sql


def test_hours_wrap_midnight():
    f = CrimeFilter(hours=(22, 5), include_non_criminal=True)
    params = []
    sql = f.where("c", params, CASES_COLS)
    assert sql == "(c.hour >= $1 OR c.hour <= $2)" and params == [22, 5]


def test_monthly_views_use_ym():
    f = CrimeFilter(date_from=date(2023, 3, 15), date_to=date(2024, 1, 2), include_non_criminal=True)
    params = []
    sql = f.where("m", params, HEX_MV_COLS)
    assert sql == "m.ym >= $1 AND m.ym <= $2" and params == [202303, 202401]


def test_unsupported_detection():
    assert not CrimeFilter(categories=["X"], transport_only=True).unsupported(HEX_MV_COLS)
    assert CrimeFilter(hours=(1, 2)).unsupported(HEX_MV_COLS)
    assert CrimeFilter(modes=["METRO"]).unsupported(HEX_MV_COLS)
    assert not CrimeFilter(modes=["METRO"]).unsupported(STATION_MV_COLS)
    assert CrimeFilter(alcaldia_id=1).unsupported(STATION_MV_COLS)
    assert not CrimeFilter(alcaldia_id=1).unsupported(DAILY_COLS)
    assert CrimeFilter(delitos=["X"]).unsupported(DAILY_COLS)
    assert not CrimeFilter(delitos=["X"], hours=(1, 2), dows=[1]).unsupported(CASES_COLS)


def test_dependency_parses_query_params():
    f = crime_filter(date_from=date(2024, 1, 1), date_to=None, categories="A, B", delitos=None,
                     transport_only=True, modes="metro,mb", alcaldia="Iztapalapa", colonia_id=None,
                     hours="22-5", dows="6,7", include_non_criminal=False)
    assert f.categories == ["A", "B"] and f.modes == ["METRO", "MB"] and f.hours == (22, 5) and f.dows == [6, 7]
    assert f.active()["hours"] == "22-5"


@pytest.mark.parametrize("kwargs", [
    dict(hours="25-3"), dict(hours="abc"), dict(dows="0"), dict(dows="x"),
    dict(date_from=date(2024, 2, 1), date_to=date(2024, 1, 1)),
])
def test_dependency_rejects_bad_input(kwargs):
    base = dict(date_from=None, date_to=None, categories=None, delitos=None, transport_only=False,
                modes=None, alcaldia=None, colonia_id=None, hours=None, dows=None, include_non_criminal=False)
    with pytest.raises(HTTPException):
        crime_filter(**{**base, **kwargs})
