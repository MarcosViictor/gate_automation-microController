import time

# Tenta importar machine (MicroPython). Se falhar, usa modo mock para desenvolvimento em PC.
try:
    from machine import Pin, UART
    IS_MICROPYTHON = True
except ImportError:
    IS_MICROPYTHON = False


class SensorManager:
    """
    Gerencia os 4 sensores da automação do portão:
    1. Sensor de Barreira (GPIO - PULL_UP. 0 = Veículo no caminho, 1 = Acesso livre)
    2. Sensor Hall (GPIO - PULL_UP. 0 = Portão Aberto, 1 = Portão Fechado)
    3. Sensor Auxiliar / Botoeira (GPIO - PULL_UP. 0 = Pressionado/Acionado)
    4. Leitor RFID (UART ou Simulação Web)
    """

    def __init__(self, config_manager):
        self.config = config_manager
        self.barrier_pin = None
        self.hall_pin = None
        self.aux_pin = None
        self.uart = None
        self.last_tag = None
        self.last_tag_time = 0

        self.setup_hardware()

    def setup_hardware(self):
        if not IS_MICROPYTHON:
            print("[MOCK] SensorManager iniciado em modo de simulação (Python padrão)")
            return

        pin_b = self.config.get("pin_barrier", 2)
        pin_h = self.config.get("pin_hall", 3)
        pin_a = self.config.get("pin_aux", 4)

        try:
            self.barrier_pin = Pin(pin_b, Pin.IN, Pin.PULL_UP)
            print("Sensor de Barreira configurado no pino GPIO", pin_b)
        except Exception as e:
            print("Erro ao configurar pino da barreira:", e)

        try:
            self.hall_pin = Pin(pin_h, Pin.IN, Pin.PULL_UP)
            print("Sensor Hall configurado no pino GPIO", pin_h)
        except Exception as e:
            print("Erro ao configurar pino Hall:", e)

        try:
            self.aux_pin = Pin(pin_a, Pin.IN, Pin.PULL_UP)
            print("Sensor Auxiliar/Botoeira configurado no pino GPIO", pin_a)
        except Exception as e:
            print("Erro ao configurar pino auxiliar:", e)

        try:
            uart_id = self.config.get("rfid_uart_id", 0)
            baudrate = self.config.get("rfid_baudrate", 9600)
            rx_pin = self.config.get("rfid_rx_pin", 5)
            self.uart = UART(uart_id, baudrate=baudrate, rx=Pin(rx_pin))
            print("UART RFID configurado no UART", uart_id, "Baudrate", baudrate, "Rx Pin", rx_pin)
        except Exception as e:
            print("Aviso: UART RFID nao inicializado:", e)

    def is_barrier_clear(self):
        """Retorna True se o acesso estiver livre (sem veículo)."""
        if not IS_MICROPYTHON or self.barrier_pin is None:
            return True  # Mock: livre por padrao

        # Conforme implementacao do usuario: 0 = Veiculo no caminho, 1 = acesso livre
        return self.barrier_pin.value() == 1

    def get_barrier_status(self):
        """Retorna texto explicativo do estado do sensor de barreira."""
        if not IS_MICROPYTHON or self.barrier_pin is None:
            return "Acesso livre (Simulado)"
        val = self.barrier_pin.value()
        return "Veiculo no caminho" if val == 0 else "Acesso livre"

    def get_hall_status(self):
        """Retorna se o portão está Aberto ou Fechado pelo Sensor Hall."""
        if not IS_MICROPYTHON or self.hall_pin is None:
            return "Fechado (Simulado)"
        val = self.hall_pin.value()
        return "Aberto" if val == 0 else "Fechado"

    def is_aux_pressed(self):
        """Retorna True se a botoeira/sensor auxiliar for acionado (0)."""
        if not IS_MICROPYTHON or self.aux_pin is None:
            return False
        return self.aux_pin.value() == 0

    def get_aux_status(self):
        """Retorna o estado da botoeira auxiliar."""
        if not IS_MICROPYTHON or self.aux_pin is None:
            return "Em espera (Simulado)"
        return "Pressionado" if self.aux_pin.value() == 0 else "Em espera"

    def poll_rfid(self):
        """Lê caracteres da porta UART RFID se disponíveis."""
        if not IS_MICROPYTHON or self.uart is None:
            return None

        try:
            if self.uart.any():
                data = self.uart.read()
                if data:
                    raw_str = data.decode("utf-8", "ignore").strip()
                    if raw_str:
                        self.last_tag = raw_str
                        self.last_tag_time = time.time()
                        return raw_str
        except Exception as e:
            print("Erro ao ler UART RFID:", e)
        return None

    def get_all_status(self):
        """Retorna o status consolidado de todos os 4 sensores."""
        return {
            "barrier": {
                "clear": self.is_barrier_clear(),
                "label": self.get_barrier_status()
            },
            "hall": {
                "label": self.get_hall_status(),
                "is_closed": self.get_hall_status() == "Fechado"
            },
            "aux": {
                "pressed": self.is_aux_pressed(),
                "label": self.get_aux_status()
            },
            "rfid": {
                "last_tag": self.last_tag if self.last_tag else "Nenhuma",
                "timestamp": self.last_tag_time
            }
        }
