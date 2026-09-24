from datetime import datetime

import pytest

from services.crime_parsing import (clean_text, in_cdmx_bbox, parse_coords, parse_dt, parse_edad,
                                    parse_year, transport_mode)
from services.name_match import fix_mojibake, normalize


def test_parse_dt_time_in_date_string():
    ts, ok = parse_dt("2023-05-01 13:20:00", "")
    assert ts == datetime(2023, 5, 1, 13, 20) and ok


def test_parse_dt_time_in_separate_field():
    ts, ok = parse_dt("2023-05-01", "13:20:00")
    assert ts == datetime(2023, 5, 1, 13, 20) and ok


def test_parse_dt_date_string_wins_over_hora():
    ts, ok = parse_dt("2024-11-25 11:20:00", "07:00:00")
    assert ts.hour == 11 and ok


def test_parse_dt_midnight_is_placeholder():
    ts, ok = parse_dt("2023-05-01", "00:00:00")
    assert ts == datetime(2023, 5, 1) and not ok
    ts, ok = parse_dt("2023-05-01 00:00:00", "")
    assert ts == datetime(2023, 5, 1) and not ok


def test_parse_dt_missing_time():
    ts, ok = parse_dt("2023-05-01", "NA")
    assert ts == datetime(2023, 5, 1) and not ok


@pytest.mark.parametrize("bad", ["NA", "", None, "2023-13-01", "31/12/2023", "hoy"])
def test_parse_dt_rejects_garbage(bad):
    assert parse_dt(bad, "12:00:00") == (None, False)


def test_parse_dt_bad_time_keeps_date():
    ts, ok = parse_dt("2023-05-01", "25:99:00")
    assert ts == datetime(2023, 5, 1) and not ok


def test_parse_year():
    assert parse_year("2015.0") == 2015
    assert parse_year("2024") == 2024
    assert parse_year("NA") is None
    assert parse_year("") is None


def test_bbox():
    assert in_cdmx_bbox(19.4326, -99.1332)
    assert not in_cdmx_bbox(0.0, 0.0)
    assert not in_cdmx_bbox(19.43, -99.13 * 0)  # lon 0
    assert not in_cdmx_bbox(None, -99.1)


def test_parse_coords():
    assert parse_coords("19.1986112589353", "-99.1400644198312") == (19.1986112589353, -99.1400644198312)
    assert parse_coords("NA", "NA") == (None, None)
    assert parse_coords("40.7", "-74.0") == (None, None)      # New York → outside CDMX
    assert parse_coords("-99.13", "19.43") == (None, None)    # swapped


@pytest.mark.parametrize("delito, expected", [
    ("ROBO A PASAJERO A BORDO DE METRO CON VIOLENCIA", "METRO"),
    ("ROBO A PASAJERO A BORDO DE METRO SIN VIOLENCIA", "METRO"),
    ("ROBO A PASAJERO A BORDO DE METROBUS SIN VIOLENCIA", "MB"),
    ("ROBO A PASAJERO EN TROLEBUS SIN VIOLENCIA", "TROLE"),
    ("ROBO A PASAJERO EN TREN LIGERO SIN VIOLENCIA", "TL"),
    ("ROBO A PASAJERO EN TREN SUBURBANO CON VIOLENCIA", "SUB"),
    ("ROBO A PASAJERO EN RTP SIN VIOLENCIA", "RTP"),
    ("ROBO A PASAJERO A BORDO DE PESERO COLECTIVO CON VIOLENCIA", "MICRO"),
    ("ROBO A PASAJERO A BORDO DE MICROBUS SIN VIOLENCIA", "MICRO"),
    ("ROBO A TRANSEUNTE A BORDO DE TAXI PUBLICO Y PRIVADO SIN VIOLENCIA", "TAXI"),
    ("ROBO A PASAJERO A BORDO DE TRANSPORTE PÚBLICO SIN VIOLENCIA", "TP"),
    ("ROBO A TRANSPORTISTA CON VIOLENCIA", None),
    ("ROBO A REPARTIDOR CON VIOLENCIA", None),
    ("ROBO DE VEHICULO DE SERVICIO PARTICULAR SIN VIOLENCIA", None),
    ("ROBO DE OBJETOS DEL INTERIOR DE UN VEHICULO", None),
    ("HOMICIDIO DOLOSO", None),
    ("", None),
    (None, None),
])
def test_transport_mode(delito, expected):
    assert transport_mode(delito) == expected


def test_transport_mode_category_fallback():
    assert transport_mode("ROBO A PASAJERO", "ROBO A PASAJERO A BORDO DEL METRO CON Y SIN VIOLENCIA") == "METRO"
    assert transport_mode("ROBO A PASAJERO", "ROBO A PASAJERO A BORDO DE MICROBUS CON Y SIN VIOLENCIA") == "MICRO"
    assert transport_mode("FRAUDE", "DELITO DE BAJO IMPACTO") is None


def test_parse_edad():
    assert parse_edad("42") == 42
    assert parse_edad("42.0") == 42
    assert parse_edad("NA") is None
    assert parse_edad("250") is None
    assert parse_edad("-3") is None


def test_clean_text():
    assert clean_text("  ROMA   NORTE ") == "ROMA NORTE"
    assert clean_text("NA") is None
    assert clean_text("") is None


def test_mojibake_and_normalize():
    assert fix_mojibake("LÃ­nea 1") == "Línea 1"
    assert normalize("Pantitlán") == "pantitlan"
    assert normalize("  Bellas   Artes ") == "bellas artes"
