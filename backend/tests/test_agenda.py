from datetime import datetime, timezone

from orquestador.agenda import parse_dias, parse_hora, seconds_until_next


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def test_parse():
    assert parse_hora("10:20") == (10, 20)
    for bad in ["", "9:00", "25:00", "10:60", None, 5]:
        assert parse_hora(bad) is None
    assert parse_dias([4, 0, 0]) == [0, 4]
    for bad in [[], [7], ["1"], None, [True], "x"]:
        assert parse_dias(bad) == [0, 1, 2, 3, 4]


def test_seconds_until_next_salta_fin_de_semana():
    lun = [0, 1, 2, 3, 4]
    assert seconds_until_next((10, 20), lun, at(2, 9, 20)) == 3600
    assert seconds_until_next((10, 20), lun, at(2, 10, 20)) == 24 * 3600
    assert seconds_until_next((10, 20), lun, at(6, 10, 20)) == 72 * 3600
