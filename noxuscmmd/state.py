import fcntl
import os
import asyncio
import subprocess
import base64
import json
import reflex as rx
import time
from pathlib import Path
from dotenv import load_dotenv

from .core.connectivity import NetUtils
from .core.ssh_manager import SSHManager
from .core.sensors import Sensors
from .core.shared_state import (
    get_sistema_armado, get_tamper1_armado, set_tamper1_abierto, set_tamper1_armado, toggle_sistema_armado,
    get_notificacion_enviada, set_notificacion_enviada,
    get_notificacion_tamper1_enviada, set_notificacion_tamper1_enviada,  # <--- IMPORTADAS
    get_puerta_abierta, get_tamper1_abierto, get_tamper2_abierto,
)
from .core import device_actions
from .core.mqtt_client import MQTTClient

load_dotenv()

VAPID_PRIVATE = os.getenv("VAPID_PRIVATE_KEY")
VAPID_PUBLIC  = os.getenv("VAPID_PUBLIC_KEY")
VAPID_EMAIL   = os.getenv("VAPID_EMAIL", "mailto:admin@noxuscmmd.uk")

_SSH_STARTED = False

# ---------- GESTOR MQTT GLOBAL ----------
_mqtt_client_instance = None

def get_mqtt_client(broker, port, topic, state_instance):
    global _mqtt_client_instance
    if _mqtt_client_instance is None:
        _mqtt_client_instance = MQTTClient(broker, port, topic, state_instance)
        _mqtt_client_instance.start()
    return _mqtt_client_instance

class State(rx.State):

    # ── Dispositivos ──────────────────────────────────────────────────────
    raspberry_online: bool = False
    iphone_online:    bool = False
    pc_online:        bool = False
    portatil_online:  bool = False
    pi_zero_online:   bool = False
    server_online:    bool = False
    tablet_online:    bool = False
    cam_ptz_online:   bool = False
    cam_fija_online:  bool = False

    # ── UI ────────────────────────────────────────────────────────────────
    status:              str       = "Esperando..."
    temperaturas:        list[str] = []
    last_rpi_photo:      str       = ""
    dialog_foto_abierto: bool      = False
    uploaded_files:      list[str] = []
    cam_msg:             str       = "Vídeo: Listo"

    # ── Seguridad ─────────────────────────────────────────────────────────
    sistema_armado: bool = False
    puerta_abierta: bool = False
    tamper1_abierto: bool = False
    tamper2_abierto: bool = False
    tamper1_armado: bool = False
    ultimos_abiertos_armado: list[str] = []

    # ── Control comandos personalizados ───────────────────────────────────
    custom_command: dict[str, str] = {}
    custom_output:  dict[str, str] = {}
    current_user: str = ""
    current_session: str = ""
    _sync_running: bool = False

    # ── Cámaras ──────────────────────────────────────────────────────────
    cam_mode: str = "pc"
    show_fija_stream: bool = False
    show_ptz_stream: bool = False

    # ── Logs ─────────────────────────────────────────────────────────────
    _logs_update_counter: int = 0
    _ultimo_evento_puerta: str = ""
    last_puerta_log_time: float = 0.0

    # ════════════════════════════════════════════════════════════════════
    # MÉTODOS DE LOGS
    # ════════════════════════════════════════════════════════════════════

    def _ultimo_log_puerta(self) -> str:
        archivo = "logs.json"
        if not os.path.exists(archivo):
            return ""
        try:
            with open(archivo, "r") as f:
                content = f.read().strip()
                if not content:
                    return ""
                logs = json.loads(content)
            for log in reversed(logs):
                accion = log.get("accion", "")
                if accion in ("PUERTA_ABIERTA", "PUERTA_ABIERTA_ARMADA", "PUERTA_CERRADA"):
                    return accion
        except:
            pass
        return ""

    def refresh_logs(self):
        self._logs_update_counter += 1

    @rx.var
    def logs_recientes(self) -> list[dict]:
        _ = self._logs_update_counter
        archivo = "logs.json"
        if not os.path.exists(archivo):
            return []
        try:
            with open(archivo, "r") as f:
                content = f.read().strip()
                if not content:
                    return []
                logs = json.loads(content)
            return logs[::-1]
        except:
            return []

    def registrar_log(self, accion: str, detalle: str = "", usar_usuario: bool = True, usuario_override: str = None):
        archivo = "logs.json"
        try:
            with open(archivo, "a+" if os.path.exists(archivo) else "w+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
                f.seek(0)
                content = f.read().strip()
                logs = []
                if content:
                    try:
                        logs = json.loads(content)
                    except:
                        logs = []
                if logs:
                    ultimo = logs[-1]
                    if ultimo.get("accion") == accion and ultimo.get("detalle") == detalle:
                        return
                if usuario_override is not None:
                    usuario = usuario_override
                else:
                    usuario = self.current_user if (self.current_user.strip() and usar_usuario) else "sistema"
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
                entrada = {
                    "timestamp": timestamp,
                    "accion": accion,
                    "usuario": usuario,
                    "detalle": detalle
                }
                logs.append(entrada)
                if len(logs) > 500:
                    logs = logs[-500:]
                f.seek(0)
                f.truncate()
                json.dump(logs, f, indent=4, ensure_ascii=False)
                f.flush()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except Exception as e:
            print(f"❌ Error escribiendo log: {e}")

    # ════════════════════════════════════════════════════════════════════
    # CARGA DE USUARIO DESDE SUSCRIPCIÓN
    # ════════════════════════════════════════════════════════════════════

    @rx.event
    def cargar_usuario_desde_subscripcion(self, endpoint: str):
        archivo = "suscriptores.json"
        try:
            if os.path.exists(archivo):
                with open(archivo, "r") as f:
                    subs = json.load(f)
                for s in subs:
                    if s.get("endpoint") == endpoint:
                        self.current_user = s.get("nombre_usuario", "")
                        self.current_session = endpoint
                        print(f"👤 Usuario cargado: {self.current_user}")
                        return
            self.current_user = ""
            self.current_session = ""
            print("👤 No se encontró usuario para este endpoint")
        except Exception as e:
            print(f"❌ Error cargando usuario: {e}")

    # ════════════════════════════════════════════════════════════════════
    # ON_LOAD
    # ════════════════════════════════════════════════════════════════════

    @rx.event
    async def on_load(self):
        global _SSH_STARTED
        self.refresh_logs()
        self._ultimo_evento_puerta = self._ultimo_log_puerta()
        self.sistema_armado = await asyncio.to_thread(get_sistema_armado)
        self.puerta_abierta = await asyncio.to_thread(get_puerta_abierta)
        self.tamper1_abierto = await asyncio.to_thread(get_tamper1_abierto)
        self.tamper2_abierto = await asyncio.to_thread(get_tamper2_abierto)
        self.tamper1_armado = await asyncio.to_thread(get_tamper1_armado)

        self.status = "🔒 Sistema de Seguridad: ARMADO" if self.sistema_armado else "🔓 Sistema de Seguridad: DESARMADO"

        if not _SSH_STARTED:
            _SSH_STARTED = True
            asyncio.create_task(SSHManager.connect_async())
            yield State.keepalive_ssh_task
            yield State.monitor_temperatura_fan

        yield State.sync_ui_loop

        mqtt_broker = os.getenv("MQTT_BROKER", "127.0.0.1")
        mqtt_port = int(os.getenv("MQTT_PORT", 1883))
        topic_puerta = "casa/raspberry/puerta"

        try:
            get_mqtt_client(mqtt_broker, mqtt_port, topic_puerta, self)
        except Exception as e:
            print(f"⚠️ Error controlado al iniciar MQTT: {e}")

        yield rx.call_script(
            """
            (async function() {
                try {
                    const reg = await navigator.serviceWorker.ready;
                    const pushSub = await reg.pushManager.getSubscription();
                    if (pushSub) {
                        return pushSub.endpoint;
                    }
                    return null;
                } catch(e) {
                    return null;
                }
            })();
            """,
            callback=State.cargar_usuario_desde_subscripcion
        )

        yield State.actualizar_estados

    # ════════════════════════════════════════════════════════════════════
    # ARMAR / DESARMAR
    # ════════════════════════════════════════════════════════════════════

    @rx.event
    async def toggle_tamper1_armado(self, valor: bool):
        """Arma o desarma Tamper1 independientemente."""
        await asyncio.to_thread(set_tamper1_armado, valor)
        self.tamper1_armado = valor
        if not valor:
            await asyncio.to_thread(set_notificacion_tamper1_enviada, False)
        estado = "ARMADO" if valor else "DESARMADO"
        self.registrar_log("TAMPER1_" + estado, f"Tamper1 {estado} (manual)", usar_usuario=False)

    @rx.event
    async def conmutar_alarma(self):
        nuevo = await asyncio.to_thread(toggle_sistema_armado)
        self.sistema_armado = nuevo
        self.status = "🔒 Sistema de Seguridad: ARMADO" if nuevo else "🔓 Sistema de Seguridad: DESARMADO"

        if nuevo:
            abiertos = self.obtener_abiertos()
            if abiertos:
                lista = ", ".join(abiertos)
                detalle = f"Armado con abiertos: {lista}"
            else:
                detalle = "Armado (sin abiertos)"
            self.registrar_log("ARMADO", detalle, usar_usuario=True)
        else:
            self.registrar_log("DESARMADO", "", usar_usuario=True)

    # ════════════════════════════════════════════════════════════════════
    # LOOP DE SINCRONIZACIÓN GENERAL
    # ════════════════════════════════════════════════════════════════════

    def obtener_abiertos(self) -> list[str]:
        abiertos = []
        if self.puerta_abierta:
            abiertos.append("Puerta principal")
        if self.tamper1_abierto:
            abiertos.append("Tamper1")
        if self.tamper2_abierto:
            abiertos.append("Tamper2")
        return abiertos

    @rx.var
    def lista_abiertos(self) -> str:
        abiertos = self.obtener_abiertos()
        return ", ".join(abiertos) if abiertos else "Ninguno"

    @rx.event(background=True)
    async def sync_ui_loop(self):
        ultima_puerta = None
        ultimo_tamper1 = None
        ultimo_tamper2 = None
        while True:
            try:
                real_armado = await asyncio.to_thread(get_sistema_armado)
                real_puerta = await asyncio.to_thread(get_puerta_abierta)
                real_tamper1 = await asyncio.to_thread(get_tamper1_abierto)
                real_tamper2 = await asyncio.to_thread(get_tamper2_abierto)
                real_tamper1_armado = await asyncio.to_thread(get_tamper1_armado)

                async with self:
                    # Actualizar estados
                    if (self.sistema_armado != real_armado or self.puerta_abierta != real_puerta or
                        self.tamper1_abierto != real_tamper1 or self.tamper2_abierto != real_tamper2 or
                        self.tamper1_armado != real_tamper1_armado):
                        self.sistema_armado = real_armado
                        self.puerta_abierta = real_puerta
                        self.tamper1_abierto = real_tamper1
                        self.tamper2_abierto = real_tamper2
                        self.tamper1_armado = real_tamper1_armado
                        self.status = "🔒 Sistema de Seguridad: ARMADO" if real_armado else "🔓 Sistema de Seguridad: DESARMADO"

                    # Detectar cambios en puerta principal
                    if ultima_puerta is None:
                        ultima_puerta = real_puerta
                    elif ultima_puerta != real_puerta:
                        if real_puerta:
                            accion = "PUERTA_ABIERTA"
                            detalle = "ABIERTA"
                            usuario = "puerta ppal"
                            if real_armado:
                                ya_notificado = await asyncio.to_thread(get_notificacion_enviada)
                                if not ya_notificado:
                                    await asyncio.to_thread(set_notificacion_enviada, True)
                                    self.enviar_notificacion(
                                        "🚨 ALERTA: INTRUSIÓN (Puerta)",
                                        "La puerta principal se ha abierto con el sistema armado.",
                                        "todos"
                                    )
                        else:
                            accion = "PUERTA_CERRADA"
                            detalle = "CERRADA"
                            usuario = "puerta ppal"
                            await asyncio.to_thread(set_notificacion_enviada, False)
                        self.registrar_log(accion, detalle, usar_usuario=False, usuario_override=usuario)
                        ultima_puerta = real_puerta

                    # Detectar cambios en Tamper1 (ABIERTO/CERRADO) - INDEPENDIENTE
                    if ultimo_tamper1 is None:
                        ultimo_tamper1 = real_tamper1
                    elif ultimo_tamper1 != real_tamper1:
                        if real_tamper1:
                            accion = "TAMPER1_ABIERTO"
                            detalle = "ABIERTO"
                            usuario = "Tamper1"
                            if real_tamper1_armado:
                                ya_notificado_tamper1 = await asyncio.to_thread(get_notificacion_tamper1_enviada)
                                if not ya_notificado_tamper1:
                                    await asyncio.to_thread(set_notificacion_tamper1_enviada, True)
                                    self.enviar_notificacion(
                                        "🚨 ALERTA: TAMPER1",
                                        "Tamper1 se ha abierto con su sistema armado.",
                                        "todos"
                                    )
                        else:
                            accion = "TAMPER1_CERRADO"
                            detalle = "CERRADO"
                            usuario = "Tamper1"
                            await asyncio.to_thread(set_notificacion_tamper1_enviada, False)
                        self.registrar_log(accion, detalle, usar_usuario=False, usuario_override=usuario)
                        ultimo_tamper1 = real_tamper1

                    # Detectar cambios en Tamper2 (sigue dependiendo del sistema global)
                    if ultimo_tamper2 is None:
                        ultimo_tamper2 = real_tamper2
                    elif ultimo_tamper2 != real_tamper2:
                        if real_tamper2:
                            accion = "TAMPER2_ABIERTO"
                            detalle = "ABIERTO"
                            usuario = "Tamper2"
                            if real_armado:
                                ya_notificado = await asyncio.to_thread(get_notificacion_enviada)
                                if not ya_notificado:
                                    await asyncio.to_thread(set_notificacion_enviada, True)
                                    self.enviar_notificacion(
                                        "🚨 ALERTA: INTRUSIÓN (Tamper2)",
                                        "Tamper2 se ha abierto con el sistema armado.",
                                        "todos"
                                    )
                        else:
                            accion = "TAMPER2_CERRADO"
                            detalle = "CERRADO"
                            usuario = "Tamper2"
                            await asyncio.to_thread(set_notificacion_enviada, False)
                        self.registrar_log(accion, detalle, usar_usuario=False, usuario_override=usuario)
                        ultimo_tamper2 = real_tamper2

                await asyncio.sleep(0.5)

            except Exception as e:
                print(f"⚠️ Error en bucle de sincronización: {e}")
                await asyncio.sleep(1)

    # ════════════════════════════════════════════════════════════════════
    # SSH keepalive
    # ════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def keepalive_ssh_task(self):
        await SSHManager.keep_alive_loop()

    # ════════════════════════════════════════════════════════════════════
    # Pings paralelos
    # ════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def actualizar_estados(self):
        hosts = [
            (os.getenv("IP_SERVER",    "0.0.0.0"), 1),
            (os.getenv("IP_RASPBERRY", "0.0.0.0"), 1),
            (os.getenv("IP_TABLET",    "0.0.0.0"), 1),
            (os.getenv("IP_IPHONE",    "0.0.0.0"), 2),
            (os.getenv("IP_PC",        "0.0.0.0"), 1),
            (os.getenv("IP_PORTATIL",  "0.0.0.0"), 1),
            (os.getenv("IP_PI_ZERO",   "0.0.0.0"), 2),
            (os.getenv("IP_CAM_PTZ",   "0.0.0.0"), 1),
            (os.getenv("IP_CAM_FIJA",  "0.0.0.0"), 1),
        ]
        results = await NetUtils.ping_all(hosts)
        (server_r, rpi_r, tablet_r, iphone_r,
         pc_r, port_r, zero_r, ptz_r, fija_r) = results
        async with self:
            self.server_online    = server_r
            self.raspberry_online = rpi_r
            self.tablet_online    = tablet_r
            self.iphone_online    = iphone_r
            self.pc_online        = pc_r
            self.portatil_online  = port_r
            self.pi_zero_online   = zero_r
            self.cam_ptz_online   = ptz_r
            self.cam_fija_online  = fija_r

    # ════════════════════════════════════════════════════════════════════
    # Termostato (ventilador automático, GPIO17)
    # ════════════════════════════════════════════════════════════════════
    @rx.event(background=True)
    async def monitor_temperatura_fan(self):
        while True:
            try:
                temp_str = await SSHManager.execute_async(
                    "cat /sys/class/thermal/thermal_zone0/temp", timeout=2
                )
                if temp_str and not temp_str.startswith("ERROR"):
                    t = int(temp_str) / 1000.0
                    if t >= 80.0:
                        await SSHManager.execute_async("raspi-gpio set 17 op dh", timeout=2)
                    elif t <= 75.0:
                        await SSHManager.execute_async("raspi-gpio set 17 op dl", timeout=2)
            except Exception as e:
                print(f"⚠️ Termostato: {e}")
            await asyncio.sleep(10)

    # ════════════════════════════════════════════════════════════════════
    # ALERTA MANUAL
    # ════════════════════════════════════════════════════════════════════
    @rx.event
    def lanzar_alerta_global(self):
        asyncio.create_task(
            asyncio.to_thread(
                self.enviar_notificacion,
                "Notificación del Panel",
                "Alguien quiere que sepas que hay un mensaje importante.",
            )
        )
        self.status = "🆘 Alerta Global Enviada"

    @rx.event
    def lanzar_alerta_global_con_subscripcion(self, subscription_json: str):
        import json
        sub_data = None
        if subscription_json and subscription_json != "null":
            try:
                sub_data = json.loads(subscription_json)
            except:
                sub_data = None
        archivo = "suscriptores.json"
        emisor = "Panel de Control"
        try:
            if os.path.exists(archivo):
                with open(archivo, "r") as f:
                    subs = json.load(f)
                if sub_data and subs:
                    endpoint_buscado = sub_data.get("endpoint")
                    for s in subs:
                        if s.get("endpoint") == endpoint_buscado:
                            emisor = s.get("nombre_usuario", "Panel de Control")
                            break
        except Exception as e:
            print(f"Error leyendo suscriptores: {e}")
            emisor = "Panel de Control"
        titulo = "📢 ¡Notificación de Seguridad!"
        mensaje = f"Alerta manual activada desde **{emisor}**. Revisa las cámaras y el estado de la casa."
        asyncio.create_task(
            asyncio.to_thread(
                self.enviar_notificacion,
                titulo,
                mensaje,
                "todos"
            )
        )
        self.status = f"📢 Alerta enviada desde {emisor}"

    # ════════════════════════════════════════════════════════════════════
    # PUSH
    # ════════════════════════════════════════════════════════════════════
    def enviar_notificacion(self, titulo: str, mensaje: str, destino: str = "todos"):
        from pywebpush import webpush, WebPushException
        archivo = "suscriptores.json"
        if not os.path.exists(archivo):
            return
        try:
            with open(archivo) as f:
                subs = json.load(f)
            payload = json.dumps({
                "title": titulo, "body": mensaje,
                "icon": "/icono.png", "badge": "/icono.png",
            })
            for sub in subs:
                if destino != "todos" and sub.get("nombre_usuario") != destino:
                    continue
                try:
                    webpush(
                        subscription_info=sub, data=payload,
                        vapid_private_key=VAPID_PRIVATE,
                        vapid_claims={"sub": VAPID_EMAIL}, timeout=5,
                    )
                    print(f"✅ Push → {sub.get('nombre_usuario', '?')}")
                except Exception as ex:
                    print(f"❌ Push → {sub.get('nombre_usuario', '?')}: {ex}")
        except Exception as e:
            print(f"❌ enviar_notificacion: {e}")

    @rx.event
    def guardar_subscripcion(self, js_result: str):
        if js_result == "USER_CANCEL":
            self.status = "Registro cancelado"
            return
        if not js_result or "ERROR" in js_result or js_result == "PERMISO_DENEGADO":
            self.status = f"❌ Push: {js_result}"
            return rx.window_alert(f"Error en notificaciones: {js_result}")
        try:
            data           = json.loads(js_result)
            sub_dict       = data.get("subscription")
            nombre_usuario = data.get("nombre", "").strip()
            if not nombre_usuario:
                self.status = "❌ Nombre inválido"
                return rx.window_alert("Debe proporcionar un nombre para el dispositivo.")
            archivo = "suscriptores.json"
            subs = []
            if os.path.exists(archivo):
                with open(archivo) as f:
                    try: subs = json.load(f)
                    except: subs = []
            existe_endpoint = False
            existe_nombre   = False
            endpoint_dup    = None
            for s in subs:
                if s.get("endpoint") == sub_dict.get("endpoint"):
                    existe_endpoint = True; endpoint_dup = s; break
                if s.get("nombre_usuario") == nombre_usuario:
                    existe_nombre = True
            if existe_endpoint:
                if endpoint_dup.get("nombre_usuario") != nombre_usuario:
                    endpoint_dup["nombre_usuario"] = nombre_usuario
                    with open(archivo, "w") as f: json.dump(subs, f, indent=4)
                    self.current_user = nombre_usuario
                    self.current_session = sub_dict.get("endpoint", "")
                    self.status = f"🔄 Nombre actualizado: '{nombre_usuario}'"
                    return rx.window_alert(f"✅ Nombre actualizado a '{nombre_usuario}'")
                else:
                    self.status = "ℹ️ Ya registrado"
                    return rx.window_alert("Este dispositivo ya estaba registrado.")
            if existe_nombre:
                self.status = f"❌ Nombre en uso"
                return rx.window_alert(f"El nombre '{nombre_usuario}' ya está en uso.")
            sub_dict["nombre_usuario"] = nombre_usuario
            subs.append(sub_dict)
            with open(archivo, "w") as f: json.dump(subs, f, indent=4)
            self.current_user = nombre_usuario
            self.current_session = sub_dict.get("endpoint", "")
            self.status = f"🔔 Vinculado: '{nombre_usuario}'"
            return rx.window_alert(f"✅ Dispositivo '{nombre_usuario}' vinculado!")
        except Exception as e:
            print(f"guardar_subscripcion error: {e}")
            self.status = "❌ Error al vincular"
            return rx.window_alert("Error inesperado.")

    # ════════════════════════════════════════════════════════════════════
    # CÁMARAS
    # ════════════════════════════════════════════════════════════════════

    @rx.var
    def url_fija_stream(self) -> str:
        if self.cam_mode == "pc":
            return "https://cam.noxuscmmd.uk/stream.html?src=fija&mode=webrtc"
        else:
            return "https://cam.noxuscmmd.uk/api/stream.m3u8?src=fija"

    @rx.var
    def url_ptz_stream(self) -> str:
        if self.cam_mode == "pc":
            return "https://cam.noxuscmmd.uk/stream.html?src=ptz&mode=webrtc"
        else:
            return "https://cam.noxuscmmd.uk/api/stream.m3u8?src=ptz"

    @rx.var
    def url_ptz_embed(self) -> str:
        return f"http://{os.getenv('IP_RASPBERRY', '0.0.0.0')}:1984/webrtc.html?src=ptz"

    def toggle_fija_stream(self):
        self.show_fija_stream = not self.show_fija_stream

    def toggle_ptz_stream(self):
        self.show_ptz_stream = not self.show_ptz_stream

    def toggle_cam_mode(self):
        self.cam_mode = "mobile" if self.cam_mode == "pc" else "pc"
        self.status = f"📷 Modo: {self.cam_mode.upper()}"

    # ── Control PTZ ──────────────────────────────────────────────────────

    @rx.event(background=True)
    async def move_ptz(self, direction: str):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                go2rtc_url = f"http://{os.getenv('IP_RASPBERRY', '100.76.90.7')}:1984/api/ptz"
                move_map = {"0": "up", "4": "down", "6": "left", "2": "right", "stop": "stop"}
                move = move_map.get(direction, "stop")
                params = {"move": move}
                async with s.get(go2rtc_url, params=params, timeout=2) as r:
                    if r.status == 200:
                        async with self:
                            self.cam_msg = f"✅ PTZ {move}"
                            self.status = f"✅ PTZ {move}"
                        return
        except Exception as e:
            print(f"⚠️ Error en go2rtc: {e}, intentando Tuya...")

        # Fallback a Tuya
        import hmac, hashlib
        t_id = os.getenv("TUYA_ACCESS_ID")
        t_secret = os.getenv("TUYA_ACCESS_SECRET")
        dev_id = os.getenv("ID_PTZ_TUYA")
        endpoint = "https://openapi.tuyaeu.com"
        if not t_id or not t_secret or not dev_id:
            async with self:
                self.cam_msg = "❌ Faltan credenciales Tuya"
                self.status = "❌ Faltan credenciales Tuya"
            return

        def get_sign(method, path, token="", body=""):
            ts = str(int(time.time() * 1000))
            cs = hashlib.sha256(body.encode()).hexdigest()
            sp = t_id + token + ts + f"{method}\n{cs}\n\n{path}"
            return hmac.new(t_secret.encode(), sp.encode(), hashlib.sha256).hexdigest().upper(), ts

        try:
            async with aiohttp.ClientSession() as s:
                sg, ts = get_sign("GET", "/v1.0/token?grant_type=1")
                async with s.get(endpoint + "/v1.0/token?grant_type=1",
                    headers={"client_id": t_id, "sign": sg, "t": ts, "sign_method": "HMAC-SHA256"},
                    timeout=aiohttp.ClientTimeout(total=5)) as r:
                    data = await r.json()
                    if not data.get("success"):
                        async with self:
                            self.cam_msg = f"❌ Error token: {data.get('msg')}"
                            self.status = f"❌ Error token: {data.get('msg')}"
                        return
                    token = data.get("result", {}).get("access_token")
                cp = f"/v1.0/devices/{dev_id}/commands"
                bm = json.dumps({"commands": [{"code": "ptz_control", "value": direction}]})
                sm, tm = get_sign("POST", cp, token, bm)
                h = {"client_id": t_id, "access_token": token, "sign": sm, "t": tm,
                    "sign_method": "HMAC-SHA256", "Content-Type": "application/json"}
                async with s.post(endpoint + cp, headers=h, data=bm, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    result = await r.json()
                    if result.get("success"):
                        async with self:
                            self.cam_msg = f"✅ PTZ {direction}"
                            self.status = f"✅ PTZ {direction}"
                        await asyncio.sleep(0.2)
                        bs = json.dumps({"commands": [{"code": "ptz_stop", "value": True}]})
                        ss2, ts2 = get_sign("POST", cp, token, bs)
                        h["sign"] = ss2; h["t"] = ts2
                        async with s.post(endpoint + cp, headers=h, data=bs, timeout=aiohttp.ClientTimeout(total=5)): pass
                    else:
                        async with self:
                            self.cam_msg = f"❌ Error: {result.get('msg')}"
                            self.status = f"❌ Error: {result.get('msg')}"
        except Exception as e:
            async with self:
                self.cam_msg = f"❌ Error: {str(e)[:60]}"
                self.status = f"❌ Error: {str(e)[:60]}"

    # ── Modo privacidad ──────────────────────────────────────────────────

    @rx.event(background=True)
    async def toggle_privacy(self, device_id: str, enable: bool):
        import aiohttp, hmac, hashlib
        t_id = os.getenv("TUYA_ACCESS_ID")
        t_secret = os.getenv("TUYA_ACCESS_SECRET")
        endpoint = "https://openapi.tuyaeu.com"
        if not t_id or not t_secret or not device_id:
            async with self:
                self.status = "❌ Faltan credenciales Tuya o ID de dispositivo"
            return

        def get_sign(method, path, token="", body=""):
            ts = str(int(time.time() * 1000))
            cs = hashlib.sha256(body.encode()).hexdigest()
            sp = t_id + token + ts + f"{method}\n{cs}\n\n{path}"
            return hmac.new(t_secret.encode(), sp.encode(), hashlib.sha256).hexdigest().upper(), ts

        try:
            async with aiohttp.ClientSession() as s:
                sg, ts = get_sign("GET", "/v1.0/token?grant_type=1")
                async with s.get(endpoint + "/v1.0/token?grant_type=1",
                    headers={"client_id": t_id, "sign": sg, "t": ts, "sign_method": "HMAC-SHA256"},
                    timeout=aiohttp.ClientTimeout(total=5)) as r:
                    data = await r.json()
                    if not data.get("success"):
                        async with self:
                            self.status = f"❌ Error token: {data.get('msg')}"
                        return
                    token = data.get("result", {}).get("access_token")
                cp = f"/v2.0/cloud/thing/{device_id}/shadow/properties/issue"
                body = json.dumps({"basic_private": enable})
                sm, tm = get_sign("POST", cp, token, body)
                h = {
                    "client_id": t_id,
                    "access_token": token,
                    "sign": sm,
                    "t": tm,
                    "sign_method": "HMAC-SHA256",
                    "Content-Type": "application/json"
                }
                async with s.post(endpoint + cp, headers=h, data=body, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    result = await r.json()
                    if result.get("success"):
                        async with self:
                            self.status = f"🔒 Privacidad {'ACTIVADA' if enable else 'DESACTIVADA'}"
                    else:
                        async with self:
                            self.status = f"❌ Error: {result.get('msg', 'desconocido')}"
        except Exception as e:
            async with self:
                self.status = f"❌ Error: {str(e)[:60]}"

    # ════════════════════════════════════════════════════════════════════
    # ACCIONES GENÉRICAS (usan DEVICE_CONFIG y device_actions)
    # ════════════════════════════════════════════════════════════════════

    @rx.event(background=True)
    async def accion_apagar(self, device_key: str):
        dev = DEVICE_CONFIG[device_key]
        async with self: self.status = f"🔌 Apagando {device_key}..."
        res = await device_actions.accion_apagar(dev["host"], dev["user"], dev["os"])
        async with self: self.status = f"✅ {device_key}: {res[:80]}"

    @rx.event(background=True)
    async def accion_reiniciar(self, device_key: str):
        dev = DEVICE_CONFIG[device_key]
        async with self: self.status = f"🔄 Reiniciando {device_key}..."
        res = await device_actions.accion_reiniciar(dev["host"], dev["user"], dev["os"])
        async with self: self.status = f"✅ {device_key}: {res[:80]}"

    @rx.event(background=True)
    async def accion_temperatura(self, device_key: str):
        dev = DEVICE_CONFIG[device_key]
        async with self: self.status = f"🌡️ Leyendo temperatura de {device_key}..."
        res = await device_actions.accion_temperatura(dev["host"], dev["user"], dev["os"])
        async with self: self.status = f"🌡️ {device_key}: {res}"

    @rx.event(background=True)
    async def accion_gpio(self, device_key: str, pin: str, estado: str):
        async with self: self.status = f"🔌 {device_key} GPIO{pin} -> {estado}"
        await device_actions.raspberry_gpio_set(pin, estado)
        async with self: self.status = f"✅ GPIO {pin} {estado}"

    @rx.event(background=True)
    async def ejecutar_comando_personalizado(self, device_key: str):
        dev = DEVICE_CONFIG[device_key]
        cmd = self.custom_command.get(device_key, "")
        if not cmd.strip():
            return
        async with self:
            self.status = f"⚡ Ejecutando en {device_key}: {cmd[:30]}..."
            self.custom_output[device_key] = "Ejecutando..."
        res = await device_actions.ssh_execute(dev["host"], dev["user"], cmd)
        async with self:
            self.custom_output[device_key] = res
            self.status = f"✅ {device_key}: comando completado"

    def set_custom_command(self, device_key: str, value: str):
        self.custom_command[device_key] = value

    # ════════════════════════════════════════════════════════════════════
    # MÉTODOS RDP / WOL / extras
    # ════════════════════════════════════════════════════════════════════

    def rdp_pc(self):
        device_actions.pc_rdp()
        self.status = "▶ PC RDP"

    def rdp_portatil(self):
        device_actions.portatil_rdp()
        self.status = "▶ Portátil RDP"

    def rdp_raspberry(self):
        device_actions.raspberry_rdp()
        self.status = "▶ Raspberry RDP"

    def wake_pc(self):
        device_actions.pc_wol()
        self.status = "⚡ WOL enviado"

    @rx.event(background=True)
    async def gpio_17_test(self):
        async with self: self.status = "🌬️ Ventilador ON..."
        try:
            await device_actions.raspberry_gpio_17_test()
            async with self: self.status = "🌬️ Test completado"
        except Exception as e:
            async with self: self.status = f"❌ GPIO: {e}"

    @rx.event(background=True)
    async def tomar_foto_raspberry(self):
        async with self:
            if not self.pi_zero_online:
                self.status = "❌ Pi Zero OFFLINE"; return
            self.status = "📸 Capturando..."
        try:
            foto_bytes = await device_actions.pizero_tomar_foto()
            foto_b64   = base64.b64encode(foto_bytes).decode()
            async with self:
                self.last_rpi_photo = f"data:image/jpeg;base64,{foto_b64}"
                self.dialog_foto_abierto = True
                self.status = "✅ Foto capturada"
        except Exception as e:
            async with self: self.status = f"❌ Foto: {e}"

    def toggle_dialog(self):
        self.dialog_foto_abierto = not self.dialog_foto_abierto

    async def handle_upload(self, files: list[rx.UploadFile]):
        upload_dir = Path(os.getenv("UPLOAD_FOLDER", "/home/spamer/archivos"))
        upload_dir.mkdir(parents=True, exist_ok=True)
        for file in files:
            data = await file.read()
            (upload_dir / file.name).write_bytes(data)
        self.status = f"✅ {len(files)} archivo(s) subido(s)"

    @rx.event(background=True)
    async def medir_temperatura(self):
        async with self: self.temperaturas = []; self.status = "🌡️ Midiendo..."
        resultados = await asyncio.gather(
            Sensors.get_cpu_temp_async(),
            Sensors.get_cpu_temp_async(),
            Sensors.get_cpu_temp_async(),
        )
        async with self:
            self.temperaturas = [f"🌡️ {t:.1f} °C" for t in resultados]
            self.status = f"🌡️ Temp: {resultados[1]:.1f} °C"

    @rx.event(background=True)
    async def restart_raspberry(self):
        async with self: self.status = "🔄 Reiniciando Raspberry..."
        await asyncio.to_thread(
            subprocess.Popen,
            f'ssh -o StrictHostKeyChecking=no -o ConnectTimeout=4 '
            f'vpn@{os.getenv("IP_RASPBERRY", "100.76.90.7")} "sudo reboot now"',
            shell=True
        )
        async with self: self.status = "🔄 Reboot enviado"

# ══════════════════════════════════════════════════════════════════════
# CONFIGURACIÓN DE DISPOSITIVOS
# ══════════════════════════════════════════════════════════════════════
DEVICE_CONFIG = {
    "server": {
        "host": os.getenv("IP_SERVER", ""),
        "user": os.getenv("SERVER_USER", "spamer"),
        "os": "linux",
        "gpio_pins": {},
        "acciones_extra": [],
    },
    "pc": {
        "host": os.getenv("IP_PC", ""),
        "user": os.getenv("PC_USER", "ruben"),
        "os": "windows",
        "gpio_pins": {},
        "acciones_extra": [
            {"nombre": "Wake on LAN", "funcion": State.wake_pc},
            {"nombre": "RDP", "funcion": State.rdp_pc},
        ],
    },
    "portatil": {
        "host": os.getenv("IP_PORTATIL", ""),
        "user": os.getenv("PORTATIL_USER", "ruben"),
        "os": "windows",
        "gpio_pins": {},
        "acciones_extra": [
            {"nombre": "RDP", "funcion": State.rdp_portatil},
        ],
    },
    "raspberry": {
        "host": os.getenv("IP_RASPBERRY", ""),
        "user": os.getenv("RASPBY_USER", "vpn"),
        "os": "linux",
        "gpio_pins": {
            "17": "Ventilador",
        },
        "acciones_extra": [
            {"nombre": "Test Ventilador", "funcion": State.gpio_17_test},
            {"nombre": "RDP", "funcion": State.rdp_raspberry},
            {"nombre": "Foto (Pi Zero)", "funcion": State.tomar_foto_raspberry},
        ],
    },
    "pi_zero": {
        "host": os.getenv("IP_PI_ZERO", ""),
        "user": os.getenv("ZERO_USER", "zero"),
        "os": "linux",
        "gpio_pins": {},
        "acciones_extra": [
            {"nombre": "Capturar Foto", "funcion": State.tomar_foto_raspberry},
        ],
    },
}