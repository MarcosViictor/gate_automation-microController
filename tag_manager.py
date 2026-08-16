import time

class TagManager:
    """
    Gerencia a autorização de tags RFID e histórico de acessos.
    Integra a leitura da tag com o servidor local, cache local (StorageManager) e acionamento do relé.
    """

    def __init__(self, config_manager, server_client, sensor_manager, gate_relay, storage_manager=None):
        self.config = config_manager
        self.server_client = server_client
        self.sensor_manager = sensor_manager
        self.gate_relay = gate_relay
        self.storage_manager = storage_manager
        self.access_logs = []
        self.max_logs = 50

    def process_tag(self, tag_code, source="RFID"):
        """
        Processa uma tag escaneada ou informada via Web:
        1. Consulta o servidor local
        2. Em caso de sucesso (200 OK) -> Atualiza cache local (history.json)
        3. Em caso de erro do servidor/rede (5xx/Timeout) -> Fallback para history.json + outbox.json
        4. Se autorizada E barreira livre -> aciona o relé do portão
        5. Registra no histórico de acessos
        """
        tag_code = str(tag_code).strip()
        if not tag_code:
            return {"authorized": False, "reason": "Codigo de tag invalido"}

        # 1. Consulta o servidor local
        is_valid, server_info, status_type = self.server_client.check_tag(tag_code)

        authorized = False
        mode = "online"
        reason = ""

        if status_type == "online_success":
            authorized = True
            mode = "online"
            if self.storage_manager:
                self.storage_manager.add_to_history(tag_code, authorized=True)
        elif status_type == "online_denied":
            authorized = False
            mode = "online"
            reason = "Tag negada pelo servidor local"
            if self.storage_manager:
                self.storage_manager.add_to_history(tag_code, authorized=False)
        else:
            # Mode "server_error": Fallback para histórico local offline
            mode = "offline_fallback"
            if self.storage_manager and self.storage_manager.is_tag_authorized_offline(tag_code):
                authorized = True
                reason = "Autorizado em modo offline (historico local)"
                # Registra na outbox para sincronização posterior
                self.storage_manager.add_to_outbox(tag_code, source=source)
            else:
                authorized = False
                reason = "Servidor indisponivel e tag nao autorizada no historico local"

        # 2. Verificação de segurança da barreira
        barrier_clear = self.sensor_manager.is_barrier_clear() if self.sensor_manager else True

        gate_triggered = False

        if not authorized:
            if not reason:
                reason = "Tag nao autorizada"
        elif not barrier_clear:
            reason = "Tag valida, mas portao bloqueado: Veiculo no caminho!"
        else:
            # Aciona o relé do portão
            success, msg = self.gate_relay.trigger_open()
            gate_triggered = success
            reason = "Acesso concedido. Portao acionado!" if success else f"Erro ao acionar portao: {msg}"

        # 3. Registrar log de memória
        log_entry = {
            "timestamp": time.time(),
            "tag_code": tag_code,
            "authorized": authorized,
            "gate_triggered": gate_triggered,
            "barrier_clear": barrier_clear,
            "source": source,
            "reason": reason,
            "mode": mode,
            "server_status": server_info.get("status", 0)
        }
        self.add_log(log_entry)

        return log_entry

    def add_log(self, entry):
        self.access_logs.insert(0, entry)
        if len(self.access_logs) > self.max_logs:
            self.access_logs.pop()

    def get_logs(self):
        return self.access_logs

