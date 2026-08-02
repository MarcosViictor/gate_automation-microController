import json
import time

try:
    import usocket as socket
except ImportError:
    import socket


class WebServer:
    """
    Servidor HTTP leve para MicroPython.
    Serve a interface SPA (index.html) e expõe APIs REST.
    """

    def __init__(self, config_manager, wifi_manager, sensor_manager, gate_relay, tag_manager, port=80):
        self.config = config_manager
        self.wifi = wifi_manager
        self.sensors = sensor_manager
        self.relay = gate_relay
        self.tags = tag_manager
        self.port = port
        self.server_socket = None

    def start(self):
        try:
            addr = socket.getaddrinfo("0.0.0.0", self.port)[0][-1]
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(addr)
            self.server_socket.listen(5)
            print("Servidor Web iniciado na porta", self.port, "- Acesse http://" + self.wifi.ip_address)
        except Exception as e:
            print("Erro ao iniciar servidor socket:", e)

    def handle_client(self, client_sock):
        try:
            client_sock.settimeout(2.0)
            req_data = client_sock.recv(2048)
            if not req_data:
                client_sock.close()
                return

            req_str = req_data.decode("utf-8", "ignore")
            lines = req_str.split("\r\n")
            if not lines or len(lines[0].split()) < 2:
                client_sock.close()
                return

            method, path = lines[0].split()[:2]

            # Extrai corpo se for POST
            body = ""
            if method == "POST":
                parts = req_str.split("\r\n\r\n")
                if len(parts) > 1:
                    body = parts[1]

            # Roteamento
            if method == "GET" and (path == "/" or path == "/index.html"):
                self._send_file(client_sock, "wwwroot/index.html", "text/html")
            elif method == "GET" and path == "/api/status":
                self._send_json(client_sock, {
                    "sensors": self.sensors.get_all_status(),
                    "wifi": self.wifi.get_status(),
                    "relay": self.relay.get_status()
                })
            elif method == "GET" and path == "/api/config":
                cfg = dict(self.config.config)
                cfg["wifi_password"] = "******" if cfg.get("wifi_password") else ""
                self._send_json(client_sock, cfg)
            elif method == "POST" and path == "/api/config":
                try:
                    payload = json.loads(body)
                    # Se a senha veio mascarada, nao altera
                    if payload.get("wifi_password") == "******":
                        del payload["wifi_password"]
                    self.config.update(payload)
                    self._send_json(client_sock, {"success": True, "message": "Configuraçoes salvas com sucesso!"})
                except Exception as e:
                    self._send_json(client_sock, {"success": False, "error": str(e)}, status=400)
            elif method == "GET" and path == "/api/tags":
                self._send_json(client_sock, self.tags.get_logs())
            elif method == "POST" and path == "/api/scan":
                try:
                    payload = json.loads(body)
                    tag_code = payload.get("code", "")
                    result = self.tags.process_tag(tag_code, source="WEB_MANUAL")
                    self._send_json(client_sock, result)
                except Exception as e:
                    self._send_json(client_sock, {"success": False, "error": str(e)}, status=400)
            elif method == "POST" and path == "/api/trigger":
                success, msg = self.relay.trigger_open()
                status_code = 200 if success else 400
                self._send_json(client_sock, {"success": success, "message": msg}, status=status_code)
            else:
                self._send_response(client_sock, 404, "text/plain", "404 Not Found")

        except Exception as e:
            print("Erro ao tratar requisicao do cliente:", e)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass

    def poll(self):
        """Atende a uma conexao se disponivel (para loop nao-bloqueante)."""
        if self.server_socket is None:
            return

        try:
            self.server_socket.settimeout(0.1)
            client_sock, addr = self.server_socket.accept()
            self.handle_client(client_sock)
        except Exception:
            pass

    def _send_file(self, client_sock, filepath, content_type):
        try:
            with open(filepath, "r") as f:
                content = f.read()
            header = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}; charset=utf-8\r\nContent-Length: {len(content.encode('utf-8'))}\r\nConnection: close\r\n\r\n"
            client_sock.sendall(header.encode("utf-8"))
            client_sock.sendall(content.encode("utf-8"))
        except Exception as e:
            self._send_response(client_sock, 500, "text/plain", "Erro ao carregar arquivo: " + str(e))

    def _send_json(self, client_sock, data, status=200):
        try:
            body = json.dumps(data)
            header = f"HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(body.encode('utf-8'))}\r\nConnection: close\r\n\r\n"
            client_sock.sendall(header.encode("utf-8"))
            client_sock.sendall(body.encode("utf-8"))
        except Exception as e:
            print("Erro ao enviar JSON:", e)

    def _send_response(self, client_sock, status_code, content_type, body_text):
        try:
            header = f"HTTP/1.1 {status_code} OK\r\nContent-Type: {content_type}\r\nContent-Length: {len(body_text.encode('utf-8'))}\r\nConnection: close\r\n\r\n"
            client_sock.sendall(header.encode("utf-8"))
            client_sock.sendall(body_text.encode("utf-8"))
        except Exception as e:
            print("Erro ao enviar resposta:", e)
