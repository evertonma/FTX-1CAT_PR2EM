# -*- coding: utf-8 -*-
"""
Simulador de FTX-1: um objeto "tipo pyserial.Serial" que responde aos comandos
CAT que o aplicativo usa. Serve para:

  * rodar a interface sem o rádio (`python -m ftx1cat --simulate`);
  * testes automatizados (`pytest`), inclusive em CI;
  * reproduzir cenários de erro (sem resposta, '?;', valores estranhos).

NÃO é uma emulação fiel do firmware: só implementa o subconjunto de comandos
usado aqui, com valores plausíveis. Se um comando desconhecido chegar, responde
'?;' como o rádio real faz.
"""

import re
import threading
from typing import Dict, Optional

from . import commands as C
from .menu import ALL_ITEMS, BY_KEY, Item

# Band Stack simulado (código BS -> frequência, modo)
BAND_STACK: Dict[str, tuple] = {
    "00": (1_840_000, "1"), "01": (3_750_000, "1"), "02": (5_357_000, "2"),
    "03": (7_100_000, "1"), "04": (10_120_000, "3"), "05": (14_250_000, "2"),
    "06": (18_120_000, "2"), "07": (21_250_000, "2"), "08": (24_950_000, "2"),
    "09": (28_410_000, "2"), "10": (50_150_000, "2"), "11": (70_200_000, "2"),
    "12": (118_100_000, "5"), "13": (144_800_000, "4"), "14": (433_500_000, "4"),
}


def _default_raw(item: Item) -> str:
    """Valor inicial plausível para um item do menu."""
    if item.kind == "enum":
        return item.opts[0][0]
    if item.kind == "int":
        return str(item.lo).zfill(item.digits)
    if item.kind == "sint":
        return f"+{0:0{item.digits - 1}d}"
    if item.kind == "text":
        return " " * item.digits
    return "0" * item.digits           # "ro"


class FakeFTX1:
    """Porta serial falsa que se comporta como um FTX-1.

    Atributos úteis em testes:
      * `sent`: lista de comandos recebidos (strings).
      * `silent`: se True, não responde nada (simula rádio desligado).
      * `prepend`: bytes enviados antes da próxima resposta (simula Auto Information).
      * `menu`: dict chave -> P4 atual.
    """

    def __init__(self, frequency: int = 28_410_000, mode: str = "2",
                 firmware: str = "0113", radio_id: str = "0840"):
        self.is_open = True
        self.silent = False
        self.prepend = b""        # bytes "espúrios" enviados antes da próxima resposta
        self.sent = []
        self.menu: Dict[str, str] = {it.key: _default_raw(it) for it in ALL_ITEMS}
        self.frequency = frequency
        self.mode = mode
        self.firmware = firmware
        self.radio_id = radio_id
        self.controls: Dict[str, str] = {
            "PC": "2013",      # P1=2 (SPA-1), 13 W
            "SS04": "+11.0",
            "SS01": "30000",   # LV4
            "NL0": "000",
            "RL0": "04",
            "MG": "050", "PL": "050", "AO": "050", "VG": "050", "VD": "05",
            "ML1": "020", "KS": "020", "KP": "040", "SD": "05",
            "SS03": "0",
            "DA": "001010",    # contraste 10, dimmer 10 (formato suposto)
        }
        # valores de menu mais realistas para o que a interface usa
        self.menu["030604"] = "0"   # CH STEP 1 kHz
        self.menu["030605"] = "1"   # AM CH STEP 5 kHz
        self.menu["030606"] = "3"   # FM CH STEP 12.5 kHz
        self.menu["030202"] = "1"   # BAND STACK ON
        self._rx = b""
        self._pending = b""
        self._lock = threading.Lock()

    # -- interface tipo Serial ------------------------------------------------
    @property
    def in_waiting(self) -> int:
        return len(self._rx)

    def write(self, data: bytes) -> int:
        with self._lock:
            self.sent.extend(c for c in data.decode("ascii").split(";") if c)
            self._pending += data
            while b";" in self._pending:
                cmd, self._pending = self._pending.split(b";", 1)
                reply = self._handle(cmd.decode("ascii"))
                if reply and not self.silent:
                    self._rx += self.prepend + reply.encode("ascii")
                    self.prepend = b""
        return len(data)

    def read(self, n: int = 1) -> bytes:
        with self._lock:
            out, self._rx = self._rx[:n], self._rx[n:]
        return out

    def reset_input_buffer(self) -> None:
        with self._lock:
            self._rx = b""

    def close(self) -> None:
        self.is_open = False

    # -- comportamento do rádio ----------------------------------------------
    def _handle(self, cmd: str) -> Optional[str]:
        if cmd == "ID":
            return f"ID{self.radio_id};"
        m = re.fullmatch(r"VE(\d)", cmd)
        if m:
            return f"VE{m.group(1)}{self.firmware};"
        if cmd == "FA":
            return f"FA{self.frequency:09d};"
        m = re.fullmatch(r"FA(\d{9})", cmd)
        if m:
            hz = int(m.group(1))
            if not C.in_rx_range(hz):
                return "?;"
            self.frequency = hz
            return None
        if cmd == "MD0":
            return f"MD0{self.mode};"
        m = re.fullmatch(r"MD0([0-9A-Z])", cmd)
        if m:
            if m.group(1) not in C.MODE_BY_CODE:
                return "?;"
            self.mode = m.group(1)
            return None
        m = re.fullmatch(r"BS0(\d{2})", cmd)
        if m:
            if m.group(1) not in BAND_STACK:
                return "?;"
            self.frequency, self.mode = BAND_STACK[m.group(1)]
            return None
        m = re.fullmatch(r"EX(\d{6})(.*)", cmd)
        if m:
            key, value = m.groups()
            if key not in BY_KEY:
                return "?;"
            if value:
                item = BY_KEY[key]
                if not item.writable:
                    return "?;"
                try:
                    self.menu[key] = item.encode(item.decode(value))
                except ValueError:
                    return "?;"
                return None
            return f"EX{key}{self.menu[key]};"
        # controles: leitura = prefixo exato; escrita = prefixo + payload
        for prefix in sorted(self.controls, key=len, reverse=True):
            if cmd == prefix:
                return f"{prefix}{self.controls[prefix]};"
            if cmd.startswith(prefix) and len(cmd) > len(prefix):
                # guarda o payload como veio (em PC isso inclui o P1 = 1 ou 2)
                self.controls[prefix] = cmd[len(prefix):]
                return None
        return "?;"
