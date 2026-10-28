# -*- coding: utf-8 -*-
"""Camada serial testada contra o simulador."""

import pytest

from ftx1cat.cat import BY_KEY, CatError, CatRejected, Item, Radio
from ftx1cat.cat import commands as C
from ftx1cat.cat.simulator import FakeFTX1


@pytest.fixture
def fake():
    return FakeFTX1()


@pytest.fixture
def radio(fake):
    return Radio(fake, timeout=0.2, gap=0)


def test_identify_and_firmware(radio):
    assert radio.identify() == "0840"
    assert radio.firmware() == "0113"


def test_frequency_and_mode(radio, fake):
    assert radio.read_frequency() == 28_410_000
    assert radio.set_frequency(14_250_000) == 14_250_000
    assert fake.sent[-2] == "FA014250000"
    assert radio.set_mode("1") == "1"


def test_band_select_uses_band_stack(radio):
    radio.select_band("13")
    freq, mode, item, raw, khz = radio.read_tuning()
    assert (freq, mode) == (144_800_000, "4")
    assert item.name == "FM CH STEP" and khz == 12.5


def test_band_11m_tunes_directly(radio):
    radio.select_band("11m")
    assert radio.read_frequency() == C.FREQ_11M_DX_CALL_HZ


def test_menu_read_write(radio):
    it = BY_KEY["010101"]
    assert radio.read_menu(it) == "+00"
    assert radio.write_menu(it, it.encode(-7)) == "-07"


def test_controls(radio):
    assert radio.read_control(C.RF_POWER) == 13
    assert radio.set_control(C.RF_POWER, 42) == 42
    assert radio.set_control(C.FUNC_PARAMETERS["4"], 5) == 5      # CONTRAST via DA
    assert radio.read_control(C.FUNC_PARAMETERS["5"]) == 10       # DIMMER intacto
    with pytest.raises(ValueError):
        radio.set_control(C.Control("x", "x", "XX;", "XX", 0, 1, 1, int, None, str), 1)


def test_rejected_command_raises_fast(radio):
    with pytest.raises(CatRejected):
        radio.query("ZZ;", "ZZ")
    with pytest.raises(CatRejected):
        radio.read_menu(Item(9, 9, 9, "does not exist", "ro", 1))
    with pytest.raises(CatRejected):
        radio.write_menu(BY_KEY["010101"], "+99")          # fora da faixa: rádio recusa


def test_silent_radio_times_out(radio, fake):
    fake.silent = True
    with pytest.raises(CatError) as exc:
        radio.identify()
    assert "no response" in str(exc.value)


def test_logger_receives_tx_rx(fake):
    seen = []
    radio = Radio(fake, timeout=0.2, gap=0, logger=lambda d, t: seen.append((d, t)))
    radio.identify()
    assert seen == [("TX", "ID;"), ("RX", "ID0840;")]


def test_unexpected_frames_are_skipped(fake, radio):
    fake.prepend = b"AI1;MD02;"                # informação automática antes da resposta
    assert radio.read_frequency() == 28_410_000
