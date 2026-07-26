import reflex as rx
import os
from ..state import State
from ..components.status_row import status_row

VAPID_PUBLIC = os.getenv("VAPID_PUBLIC_KEY")

# Coordenadas del sensor magnético sobre el plano
SENSOR_POS = {
    "top": "81%",
    "left": "88%",
}
CAM_1_POS = {
    "top": "83%",
    "left": "5%",
}

# Coordenadas para los tamper en la esquina inferior izquierda
TAMPER1_POS = {
    "top": "85%",
    "left": "24%",
}
TAMPER2_POS = {
    "top": "92%",
    "left": "15%",
}

def logs_popover():
    """Popover que muestra el historial de logs con el formato solicitado."""
    return rx.popover.root(
        rx.popover.trigger(
            rx.button(
                rx.icon("clipboard-list", size=18, color="#94a3b8"),
                variant="ghost",
                size="1",
                cursor="pointer",
                aria_label="Ver registros",
                title="Historial de eventos",
            )
        ),
        rx.popover.content(
            rx.vstack(
                rx.hstack(
                    rx.icon("clipboard-list", size=16, color="#94a3b8"),
                    # Título clickeable que ejecuta refresh_logs
                    rx.button(
                        "REGISTROS",
                        variant="ghost",
                        size="3",
                        letter_spacing="0.05em",
                        font_weight="bold",
                        padding="0",
                        on_click=State.refresh_logs,
                        _active={"transform": "scale(1.1)"},
                        _hover={"color": "#e2e8f0"},
                    ),
                    rx.spacer(),
                    rx.button(
                        rx.icon("x", size=14),
                        variant="ghost",
                        size="1",
                        on_click=rx.call_script("document.querySelector('[data-state=open]')?.click()"),
                        title="Cerrar",
                    ),
                    width="100%",
                    align="center",
                ),
                rx.divider(opacity="0.1"),
                rx.box(
                    rx.foreach(
                        State.logs_recientes,
                        lambda log: rx.hstack(
                            # Icono según el tipo de acción
                            rx.cond(
                                log["accion"] == "ALARMA_DISPARADA",
                                rx.icon("triangle-alert", size=16, color="#ef4444"),
                                rx.cond(
                                    log["accion"] == "ARMADO",
                                    rx.icon("shield-check", size=16, color="#22c55e"),
                                    rx.cond(
                                        log["accion"] == "DESARMADO",
                                        rx.icon("shield-off", size=16, color="#64748b"),
                                        rx.cond(
                                            log["accion"] == "PUERTA_ABIERTA",
                                            rx.icon("door-open", size=16, color="#f97316"),
                                            rx.cond(
                                                log["accion"] == "PUERTA_CERRADA",
                                                rx.icon("door-closed", size=16, color="#22c55e"),
                                                rx.cond(
                                                    log["accion"] == "TAMPER1_ABIERTO",
                                                    rx.icon("lock", size=16, color="#ef4444"),
                                                    rx.cond(
                                                        log["accion"] == "TAMPER1_CERRADO",
                                                        rx.icon("lock", size=16, color="#22c55e"),
                                                        rx.cond(
                                                            log["accion"] == "TAMPER2_ABIERTO",
                                                            rx.icon("lock", size=16, color="#ef4444"),
                                                            rx.cond(
                                                                log["accion"] == "TAMPER2_CERRADO",
                                                                rx.icon("lock", size=16, color="#22c55e"),
                                                                rx.icon("file-text", size=16, color="#94a3b8")
                                                            )
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                            ),
                            rx.text(log["timestamp"], size="1", color="#94a3b8", width="150px", font_family="monospace"),
                            rx.text(log["usuario"], size="1", color="#38bdf8", width="100px"),
                            # Detalle con POPOVER para ARMADO con abiertos
                            rx.cond(
                                log["accion"] == "ARMADO",
                                rx.cond(
                                    log["detalle"].to(str) != "Armado (sin abiertos)",
                                    rx.popover.root(
                                        rx.popover.trigger(
                                            rx.icon("info", size=16, color="#f97316", cursor="pointer")
                                        ),
                                        rx.popover.content(
                                            rx.vstack(
                                                rx.text("Elementos abiertos al armar:", weight="bold", color="#e2e8f0"),
                                                rx.text(
                                                    log["detalle"].to(str).replace("Armado con abiertos: ", ""),
                                                    color="#94a3b8"
                                                ),
                                                spacing="2",
                                            ),
                                            background="#1e293b",
                                            border="1px solid #475569",
                                            padding="12px",
                                            border_radius="8px",
                                        ),
                                    ),

                                    
                                ),
                                rx.cond(
                                    log["accion"] == "DESARMADO",
                                    rx.icon("shield-off", size=16, color="#64748b"),
                                    rx.text(log["detalle"], size="1", color="#e2e8f0", flex="1"),
                                ),
                            ),
                            spacing="2",
                            width="100%",
                            align="center",
                            padding_y="0.3em",
                            border_bottom="1px solid rgba(255,255,255,0.05)",
                        ),
                    ),
                    max_height="350px",
                    overflow_y="auto",
                    width="100%",
                    font_family="monospace",
                ),
                spacing="2",
                width="min(700px, 92vw)",
                padding="8px",
            ),
            background="#111827",
            border="1px solid rgba(255,255,255,0.1)",
            box_shadow="0 10px 25px -5px rgba(0,0,0,0.5)",
            padding="12px",
        ),
    )

def alarma_control_view():
    return rx.card(
        rx.vstack(
            rx.hstack(
                # Popover del escudo (plano interactivo) - ICONO ROJO O GRIS
                rx.popover.root(
                    rx.popover.trigger(
                        rx.button(
                            rx.icon(
                                rx.cond(State.sistema_armado, "shield-check", "shield-off"),
                                # ROJO cuando armado, GRIS cuando desarmado
                                color=rx.cond(State.sistema_armado, "#ef4444", "#64748b"),
                                size=22,
                            ),
                            variant="ghost",
                            size="1",
                            cursor="pointer",
                            aria_label="Ver plano de sensores",
                            title="Ver mapa de sensores",
                        )
                    ),
                    rx.popover.content(
                        rx.vstack(
                            rx.text("Plano de Planta", size="1", weight="bold", color="#94a3b8"),
                            rx.divider(opacity="0.1"),
                            rx.box(
                                rx.image(
                                    src="/room.png",
                                    width="100%",
                                    height="auto",
                                    object_fit="contain",
                                    border_radius="6px",
                                    opacity="0.9",
                                ),
                                # Sensor puerta principal
                                rx.box(
                                    rx.cond(
                                        State.puerta_abierta,
                                        rx.box(
                                            rx.icon("door-open", size=14, color="#ef4444"),
                                            background="rgba(239, 68, 68, 0.25)",
                                            border="2px solid #ef4444",
                                            border_radius="50%",
                                            padding="6px",
                                            box_shadow="0 0 16px #ef4444",
                                            animation="pulse 1.5s infinite alternate",
                                        ),
                                        rx.box(
                                            rx.icon("lock", size=12, color="#22c55e"),
                                            background="rgba(34, 197, 94, 0.2)",
                                            border="2px solid #22c55e",
                                            border_radius="50%",
                                            padding="4px",
                                            box_shadow="0 0 8px #22c55e",
                                        ),
                                    ),
                                    position="absolute",
                                    top=SENSOR_POS["top"],
                                    left=SENSOR_POS["left"],
                                    transform="translate(-50%, -50%)",
                                    cursor="help",
                                    title=rx.cond(State.puerta_abierta, "Puerta Principal: ABIERTA", "Puerta Principal: Cerrada"),
                                    z_index="10",
                                ),
                                # Cámara fija
                                rx.box(
                                    rx.icon("cctv", size=14, color="#38bdf8"),
                                    background="rgba(56, 189, 248, 0.2)",
                                    border="2px solid #38bdf8",
                                    border_radius="50%",
                                    padding="6px",
                                    box_shadow="0 0 12px #38bdf8",
                                    position="absolute",
                                    top=CAM_1_POS["top"],
                                    left=CAM_1_POS["left"],
                                    transform="translate(-50%, -50%)",
                                    cursor="pointer",
                                    title="Cámara Fija Principal",
                                    z_index="10",
                                    on_click=State.toggle_fija_stream,
                                ),
                                # Tamper 1 - RECTÁNGULO DE BORDE (3px alto, 6px ancho) SIN RELLENO
                                rx.popover.root(
                                    rx.popover.trigger(
                                        rx.box(
                                            # El rectángulo: solo borde, sin relleno
                                            width="29px",
                                            height="16px",
                                            border=rx.cond(
                                                State.tamper1_abierto,
                                                "1px solid #ef4444",   # ROJO cuando abierto (1px para no colapsar los 3px de alto)
                                                "1px solid #3b82f6"    # AZUL cuando cerrado
                                            ),
                                            border_radius="1px",
                                            background="transparent",
                                            box_sizing="border-box",   # Garantiza que el borde no aumente las dimensiones finales
                                            cursor="pointer",
                                            title=rx.cond(
                                                State.tamper1_abierto,
                                                f"Tamper1: ABIERTO (estado: {rx.cond(State.tamper1_armado, 'ARMADO', 'DESARMADO')})",
                                                f"Tamper1: CERRADO (estado: {rx.cond(State.tamper1_armado, 'ARMADO', 'DESARMADO')})"
                                            ),
                                        ),
                                        position="absolute",
                                        top=TAMPER1_POS["top"],
                                        left=TAMPER1_POS["left"],
                                        transform="translate(-50%, -50%)",
                                        z_index="10",
                                    ),
                                    rx.popover.content(
                                        rx.vstack(
                                            rx.text("Control Tamper1", size="2", weight="bold", color="#e2e8f0"),
                                            rx.divider(opacity="0.1"),
                                            rx.hstack(
                                                rx.button(
                                                    "ARMAR",
                                                    on_click=State.toggle_tamper1_armado(True),
                                                    color_scheme="red",
                                                    variant=rx.cond(State.tamper1_armado, "solid", "surface"),
                                                    size="2",
                                                    width="100px",
                                                ),
                                                rx.button(
                                                    "DESARMAR",
                                                    on_click=State.toggle_tamper1_armado(False),
                                                    color_scheme="gray",
                                                    variant=rx.cond(~State.tamper1_armado, "solid", "surface"),
                                                    size="2",
                                                    width="100px",
                                                ),
                                                spacing="2",
                                                width="100%",
                                                justify="center",
                                            ),
                                            rx.cond(
                                                State.tamper1_armado,
                                                rx.text("🔴 ARMADO", size="1", color="#ef4444"),
                                                rx.text("🔓 DESARMADO", size="1", color="#94a3b8"),
                                            ),
                                            spacing="2",
                                            width="200px",
                                            padding="8px",
                                        ),
                                        background="#1e293b",
                                        border="1px solid #475569",
                                        border_radius="8px",
                                        padding="12px",
                                    ),
                                    position="absolute",
                                    top=TAMPER1_POS["top"],
                                    left=TAMPER1_POS["left"],
                                    transform="translate(-50%, -50%)",
                                    z_index="10",
                                ),
                                # Tamper 2
                                rx.box(
                                    rx.cond(
                                        State.tamper2_abierto,
                                        rx.icon("lock-open", size=12, color="#ef4444"),
                                        rx.icon("lock", size=12, color="#22c55e"),
                                    ),
                                    background=rx.cond(
                                        State.tamper2_abierto,
                                        "rgba(239, 68, 68, 0.25)",
                                        "rgba(34, 197, 94, 0.2)",
                                    ),
                                    border=rx.cond(
                                        State.tamper2_abierto,
                                        "2px solid #ef4444",
                                        "2px solid #22c55e",
                                    ),
                                    border_radius="50%",
                                    padding="4px",
                                    box_shadow=rx.cond(
                                        State.tamper2_abierto,
                                        "0 0 12px #ef4444",
                                        "0 0 8px #22c55e",
                                    ),
                                    position="absolute",
                                    top=TAMPER2_POS["top"],
                                    left=TAMPER2_POS["left"],
                                    transform="translate(-50%, -50%)",
                                    cursor="help",
                                    title=rx.cond(State.tamper2_abierto, "Tamper2: ABIERTO", "Tamper2: Cerrado"),
                                    z_index="10",
                                ),
                                position="relative",
                                width="100%",
                                max_height="55vh",
                                overflow="hidden",
                                background="#0f172a",
                                border_radius="6px",
                                border="1px solid rgba(255, 255, 255, 0.05)",
                            ),
                            spacing="2",
                            width="min(340px, 92vw)",
                        ),
                        background="#111827",
                        border="1px solid rgba(255, 255, 255, 0.1)",
                        box_shadow="0 10px 25px -5px rgba(0, 0, 0, 0.5)",
                        padding="10px",
                    ),
                ),
                logs_popover(),
                rx.heading("SEGURIDAD", size="3", letter_spacing="0.05em"),
                rx.spacer(),
                rx.badge(
                    rx.cond(State.puerta_abierta, "ABIERTA", "CERRADA"),
                    color_scheme=rx.cond(State.puerta_abierta, "red", "green"),
                    variant="surface"
                ),
                rx.button(
                    rx.icon("triangle-alert", size=18, color="#f97316"),
                    on_click=rx.call_script(
                        f"""
                        (async function() {{
                            let sub = null;
                            try {{
                                const reg = await navigator.serviceWorker.ready;
                                const pushSub = await reg.pushManager.getSubscription();
                                if (pushSub) {{
                                    sub = {{
                                        endpoint: pushSub.endpoint,
                                        keys: {{
                                            p256dh: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('p256dh')))),
                                            auth: btoa(String.fromCharCode.apply(null, new Uint8Array(pushSub.getKey('auth')))),
                                        }}
                                    }};
                                }}
                            }} catch(e) {{
                                console.warn('No se pudo obtener la suscripción:', e);
                            }}
                            const subscription = sub ? JSON.stringify(sub) : 'null';
                            return subscription;
                        }})();
                        """,
                        callback=State.lanzar_alerta_global_con_subscripcion
                    ),
                    variant="ghost",
                    size="1",
                    title="Enviar alerta a todos",
                    aria_label="Enviar alerta push a todos los dispositivos",
                ),
                rx.button(
                    rx.icon("bell", size=18),
                    on_click=rx.call_script(
                        f"""
                        (async function() {{
                            try {{
                                let nombre = window.prompt("Nombre para este dispositivo (ej: Mi iPhone, PC Oficina):", "");
                                if (nombre === null) return "USER_CANCEL";
                                nombre = nombre.trim();
                                if (nombre === "") {{
                                    alert("El nombre no puede estar vacío. Cancelado.");
                                    return "USER_CANCEL";
                                }}
                                
                                let reg;
                                for (let intentos = 0; intentos < 3; intentos++) {{
                                    try {{
                                        reg = await navigator.serviceWorker.register('/sw.js');
                                        await navigator.serviceWorker.ready;
                                        break;
                                    }} catch (e) {{
                                        console.warn("Intento " + (intentos+1) + " fallido", e);
                                        await new Promise(r => setTimeout(r, 500));
                                    }}
                                }}
                                if (!reg) throw new Error("No se pudo registrar el Service Worker");
                                
                                const publicKey = '{VAPID_PUBLIC}';
                                const toUint8 = (b) => {{
                                    const pad = '='.repeat((4 - b.length % 4) % 4);
                                    const b64 = (b + pad).replace(/-/g, '+').replace(/_/g, '/');
                                    const raw = window.atob(b64);
                                    const out = new Uint8Array(raw.length);
                                    for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
                                    return out;
                                }};
                                
                                const perm = await Notification.requestPermission();
                                if (perm !== 'granted') return "PERMISO_DENEGADO";
                                
                                const sub = await reg.pushManager.subscribe({{
                                    userVisibleOnly: true,
                                    applicationServerKey: toUint8(publicKey)
                                }});
                                
                                return JSON.stringify({{
                                    subscription: sub,
                                    nombre: nombre
                                }});
                            }} catch (err) {{
                                if (err.name === "NotAllowedError") return "PERMISO_BLOQUEADO";
                                return "ERROR_" + err.message;
                            }}
                        }})();
                        """,
                        callback=State.guardar_subscripcion
                    ),
                    variant="ghost",
                    size="1",
                    title="Suscribirse a notificaciones push",
                    aria_label="Suscribirse a notificaciones push",
                ),
                width="100%",
                align="center",
                spacing="2",
            ),
            rx.divider(opacity="0.1"),
            rx.hstack(
                rx.text("Monitoreo de Intrusión", size="2", color="#94a3b8"),
                rx.spacer(),
                rx.button(
                    rx.cond(State.sistema_armado, "DESARMAR", "ARMAR"),
                    on_click=State.conmutar_alarma,
                    color_scheme=rx.cond(State.sistema_armado, "red", "green"),
                    variant=rx.cond(State.sistema_armado, "solid", "surface"),
                    size="2",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.03)",
        backdrop_filter="blur(10px)",
        # BORDE ROJO cuando armado, gris cuando desarmado
        border=rx.cond(State.sistema_armado, "1px solid rgba(239, 68, 68, 0.3)", "1px solid rgba(255, 255, 255, 0.1)"),
        padding="4",
    )

def cctv_view():
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.icon("video", size=20, color="#818cf8"),
                rx.heading("CCTV", size="3", letter_spacing="0.05em"),
                rx.spacer(),
                rx.vstack(
                    rx.text("H.Ppal", size="1", color="gray"),
                    rx.icon("cctv", size=20, color="#38bdf8"),
                    on_click=State.toggle_fija_stream,
                    cursor="pointer",
                    align="center",
                    spacing="0",
                ),
                rx.vstack(
                    rx.text("PTZ", size="1", color="gray"),
                    rx.icon("rotate-cw", size=20, color="#a78bfa"),
                    on_click=State.toggle_ptz_stream,
                    cursor="pointer",
                    align="center",
                    spacing="0",
                ),
                width="100%",
                align="center",
            ),
            spacing="3",
        ),
        width="100%",
        background="rgba(255, 255, 255, 0.03)",
        backdrop_filter="blur(10px)",
        border="1px solid rgba(255, 255, 255, 0.1)",
        padding="4",
    )

def device_list_view():
    return rx.vstack(
        alarma_control_view(),
        cctv_view(),
        rx.hstack(
            rx.icon("activity", size=20, color="#38bdf8"),
            rx.heading("INFRAESTRUCTURA", size="3", letter_spacing="0.05em"),
            rx.spacer(),
            width="100%",
            align="center",
            px="2",
            pt="2",
        ),
        rx.card(
            rx.vstack(
                status_row("Servidor", os.getenv("IP_SERVER", "0.0.0.0"), State.server_online, "network"),
                status_row("PC", os.getenv("IP_PC", "0.0.0.0"), State.pc_online, "monitor", on_rdp=State.rdp_pc),
                status_row("Portátil", os.getenv("IP_PORTATIL", "0.0.0.0"), State.portatil_online, "laptop", on_rdp=State.rdp_portatil),
                status_row("Raspberry", os.getenv("IP_RASPBERRY", "0.0.0.0"), State.raspberry_online, "grape", on_rdp=State.rdp_raspberry),
                status_row("Pi Zero", os.getenv("IP_PI_ZERO", "0.0.0.0"), State.pi_zero_online, "microchip"),
                status_row("iPhone", os.getenv("IP_IPHONE", "0.0.0.0"), State.iphone_online, "smartphone"),
                status_row("Tablet", os.getenv("IP_TABLET", "0.0.0.0"), State.tablet_online, "tablet"),
                spacing="2",
                width="100%",
            ),
            width="100%",
            background="rgba(255, 255, 255, 0.03)",
            backdrop_filter="blur(10px)",
            border="1px solid rgba(255, 255, 255, 0.1)",
            padding="4",
        ),
        width="100%",
        spacing="3",
    )