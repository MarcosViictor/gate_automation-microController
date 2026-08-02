import time
import _thread

try:
    from machine import Pin
    IS_MICROPYTHON = True
except ImportError:
    IS_MICROPYTHON = False


class GateRelay:
    """
    Controlador do Relé do Portão com proteção de Alta Impedância (Hack 5V).
    - Desligado: Pin.IN (Alta Impedância, evita fuga de corrente de 5V)
    - Ligado: Pin.OUT com nível LOW (Aciona o relé do motor) por N segundos
    """

    def __init__(self, config_manager, sensor_manager=None):
        self.config = config_manager
        self.sensor_manager = sensor_manager
        self.is_busy = False
        self.last_action_time = 0
        self.last_action_status = "Pronto"

        self.setup_gpio()

    def setup_gpio(self):
        if not IS_MICROPYTHON:
            print("[MOCK] GateRelay iniciado em modo de simulação")
            return

        pin_num = self.config.get("relay_pin", 18)
        try:
            # Inicializa pino como Entrada (Alta Impedância) por segurança
            Pin(pin_num, Pin.IN)
            print("GPIO do Relé configurado no pino", pin_num, "(Alta Impedancia)")
        except Exception as e:
            print("Erro ao configurar GPIO do Relé:", e)

    def trigger_open(self, duration=None, ignore_barrier=False):
        """
        Aciona o pulso do relé para abrir o portão.
        Verifica a barreira de segurança antes de disparar.
        """
        if self.is_busy:
            return False, "Portao ja esta em processo de abertura"

        # Verificação do sensor de barreira
        if not ignore_barrier and self.sensor_manager:
            if not self.sensor_manager.is_barrier_clear():
                self.last_action_status = "Bloqueado: Veiculo no caminho!"
                print("[SEGURANCA] Tentativa de abertura bloqueada: Veiculo no caminho!")
                return False, "Bloqueado pelo sensor de barreira (Veiculo no caminho)"

        if duration is None:
            duration = self.config.get("gate_open_duration", 5)

        self.is_busy = True
        self.last_action_status = "Abrindo portao..."

        if IS_MICROPYTHON:
            try:
                _thread.start_new_thread(self._pulse_thread, (duration,))
            except Exception as e:
                print("Erro ao iniciar thread do rele, executando direto:", e)
                self._pulse_sync(duration)
        else:
            print("[MOCK] Portão ABERTO por", duration, "segundos (Sinal LOW na GPIO", self.config.get("relay_pin", 18), ")")
            self._pulse_mock(duration)

        return True, "Acionamento do portao iniciado"

    def _pulse_sync(self, duration):
        pin_num = self.config.get("relay_pin", 18)
        try:
            relay = Pin(pin_num, Pin.OUT)
            relay.value(0)  # LOW aciona o relé
            print("Portao ABERTO - Sinal LOW no pino", pin_num)
            time.sleep(duration)
            Pin(pin_num, Pin.IN)  # Retorna para Alta Impedância
            print("Portao FECHADO - Alta Impedancia no pino", pin_num)
            self.last_action_status = "Portao acionado com sucesso"
        except Exception as e:
            print("Erro no acionamento do relé:", e)
            self.last_action_status = "Erro no relé: " + str(e)
        finally:
            self.is_busy = False

    def _pulse_thread(self, duration):
        self._pulse_sync(duration)

    def _pulse_mock(self, duration):
        try:
            time.sleep(duration)
            print("[MOCK] Portão FECHADO (Retornou a Alta Impedância)")
            self.last_action_status = "Portao acionado com sucesso (Simulado)"
        finally:
            self.is_busy = False

    def get_status(self):
        return {
            "is_busy": self.is_busy,
            "relay_pin": self.config.get("relay_pin", 18),
            "gate_open_duration": self.config.get("gate_open_duration", 5),
            "last_status": self.last_action_status
        }
