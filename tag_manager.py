import time

class TagManager:
    """
    Gerencia a autorização de tags RFID e histórico de acessos.
    Integra a leitura da tag com o servidor local e o acionamento do relé.
    """

    def __init__(self, config_manager, server_client, sensor_manager, gate_relay):
        self.config = config_manager
        self.server_client = server_client
        self.sensor_manager = sensor_manager
        self.gate_relay = gate_relay
        self.access_logs = []
        self.max_logs = 50

    def process_tag(self, tag_code, source="RFID"):
        """
        Processa uma tag escaneada ou informada via Web:
        1. Consulta o servidor local
        2. Se autorizada E barreira livre -> aciona o relé do portão
        3. Registra no histórico de acessos
        """
        tag_code = str(tag_code).strip()
        if not tag_code:
            return {"authorized": False, "reason": "Codigo de tag invalido"}

        # 1. Consulta o servidor local
        is_valid, server_info = self.server_client.check_tag(tag_code)

        # 2. Verificação de segurança da barreira
        barrier_clear = self.sensor_manager.is_barrier_clear() if self.sensor_manager else True

        authorized = is_valid
        gate_triggered = False
        reason = ""

        if not authorized:
            reason = "Tag nao autorizada pelo servidor local"
        elif not barrier_clear:
            reason = "Tag valida, mas portao bloqueado: Veiculo no caminho!"
        else:
            # Aciona o relé do portão
            success, msg = self.gate_relay.trigger_open()
            gate_triggered = success
            reason = "Acesso concedido. Portao acionado!" if success else f"Erro ao acionar portao: {msg}"

        # 3. Registrar log
        log_entry = {
            "timestamp": time.time(),
            "tag_code": tag_code,
            "authorized": authorized,
            "gate_triggered": gate_triggered,
            "barrier_clear": barrier_clear,
            "source": source,
            "reason": reason,
            "server_mode": server_info.get("mode", "desconhecido")
        }
        self.add_log(log_entry)

        return log_entry

    def add_log(self, entry):
        self.access_logs.insert(0, entry)
        if len(self.access_logs) > self.max_logs:
            self.access_logs.pop()

    def get_logs(self):
        return self.access_logs
