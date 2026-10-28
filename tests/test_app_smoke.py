# -*- coding: utf-8 -*-
"""
Smoke test da interface com o simulador: abre a janela, conecta, mexe nos
controles, lê/grava menu, faz backup e restore. Precisa de um display
(no Linux: `xvfb-run -a pytest`); sem display o teste é pulado.
"""

import json
import os
import sys
import time

import pytest

tk = pytest.importorskip("tkinter")

if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
    pytest.skip("no DISPLAY available", allow_module_level=True)

from ftx1cat.cat import BY_KEY  # noqa: E402
from ftx1cat.ui.app import App  # noqa: E402
from ftx1cat.ui.settings import Settings  # noqa: E402


def pump(app, seconds=0.4):
    """Processa eventos Tk e a fila do worker por um tempo."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        time.sleep(0.01)


def wait_idle(app, seconds=3.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.update()
        if app.worker.is_idle() and app.q.empty():
            app.update()
            return
        time.sleep(0.01)
    raise AssertionError("worker did not become idle")


@pytest.fixture
def app(tmp_path):
    try:
        application = App(settings=Settings(tmp_path / "settings.json"), simulate=True)
    except tk.TclError as exc:                      # pragma: no cover
        pytest.skip(f"Tk not usable here: {exc}")
    application.withdraw()
    yield application
    try:
        application._close()
    except tk.TclError:
        pass                                        # o teste já fechou a janela


def test_connect_reads_everything(app):
    app.connect()
    wait_idle(app)
    fake = app.radio.ser
    assert "Connected" in app.conn_lbl.cget("text")
    assert app.quick.freq_lbl.cget("text") == "28.410.000 Hz"
    assert app.quick.mode_var.get() == "2"
    assert app.quick.cards["RF POWER"].value_lbl.cget("text") == "13 W"
    assert "ID" in fake.sent and "FA" in fake.sent


def test_band_mode_and_slider(app):
    app.connect()
    wait_idle(app)
    fake = app.radio.ser
    app.quick.select_band("13")
    wait_idle(app)
    assert app.quick.freq_lbl.cget("text") == "144.800.000 Hz"
    assert "FM" in app.quick.freq_hint.cget("text")
    assert "12.5 kHz" in app.quick.freq_hint.cget("text")

    app.quick.set_mode("1")
    wait_idle(app)
    assert fake.mode == "1"

    card = app.quick.cards["NB"]
    card.var.set(7)
    card._moved("7")
    wait_idle(app)
    assert fake.controls["NL0"] == "007"
    assert card.status.cget("text") == "Radio: Level 7"

    app.quick._knob_ticks(+3)                       # 3 passos de 1 kHz para cima
    wait_idle(app)
    assert fake.frequency == 144_800_000 + 3_000


def test_frequency_poll_follows_physical_dial(app):
    app.connect()
    wait_idle(app)
    app.radio.ser.frequency = 7_100_000               # "girou o dial" no rádio
    pump(app, 1.5)
    assert app.quick.freq_lbl.cget("text") == "7.100.000 Hz"


def test_func_parameter_roundtrip(app):
    app.connect()
    wait_idle(app)
    app.quick.select_func("7")                        # MIC GAIN
    wait_idle(app)
    assert app.quick.func_status.cget("text") == "Radio: 50"
    app.quick.func_slider_var.set(60)
    app.quick._func_slider_moved("60")
    wait_idle(app)
    assert app.radio.ser.controls["MG"] == "060"


def test_menu_page_read_and_write(app, monkeypatch):
    app.connect()
    wait_idle(app)
    app.menu.show_group(3, 2)                         # BAND-SCAN
    wait_idle(app)
    rows = {r.item.name: r for r in app.menu.rows}
    assert rows["BAND STACK"].status.cget("text") == "Read"
    row = rows["BAND STACK"]
    row.var.set("0 – OFF")
    assert row.dirty()
    assert "Changed" in row.status.cget("text")
    monkeypatch.setattr("ftx1cat.ui.menu_page.messagebox.askokcancel", lambda *a, **k: True)
    app.menu.write_dirty()
    wait_idle(app)
    assert app.radio.ser.menu["030202"] == "0"
    assert row.status.cget("text") == "Written ✓"


def test_search_and_rejected_item(app):
    app.connect()
    wait_idle(app)
    app.menu.search_var.set("ch step")
    pump(app, 0.2)
    assert {r.item.name for r in app.menu.rows} >= {"CH STEP", "AM CH STEP", "FM CH STEP"}
    assert app.menu.title_lbl.cget("text").startswith("Search")
    app.menu.search_var.set("")
    pump(app, 0.2)
    assert app.menu.rows == []


def test_backup_and_restore(app, tmp_path, monkeypatch):
    app.connect()
    wait_idle(app)
    path = tmp_path / "bk.json"
    monkeypatch.setattr("ftx1cat.ui.menu_page.filedialog.asksaveasfilename", lambda **k: str(path))
    app.menu.backup()
    wait_idle(app, 10)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "ftx1-menu-backup-1"
    assert len(data["items"]) == len(BY_KEY)
    assert data["items"]["030202"] == "1"

    # muda algo no "rádio" e restaura
    app.radio.ser.menu["030202"] = "0"
    app.radio.ser.menu["030105"] = "0"                # CAT-1 RATE: arriscado, deve ser pulado
    monkeypatch.setattr("ftx1cat.ui.menu_page.filedialog.askopenfilename", lambda **k: str(path))
    asked = {}

    def ok(title, text, **k):
        asked["text"] = text
        return True

    monkeypatch.setattr("ftx1cat.ui.menu_page.messagebox.askokcancel", ok)
    app.menu.restore()
    wait_idle(app, 10)
    wait_idle(app, 10)
    assert "1 items differ" in asked["text"]
    assert app.radio.ser.menu["030202"] == "1"
    assert app.radio.ser.menu["030105"] == "0"        # não tocou no CAT-1 RATE


def test_disconnect_and_settings_saved(app, tmp_path):
    app.connect()
    wait_idle(app)
    app.disconnect()
    assert app.radio is None
    assert app.conn_lbl.cget("text") == "Disconnected"
    app._close()
    saved = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert saved["port"] == "SIM"
    assert saved["baud"] == "38400"
