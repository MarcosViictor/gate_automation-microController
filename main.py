import time
from config_manager import ConfigManager
from wifi_manager import WifiManager
from sensor_manager import SensorManager
from gate_relay import GateRelay
from server_client import ServerClient
from tag_manager import TagManager
from web_server import WebServer


def main():
    print("Iniciando sistema Gate Automation...")

    # 1. Carrega configuracoes
    config = ConfigManager()

    # 2. Conecta ao Wi-Fi ou ativa modo AP
    wifi = WifiManager(config)
    wifi.connect()

    # 3. Inicializa Sensores e Relé
    sensors = SensorManager(config)
    relay = GateRelay(config, sensor_manager=sensors)

    # 4. Inicializa Cliente HTTP e Gerenciador de Tags
    server_client = ServerClient(config)
    tag_mgr = TagManager(config, server_client, sensors, relay)

    # 5. Inicia Servidor Web na porta 80
    web_server = WebServer(config, wifi, sensors, relay, tag_mgr, port=80)
    web_server.start()

    print("\n[OK] Sistema rodando com sucesso!")
    print("Monitorando sensores: RFID (UART), Barreira (GPIO 2), Hall (GPIO 3), Aux (GPIO 4)...")
    print("Pressione Ctrl+C para encerrar.\n")

    last_aux_press = 0

    try:
        while True:
            # 1. Poll Leitor RFID
            tag_code = sensors.poll_rfid()
            if tag_code:
                print("Tag RFID detectada via UART:", tag_code)
                tag_mgr.process_tag(tag_code, source="UART_RFID")

            # 2. Poll Sensor Auxiliar / Botoeira (com debounce de 1s)
            if sensors.is_aux_pressed() and (time.time() - last_aux_press > 1.0):
                last_aux_press = time.time()
                print("Botoeira Auxiliar pressionada!")
                relay.trigger_open()

            # 3. Atende requisicoes HTTP no servidor web
            web_server.poll()

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nEncerrando sistema...")


if __name__ == "__main__":
    main()
