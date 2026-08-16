import json

# Tenta usar urequests do MicroPython, fallback para requests do Python padrao
try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None


class ServerClient:
    """
    Realiza a consulta da TAG no servidor local e sincronização da outbox:
    POST <SERVER_BASE_URL>/api/gate/check
    Headers: Authorization: sbs, Content-Type: application/json
    Body: {"code": "<tag_code>"}
    """

    def __init__(self, config_manager):
        self.config = config_manager

    def check_tag(self, tag_code):
        """
        Consulta o servidor local para saber se a tag é válida.
        Retorna tuple: (is_valid: bool, response_info: dict, status_type: str)
        status_type pode ser:
          - "online_success": Servidor respondeu 200 e autorizou.
          - "online_denied": Servidor respondeu 4xx (tag explicitamente recusada).
          - "server_error": Erro 5xx, timeout ou falha de comunicação (deve ativar fallback offline).
        """
        base_url = self.config.get("server_base_url", "http://sitiobarreiras.app.br:55432").rstrip("/")
        auth_header = self.config.get("auth_header", "sbs")
        timeout_sec = self.config.get("server_timeout", 4)
        url = base_url + "/api/gate/check"

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        payload = {"code": str(tag_code).strip()}

        if requests is None:
            print("[SERVER_CLIENT] Sem bibliotecas HTTP (requests/urequests). Tratando como erro de servidor.")
            return False, {"status": 0, "mode": "no_http", "error": "Bibliotecas HTTP indisponiveis"}, "server_error"

        try:
            print(f"[SERVER_CLIENT] Enviando requisicao: {url} (Tag: {tag_code}, Timeout: {timeout_sec}s)")
            res = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
            status_code = res.status_code

            response_data = {}
            try:
                response_data = res.json()
            except Exception:
                response_data = {"raw_text": res.text}

            res.close()

            if status_code == 200:
                print(f"[SERVER_CLIENT] Servidor autorizou tag: {tag_code}")
                return True, {"status": 200, "mode": "online", "data": response_data}, "online_success"
            elif 400 <= status_code < 500:
                print(f"[SERVER_CLIENT] Servidor RECUSOU tag (Status {status_code}): {tag_code}")
                return False, {"status": status_code, "mode": "online", "data": response_data}, "online_denied"
            else:
                print(f"[SERVER_CLIENT] Erro de Servidor (Status {status_code}): {tag_code}")
                return False, {"status": status_code, "mode": "server_error", "data": response_data}, "server_error"

        except Exception as e:
            print("[SERVER_CLIENT] Excecao ao comunicar com servidor (Timeout/Rede):", e)
            return False, {"status": 500, "mode": "error", "error": str(e)}, "server_error"

    def sync_outbox_item(self, item, overflow_count=0):
        """
        Envia um registro de passagem offline para o servidor.
        """
        base_url = self.config.get("server_base_url", "http://sitiobarreiras.app.br:55432").rstrip("/")
        auth_header = self.config.get("auth_header", "sbs")
        timeout_sec = self.config.get("server_timeout", 4)
        url = base_url + "/api/gate/check"

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        payload = {
            "code": item.get("tag_code"),
            "source": item.get("source", "RFID_OFFLINE"),
            "offline_timestamp": item.get("timestamp"),
            "offline_pass": True
        }
        if overflow_count > 0:
            payload["outbox_overflow_count"] = overflow_count

        if requests is None:
            return False

        try:
            print(f"[SERVER_CLIENT] Sincronizando item da outbox ({item.get('id')})...")
            res = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
            status_code = res.status_code
            res.close()

            if status_code in (200, 201):
                print(f"[SERVER_CLIENT] Item da outbox sincronizado com sucesso: {item.get('id')}")
                return True
            else:
                print(f"[SERVER_CLIENT] Falha ao sincronizar item da outbox (Status {status_code})")
                return False
        except Exception as e:
            print("[SERVER_CLIENT] Erro de comunicacao na sincronizacao da outbox:", e)
            return False

