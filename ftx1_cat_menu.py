#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FTX-1 - Menu via CAT (interface grafica simples)

Requisitos:  Python 3.8+, tkinter (ja vem no Python do Windows/macOS;
             no Debian/Ubuntu: sudo apt install python3-tk) e pyserial:
                 pip install pyserial

Uso:         python ftx1_cat_menu.py
             (precisa do arquivo ftx1_menu.py na mesma pasta)

Porta:       use a porta "Enhanced COM Port" (CAT-1) do FTX-1, 38400 bps
             (padrao de fabrica), conforme o manual CAT oficial.
"""

import datetime
import json
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
            note = f"{item.lo} a {item.hi} {item.unit}".strip()
        elif item.kind == "text":
            note = f"texto, {item.digits} caract. (somente leitura)"
        elif item.kind == "ro":
            note = item.hint
        else:
            note = ""
        ttk.Label(parent, text=note, foreground=GRAY, wraplength=320, justify="left").grid(
            row=r, column=3, padx=4, sticky="w")

        ttk.Button(parent, text="Ler", width=5, command=self.read).grid(row=r, column=4, padx=2)
        self.btn_w = ttk.Button(parent, text="Gravar", width=7, command=self.write)
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
                             else f"{raw}{SEP}(fora da tabela)")
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
        self.title("FTX-1 • Menu via CAT")
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

        self._build_ui()
        self.refresh_ports()
        self.after(40, self._pump)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.log("Pronto. Escolha a porta CAT-1 (Enhanced COM Port), 38400 bps, e clique em Conectar.")

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
        ttk.Label(top, text="Porta:").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(top, textvariable=self.port_var, width=46)
        self.port_cb.pack(side="left", padx=4)
        ttk.Button(top, text="↻", width=3, command=self.refresh_ports).pack(side="left")
        ttk.Label(top, text="Taxa:").pack(side="left", padx=(10, 2))
        self.baud_var = tk.StringVar(value="38400")
        ttk.Combobox(top, textvariable=self.baud_var, values=BAUDS, width=8,
                     state="readonly").pack(side="left")
        self.btn_conn = ttk.Button(top, text="Conectar", command=self.toggle_connect)
        self.btn_conn.pack(side="left", padx=10)
        self.conn_lbl = ttk.Label(top, text="Desconectado", foreground=GRAY)
        self.conn_lbl.pack(side="left")

        pages = ttk.Notebook(self)
        pages.pack(fill="both", expand=True, padx=6)
        menu_page = ttk.Frame(pages)
        pages.add(menu_page, text="Menu CAT")

        body = ttk.PanedWindow(menu_page, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        self.search_var = tk.StringVar()
        ttk.Label(left, text="Buscar item:").pack(anchor="w")
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
        self.title_lbl = ttk.Label(right, text="Selecione um grupo à esquerda",
                                   font=("TkDefaultFont", 11, "bold"))
        self.title_lbl.pack(anchor="w", pady=(0, 4))
        self.sf = ScrollFrame(right)
        self.sf.pack(fill="both", expand=True)
        body.add(right, weight=4)

        controls_page = ttk.Frame(pages, padding=12)
        pages.add(controls_page, text="Controles rápidos")
        self._build_quick_controls(controls_page)

        bar = ttk.Frame(self, padding=(6, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Ler lista", command=self.read_all_visible).pack(side="left")
        ttk.Button(bar, text="Gravar alterados", command=self.write_dirty).pack(side="left", padx=4)
        ttk.Button(bar, text="Parar", command=self.stop.set).pack(side="left")
        self.auto_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Ler ao abrir o grupo", variable=self.auto_var).pack(
            side="left", padx=12)
        ttk.Button(bar, text="Salvar backup…", command=self.backup).pack(side="right")
        ttk.Button(bar, text="Restaurar backup…", command=self.restore).pack(side="right", padx=4)
        self.prog_lbl = ttk.Label(bar, text="", foreground=GRAY)
        self.prog_lbl.pack(side="right", padx=10)

        logf = ttk.Frame(self, padding=(6, 0, 6, 6))
        logf.pack(fill="x")
        head = ttk.Frame(logf)
        head.pack(fill="x")
        ttk.Label(head, text="Registro").pack(side="left")
        self.cat_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(head, text="mostrar comandos (TX/RX)", variable=self.cat_var).pack(
            side="left", padx=10)
        self.logbox = tk.Text(logf, height=8, wrap="none", state="disabled")
        self.logbox.pack(fill="x")

    def _build_quick_controls(self, parent):
        ttk.Label(parent, text="Atalhos CAT do FTX-1",
                  font=("TkDefaultFont", 13, "bold")).grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 4))
        ttk.Label(parent, text=(
            "Os comandos atuam no lado MAIN quando aplicável. Ler mostra o estado atual; "
            "Aplicar pede confirmação e confere o resultado por releitura."),
            wraplength=900, justify="left").grid(
                row=1, column=0, columnspan=5, sticky="w", pady=(0, 12))

        self.quick_vars = {}
        row = 2

        def add_control(name, variable, values, read_cmd, prefix, make_set, display=None,
                        state="readonly", width=30):
            nonlocal row
            ttk.Label(parent, text=name, font=("TkDefaultFont", 10, "bold")).grid(
                row=row, column=0, sticky="w", padx=(0, 10), pady=5)
            widget = ttk.Combobox(parent, textvariable=variable, values=values,
                                  state=state, width=width)
            widget.grid(row=row, column=1, sticky="w", padx=4, pady=5)
            ttk.Button(parent, text="Ler", command=lambda: self.quick_action(
                name, read_cmd, prefix, None, variable, display)).grid(
                    row=row, column=2, padx=4)
            ttk.Button(parent, text="Aplicar", command=lambda: self.quick_apply(
                name, read_cmd, prefix, make_set, variable, display)).grid(
                    row=row, column=3, padx=4)
            status = ttk.Label(parent, text="não lido", foreground=GRAY, width=32)
            status.grid(row=row, column=4, sticky="w", padx=8)
            self.quick_status[name] = status
            self.quick_vars[name] = variable
            row += 1

        ch_options = [f"{code} – {label}" for code, label in
                      BY_KEY["030604"].opts]
        ch_var = tk.StringVar()
        add_control("CH STEP", ch_var, ch_options, "EX030604;", "EX030604",
                    lambda: "EX030604" + ch_var.get().split(" – ", 1)[0] + ";")

        power_var = tk.StringVar()
        add_control("RF POWER (W)", power_var, [str(v) for v in range(5, 11)],
                    "PC;", "PC", lambda: "PC1" + f"{int(power_var.get()):03d}" + ";",
                    display=lambda raw: f"{int(raw[1:4])} W")

        level_values = [f"{v / 2:+.1f} dB" for v in range(-60, 61)]
        level_var = tk.StringVar()
        def level_set():
            db = float(level_var.get().split(" ", 1)[0].replace(",", "."))
            return "SS04" + f"{db:+05.1f}" + ";"
        add_control("D-LEVEL", level_var, level_values, "SS04;", "SS04", level_set,
                    display=lambda raw: f"{float(raw):+.1f} dB")

        nb_var = tk.StringVar()
        add_control("NB", nb_var, ["OFF"] + [str(v) for v in range(1, 11)],
                    "NL0;", "NL0",
                    lambda: "NL0" + f"{0 if nb_var.get() == 'OFF' else int(nb_var.get()):03d}" + ";",
                    display=lambda raw: "OFF" if int(raw) == 0 else f"nível {int(raw)}")

        dnr_var = tk.StringVar()
        add_control("DNR", dnr_var, ["OFF"] + [str(v) for v in range(1, 11)],
                    "RL0;", "RL0",
                    lambda: "RL0" + f"{0 if dnr_var.get() == 'OFF' else int(dnr_var.get()):02d}" + ";",
                    display=lambda raw: "OFF" if int(raw) == 0 else f"nível {int(raw)}")

        func_options = ["0 – (sem atribuição)", "1 – SCOPE LEVEL", "2 – PEAK", "3 – COLOR", "4 – CONTRAST",
                        "5 – DIMMER", "7 – MIC GAIN", "8 – PROC LEVEL", "9 – AMC LEVEL",
                        "A – VOX GAIN", "B – VOX DELAY", "D – RF POWER", "E – MONI LEVEL",
                        "F – CW SPEED", "G – CW PITCH", "H – BK-DELAY"]
        func_var = tk.StringVar()
        add_control("Função do knob FUNC", func_var, func_options, "SF0;", "SF0",
                    lambda: "SF0" + func_var.get().split(" – ", 1)[0] + ";",
                    display=lambda raw: next((x for x in func_options
                                              if x.startswith(raw + " – ")), raw))

        note = ("HOME: o manual CAT não lista um comando para acionar HOME. "
                "O comando SF permite consultar/selecionar a função do knob FUNC, "
                "mas CH STEP não consta entre as funções válidas de SF.")
        ttk.Label(parent, text=note, foreground=GRAY, wraplength=900,
                  justify="left").grid(row=row + 1, column=0, columnspan=5,
                                      sticky="w", pady=(12, 0))

    def quick_action(self, name, read_cmd, prefix, set_cmd, variable, display=None):
        if not self.need_conn():
            return
        radio = self.radio
        def job():
            if set_cmd:
                radio.send(set_cmd())
            frame = radio.query(read_cmd, prefix)
            return frame[len(prefix):-1]
        def then(raw):
            value = display(raw) if display else raw
            if name == "CH STEP":
                shown = f"{raw} – {dict(BY_KEY['030604'].opts).get(raw, 'desconhecido')}"
            elif name == "Função do knob FUNC":
                shown = value
            elif name == "RF POWER (W)":
                shown = str(int(raw[1:4]))
            elif name == "D-LEVEL":
                shown = value
            elif name in ("NB", "DNR"):
                shown = "OFF" if int(raw) == 0 else str(int(raw))
            else:
                shown = value
            variable.set(shown)
            self.quick_status[name].config(text=f"Rádio: {value}", foreground=GREEN)
        self.run_bg(job, f"Leitura de {name}", then)

    def quick_apply(self, name, read_cmd, prefix, make_set, variable, display=None):
        if not variable.get().strip():
            messagebox.showinfo(name, "Leia o valor atual ou escolha um valor antes de aplicar.")
            return
        try:
            command = make_set()
        except (ValueError, IndexError) as exc:
            messagebox.showerror(name, f"Valor inválido: {exc}")
            return
        if not messagebox.askokcancel("Aplicar controle CAT", f"Enviar ao rádio:\n\n{name}\n{command}"):
            return
        self.quick_action(name, read_cmd, prefix, lambda: command, variable, display)

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
        ports = [f"{p.device}{SEP}{p.description}" for p in list_ports.comports()]
        self.port_cb.config(values=ports)
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def toggle_connect(self):
        if self.radio:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        port = self.port_var.get().split(SEP)[0].strip()
        if not port:
            messagebox.showwarning("Porta", "Escolha a porta serial do FTX-1.")
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
            messagebox.showerror("Erro ao abrir a porta", str(e))
            return
        self.radio = Radio(ser, logger=self._cat_log)
        self.btn_conn.config(text="Desconectar")
        self.conn_lbl.config(text="Conectando…", foreground=AMBER)
        self.log(f"Porta {port} aberta a {self.baud_var.get()} bps, 8N1.")

        def job():
            try:
                rid = self.radio.identify()
                fw = self.radio.firmware(0)
            except CatError:
                self.ui(lambda: self.conn_lbl.config(
                    text="Sem resposta do rádio", foreground=RED))
                self.ui(lambda: self.log(
                    "Sem resposta a ID;. Confira: porta CAT-1 (Enhanced COM Port), taxa igual "
                    "à do menu CAT-1 RATE (padrão 38400) e firmware MAIN 1.08 ou superior."))
                return
            self.fw = fw
            self.ui(lambda: self.conn_lbl.config(
                text=f"Conectado • ID {rid} • FW MAIN {fw}", foreground=GREEN))
            self.ui(lambda: self.log(f"Rádio respondeu: ID {rid}, firmware MAIN {fw}."))
            if self.rows and self.auto_var.get() and self.cur_group:
                self.ui(self.read_all_visible)

        threading.Thread(target=job, daemon=True).start()

    def disconnect(self):
        self.stop.set()
        if self.radio:
            try:
                self.radio.ser.close()
            except Exception:
                pass
        self.radio = None
        self.btn_conn.config(text="Conectar")
        self.conn_lbl.config(text="Desconectado", foreground=GRAY)
        self.log("Desconectado.")

    def _close(self):
        self.disconnect()
        self.destroy()

    def need_conn(self):
        if not self.radio:
            messagebox.showinfo("Conexão", "Conecte-se ao rádio primeiro.")
            return False
        return True

    # -- execucao em segundo plano ------------------------------------------
    def run_bg(self, job, title, then=None):
        if self.busy:
            self.log("Aguarde a operação em andamento (ou clique em Parar).")
            return False
        self.busy = True
        self.stop.clear()
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
                if err is not None:
                    self.log(f"Erro: {err}")
                elif self.stop.is_set():
                    self.log(f"{title}: interrompido.")
                else:
                    self.log(f"{title}: concluído.")
                if then and err is None and not self.stop.is_set():
                    then(result)
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
        self.show_items(hits[:150], f"Busca “{q}”: {len(hits)} itens{note}", crumb=True)

    def show_items(self, items, title, crumb=False):
        for r in self.rows:
            r.alive = False
        self.sf.clear()
        self.title_lbl.config(text=title)
        self.rows = [Row(self, self.sf.inner, it, i, crumb) for i, it in enumerate(items)]

    # -- leitura ----------------------------------------------------------------
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
                self.ui(lambda r=row: r.set_status("lendo…"))
                try:
                    raw = radio.read_menu(row.item)
                except CatError:
                    self.ui(lambda r=row: r.set_status("sem resposta", RED))
                else:
                    self.ui(lambda r=row, v=raw: (r.show_raw(v), r.set_status("lido", GREEN)))
                self.progress(i, n, "lendo")

        self.run_bg(job, "Leitura")

    # -- gravacao ---------------------------------------------------------------
    def write_dirty(self):
        rows = [r for r in self.rows if r.dirty()]
        if not rows:
            messagebox.showinfo("Gravar", "Nenhum valor alterado nesta lista.\n"
                                "(Leia os itens antes de alterá-los.)")
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
                messagebox.showerror("Valor inválido", str(e))
                return
        lines = [f"{r.item.path1} › {r.item.path2} › {r.item.name}  →  {r.item.pretty(raw)}"
                 for r, raw in plan]
        text = "\n".join(lines[:20]) + (f"\n… e mais {len(lines) - 20}" if len(lines) > 20 else "")
        if any(r.item.risky for r, _ in plan):
            text += ("\n\nAtenção: CAT-x RATE / STOP BIT / TIME OUT e TUN/LIN PORT SELECT "
                     "alteram a configuração das portas CAT. Depois de gravar pode ser "
                     "necessário reconectar com a nova taxa.")
        if not messagebox.askokcancel("Gravar no rádio", text):
            return
        radio = self.radio

        def job():
            n = len(plan)
            for i, (row, raw) in enumerate(plan, 1):
                if self.stop.is_set() or radio is not self.radio:
                    break
                self.ui(lambda r=row: r.set_status("gravando…"))
                try:
                    back = radio.write_menu(row.item, raw)
                except CatError:
                    self.ui(lambda r=row: r.set_status("enviado, sem confirmação", AMBER))
                else:
                    if row.item.norm(back) == row.item.norm(raw):
                        self.ui(lambda r=row, v=back: (r.show_raw(v), r.set_status("gravado ✓", GREEN)))
                    else:
                        self.ui(lambda r=row, v=back: (
                            r.show_raw(v), r.set_status(f"relido: {v}", RED)))
                self.progress(i, n, "gravando")

        self.run_bg(job, "Gravação")

    # -- backup / restauracao -----------------------------------------------------
    def backup(self):
        if not self.need_conn():
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        path = filedialog.asksaveasfilename(
            title="Salvar backup do menu", defaultextension=".json",
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
                self.log(f"Backup salvo em {path}: {res[0]} itens lidos, {res[1]} sem resposta.")

        self.run_bg(job, "Backup", then)

    def restore(self):
        if not self.need_conn():
            return
        path = filedialog.askopenfilename(title="Restaurar backup do menu",
                                          filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            saved = payload["items"]
            if payload.get("format") != "ftx1-menu-backup-1":
                raise ValueError("formato de backup desconhecido")
        except (OSError, ValueError, KeyError) as e:
            messagebox.showerror("Backup inválido", str(e))
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
                self.progress(i, len(keys), "comparando")
            return diffs, skipped

        def then(res):
            diffs, skipped = res
            if skipped:
                self.log(f"{skipped} itens de configuração das portas CAT foram ignorados.")
            if not diffs:
                messagebox.showinfo("Restaurar", "O rádio já está igual ao backup.")
                return
            lines = [f"{it.path2} › {it.name}: {it.pretty(now)} → {it.pretty(new)}"
                     for it, now, new in diffs[:20]]
            more = f"\n… e mais {len(diffs) - 20}" if len(diffs) > 20 else ""
            if not messagebox.askokcancel(
                    "Restaurar backup", f"{len(diffs)} itens diferem do backup:\n\n"
                    + "\n".join(lines) + more + "\n\nGravar estes valores no rádio?"):
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
                                f"Atenção: {it.name} relido como {b}"))
                    except CatError:
                        bad += 1
                        self.ui(lambda it=it: self.log(f"Sem confirmação: {it.name}"))
                    self.progress(i, len(diffs), "restaurando")
                return bad

            self.run_bg(job2, "Restauração", lambda bad: self.log(
                f"Restauração terminada; {bad} item(ns) sem confirmação."))

        self.run_bg(job, "Comparação com o backup", then)


if __name__ == "__main__":
    App().mainloop()
