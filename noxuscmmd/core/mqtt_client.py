import asyncio
import paho.mqtt.client as mqtt
import time
from .shared_state import set_puerta_abierta, set_tamper1_abierto, set_tamper2_abierto

class MQTTClient:
    def __init__(self, broker, port, topic_puerta, state_instance=None):
        self.broker = broker
        self.port = port
        self.topic_puerta = topic_puerta
        self.topic_tamper1 = "casa/pizero/tamper1"
        self.topic_tamper2 = "casa/pizero/tamper2"
        self.state = state_instance  # Guardado por compatibilidad, no se usa para la UI
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.ultimo_estado_puerta = None
        self.ultimo_estado_tamper1 = None
        self.ultimo_estado_tamper2 = None
        self.ultimo_timestamp = 0

    def on_connect(self, client, userdata, flags, rc):
        print(f"✅ Conectado MQTT (código {rc})")
        client.subscribe(self.topic_puerta)
        client.subscribe(self.topic_tamper1)
        client.subscribe(self.topic_tamper2)

    def on_message(self, client, userdata, msg):
        ahora = time.time()
        payload = msg.payload.decode()
        topic = msg.topic

        # Filtro anti-rebote por tópico
        if topic == self.topic_puerta:
            if payload == self.ultimo_estado_puerta and (ahora - self.ultimo_timestamp) < 0.5:
                return
            self.ultimo_estado_puerta = payload
            abierta = (payload == "ON")
            print(f"📨 [{ahora:.3f}] MQTT Puerta: {payload} -> abierta={abierta}")
            set_puerta_abierta(abierta)

        elif topic == self.topic_tamper1:
            if payload == self.ultimo_estado_tamper1 and (ahora - self.ultimo_timestamp) < 0.5:
                return
            self.ultimo_estado_tamper1 = payload
            abierto = (payload == "ON")
            print(f"📨 [{ahora:.3f}] MQTT Tamper1: {payload} -> abierto={abierto}")
            set_tamper1_abierto(abierto)

        elif topic == self.topic_tamper2:
            if payload == self.ultimo_estado_tamper2 and (ahora - self.ultimo_timestamp) < 0.5:
                return
            self.ultimo_estado_tamper2 = payload
            abierto = (payload == "ON")
            print(f"📨 [{ahora:.3f}] MQTT Tamper2: {payload} -> abierto={abierto}")
            set_tamper2_abierto(abierto)

        self.ultimo_timestamp = ahora

    def start(self):
        self.client.connect(self.broker, self.port, 60)
        self.client.loop_start()

    def stop(self):
        self.client.loop_stop()
        self.client.disconnect()

# Fuente global de inicialización
_mqtt_client_instance = None

def get_mqtt_client(broker, port, topic, state_instance=None):
    global _mqtt_client_instance
    if _mqtt_client_instance is None:
        _mqtt_client_instance = MQTTClient(broker, port, topic, state_instance)
        _mqtt_client_instance.start()
    return _mqtt_client_instance