# -*- coding: utf-8 -*-
"""
Camada serial CAT: envia comandos e lê respostas do FTX-1.

Funciona com qualquer objeto "tipo pyserial.Serial" (write/read/in_waiting/
reset_input_buffer). Isso permite usar o simulador (`ftx1cat.cat.simulator`)
nos testes e no modo `--simulate` da interface.
"""

import logging
import threading
import time
from typing import Callable, Optional

from . import commands as C
from .menu import Item

log = logging.getLogger(__name__)

Logger = Callable[[str, str], None]   # (direção "TX"/"RX", texto)


class CatError(Exception):
    """Falha de comunicação: o rádio não respondeu no tempo esperado."""


class CatRejected(CatError):
    """O rádio respondeu '?;' — comando desconhecido, parâmetro inválido ou
    estado que não permite o comando (ex.: item de menu inexistente)."""


class Radio:
    """Fala com o rádio por qualquer objeto tipo pyserial.Serial.

    Todo comando termina em ';'. A resposta de leitura repete o comando
    (ex.: 'EX010101+05;'). Quadros que não começam com o prefixo esperado
    (por exemplo, informação automática) são descartados. '?;' é erro.
    """

    def __init__(self, ser, timeout: float = 0.8, gap: float = 0.02,
                 logger: Optional[Logger] = None):
        self.ser = ser
        self.timeout = timeout
        self.gap = gap
        self.logger = logger
        self.quiet = False          # True suprime o logger (ex.: leitura periódica)
        self.buf = b""
        self.lock = threading.RLock()

    # -- baixo nível ---------------------------------------------------------
    def _log(self, direction: str, text: str) -> None:
        log.debug("%s %s", direction, text)
        if self.logger and not self.quiet:
            self.logger(direction, text)

    def _write(self, cmd: str) -> None:
        self._log("TX", cmd)
        self.ser.write(cmd.encode("ascii"))

    def _next_frame(self, deadline: float) -> Optional[str]:
        while True:
            i = self.buf.find(b";")
            if i >= 0:
                frame, self.buf = self.buf[:i + 1], self.buf[i + 1:]
                return frame.decode("ascii", "replace")
            n = getattr(self.ser, "in_waiting", 0) or 1
            chunk = self.ser.read(n)
            if chunk:
                self.buf += chunk
                continue
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.005)

    def query(self, cmd: str, prefix: str) -> str:
        """Envia `cmd` e espera um quadro que comece com `prefix`."""
        with self.lock:
            self.ser.reset_input_buffer()
            self.buf = b""
            self._write(cmd)
            deadline = time.monotonic() + self.timeout
            while True:
                frame = self._next_frame(deadline)
                if frame is None:
                    raise CatError(f"no response to {cmd}")
                self._log("RX", frame)
                if frame == "?;":
                    raise CatRejected(f"radio rejected {cmd}")
                if frame.startswith(prefix):
                    return frame

    def send(self, cmd: str) -> None:
        """Envia um comando de escrita (que normalmente não tem resposta).

        Espera `gap` segundos olhando a porta: se o rádio responder '?;' nesse
        intervalo, o comando foi recusado e levantamos CatRejected — em vez de
        a recusa ser descartada silenciosamente pela próxima leitura.
        """
        with self.lock:
            self.ser.reset_input_buffer()
            self.buf = b""
            self._write(cmd)
            deadline = time.monotonic() + self.gap
            while True:
                frame = self._next_frame(deadline)
                if frame is None:
                    return
                self._log("RX", frame)
                if frame == "?;":
                    raise CatRejected(f"radio rejected {cmd}")

    def close(self) -> None:
        try:
            self.ser.close()
        except Exception:   # noqa: BLE001 - fechar nunca deve derrubar o app
            pass

    # -- menu (EX) ---------------------------------------------------------
    def read_menu(self, item: Item) -> str:
        frame = self.query(f"EX{item.key};", f"EX{item.key}")
        return frame[len("EX") + 6:-1]

    def write_menu(self, item: Item, raw: str) -> str:
        """Grava e devolve o valor relido (CatError se não houver resposta)."""
        self.send(f"EX{item.key}{raw};")
        return self.read_menu(item)

    # -- identificação -----------------------------------------------------
    def identify(self) -> str:
        """ID; -> '0840' (valor fixo segundo o manual)."""
        return C.parse_id(self.query(C.id_cmd(), "ID"))

    def firmware(self, which: int = 0) -> str:
        """VE<n>; -> versão (0 = MAIN CPU)."""
        return C.parse_firmware(self.query(C.firmware_cmd(which), f"VE{which}"))

    # -- sintonia ------------------------------------------------------------
    def read_frequency(self) -> int:
        return C.parse_frequency(self.query(C.read_frequency_cmd(), "FA"))

    def set_frequency(self, hz: int) -> int:
        """Sintoniza e devolve a frequência que o rádio aceitou."""
        self.send(C.set_frequency_cmd(hz))
        return self.read_frequency()

    def read_mode(self) -> str:
        return C.parse_mode(self.query(C.read_mode_cmd(), "MD0"))

    def set_mode(self, code: str) -> str:
        self.send(C.set_mode_cmd(code))
        return self.read_mode()

    def select_band(self, code: str) -> None:
        self.send(C.select_band_cmd(code))

    def read_tuning(self):
        """Devolve (frequência, modo, item CH STEP, código do passo, passo em kHz)."""
        frequency = self.read_frequency()
        mode = self.read_mode()
        item = C.ch_step_item_for_mode(mode)
        step_raw = self.read_menu(item)
        return frequency, mode, item, step_raw, C.ch_step_khz(item, step_raw)

    # -- controles -----------------------------------------------------------
    def read_control(self, ctl: C.Control) -> float:
        return ctl.value_from_frame(self.query(ctl.read_cmd, ctl.prefix))

    def set_control(self, ctl: C.Control, value: float) -> float:
        """Grava o controle e devolve o valor relido."""
        if ctl.da_slot is not None:
            cmd = C.da_set_cmd(self.query("DA;", "DA"), ctl.da_slot, int(value))
        elif ctl.encode is not None:
            cmd = ctl.encode(value)
        else:
            raise ValueError(f"{ctl.title} is read-only")
        self.send(cmd)
        return self.read_control(ctl)
