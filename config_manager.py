import json

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "wifi_ssid": "",
    "wifi_password": "",
    "server_base_url": "http://sitiobarreiras.app.br:55432",
    "auth_header": "sbs",
    "relay_pin": 18,
    "gate_open_duration": 5,
    "pin_barrier": 2,
    "pin_hall": 3,
    "pin_aux": 4,
    "rfid_uart_id": 0,
    "rfid_baudrate": 9600,
    "rfid_rx_pin": 5
}

class ConfigManager:
    def __init__(self, filepath=CONFIG_FILE):
        self.filepath = filepath
        self.config = dict(DEFAULT_CONFIG)
        self.load()

    def load(self):
        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
                for k, v in data.items():
                    self.config[k] = v
        except Exception as e:
            print("Aviso ao carregar config.json, usando padrao:", e)
            self.save()

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.config, f)
            return True
        except Exception as e:
            print("Erro ao salvar config.json:", e)
            return False

    def get(self, key, default=None):
        return self.config.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def update(self, new_data):
        for k, v in new_data.items():
            if k in DEFAULT_CONFIG:
                # Converte tipos numericos caso venham como string
                if k in ["relay_pin", "gate_open_duration", "pin_barrier", "pin_hall", "pin_aux", "rfid_uart_id", "rfid_baudrate", "rfid_rx_pin"]:
                    try:
                        self.config[k] = int(v)
                    except (ValueError, TypeError):
                        pass
                else:
                    self.config[k] = str(v)
        return self.save()
