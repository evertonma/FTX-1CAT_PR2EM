#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FTX-1 - CAT Menu (simple graphical interface)

Requisitos:  Python 3.8+, tkinter (ja vem no Python do Windows/macOS;
             no Debian/Ubuntu: sudo apt install python3-tk) e pyserial:
                 pip install pyserial

Usage:       python ftx1_cat_menu.py
             (requires ftx1_menu.py in the same folder)

Port:        use the FTX-1 "Enhanced COM Port" (CAT-1), 38400 bps
             (factory default), as described in the official CAT manual.
"""

import datetime
import json
import math
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path

# Algumas instalações do Python no Windows guardam Tcl/Tk em `tcl/`, mas o
# tkinter tenta encontrá-los em `lib/`. Definir estes caminhos antes de criar
# a janela permite iniciar o app sem configurar variáveis no PowerShell.
_tcl_root = Path(sys.base_prefix) / "tcl"
_tcl_dir = next((p for p in _tcl_root.glob("tcl*") if (p / "init.tcl").is_file()), None)
_tk_dir = next((p for p in _tcl_root.glob("tk*") if (p / "tk.tcl").is_file()), None)
if _tcl_dir:
    os.environ["TCL_LIBRARY"] = str(_tcl_dir)
if _tk_dir:
    os.environ["TK_LIBRARY"] = str(_tk_dir)

import serial
from serial.tools import list_ports

from ftx1_menu import BY_KEY, MENU, CatError, Radio, all_items

SEP = " – "
BAUDS = ["4800", "9600", "19200", "38400", "115200"]
GREEN, RED, GRAY, AMBER = "#1a7f37", "#b42318", "#555555", "#9a6700"
ALL_ITEMS = all_items()


# --------------------------------------------------------------------------
# Painel rolavel
# --------------------------------------------------------------------------
class ScrollFrame(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.win, width=e.width))
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    def _bind_wheel(self, _=None):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", self._wheel)
        self.canvas.bind_all("<Button-5>", self._wheel)

    def _unbind_wheel(self, _=None):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _wheel(self, e):
        if getattr(e, "num", None) == 4:
            step = -1
        elif getattr(e, "num", None) == 5:
            step = 1
        else:
            step = -1 if e.delta > 0 else 1
        self.canvas.yview_scroll(step, "units")

    def clear(self):
        for w in self.inner.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)


# --------------------------------------------------------------------------
# Uma linha = um item de menu
# --------------------------------------------------------------------------
class Row:
    def __init__(self, app, parent, item, r, crumb=False):
        self.app, self.item = app, item
        self.raw = None
        self.alive = True
        self.var = tk.StringVar()

        title = f"{item.path1} › {item.path2} › {item.name}" if crumb else item.name
        ttk.Label(parent, text=f"{item.p3:02d}", width=3, anchor="e").grid(
            row=r, column=0, padx=(4, 2), pady=2, sticky="e")
        ttk.Label(parent, text=title, anchor="w").grid(row=r, column=1, padx=4, sticky="w")

        if item.kind == "enum":
            self.w = ttk.Combobox(parent, textvariable=self.var, state="readonly", width=34,
                                  values=[f"{c}{SEP}{l}" for c, l in item.opts])
        elif item.kind in ("int", "sint"):
            self.w = ttk.Spinbox(parent, textvariable=self.var, from_=item.lo, to=item.hi,
                                 increment=item.step, width=10)
        else:
            self.w = ttk.Entry(parent, textvariable=self.var, state="readonly", width=34)
        self.w.grid(row=r, column=2, padx=4, sticky="w")

        if item.kind in ("int", "sint"):
            note = f"{item.lo} to {item.hi} {item.unit}".strip()
        elif item.kind == "text":
            note = f"text, {item.digits} chars (read-only)"
        elif item.kind == "ro":
            note = item.hint
        else:
            note = ""
        ttk.Label(parent, text=note, foreground=GRAY, wraplength=320, justify="left").grid(
            row=r, column=3, padx=4, sticky="w")

        ttk.Button(parent, text="Read", width=5, command=self.read).grid(row=r, column=4, padx=2)
        self.btn_w = ttk.Button(parent, text="Write", width=7, command=self.write)
        self.btn_w.grid(row=r, column=5, padx=2)
        if not item.writable:
            self.btn_w.state(["disabled"])
        self.status = ttk.Label(parent, text="", width=26, anchor="w")
        self.status.grid(row=r, column=6, padx=4, sticky="w")

    # -- helpers ----------------------------------------------------------
    def set_status(self, text, color=GRAY):
        if self.alive:
            try:
                self.status.config(text=text, foreground=color)
            except tk.TclError:
                self.alive = False

    def show_raw(self, raw):
        if not self.alive:
            return
        self.raw = raw
        it = self.item
        try:
            if it.kind == "enum":
                lab = dict(it.opts).get(raw)
                self.var.set(f"{raw}{SEP}{lab}" if lab is not None
                             else f"{raw}{SEP}(not in table)")
            elif it.kind in ("int", "sint"):
                self.var.set(str(it.decode(raw)))
            else:
                self.var.set(raw)
        except (ValueError, tk.TclError):
            try:
                self.var.set(raw)
            except tk.TclError:
                self.alive = False

    def current_raw(self):
        it = self.item
        if it.kind == "enum":
            code = self.var.get().split(SEP, 1)[0].strip()
            return it.encode(code)
        return it.encode(self.var.get())

    def dirty(self):
        if not self.item.writable or self.raw is None:
            return False
        try:
            return self.item.norm(self.current_raw()) != self.item.norm(self.raw)
        except ValueError:
            return False

    def read(self):
        self.app.read_rows([self])

    def write(self):
        self.app.write_rows([self])


# --------------------------------------------------------------------------
# Aplicacao
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Yaesu FTX-1 CAT Menu - by PR2EM - v0.1 Alpha")
        self.geometry("1280x760")
        self.minsize(980, 560)

        self.radio = None
        self.fw = ""
        self.rows = []
        self.q = queue.Queue()
        self.busy = False
        self.stop = threading.Event()
        self.cur_group = None
        self.quick_status = {}
        self.quick_vars = {}
        self.quick_specs = {}
        self.quick_value_labels = {}
        self.quick_widgets = {}
        self.func_active = None
        self.frequency_hz = None
        self.current_mode = None
        self.pending_tune = 0
        self.tune_retry_scheduled = False
        self.knob_position = 0
        self.pending_slider_updates = []
        self.setting_slider_from_radio = False
        self.pending_func_parameter_read = None
        self.pending_band_selection = None
        self.frequency_poll_after_id = None

        self._build_ui()
        cat_port_found = self.refresh_ports()
        self.after(40, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._close)
        if cat_port_found:
            self.log("Ready. CAT-1 (Enhanced COM Port) selected automatically; click Connect.")
        else:
            self.log("Ready. CAT-1 port was not found automatically. Select it and click Connect.")

    # -- fila de atualizacoes da interface (threads -> Tk) -----------------
    def ui(self, fn):
        self.q.put(fn)

    def _pump(self):
        try:
            while True:
                self.q.get_nowait()()
        except queue.Empty:
            pass
        self.after(40, self._pump)

    # -- construcao da janela ---------------------------------------------
    def _build_ui(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Port:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=46)
        self.port_cb.pack(side="left", padx=4)
        ttk.Button(top, text="↻", width=3, command=self.refresh_ports).pack(side="left")
        ttk.Label(top, text="Baud rate:").pack(side="left", padx=(10, 2))
        self.baud_var = tk.StringVar(value="38400")
        ttk.Combobox(top, textvariable=self.baud_var, values=BAUDS, width=8,
                     state="readonly").pack(side="left")
        self.btn_conn = ttk.Button(top, text="Connect", command=self.toggle_connect)
        self.btn_conn.pack(side="left", padx=10)
        self.conn_lbl = ttk.Label(top, text="Disconnected", foreground=GRAY)
        self.conn_lbl.pack(side="left")

        pages = ttk.Notebook(self)
        pages.pack(fill="both", expand=True, padx=6)
        self.pages = pages
        controls_page = ttk.Frame(pages, padding=12)
        pages.add(controls_page, text="Quick Controls")
        self.quick_controls_page = controls_page
        self._build_quick_controls(controls_page)

        menu_page = ttk.Frame(pages)
        pages.add(menu_page, text="CAT Menu")

        body = ttk.PanedWindow(menu_page, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        self.search_var = tk.StringVar()
        ttk.Label(left, text="Search items:").pack(anchor="w")
        ent = ttk.Entry(left, textvariable=self.search_var)
        ent.pack(fill="x", pady=(0, 4))
        self.search_var.trace_add("write", lambda *_: self.on_search())
        self.tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.tree.pack(fill="both", expand=True)
        for p1, n1, groups in MENU:
            top_id = self.tree.insert("", "end", text=f"{p1:02d}  {n1}")
            for p2, n2, items in groups:
                self.tree.insert(top_id, "end", text=f"{p2:02d}  {n2}  ({len(items)})",
                                 values=(p1, p2))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree)
        body.add(left, weight=1)

        right = ttk.Frame(body)
        self.title_lbl = ttk.Label(right, text="Select a group on the left",
                                   font=("TkDefaultFont", 11, "bold"))
        self.title_lbl.pack(anchor="w", pady=(0, 4))
        self.sf = ScrollFrame(right)
        self.sf.pack(fill="both", expand=True)
        body.add(right, weight=4)

        pages.select(controls_page)

        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Read List", command=self.read_all_visible).pack(side="left")
        ttk.Button(bar, text="Write Changes", command=self.write_dirty).pack(side="left", padx=4)
        ttk.Button(bar, text="Stop", command=self.stop.set).pack(side="left")
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Read when opening a group", variable=self.auto_var).pack(
            side="left", padx=12)
        ttk.Button(bar, text="Save Backup…", command=self.backup).pack(side="right")
        ttk.Button(bar, text="Restore Backup…", command=self.restore).pack(side="right", padx=4)
        self.prog_lbl = ttk.Label(bar, text="", foreground=GRAY)
        self.prog_lbl.pack(side="right", padx=10)

        logf = ttk.Frame(self, padding=(6, 0, 6, 6))
        logf.pack(fill="x")
        head = ttk.Frame(logf)
        head.pack(fill="x")
        ttk.Label(head, text="Log").pack(side="left")
        self.cat_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(head, text="Show commands (TX/RX)", variable=self.cat_var).pack(
            side="left", padx=10)
        self.logbox = tk.Text(logf, height=8, wrap="none", state="disabled")
        self.logbox.pack(fill="x")

    def _build_quick_controls(self, parent):
        parent.columnconfigure(0, weight=1)
        parent.columnconfigure(1, weight=1)
        heading = ttk.Frame(parent)
        heading.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        ttk.Button(heading, text="Refresh Values", command=self.quick_read_all).pack(side="right")
        tuning = ttk.Frame(heading)
        tuning.pack(side="left", fill="x", expand=True, padx=(0, 10))
        frequency_box = ttk.LabelFrame(tuning, text="MAIN Frequency", padding=(8, 4))
        frequency_box.pack(side="left", fill="y", padx=(0, 8))
        self.frequency_label = ttk.Label(frequency_box, text="---.---.--- Hz",
                                         font=("TkDefaultFont", 18, "bold"), width=18,
                                         anchor="center", cursor="hand2")
        self.frequency_label.pack(fill="x")
        self.frequency_label.bind("<Button-1>", self._open_frequency_dialog)
        self.frequency_hint = ttk.Label(frequency_box, text="Scroll the dial to tune",
                                        foreground=GRAY, anchor="center")
        self.frequency_hint.pack(fill="x")

        self.frequency_knob = tk.Canvas(tuning, width=96, height=96, highlightthickness=0,
                                        background=self.cget("background"))
        self.frequency_knob.pack(side="left", padx=(0, 8))
        self.frequency_knob.bind("<MouseWheel>", self._frequency_wheel)
        self.frequency_knob.bind("<Button-4>", self._frequency_wheel)
        self.frequency_knob.bind("<Button-5>", self._frequency_wheel)
        self._draw_frequency_knob()

        self.ch_step_var = tk.IntVar(value=0)
        self.ch_step_item = None
        self.setting_ch_step_from_radio = False
        self.ch_step_frame = ttk.Frame(tuning, width=76, height=96)
        self.ch_step_frame.pack(side="left", padx=(0, 8))
        self.ch_step_frame.pack_propagate(False)
        ttk.Label(self.ch_step_frame, text="CH-STEP", font=("TkDefaultFont", 8),
                  anchor="center").pack(fill="x", pady=(1, 0))
        self.ch_step_scale = tk.Scale(self.ch_step_frame, variable=self.ch_step_var,
                                      from_=0, to=1, resolution=1, orient="vertical",
                                      showvalue=False, length=48, width=12, sliderlength=13,
                                      highlightthickness=0, bd=0,
                                      command=self._ch_step_slider_moved)
        self.ch_step_scale.pack(fill="y", expand=True, anchor="center")
        self.ch_step_value = ttk.Label(self.ch_step_frame, text="—", width=9,
                                       font=("TkDefaultFont", 7), anchor="center")
        self.ch_step_value.pack(fill="x", pady=(0, 1))
        self._bind_scale_click(self.ch_step_scale,
                               lambda _e: self._queue_slider_update("CH STEP"))
        self.quick_vars["CH STEP"] = self.ch_step_var
        self.quick_specs["CH STEP"] = {
            "read_cmd": "EX030604;", "prefix": "EX030604",
            "decode": lambda raw: raw, "make_set": lambda: "", "display": str,
        }
        self.quick_status["CH STEP"] = self.ch_step_value

        band_frame = ttk.LabelFrame(tuning, text="MAIN Bands", padding=(4, 3))
        band_frame.pack(side="left", fill="y", padx=(0, 6))
        band_options = [
            ("00", "160m"), ("01", "80m"), ("02", "60m"), ("03", "40m"),
            ("04", "30m"), ("05", "20m"), ("06", "17m"), ("07", "15m"),
            ("08", "12m"), ("09", "10m"), ("11m", "11m"), ("10", "6m"), ("11", "4m/GEN"),
            ("12", "AIR"), ("13", "2m"), ("14", "70cm"),
        ]
        for index, (band_code, label) in enumerate(band_options):
            button = ttk.Button(band_frame, text=label, width=6,
                                command=lambda code=band_code: self._select_band(code))
            button.grid(row=index // 8, column=index % 8, sticky="ew", padx=1, pady=1)
        for col in range(8):
            band_frame.columnconfigure(col, weight=1)

        self.mode_var = tk.StringVar()
        mode_frame = ttk.LabelFrame(tuning, text="Mode", padding=(5, 3))
        mode_frame.pack(side="left", fill="both", expand=True)
        self.mode_buttons = {}
        mode_options = [("1", "LSB"), ("2", "USB"), ("3", "CW-U"), ("4", "FM"),
                        ("5", "AM"), ("6", "RTTY-L"), ("7", "CW-L"), ("8", "DATA-L"),
                        ("9", "RTTY-U"), ("A", "DATA-FM"), ("B", "FM-N"), ("C", "DATA-U"),
                        ("D", "AM-N"), ("E", "PSK"), ("F", "DATA-FM-N"),
                        ("H", "C4FM-DN"), ("I", "C4FM-VW")]
        for index, (code, label) in enumerate(mode_options):
            button = ttk.Radiobutton(mode_frame, text=label, value=code, variable=self.mode_var,
                                     style="Toolbutton", command=lambda m=code: self._set_radio_mode(m))
            button.grid(row=index // 6, column=index % 6, sticky="ew", padx=2, pady=1)
            self.mode_buttons[code] = button
        for col in range(6):
            mode_frame.columnconfigure(col, weight=1)
        ttk.Label(parent, text="Values are read when you connect. Changes are sent directly to the radio.",
                  foreground=GRAY).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        power_var = tk.DoubleVar(value=5)
        power_card = ttk.LabelFrame(parent, text="RF POWER — SPA-1", padding=10)
        power_card.grid(row=2, column=0, sticky="nsew", padx=(0, 6), pady=5)
        power_value = ttk.Label(power_card, text="— W", font=("TkDefaultFont", 14, "bold"))
        power_value.pack(anchor="center")
        power_scale = tk.Scale(power_card, variable=power_var, from_=5, to=100, resolution=1,
                               orient="horizontal", showvalue=False, length=420,
                               highlightthickness=0,
                               command=lambda v: self._quick_scale_moved("RF POWER (W)", v))
        power_scale.pack(fill="x", padx=8)
        self._bind_scale_click(power_scale, lambda _e: self._queue_slider_update("RF POWER (W)"))
        self._register_quick("RF POWER (W)", power_var, "PC;", "PC",
                             lambda raw: float(int(raw[1:4])),
                             # PC1 controla o field head e limita a 10 W; PC2 controla o SPA-1.
                             lambda: "PC2" + f"{int(power_var.get()):03d}" + ";",
                             lambda value: f"{int(float(value))} W", power_card, power_value)
        self.quick_status["RF POWER (W)"].pack(anchor="w", pady=(5, 0))

        level_var = tk.DoubleVar(value=0)
        level_card = ttk.LabelFrame(parent, text="D-LEVEL", padding=10)
        level_card.grid(row=2, column=1, sticky="nsew", padx=(6, 0), pady=5)
        level_value = ttk.Label(level_card, text="— dB", font=("TkDefaultFont", 14, "bold"))
        level_value.pack(anchor="center")
        level_scale = tk.Scale(level_card, variable=level_var, from_=-30, to=30, resolution=0.5,
                               orient="horizontal", showvalue=False, length=420,
                               highlightthickness=0,
                               command=lambda v: self._quick_scale_moved("D-LEVEL", v))
        level_scale.pack(fill="x", padx=8)
        self._bind_scale_click(level_scale, lambda _e: self._queue_slider_update("D-LEVEL"))
        self._register_quick("D-LEVEL", level_var, "SS04;", "SS04",
                             lambda raw: float(raw),
                             lambda: "SS04" + f"{level_var.get():+05.1f}" + ";",
                             lambda value: f"{float(value):+.1f} dB", level_card, level_value)
        self.quick_status["D-LEVEL"].pack(anchor="w", pady=(5, 0))

        peak_card = ttk.LabelFrame(parent, text="D-PEAK", padding=10)
        peak_card.grid(row=3, column=1, sticky="nsew", padx=(6, 0), pady=5)
        peak_var = tk.IntVar(value=1)
        peak_value = ttk.Label(peak_card, text="LV1", font=("TkDefaultFont", 14, "bold"))
        peak_value.pack(anchor="center")
        peak_scale = tk.Scale(peak_card, variable=peak_var, from_=1, to=5, resolution=1,
                              orient="horizontal", showvalue=False, length=420,
                              highlightthickness=0,
                              command=lambda v: self._quick_scale_moved("D-PEAK", v))
        peak_scale.pack(fill="x", padx=8)
        self._bind_scale_click(peak_scale, lambda _e: self._queue_slider_update("D-PEAK"))
        self._register_quick("D-PEAK", peak_var, "SS01;", "SS01",
                             lambda raw: int(raw[0]) + 1,
                             lambda: "SS01" + str(int(peak_var.get()) - 1) + "0000;",
                             lambda value: f"LV{int(value)}", peak_card, peak_value)
        self.quick_status["D-PEAK"].pack(anchor="w", pady=(5, 0))

        noise_frame = ttk.Frame(parent)
        noise_frame.grid(row=3, column=0, sticky="ew", padx=(0, 6), pady=5)
        noise_frame.columnconfigure(0, weight=1)
        noise_frame.columnconfigure(1, weight=1)

        nb_var = tk.IntVar(value=0)
        nb_card = ttk.LabelFrame(noise_frame, text="NB", padding=(6, 4))
        nb_card.grid(row=0, column=0, sticky="ew", padx=(0, 3))
        nb_value = ttk.Label(nb_card, text="OFF", font=("TkDefaultFont", 11, "bold"))
        nb_value.pack(anchor="center")
        nb_scale = tk.Scale(nb_card, variable=nb_var, from_=0, to=10, resolution=1,
                            orient="horizontal", showvalue=False, length=180,
                            highlightthickness=0,
                            command=lambda v: self._quick_scale_moved("NB", v))
        nb_scale.pack(fill="x", padx=4)
        self._bind_scale_click(nb_scale, lambda _e: self._queue_slider_update("NB"))
        self._register_quick("NB", nb_var, "NL0;", "NL0",
                             lambda raw: int(raw),
                             lambda: "NL0" + f"{int(nb_var.get()):03d}" + ";",
                             lambda value: "OFF" if int(float(value)) == 0
                             else f"Level {int(float(value))}", nb_card, nb_value)
        self.quick_status["NB"].pack(anchor="w", pady=(1, 0))

        dnr_var = tk.IntVar(value=0)
        dnr_card = ttk.LabelFrame(noise_frame, text="DNR", padding=(6, 4))
        dnr_card.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        dnr_value = ttk.Label(dnr_card, text="OFF", font=("TkDefaultFont", 11, "bold"))
        dnr_value.pack(anchor="center")
        dnr_scale = tk.Scale(dnr_card, variable=dnr_var, from_=0, to=10, resolution=1,
                             orient="horizontal", showvalue=False, length=180,
                             highlightthickness=0,
                             command=lambda v: self._quick_scale_moved("DNR", v))
        dnr_scale.pack(fill="x", padx=4)
        self._bind_scale_click(dnr_scale, lambda _e: self._queue_slider_update("DNR"))
        self._register_quick("DNR", dnr_var, "RL0;", "RL0",
                             lambda raw: int(raw),
                             lambda: "RL0" + f"{int(dnr_var.get()):02d}" + ";",
                             lambda value: "OFF" if int(float(value)) == 0
                             else f"Level {int(float(value))}", dnr_card, dnr_value)
        self.quick_status["DNR"].pack(anchor="w", pady=(1, 0))

        func_options = [(code, label) for code, label in [
            ("3", "COLOR"),
            ("4", "CONTRAST"), ("5", "DIMMER"), ("7", "MIC GAIN"), ("8", "PROC LEVEL"),
            ("9", "AMC LEVEL"), ("A", "VOX GAIN"), ("B", "VOX DELAY"), ("D", "RF POWER"),
            ("E", "MONI LEVEL"), ("F", "CW SPEED"), ("G", "CW PITCH"), ("H", "BK-DELAY")]]
        func_var = tk.StringVar(value="")
        self.func_control_var = func_var
        func_card = ttk.LabelFrame(parent, text="Radio Parameter Controls", padding=8)
        func_card.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(func_card,
                  text="Select a parameter to adjust. This does not change the function assigned to the radio's FUNC button.",
                  foreground=GRAY, wraplength=1100).grid(row=0, column=0, columnspan=3,
                                                        sticky="w", padx=8, pady=(0, 6))
        func_buttons = ttk.Frame(func_card)
        func_buttons.grid(row=1, column=0, sticky="nw", padx=(0, 16))
        func_adjust = ttk.LabelFrame(func_card, text="Selected Parameter", padding=8)
        func_adjust.grid(row=1, column=1, sticky="nsew")
        donation_text = ("Designed by Everton PR2EM and generated by AI.\n\n"
                         "Enjoying the software? Consider making a donation via PayPal to "
                         "everton.machado@gmail.com.\n\nThank you! 73!")
        donation_label = ttk.Label(func_card, text=donation_text, wraplength=280,
                                   justify="left", anchor="center")
        donation_label.grid(row=1, column=2, sticky="nsew", padx=(16, 8), pady=8)
        func_card.columnconfigure(0, weight=3)
        func_card.columnconfigure(1, weight=2)
        func_card.columnconfigure(2, weight=2)
        for index, (code, label) in enumerate(func_options):
            button = ttk.Radiobutton(func_buttons, text=label, value=code, variable=func_var,
                                     command=lambda selected=code: self._select_func_parameter(selected))
            button.grid(row=index // 4, column=index % 4, sticky="w", padx=8, pady=3)
        self.func_slider_title = ttk.Label(func_adjust, text="Select a function", anchor="center",
                                           font=("TkDefaultFont", 11, "bold"))
        self.func_slider_title.pack(fill="x", pady=(4, 8))
        self.func_slider_value = ttk.Label(func_adjust, text="", anchor="center",
                                           font=("TkDefaultFont", 13, "bold"))
        self.func_slider_value.pack(fill="x")
        self.func_slider_var = tk.DoubleVar(value=0)
        self.func_slider = tk.Scale(func_adjust, variable=self.func_slider_var, from_=0, to=100,
                                    resolution=1, orient="horizontal", showvalue=False,
                                    highlightthickness=0, state="disabled",
                                    command=self._func_slider_moved)
        self.func_slider.pack(fill="x", padx=8, pady=(0, 6))
        self._bind_scale_click(self.func_slider, lambda _e: self._queue_slider_update("FUNC"))
        self.func_slider_status = ttk.Label(func_adjust, text="", foreground=GRAY, anchor="center")
        self.func_slider_status.pack(fill="x", pady=(2, 4))
        ttk.Label(parent, text="HOME has no documented CAT command. CH STEP cannot be assigned to the FUNC button.",
                  foreground=GRAY, wraplength=900).grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))

    @staticmethod
    def _mode_name(mode):
        return {"1": "LSB", "2": "USB", "3": "CW-U", "4": "FM", "5": "AM",
                "6": "RTTY-L", "7": "CW-L", "8": "DATA-L", "9": "RTTY-U",
                "A": "DATA-FM", "B": "FM-N", "C": "DATA-U", "D": "AM-N",
                "E": "PSK", "F": "DATA-FM-N", "H": "C4FM-DN", "I": "C4FM-VW"}.get(mode, "—")

    @staticmethod
    def _format_frequency(frequency):
        return f"{int(frequency):,}".replace(",", ".")

    @staticmethod
    def _frequency_in_rx_range(frequency):
        frequency = int(frequency)
        return 30_000 <= frequency <= 174_000_000 or 400_000_000 <= frequency <= 470_000_000

    @classmethod
    def _frequency_from_entry_digits(cls, entry_text):
        # Explicit thousands groups use the radio display convention. Missing
        # right-hand groups are padded (14.400 -> 14.400.000 Hz).
        entry_text = str(entry_text).strip()
        for separator in (".", ","):
            if separator not in entry_text:
                continue
            groups = entry_text.split(separator)
            if (len(groups) == 2 and 1 <= len(groups[0]) <= 3
                    and groups[0].isdigit() and 1 <= len(groups[1]) <= 2
                    and groups[1].isdigit()):
                # Short decimal MHz input: 14,3 or 14.3 means 14.300 MHz.
                return int(groups[0]) * 1_000_000 + int(groups[1]) * 10 ** (6 - len(groups[1]))
            if (len(groups) <= 3 and 1 <= len(groups[0]) <= 3
                    and groups[0].isdigit()
                    and all(len(group) == 3 and group.isdigit() for group in groups[1:])):
                grouped_digits = "".join(groups)
                grouped_digits += "0" * (3 - len(groups)) * 3
                return int(grouped_digits)
            break

        digits = "".join(char for char in entry_text if char.isdigit())
        # Four digits can be entered as MHz with one decimal (1448 -> 144.8 MHz).
        if len(digits) == 4:
            mhz_candidate = int(digits[:3]) * 1_000_000 + int(digits[3]) * 100_000
            if cls._frequency_in_rx_range(mhz_candidate):
                return mhz_candidate
        # Five digits are commonly entered as kHz (14400 -> 14.400 MHz).
        # Check this before right-padding, which would turn 14400 into 144 MHz.
        if len(digits) == 5:
            khz_candidate = int(digits) * 1000
            if cls._frequency_in_rx_range(khz_candidate):
                return khz_candidate
        right_padded = int(digits.ljust(9, "0"))
        if not cls._frequency_in_rx_range(right_padded):
            # Compact kHz entry resolves values that would land in an RX gap.
            khz_candidate = int(digits) * 1000
            if cls._frequency_in_rx_range(khz_candidate):
                return khz_candidate
        return right_padded

    def _update_tuning_display(self, frequency, mode, step_khz=None):
        self.frequency_hz = int(frequency)
        self.current_mode = mode
        self.frequency_label.config(text=f"{self._format_frequency(frequency)} Hz")
        self.mode_var.set(mode)
        mode_name = self._mode_name(mode)
        step_text = f"Step: {step_khz:g} kHz" if step_khz is not None else "Scroll the dial to tune"
        self.frequency_hint.config(text=f"{mode_name}  •  {step_text}")

    def _open_frequency_dialog(self, _event=None):
        dialog = tk.Toplevel(self)
        dialog.title("Set MAIN Frequency")
        dialog.transient(self)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=("Enter up to 9 digits. Punctuation is added automatically.\n"
                  "A period or comma can separate MHz decimals or thousands groups.\n"
                  "Examples: 14,3 becomes 14.300.000 Hz; 1448 becomes 144.800.000 Hz; "
                  "14400 becomes 14.400.000 Hz; "
                  "27555 becomes 27.555.000 Hz."),
            justify="left", wraplength=360,
        ).pack(anchor="w", pady=(0, 8))

        frequency_var = tk.StringVar()
        entry = ttk.Entry(body, textvariable=frequency_var, width=20, font=("TkDefaultFont", 14))
        entry.pack(fill="x", pady=(0, 10))
        preview_var = tk.StringVar(value="Target frequency: —")
        ttk.Label(body, textvariable=preview_var, foreground=GRAY).pack(anchor="w", pady=(0, 8))

        def apply_frequency(_event=None):
            entry_text = frequency_var.get().strip()
            digits = "".join(char for char in entry_text if char.isdigit())[:9]
            if not digits:
                messagebox.showwarning("Frequency", "Enter a frequency.", parent=dialog)
                return "break"
            if entry_text.endswith((".", ",")):
                messagebox.showwarning(
                    "Frequency", "Complete the frequency after the separator.", parent=dialog
                )
                return "break"
            target = self._frequency_from_entry_digits(entry_text)
            if not 30_000 <= target <= 470_000_000:
                messagebox.showerror(
                    "Frequency out of range",
                    "Enter a frequency between 000.030.000 and 470.000.000 Hz.",
                    parent=dialog,
                )
                return "break"
            if not self.need_conn():
                return "break"

            radio = self.radio

            def job():
                radio.send(f"FA{target:09d};")
                frequency = int(radio.query("FA;", "FA")[2:-1])
                mode = self._read_main_mode(radio)
                item, _ = self._ch_step_for_mode(mode)
                step_raw = radio.read_menu(item)
                step_khz = float(dict(item.opts)[step_raw].split()[0])
                return frequency, mode, item, step_raw, step_khz

            def then(result):
                frequency, mode, item, step_raw, step_khz = result
                self._update_tuning_display(frequency, mode, step_khz)
                self._show_ch_step((step_raw, item, self._mode_name(mode)))

            if self.run_bg(job, "Set MAIN frequency", then):
                dialog.destroy()
            return "break"

        def format_as_typed(_event=None):
            original = frequency_var.get()
            cursor = entry.index(tk.INSERT)
            digits_before_cursor = sum(char.isdigit() for char in original[:cursor])
            digits = "".join(char for char in original if char.isdigit())[:9]
            if not digits:
                preview_var.set("Target frequency: —")
            elif original.endswith((".", ",")):
                preview_var.set("Target frequency: continue typing")
            else:
                target = self._frequency_from_entry_digits(original)
                if self._frequency_in_rx_range(target):
                    preview_var.set(f"Target frequency: {self._format_frequency(target)} Hz")
                else:
                    preview_var.set("Target frequency: out of range")
            separator_count = original.count(".") + original.count(",")
            groups = original.replace(",", ".").split(".")
            keep_typed_groups = (
                separator_count > 0
                and len(groups) <= 3
                and 1 <= len(groups[0]) <= 3
                and groups[0].isdigit()
                and all(len(group) <= 3 and group.isdigit() for group in groups[1:-1])
                and (not groups[-1] or (len(groups[-1]) <= 3 and groups[-1].isdigit()))
                and (len(groups) < 3 or len(groups[1]) == 3)
            )
            if keep_typed_groups:
                masked = original.replace(",", ".")
            else:
                right_padded = int(digits.ljust(9, "0")) if digits else 0
                khz_candidate = int(digits) * 1000 if digits else 0
                mhz_candidate = (int(digits[:3]) * 1_000_000 + int(digits[3]) * 100_000
                                 if len(digits) == 4 else 0)
                if digits and len(digits) == 4 and self._frequency_in_rx_range(mhz_candidate):
                    masked = f"{digits[:3]}.{digits[3:]}"
                elif (digits and len(digits) > 3
                        and not self._frequency_in_rx_range(right_padded)
                        and self._frequency_in_rx_range(khz_candidate)):
                    masked = f"{digits[:-3]}.{digits[-3:]}"
                else:
                    masked = ".".join(digits[index:index + 3] for index in range(0, len(digits), 3))
            if masked != original:
                frequency_var.set(masked)
                if keep_typed_groups:
                    separators_before_cursor = sum(char in ".," for char in original[:cursor])
                    new_cursor = digits_before_cursor + separators_before_cursor
                else:
                    new_cursor = digits_before_cursor + max(0, (digits_before_cursor - 1) // 3)
                entry.icursor(min(new_cursor, len(masked)))

        entry.bind("<KeyRelease>", format_as_typed)
        entry.bind("<Return>", apply_frequency)
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=apply_frequency).pack(side="right", padx=(0, 6))
        dialog.grab_set()
        entry.focus_set()
        return "break"

    def _start_frequency_poll(self):
        if self.radio and self.frequency_poll_after_id is None:
            self.frequency_poll_after_id = self.after(500, self._poll_frequency)

    def _poll_frequency(self):
        self.frequency_poll_after_id = None
        if not self.radio:
            return
        if self.busy:
            self.frequency_poll_after_id = self.after(250, self._poll_frequency)
            return
        radio = self.radio

        def job():
            try:
                frame = radio.query("FA;", "FA")
                return int(frame[2:-1])
            except Exception:  # noqa: BLE001 - a falha de um ciclo não encerra a leitura periódica
                return None

        def then(frequency):
            if radio is self.radio and frequency is not None and frequency != self.frequency_hz:
                self.frequency_hz = frequency
                self.frequency_label.config(text=f"{self._format_frequency(frequency)} Hz")
            self._start_frequency_poll()

        if not self.run_bg(job, "Periodic frequency read", then, quiet=True):
            self.frequency_poll_after_id = self.after(250, self._poll_frequency)

    def _select_band(self, band_code):
        if not self.need_conn():
            return
        if self.busy:
            self.pending_band_selection = band_code
            return
        radio = self.radio

        def job():
            if band_code == "11m":
                # O CAT Band Select não define uma entrada de 11 m. Sintoniza
                # 27.555 MHz (frequência de chamada DX em USB) diretamente.
                radio.send(f"FA{27_555_000:09d};")
            else:
                # O rádio recupera a própria memória Band Stack, sem impor FA.
                radio.send(f"BS0{band_code};")
            frequency = int(radio.query("FA;", "FA")[2:-1])
            mode = self._read_main_mode(radio)
            item, _ = self._ch_step_for_mode(mode)
            step_raw = radio.read_menu(item)
            step_khz = float(dict(item.opts)[step_raw].split()[0])
            return frequency, mode, item, step_raw, step_khz

        def then(result):
            frequency, mode, item, step_raw, step_khz = result
            self._update_tuning_display(frequency, mode, step_khz)
            self._show_ch_step((step_raw, item, self._mode_name(mode)))

        self.run_bg(job, "Band selection", then)

    def _draw_frequency_knob(self):
        canvas = self.frequency_knob
        canvas.delete("all")
        cx = cy = 48
        # Aro e corpo do dial, com bordas concêntricas em relevo.
        canvas.create_oval(5, 5, 91, 91, fill="#111315", outline="#08090a", width=2)
        canvas.create_oval(7, 7, 89, 89, fill="#303438", outline="#85898c", width=2)
        canvas.create_oval(11, 11, 85, 85, fill="#1c1f22", outline="#090a0b", width=2)
        canvas.create_oval(15, 15, 81, 81, fill="#34383b", outline="#555a5e", width=1)

        # Ranhuras radiais na face, inspiradas no acabamento facetado do dial físico.
        for groove in range(24):
            angle = math.radians(groove * 15 - 90)
            inner = 12
            outer = 31
            x1, y1 = cx + inner * math.cos(angle), cy + inner * math.sin(angle)
            x2, y2 = cx + outer * math.cos(angle), cy + outer * math.sin(angle)
            shade = "#666b6f" if groove % 2 == 0 else "#202326"
            canvas.create_line(x1, y1, x2, y2, fill=shade, width=2)
            if groove % 2 == 0:
                canvas.create_line(x1 + 1, y1 + 1, x2 + 1, y2 + 1,
                                   fill="#282c2f", width=1)

        # Rebaixo central com um pequeno ressalto circular no miolo.
        canvas.create_oval(30, 30, 66, 66, fill="#25292c", outline="#17191b", width=2)
        canvas.create_oval(34, 34, 62, 62, fill="#111315", outline="#555a5e", width=2)
        canvas.create_oval(39, 39, 57, 57, fill="#25292c", outline="#777c80", width=1)
        canvas.create_oval(43, 42, 53, 52, fill="#171a1c", outline="#0b0c0d", width=1)

        # Pequeno marcador luminoso que acompanha a rolagem do dial.
        pointer_angle = math.radians(-140 + (self.knob_position % 9) * 35)
        marker_x = cx + 37 * math.cos(pointer_angle)
        marker_y = cy + 37 * math.sin(pointer_angle)
        canvas.create_oval(marker_x - 2.5, marker_y - 2.5, marker_x + 2.5, marker_y + 2.5,
                           fill="#d6d9dc", outline="#111315", width=1)

    def _frequency_wheel(self, event):
        if getattr(event, "num", None) == 4:
            ticks = 1
        elif getattr(event, "num", None) == 5:
            ticks = -1
        else:
            ticks = 1 if event.delta > 0 else -1
        self.pending_tune += ticks
        self.knob_position = (self.knob_position + ticks) % 9
        self._draw_frequency_knob()
        self._drain_frequency_tune()
        return "break"

    def _drain_frequency_tune(self):
        if not self.radio:
            self.pending_tune = 0
            self.need_conn()
            return
        if self.busy:
            if not self.tune_retry_scheduled:
                self.tune_retry_scheduled = True
                self.after(120, self._retry_frequency_tune)
            return
        if not self.pending_tune or not self.radio:
            return
        self.tune_retry_scheduled = False
        ticks = self.pending_tune
        self.pending_tune = 0
        radio = self.radio
        def job():
            mode = self._read_main_mode(radio)
            item, _ = self._ch_step_for_mode(mode)
            step_raw = radio.read_menu(item)
            step_khz = float(dict(item.opts)[step_raw].split()[0])
            frame = radio.query("FA;", "FA")
            frequency = int(frame[2:-1])
            target = max(30000, min(470000000, frequency + round(ticks * step_khz * 1000)))
            radio.send(f"FA{target:09d};")
            actual = int(radio.query("FA;", "FA")[2:-1])
            return actual, mode, item, step_raw, step_khz
        def then(result):
            frequency, mode, item, step_raw, step_khz = result
            self._update_tuning_display(frequency, mode, step_khz)
            self._show_ch_step((step_raw, item, self._mode_name(mode)))
        self.run_bg(job, "Frequency tuning", then)

    def _retry_frequency_tune(self):
        self.tune_retry_scheduled = False
        self._drain_frequency_tune()

    def _set_radio_mode(self, mode):
        if not self.radio:
            self.mode_var.set(self.current_mode or "")
            self.need_conn()
            return
        radio = self.radio
        def job():
            radio.send(f"MD0{mode};")
            actual_mode = self._read_main_mode(radio)
            item, _ = self._ch_step_for_mode(actual_mode)
            step_raw = radio.read_menu(item)
            step_khz = float(dict(item.opts)[step_raw].split()[0])
            frequency = int(radio.query("FA;", "FA")[2:-1])
            return frequency, actual_mode, item, step_raw, step_khz
        def then(result):
            frequency, actual_mode, item, step_raw, step_khz = result
            self._update_tuning_display(frequency, actual_mode, step_khz)
            self._show_ch_step((step_raw, item, self._mode_name(actual_mode)))
        self.run_bg(job, f"Changing mode to {self._mode_name(mode)}", then)

    def _func_parameter_specs(self):
        return {
            "3": {"title": "SCOPE COLOR", "min": 1, "max": 11, "step": 1,
                  "read": "SS03;", "prefix": "SS03", "decode": lambda r: int(r, 16) + 1,
                  "encode": lambda v: "SS03" + "0123456789A"[int(v) - 1] + ";",
                  "format": lambda v: f"COLOR-{int(v)}"},
            "4": {"title": "CONTRAST", "min": 0, "max": 20, "step": 1,
                  "read": "DA;", "prefix": "DA", "decode": lambda r: int(r[2:4]),
                  "da_slot": 2, "format": lambda v: str(int(v))},
            "5": {"title": "DIMMER", "min": 0, "max": 20, "step": 1,
                  "read": "DA;", "prefix": "DA", "decode": lambda r: int(r[4:6]),
                  "da_slot": 4, "format": lambda v: str(int(v))},
            "7": {"title": "MIC GAIN", "min": 0, "max": 100, "step": 1,
                  "read": "MG;", "prefix": "MG", "decode": int,
                  "encode": lambda v: "MG" + f"{int(v):03d}" + ";",
                  "format": lambda v: str(int(v))},
            "8": {"title": "PROC LEVEL", "min": 0, "max": 100, "step": 1,
                  "read": "PL;", "prefix": "PL", "decode": int,
                  "encode": lambda v: "PL" + f"{int(v):03d}" + ";",
                  "format": lambda v: str(int(v))},
            "9": {"title": "AMC LEVEL", "min": 1, "max": 100, "step": 1,
                  "read": "AO;", "prefix": "AO", "decode": int,
                  "encode": lambda v: "AO" + f"{int(v):03d}" + ";",
                  "format": lambda v: str(int(v))},
            "A": {"title": "VOX GAIN", "min": 0, "max": 100, "step": 1,
                  "read": "VG;", "prefix": "VG", "decode": int,
                  "encode": lambda v: "VG" + f"{int(v):03d}" + ";",
                  "format": lambda v: str(int(v))},
            "B": {"title": "VOX DELAY", "min": 0, "max": 33, "step": 1,
                  "read": "VD;", "prefix": "VD", "decode": int,
                  "encode": lambda v: "VD" + f"{int(v):02d}" + ";",
                  "format": self._vox_delay_label},
            "D": {"title": "RF POWER (W)", "min": 5, "max": 100, "step": 1,
                  "read": "PC;", "prefix": "PC", "decode": lambda r: int(r[1:4]),
                  "encode": lambda v: "PC2" + f"{int(v):03d}" + ";",
                  "format": lambda v: f"{int(v)} W"},
            "E": {"title": "MONI LEVEL", "min": 0, "max": 100, "step": 1,
                  "read": "ML1;", "prefix": "ML1", "decode": int,
                  "encode": lambda v: "ML1" + f"{int(v):03d}" + ";",
                  "format": lambda v: str(int(v))},
            "F": {"title": "CW SPEED (WPM)", "min": 4, "max": 60, "step": 1,
                  "read": "KS;", "prefix": "KS", "decode": int,
                  "encode": lambda v: "KS" + f"{int(v):03d}" + ";",
                  "format": lambda v: f"{int(v)} WPM"},
            "G": {"title": "CW PITCH (Hz)", "min": 300, "max": 1050, "step": 10,
                  "read": "KP;", "prefix": "KP", "decode": lambda r: 300 + int(r) * 10,
                  "encode": lambda v: "KP" + f"{int((v - 300) / 10):02d}" + ";",
                  "format": lambda v: f"{int(v)} Hz"},
            "H": {"title": "BK-DELAY", "min": 0, "max": 33, "step": 1,
                  "read": "SD;", "prefix": "SD", "decode": int,
                  "encode": lambda v: "SD" + f"{int(v):02d}" + ";",
                  "format": self._bk_delay_label},
        }

    @staticmethod
    def _vox_delay_label(code):
        code = int(code)
        ms = [30, 50, 100, 150, 200, 250][code] if code < 6 else (code - 3) * 100
        return f"{ms} ms"

    @staticmethod
    def _bk_delay_label(code):
        code = int(code)
        ms = [30, 50, 100, 150, 200, 250][code] if code < 6 else (code - 3) * 100
        return f"{ms} ms"

    def _func_slider_moved(self, value):
        if self.func_active:
            self.func_slider_value.config(text=self.func_active["format"](float(value)))
            if not self.setting_slider_from_radio:
                self._queue_slider_update("FUNC")

    def _select_func_parameter(self, code):
        """Select a local adjustment target; never change the radio's FUNC assignment."""
        self.func_control_var.set(code)
        self.func_active = None
        self.func_slider.configure(state="disabled")
        self.func_slider_value.config(text="")
        self.pending_slider_updates = [name for name in self.pending_slider_updates if name != "FUNC"]
        if self.busy:
            self.pending_func_parameter_read = code
            self.func_slider_status.config(text="Waiting for the current operation...", foreground=AMBER)
            return
        self._load_func_parameter(code)

    def _quick_scale_moved(self, name, value):
        if name in self.quick_value_labels and not self.setting_slider_from_radio:
            self.quick_value_labels[name].config(text=self.quick_specs[name]["display"](float(value)))
            self._queue_slider_update(name)

    def _queue_slider_update(self, name):
        if not self.radio:
            return
        if name not in self.pending_slider_updates:
            self.pending_slider_updates.append(name)
        self._drain_slider_updates()

    def _drain_slider_updates(self):
        if self.busy or not self.pending_slider_updates or not self.radio:
            return
        name = self.pending_slider_updates.pop(0)
        if name == "FUNC":
            self._set_func_parameter()
        else:
            self.quick_set(name)

    def _bind_scale_click(self, scale, on_change):
        scale.bind("<Button-1>", lambda event, widget=scale, callback=on_change:
                   self._scale_track_click(widget, event, callback))
        scale.bind("<ButtonRelease-1>", on_change)
        scale.bind("<KeyRelease>", on_change)
        scale.bind("<MouseWheel>", lambda event, widget=scale, callback=on_change:
                   self._scale_mousewheel(widget, event, callback))
        scale.bind("<Button-4>", lambda event, widget=scale, callback=on_change:
                   self._scale_mousewheel(widget, event, callback, 1))
        scale.bind("<Button-5>", lambda event, widget=scale, callback=on_change:
                   self._scale_mousewheel(widget, event, callback, -1))

    def _scale_track_click(self, scale, event, on_change):
        """Clicking the track jumps to that value; clicking the knob still drags it."""
        vertical = scale.cget("orient") == "vertical"
        axis = 1 if vertical else 0
        pointer = event.y if vertical else event.x
        current_pos = scale.coords()[axis]
        knob_half = int(scale.cget("sliderlength")) / 2
        if abs(pointer - current_pos) <= knob_half:
            return None
        min_pos = scale.coords(float(scale.cget("from")))[axis]
        max_pos = scale.coords(float(scale.cget("to")))[axis]
        if max_pos == min_pos:
            return "break"
        fraction = max(0.0, min(1.0, (pointer - min_pos) / (max_pos - min_pos)))
        low = float(scale.cget("from"))
        high = float(scale.cget("to"))
        resolution = float(scale.cget("resolution"))
        value = low + fraction * (high - low)
        if resolution > 0:
            value = low + round((value - low) / resolution) * resolution
        scale.set(value)
        on_change(event)
        return "break"

    @staticmethod
    def _scale_mousewheel(scale, event, on_change, linux_direction=0):
        direction = linux_direction or (1 if event.delta > 0 else -1)
        step = float(scale.cget("resolution"))
        if step <= 0:
            step = max(1.0, (float(scale.cget("to")) - float(scale.cget("from"))) / 100)
        low, high = sorted((float(scale.cget("from")), float(scale.cget("to"))))
        value = max(low, min(high, float(scale.get()) + direction * step))
        scale.set(value)
        on_change(event)
        return "break"

    def _show_func_parameter(self, code, value):
        spec = self._func_parameter_specs().get(code)
        if not spec:
            self.func_active = None
            title = ("Select a parameter" if not code
                     else "SCOPE LEVEL (no quick control)" if code == "1"
                     else "PEAK is controlled by the D-PEAK slider" if code == "2"
                     else "No adjustment available")
            self.func_slider_title.config(text=title)
            self.func_slider_value.config(text="")
            hint = ("D-PEAK is available in Quick Controls." if code == "2" else "")
            self.func_slider_status.config(text=hint, foreground=GRAY)
            self.func_slider.configure(state="disabled")
            return
        self.func_active = spec
        self.func_slider_title.config(text=spec["title"])
        self.func_slider.configure(from_=spec["min"], to=spec["max"],
                                   resolution=spec["step"], state="normal")
        if "FUNC" not in self.pending_slider_updates:
            self.setting_slider_from_radio = True
            self.func_slider_var.set(value)
            self.setting_slider_from_radio = False
            shown_value = value
        else:
            shown_value = self.func_slider_var.get()
        self.func_slider_value.config(text=spec["format"](shown_value))
        self.func_slider_status.config(text=f"Radio: {spec['format'](value)}", foreground=GREEN)

    def _load_func_parameter(self, code, after=None):
        if self.busy:
            self.pending_func_parameter_read = code
            self.func_slider_status.config(text="Waiting for the current operation...", foreground=AMBER)
            return
        spec = self._func_parameter_specs().get(code)
        if not spec:
            self._show_func_parameter(code, 0)
            if after:
                after()
            return
        radio = self.radio
        if not radio:
            self.func_slider_title.config(text=spec["title"])
            self.func_slider_status.config(text="Connect to the radio to read this value.", foreground=GRAY)
            self.func_slider.configure(state="disabled")
            return
        def job():
            frame = radio.query(spec["read"], spec["prefix"])
            return spec["decode"](frame[len(spec["prefix"]):-1])
        def then(value):
            if code != self.func_control_var.get():
                return
            self._show_func_parameter(code, value)
            if after:
                after()
        self.func_slider_title.config(text=spec["title"])
        self.func_slider_status.config(text="Reading current value...", foreground=AMBER)
        self.run_bg(job, f"Reading {spec['title']}", then)

    def _set_func_parameter(self, _event=None):
        if not self.func_active or not self.radio:
            return
        code = self.func_control_var.get()
        spec = self.func_active
        value = self.func_slider_var.get()
        radio = self.radio
        def job():
            if "da_slot" in spec:
                frame = radio.query("DA;", "DA")
                raw = frame[2:-1]
                slot = spec["da_slot"]
                raw = raw[:slot] + f"{int(value):02d}" + raw[slot + 2:]
                command = "DA" + raw + ";"
            else:
                command = spec["encode"](value)
            radio.send(command)
            frame = radio.query(spec["read"], spec["prefix"])
            return spec["decode"](frame[len(spec["prefix"]):-1])
        def then(actual):
            if code == self.func_control_var.get():
                self._show_func_parameter(code, actual)
        self.func_slider_status.config(text="Sending to radio...", foreground=AMBER)
        self.run_bg(job, f"Setting {spec['title']}", then)

    def _register_quick(self, name, variable, read_cmd, prefix, decode, make_set, display,
                        status_parent, value_label=None):
        self.quick_vars[name] = variable
        self.quick_specs[name] = {"read_cmd": read_cmd, "prefix": prefix, "decode": decode,
                                  "make_set": make_set, "display": display}
        status = ttk.Label(status_parent, text="Waiting for read", foreground=GRAY)
        self.quick_status[name] = status
        if value_label is not None:
            self.quick_value_labels[name] = value_label

    def _quick_popup(self, parent, name, variable, values, column, read_cmd, prefix,
                     make_set, display, decode):
        card = ttk.LabelFrame(parent, text=name, padding=8)
        card.grid(row=0, column=column, sticky="ew", padx=4, pady=5)
        combo = ttk.Combobox(card, textvariable=variable, values=values, state="readonly", width=27,
                             postcommand=self._refresh_ch_step_choices if name == "CH STEP" else None)
        combo.pack(fill="x")
        combo.bind("<<ComboboxSelected>>", lambda _e, n=name: self.quick_set(n))
        self.quick_widgets[name] = combo
        self._register_quick(name, variable, read_cmd, prefix,
                             decode, make_set, display, card)
        self.quick_status[name].pack(anchor="w", pady=(5, 0))

    @staticmethod
    def _ch_step_for_mode(mode):
        """Select the FTX-1's dedicated AM/FM channel-step menu item."""
        am_modes = {"5", "D"}  # AM, AM-N
        fm_modes = {"4", "A", "B", "F", "H", "I"}  # FM and FM-based digital modes
        mode_names = {"1": "LSB", "2": "USB", "3": "CW-U", "4": "FM", "5": "AM",
                      "6": "RTTY-L", "7": "CW-L", "8": "DATA-L", "9": "RTTY-U",
                      "A": "DATA-FM", "B": "FM-N", "C": "DATA-U", "D": "AM-N",
                      "E": "PSK", "F": "DATA-FM-N", "H": "C4FM-DN", "I": "C4FM-VW"}
        if mode in am_modes:
            key = "030605"
        elif mode in fm_modes:
            key = "030606"
        else:
            key = "030604"
        return BY_KEY[key], mode_names.get(mode, "Outro")

    @staticmethod
    def _read_main_mode(radio):
        frame = radio.query("MD0;", "MD0")
        return frame[3:-1]

    def _show_ch_step(self, result):
        raw, item, mode_label = result
        self.ch_step_item = item
        option_codes = [code for code, _label in item.opts]
        try:
            radio_index = option_codes.index(str(raw))
        except ValueError:
            radio_index = 0
        if "CH STEP" in self.pending_slider_updates:
            selected_index = max(0, min(len(item.opts) - 1, self.ch_step_var.get()))
        else:
            selected_index = radio_index
        self.setting_ch_step_from_radio = True
        self.ch_step_scale.configure(from_=0, to=max(0, len(item.opts) - 1),
                                     resolution=1, state="normal")
        self.ch_step_var.set(selected_index)
        self.setting_ch_step_from_radio = False
        value = (item.opts[selected_index][1] if "CH STEP" in self.pending_slider_updates
                 else dict(item.opts).get(str(raw), "unknown"))
        self.ch_step_value.config(text=value, foreground=GREEN)
        if self.current_mode:
            step_khz = float(value.split()[0])
            self.frequency_hint.config(
                text=f"{mode_label}  •  Step: {step_khz:g} kHz")

    def _ch_step_slider_moved(self, value):
        if not self.ch_step_item or self.setting_ch_step_from_radio:
            return
        options = self.ch_step_item.opts
        index = max(0, min(len(options) - 1, int(round(float(value)))))
        self.ch_step_value.config(text=options[index][1], foreground=AMBER)
        self._queue_slider_update("CH STEP")

    def _refresh_ch_step_choices(self):
        """Refresh the menu as it opens, since the radio mode may have changed."""
        if not self.radio or self.busy:
            return
        try:
            mode = self._read_main_mode(self.radio)
            item, mode_label = self._ch_step_for_mode(mode)
            raw = self.radio.read_menu(item)
            step_khz = float(dict(item.opts)[raw].split()[0])
            frequency = int(self.radio.query("FA;", "FA")[2:-1])
        except Exception as exc:  # noqa: BLE001
            self.log(f"Could not refresh CH STEP: {exc}")
            return
        self._show_ch_step((raw, item, mode_label))
        self._update_tuning_display(frequency, mode, step_khz)

    def quick_read_all(self, after=None):
        if not self.need_conn():
            return
        radio = self.radio
        def job():
            results = {}
            for name, spec in self.quick_specs.items():
                try:
                    if name == "CH STEP":
                        mode = self._read_main_mode(radio)
                        item, mode_label = self._ch_step_for_mode(mode)
                        results[name] = ((radio.read_menu(item), item, mode_label), None)
                        continue
                    frame = radio.query(spec["read_cmd"], spec["prefix"])
                    results[name] = (spec["decode"](frame[len(spec["prefix"]):-1]), None)
                except Exception as exc:  # continue reading other controls if one command fails
                    results[name] = (None, str(exc))
            try:
                mode = self._read_main_mode(radio)
                item, _ = self._ch_step_for_mode(mode)
                step_raw = radio.read_menu(item)
                step_khz = float(dict(item.opts)[step_raw].split()[0])
                frequency = int(radio.query("FA;", "FA")[2:-1])
                results["__tuning"] = ((frequency, mode, item, step_raw, step_khz), None)
            except Exception as exc:  # noqa: BLE001
                results["__tuning"] = (None, str(exc))
            return results
        def then(results):
            tuning, tuning_error = results.get("__tuning", (None, "not read"))
            for name, (value, error) in results.items():
                if name == "__tuning":
                    continue
                if error:
                    self.quick_status[name].config(text="No response", foreground=RED)
                    self.log(f"Could not read {name}: {error}")
                elif name == "CH STEP":
                    self._show_ch_step(value)
                else:
                    self._show_quick_value(name, value)
            self.log("Quick controls updated.")
            if not tuning_error:
                frequency, mode, item, step_raw, step_khz = tuning
                self._update_tuning_display(frequency, mode, step_khz)
                self._show_ch_step((step_raw, item, self._mode_name(mode)))
            selected_code = self.func_control_var.get()
            if selected_code:
                self._load_func_parameter(selected_code, after=after)
            elif after:
                after()
        self.run_bg(job, "Reading quick controls", then)

    def _show_quick_value(self, name, value):
        variable = self.quick_vars[name]
        spec = self.quick_specs[name]
        if name not in self.pending_slider_updates:
            self.setting_slider_from_radio = True
            variable.set(value)
            self.setting_slider_from_radio = False
            shown = spec["display"](value)
        else:
            shown = spec["display"](variable.get())
        if name in self.quick_value_labels:
            self.quick_value_labels[name].config(text=shown)
        self.quick_status[name].config(text=f"Radio: {shown}", foreground=GREEN)

    def quick_set(self, name):
        if name == "CH STEP":
            self._set_ch_step()
            return
        if not self.need_conn():
            return
        spec = self.quick_specs[name]
        try:
            command = spec["make_set"]()
        except (ValueError, IndexError) as exc:
            self.log(f"Invalid value for {name}: {exc}")
            return
        radio = self.radio
        def job():
            radio.send(command)
            frame = radio.query(spec["read_cmd"], spec["prefix"])
            return spec["decode"](frame[len(spec["prefix"]):-1])
        def then(value):
            self._show_quick_value(name, value)
            self.log(f"{name} set to {spec['display'](value)}")
        self.quick_status[name].config(text="Sending…", foreground=AMBER)
        self.run_bg(job, f"Setting {name}", then)

    def _set_ch_step(self):
        if not self.need_conn():
            return
        if not self.ch_step_item:
            self.log("Read CH STEP after connecting before selecting a step.")
            return
        try:
            index = int(round(self.ch_step_var.get()))
            options = self.ch_step_item.opts
            selected_label = options[max(0, min(len(options) - 1, index))][1]
            requested_step = float(selected_label.split()[0])
        except (IndexError, ValueError, TypeError):
            self.log("Select a valid CH STEP value.")
            return
        radio = self.radio
        def job():
            mode = self._read_main_mode(radio)
            item, mode_label = self._ch_step_for_mode(mode)
            options = dict(item.opts)
            code = min(options,
                       key=lambda candidate: abs(float(options[candidate].split()[0]) - requested_step))
            raw = radio.write_menu(item, code)
            return raw, item, mode_label
        def then(result):
            self._show_ch_step(result)
            self.log(f"CH STEP ({result[2]}) set to {dict(result[1].opts).get(result[0], result[0])} kHz.")
        self.quick_status["CH STEP"].config(text="Sending…", foreground=AMBER)
        self.run_bg(job, "Setting CH STEP", then)

    # -- log ----------------------------------------------------------------
    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.logbox.config(state="normal")
        self.logbox.insert("end", f"{ts}  {msg}\n")
        if int(self.logbox.index("end-1c").split(".")[0]) > 1500:
            self.logbox.delete("1.0", "300.0")
        self.logbox.see("end")
        self.logbox.config(state="disabled")

    def _cat_log(self, direction, text):          # chamado das threads
        if self.cat_var.get():
            self.ui(lambda: self.log(f"{direction}  {text}"))

    def progress(self, i, n, what=""):
        self.ui(lambda: self.prog_lbl.config(text=f"{what} {i}/{n}" if n else ""))

    # -- conexao --------------------------------------------------------------
    def refresh_ports(self):
        detected = list(list_ports.comports())
        ports = [f"{p.device}{SEP}{p.description}" for p in detected]
        self.port_cb.config(values=ports)
        # O CP2105 expõe mais de uma interface. Para CAT, usar a Enhanced COM Port.
        enhanced = [p for p in detected
                    if "cp2105" in (p.description or "").casefold()
                    and "enhanced" in (p.description or "").casefold()]
        if enhanced:
            preferred = enhanced[0]
            selected = f"{preferred.device}{SEP}{preferred.description}"
            self.port_var.set(selected)
            return True
        elif ports and not self.port_var.get():
            self.port_var.set(ports[0])
        return False

    def toggle_connect(self):
        if self.radio:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get().split(SEP)[0].strip()
        if not port:
            messagebox.showwarning("Port", "Select the FTX-1 serial port.")
            return
        try:
            ser = serial.Serial()
            ser.port = port
            ser.baudrate = int(self.baud_var.get())
            ser.bytesize = 8
            ser.parity = "N"
            ser.stopbits = 1
            ser.timeout = 0.05
            ser.write_timeout = 1
            # DTR/RTS desligados antes de abrir: o manual avisa que, se RPTT SELECT
            # estiver em RTS/DTR, essas linhas comandam o PTT.
            ser.dtr = False
            ser.rts = False
            ser.open()
        except (serial.SerialException, ValueError, OSError) as e:
            messagebox.showerror("Port Open Error", str(e))
            return
        self.radio = Radio(ser, logger=self._cat_log)
        self.btn_conn.config(text="Disconnect")
        self.conn_lbl.config(text="Connecting…", foreground=AMBER)
        self.log(f"Port {port} opened at {self.baud_var.get()} bps, 8N1.")

        def job():
            try:
                rid = self.radio.identify()
                fw = self.radio.firmware(0)
            except CatError:
                self.ui(lambda: self.conn_lbl.config(
                    text="No response from radio", foreground=RED))
                self.ui(lambda: self.log(
                    "No response to ID;. Check the CAT-1 (Enhanced COM Port), match the baud rate "
                    "to CAT-1 RATE (38400 by default), and use MAIN firmware 1.08 or later."))
                return
            self.fw = fw
            self.ui(lambda: self.conn_lbl.config(
                text=f"Connected • ID {rid} • MAIN FW {fw}", foreground=GREEN))
            self.ui(lambda: self.log(f"Radio responded: ID {rid}, MAIN firmware {fw}."))
            self.ui(self._start_frequency_poll)
            follow_up = self.read_all_visible if self.rows and self.auto_var.get() and self.cur_group else None
            self.ui(lambda: self.quick_read_all(follow_up))

        threading.Thread(target=job, daemon=True).start()

    def disconnect(self):
        self.stop.set()
        self.pending_band_selection = None
        if self.frequency_poll_after_id is not None:
            self.after_cancel(self.frequency_poll_after_id)
            self.frequency_poll_after_id = None
        if self.radio:
            try:
                self.radio.ser.close()
            except Exception:
                pass
        self.radio = None
        self.btn_conn.config(text="Connect")
        self.conn_lbl.config(text="Disconnected", foreground=GRAY)
        self.log("Disconnected.")

    def _close(self):
        self.disconnect()
        self.destroy()

    def need_conn(self):
        if not self.radio:
            messagebox.showinfo("Connection", "Connect to the radio first.")
            return False
        return True

    # -- execucao em segundo plano ------------------------------------------
    def run_bg(self, job, title, then=None, quiet=False):
        if self.busy:
            self.log("Wait for the current operation to finish, or click Stop.")
            return False
        self.busy = True
        self.stop.clear()
        if not quiet:
            self.log(f"{title}…")

        def runner():
            result, err = None, None
            try:
                result = job()
            except Exception as e:                       # noqa: BLE001
                err = e

            def done():
                self.busy = False
                self.prog_lbl.config(text="")
                if not quiet:
                    if err is not None:
                        self.log(f"Error: {err}")
                    elif self.stop.is_set():
                        self.log(f"{title}: stopped.")
                    else:
                        self.log(f"{title}: complete.")
                if then and err is None and not self.stop.is_set():
                    then(result)
                if self.pending_band_selection is not None and self.radio:
                    band_code = self.pending_band_selection
                    self.pending_band_selection = None
                    self.after_idle(lambda selected=band_code: self._select_band(selected))
                elif self.pending_func_parameter_read and self.radio:
                    code = self.pending_func_parameter_read
                    self.pending_func_parameter_read = None
                    self.after_idle(lambda selected=code: self._load_func_parameter(selected))
                if self.pending_slider_updates:
                    self.after_idle(self._drain_slider_updates)
                if self.pending_tune and self.radio:
                    self.after_idle(self._drain_frequency_tune)
            self.ui(done)

        threading.Thread(target=runner, daemon=True).start()
        return True

    # -- navegacao --------------------------------------------------------------
    def on_tree(self, _=None):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if not vals:                                      # no de P1: abre/fecha
            self.tree.item(sel[0], open=not self.tree.item(sel[0], "open"))
            return
        p1, p2 = int(vals[0]), int(vals[1])
        for q1, n1, groups in MENU:
            for q2, n2, items in groups:
                if (q1, q2) == (p1, p2):
                    self.cur_group = (q1, q2)
                    self.show_items(items, f"{q1:02d} {n1}  ›  {q2:02d} {n2}")
                    if self.radio and self.auto_var.get():
                        self.read_all_visible()
                    return

    def on_search(self):
        q = self.search_var.get().strip().lower()
        if len(q) < 2:
            return
        tokens = q.split()
        hits = [it for it in ALL_ITEMS
                if all(t in f"{it.name} {it.path1} {it.path2}".lower() for t in tokens)]
        self.cur_group = None
        note = "  (primeiros 150)" if len(hits) > 150 else ""
        self.show_items(hits[:150], f"Search “{q}”: {len(hits)} items{note}", crumb=True)

    def show_items(self, items, title, crumb=False):
        for r in self.rows:
            r.alive = False
        self.sf.clear()
        self.title_lbl.config(text=title)
        self.rows = [Row(self, self.sf.inner, it, i, crumb) for i, it in enumerate(items)]

    # -- read ------------------------------------------------------------------
    def read_all_visible(self):
        self.read_rows(list(self.rows))

    def read_rows(self, rows):
        if not rows or not self.need_conn():
            return
        radio = self.radio

        def job():
            n = len(rows)
            for i, row in enumerate(rows, 1):
                if self.stop.is_set() or radio is not self.radio:
                    break
                self.ui(lambda r=row: r.set_status("Reading…"))
                try:
                    raw = radio.read_menu(row.item)
                except CatError:
                    self.ui(lambda r=row: r.set_status("No response", RED))
                else:
                    self.ui(lambda r=row, v=raw: (r.show_raw(v), r.set_status("Read", GREEN)))
                self.progress(i, n, "Reading")

        self.run_bg(job, "Read")

    # -- write -----------------------------------------------------------------
    def write_dirty(self):
        rows = [r for r in self.rows if r.dirty()]
        if not rows:
            messagebox.showinfo("Write", "No values have changed in this list.\n"
                                "(Read the items before changing them.)")
            return
        self.write_rows(rows)

    def write_rows(self, rows):
        if not self.need_conn():
            return
        plan = []
        for row in rows:
            try:
                plan.append((row, row.current_raw()))
            except ValueError as e:
                messagebox.showerror("Invalid Value", str(e))
                return
        lines = [f"{r.item.path1} › {r.item.path2} › {r.item.name}  →  {r.item.pretty(raw)}"
                 for r, raw in plan]
        text = "\n".join(lines[:20]) + (f"\n… e mais {len(lines) - 20}" if len(lines) > 20 else "")
        if any(r.item.risky for r, _ in plan):
            text += ("\n\nWarning: CAT-x RATE / STOP BIT / TIME OUT and TUN/LIN PORT SELECT "
                     "change the CAT port configuration. You may need to reconnect using "
                     "the new baud rate after writing.")
        if not messagebox.askokcancel("Write to Radio", text):
            return
        radio = self.radio

        def job():
            n = len(plan)
            for i, (row, raw) in enumerate(plan, 1):
                if self.stop.is_set() or radio is not self.radio:
                    break
                self.ui(lambda r=row: r.set_status("Writing…"))
                try:
                    back = radio.write_menu(row.item, raw)
                except CatError:
                    self.ui(lambda r=row: r.set_status("Sent, not confirmed", AMBER))
                else:
                    if row.item.norm(back) == row.item.norm(raw):
                        self.ui(lambda r=row, v=back: (r.show_raw(v), r.set_status("Written ✓", GREEN)))
                    else:
                        self.ui(lambda r=row, v=back: (
                            r.show_raw(v), r.set_status(f"Read back: {v}", RED)))
                self.progress(i, n, "Writing")

        self.run_bg(job, "Write")

    # -- backup / restore -------------------------------------------------------
    def backup(self):
        if not self.need_conn():
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title="Save Menu Backup", defaultextension=".json",
            initialfile=f"ftx1_menu_{stamp}.json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        radio = self.radio

        def job():
            data, missing = {}, []
            n = len(ALL_ITEMS)
            for i, it in enumerate(ALL_ITEMS, 1):
                if self.stop.is_set() or radio is not self.radio:
                    return None
                try:
                    data[it.key] = radio.read_menu(it)
                except CatError:
                    missing.append(it.key)
                self.progress(i, n, "backup")
            payload = {
                "format": "ftx1-menu-backup-1",
                "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "firmware_main": self.fw,
                "items": data,
                "names": {k: f"{BY_KEY[k].path1} > {BY_KEY[k].path2} > {BY_KEY[k].name}"
                          for k in data},
                "no_response": missing,
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=1)
            return len(data), len(missing)

        def then(res):
            if res:
                self.log(f"Backup saved to {path}: read {res[0]} items, {res[1]} did not respond.")

        self.run_bg(job, "Backup", then)

    def restore(self):
        if not self.need_conn():
            return
        path = filedialog.askopenfilename(title="Restore Menu Backup",
                                          filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            saved = payload["items"]
            if payload.get("format") != "ftx1-menu-backup-1":
                raise ValueError("Unknown backup format")
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("Invalid Backup", str(e))
            return
        radio = self.radio

        def job():                                        # 1) descobrir diferenças
            diffs, skipped = [], 0
            keys = [k for k in saved if k in BY_KEY and BY_KEY[k].writable]
            for i, k in enumerate(keys, 1):
                if self.stop.is_set() or radio is not self.radio:
                    return None
                it = BY_KEY[k]
                if it.risky:
                    skipped += 1
                    continue
                try:
                    now = radio.read_menu(it)
                except CatError:
                    continue
                if it.norm(now) != it.norm(saved[k]):
                    diffs.append((it, now, saved[k]))
            self.progress(i, len(keys), "Comparing")
            return diffs, skipped

        def then(res):
            diffs, skipped = res
            if skipped:
                self.log(f"Skipped {skipped} CAT port configuration items.")
            if not diffs:
                messagebox.showinfo("Restore", "The radio already matches the backup.")
                return
            lines = [f"{it.path2} › {it.name}: {it.pretty(now)} → {it.pretty(new)}"
                     for it, now, new in diffs[:20]]
            more = f"\n… e mais {len(diffs) - 20}" if len(diffs) > 20 else ""
            if not messagebox.askokcancel(
                    "Restore Backup", f"{len(diffs)} items differ from the backup:\n\n"
                    + "\n".join(lines) + more + "\n\nWrite these values to the radio?"):
                return

            def job2():                                   # 2) gravar diferenças
                bad = 0
                for i, (it, _, new) in enumerate(diffs, 1):
                    if self.stop.is_set() or radio is not self.radio:
                        break
                    try:
                        back = radio.write_menu(it, new)
                        if it.norm(back) != it.norm(new):
                            bad += 1
                            self.ui(lambda it=it, b=back: self.log(
                                f"Warning: {it.name} read back as {b}"))
                    except CatError:
                        bad += 1
                        self.ui(lambda it=it: self.log(f"Not confirmed: {it.name}"))
                    self.progress(i, len(diffs), "Restoring")
                return bad

            self.run_bg(job2, "Restore", lambda bad: self.log(
                f"Restore finished; {bad} item(s) were not confirmed."))

        self.run_bg(job, "Compare with backup", then)


if __name__ == "__main__":
    App().mainloop()
