import time

try:
    import network
    IS_MICROPYTHON = True
except ImportError:
    IS_MICROPYTHON = False


class WifiManager:
    """
    Gerencia a conexão Wi-Fi do MicroPython (Modo Estação STA e Modo Access Point AP).
    """

    def __init__(self, config_manager):
        self.config = config_manager
        self.is_connected = False
        self.ip_address = "127.0.0.1"
        self.mode = "STA"  # STA ou AP

    def connect(self):
        if not IS_MICROPYTHON:
            print("[MOCK] WifiManager rodando em modo de simulação (Localhost)")
            self.is_connected = True
            self.ip_address = "127.0.0.1"
            return True

        ssid = self.config.get("wifi_ssid", "").strip()
        password = self.config.get("wifi_password", "").strip()

        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)

        if ssid:
            print("Tentando conectar a rede Wi-Fi:", ssid)
            wlan.connect(ssid, password)

            # Tenta conectar por até 10 segundos
            attempts = 0
            while not wlan.isconnected() and attempts < 10:
                time.sleep(1)
                attempts += 1

            if wlan.isconnected():
                self.is_connected = True
                self.ip_address = wlan.ifconfig()[0]
                self.mode = "STA"
                print("Conectado com sucesso ao Wi-Fi! IP:", self.ip_address)
                return True

        # Se nao houver SSID configurado ou falhar a conexao, inicia modo AP
        print("Iniciando Modo Ponto de Acesso (AP) para configuracao...")
        self.start_ap()
        return False

    def start_ap(self, ap_ssid="GateAutomation-AP", ap_password=""):
        if not IS_MICROPYTHON:
            return

        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=ap_ssid, password=ap_password)

        self.is_connected = True
        self.ip_address = ap.ifconfig()[0]
        self.mode = "AP"
        print("Modo AP Ativado! Conecte-se em", ap_ssid, "- IP:", self.ip_address)

    def get_status(self):
        return {
            "connected": self.is_connected,
            "ip": self.ip_address,
            "mode": self.mode,
            "ssid": self.config.get("wifi_ssid", "")
        }
