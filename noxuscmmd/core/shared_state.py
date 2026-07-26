"""
shared_state.py — Fuente de verdad compartida entre todos los procesos y clientes.
Persiste en JSON para que todos los workers Reflex lean el mismo estado.
"""
import json
import os
import threading
from pathlib import Path

ESTADO_FILE = Path(os.getenv("ESTADO_FILE", "estado_seguridad.json"))
_lock = threading.Lock()

_DEFAULTS = {
    "sistema_armado": False,
    "puerta_abierta": False,      # H.Ppal (GPIO27 de la Pi4)
    "tamper1_abierto": False,     # GPIO22 Pi Zero
    "tamper2_abierto": False,     # GPIO23 Pi Zero
    "tamper1_armado": False,      # <--- NUEVO: armado independiente de Tamper1
    "notificacion_enviada": False,          # Global (puerta y Tamper2)
    "notificacion_tamper1_enviada": False,  # <--- NUEVO: notificación específica para Tamper1
}

def _read() -> dict:
    try:
        with _lock:
            if ESTADO_FILE.exists():
                data = json.loads(ESTADO_FILE.read_text())
                for k, v in _DEFAULTS.items():
                    data.setdefault(k, v)
                return data
    except Exception:
        pass
    return dict(_DEFAULTS)

def _write(data: dict):
    with _lock:
        ESTADO_FILE.write_text(json.dumps(data, indent=2))

# ── Sistema armado ─────────────────────────────────────────────────────────
def get_sistema_armado() -> bool:
    return _read().get("sistema_armado", False)

def set_sistema_armado(value: bool):
    data = _read()
    data["sistema_armado"] = value
    if not value:
        data["notificacion_enviada"] = False
    _write(data)

def toggle_sistema_armado() -> bool:
    data = _read()
    nuevo = not data.get("sistema_armado", False)
    data["sistema_armado"] = nuevo
    if not nuevo:
        data["notificacion_enviada"] = False
    _write(data)
    return nuevo

# ── Puerta principal ──────────────────────────────────────────────────────
def get_puerta_abierta() -> bool:
    return _read().get("puerta_abierta", False)

def set_puerta_abierta(value: bool):
    data = _read()
    if data.get("puerta_abierta") != value:
        data["puerta_abierta"] = value
        _write(data)

# ── Tamper 1 ──────────────────────────────────────────────────────────────
def get_tamper1_abierto() -> bool:
    return _read().get("tamper1_abierto", False)

def set_tamper1_abierto(value: bool):
    data = _read()
    if data.get("tamper1_abierto") != value:
        data["tamper1_abierto"] = value
        _write(data)

def get_tamper1_armado() -> bool:
    return _read().get("tamper1_armado", False)

def set_tamper1_armado(value: bool):
    data = _read()
    if data.get("tamper1_armado") != value:
        data["tamper1_armado"] = value
        _write(data)

def toggle_tamper1_armado() -> bool:
    data = _read()
    nuevo = not data.get("tamper1_armado", False)
    data["tamper1_armado"] = nuevo
    _write(data)
    return nuevo

# ── Notificación Tamper1 ──────────────────────────────────────────────────
def get_notificacion_tamper1_enviada() -> bool:
    return _read().get("notificacion_tamper1_enviada", False)

def set_notificacion_tamper1_enviada(value: bool):
    data = _read()
    if data.get("notificacion_tamper1_enviada") != value:
        data["notificacion_tamper1_enviada"] = value
        _write(data)

# ── Tamper 2 ──────────────────────────────────────────────────────────────
def get_tamper2_abierto() -> bool:
    return _read().get("tamper2_abierto", False)

def set_tamper2_abierto(value: bool):
    data = _read()
    if data.get("tamper2_abierto") != value:
        data["tamper2_abierto"] = value
        _write(data)

# ── Notificación Global (puerta y Tamper2) ──────────────────────────────
def get_notificacion_enviada() -> bool:
    return _read().get("notificacion_enviada", False)

def set_notificacion_enviada(value: bool):
    data = _read()
    if data.get("notificacion_enviada") != value:
        data["notificacion_enviada"] = value
        _write(data)

# ── Función auxiliar para saber si hay alguna apertura ───────────────────
def hay_apertura() -> bool:
    data = _read()
    return data.get("puerta_abierta", False) or data.get("tamper1_abierto", False) or data.get("tamper2_abierto", False)