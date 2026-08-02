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
    Realiza a consulta da TAG no servidor local:
    POST <SERVER_BASE_URL>/api/gate/check
    Headers: Authorization: sbs, Content-Type: application/json
    Body: {"code": "<tag_code>"}
    """

    def __init__(self, config_manager):
        self.config = config_manager

    def check_tag(self, tag_code):
        """
        Consulta o servidor local para saber se a tag é válida.
        Retorna tuple (is_valid: bool, response_info: dict)
        """
        base_url = self.config.get("server_base_url", "http://sitiobarreiras.app.br:55432").rstrip("/")
        auth_header = self.config.get("auth_header", "sbs")
        url = base_url + "/api/gate/check"

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }
        payload = {"code": tag_code}

        if requests is None:
            # Sem biblioteca HTTP, permite em modo fallback/simulado
            print("[SERVER_CLIENT] Sem bibliotecas HTTP (requests/urequests). Autorizando em modo offline/mock.")
            return True, {"status": 200, "mode": "offline_mock", "message": "Autorizado (Modo sem rede)"}

        try:
            print("Enviando requisicao para servidor local:", url, "Tag:", tag_code)
            res = requests.post(url, json=payload, headers=headers, timeout=5)
            status_code = res.status_code

            response_data = {}
            try:
                response_data = res.json()
            except Exception:
                response_data = {"raw_text": res.text}

            res.close()

            if status_code == 200:
                print("Servidor autorizou tag:", tag_code)
                return True, {"status": 200, "mode": "online", "data": response_data}
            else:
                print("Servidor recusou tag (Status", status_code, "):", tag_code)
                return False, {"status": status_code, "mode": "online", "data": response_data}

        except Exception as e:
            print("Erro ao comunicar com servidor local:", e)
            return False, {"status": 500, "mode": "error", "error": str(e)}
