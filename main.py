import gc
import json
import os
import time

import network
from machine import Pin, UART

ticks_ms = time.ticks_ms
ticks_diff = time.ticks_diff
ticks_add = time.ticks_add

try:
    import usocket as socket
except ImportError:
    import socket

try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None


try:
    from storage_manager import StorageManager
except ImportError:
    StorageManager = None


# Rota do SB Gatehouse (AccessController@store, routes/api.php).
ACCESS_PATH = "/api/raspberry/access"

DEFAULT_CONFIG = {
    "wifi_ssid": "",
    "wifi_password": "",
    # Espera do DHCP no boot. Curto demais faz o sistema cair em modo AP com a
    # senha certa, so porque o roteador demorou a entregar o IP.
    "wifi_timeout": 30,
    # Backoff entre tentativas quando a rede esta fora: dobra ate o teto.
    "wifi_retry_base_seconds": 5,
    "wifi_retry_max_seconds": 60,
    # IP fixo na rede da empresa. wifi_static_ip vazio = DHCP.
    # Se a associacao estourar o timeout com IP fixo, cai para DHCP ate reiniciar
    # ou salvar config nova: rede privada mal configurada nao pode deixar o
    # portao inalcancavel.
    "wifi_static_ip": "",
    "wifi_subnet_mask": "255.255.255.0",
    "wifi_gateway": "",
    "wifi_dns": "8.8.8.8",
    # IP do SB Gatehouse na LAN (docker expoe 8001). Sem DNS e sem saida externa.
    "server_base_url": "http://192.168.0.100:8001",
    "access_path": ACCESS_PATH,
    "auth_header": "",
    "server_timeout": 1,
    "relay_pin": 16,
    "gate_open_duration": 5,
    "pin_barrier": 2,
    # Fins de curso do portao. pin_hall (chave antiga, sensor unico) ainda e
    # aceito como o sensor de FECHADO para nao quebrar config.json em campo.
    "pin_hall": 3,
    "pin_hall_closed": 3,
    "pin_hall_open": 4,
    # Nivel que significa "ima presente / fim de curso atingido". Com PULL_UP o
    # normal e 0; inverta aqui se o sensor instalado for normalmente fechado,
    # em vez de mexer no codigo com o portao na bancada.
    "hall_active_low": 1,
    "pin_aux": 4,
    # Dois leitores. No RP2040 o GP5 e RX da UART1 e o GP1 e RX da UART0.
    # So RX e configurado: os leitores transmitem sozinhos, e assim o GP4
    # continua livre para o sensor auxiliar.
    "reader_in_uart": 1,
    "reader_in_rx": 5,
    "reader_out_uart": 0,
    "reader_out_rx": 1,
    "reader_baudrate": 115200,
    # Fim de frame por silencio: frames EPC sao binarios e nao tem terminador.
    "frame_gap_ms": 30,
    # Extracao do codigo (ver parse_tag_frame). tag_offset comeca em 0: o valor
    # real depende do leitor e se calibra com tag_debug ligado.
    "tag_offset": 0,
    "tag_trim": 4,
    "tag_offset_threshold": 20,
    "tag_debug": 1,
    # O leitor repete a tag enquanto o cartao esta proximo; ignora releituras.
    "rfid_dedup_seconds": 2,
    "max_history_size": 100,
    "max_outbox_size": 200,
    # Porta do servidor web. Precisa casar com RASPBERRY_HOST no .env do gatehouse.
    "web_port": 80,
    # Segredo do POST /open vindo do gatehouse (RASPBERRY_SECRET). Vazio = sem auth.
    "open_token": "",
}

CONFIG_FILE = "config.json"
INDEX_FILE = "wwwroot/index.html"

# Pagina minima servida quando wwwroot/index.html nao esta no dispositivo.
# Curta de proposito: fica residente na RAM, ao contrario da UI real.
FALLBACK_HTML = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<title>Gate Automation</title></head><body style='font-family:sans-serif;padding:2em'>"
    "<h2>Sistema no ar, interface ausente</h2>"
    "<p>O firmware respondeu, mas <code>wwwroot/index.html</code> nao esta no dispositivo.</p>"
    "<p>Envie a pasta inteira:<br><code>mpremote connect &lt;porta&gt; fs cp -r wwwroot :</code></p>"
    "<p>A API continua funcionando: <a href='/api/status'>/api/status</a> | "
    "<a href='/health'>/health</a></p></body></html>"
)

def parse_tag_frame(data, offset=0, trim=4, offset_threshold=20):
    """
    Extrai o codigo da tag de um frame bruto do leitor.

    Mesma regra do read_tag.py usado no cadastro: sem isso o codigo lido no
    portao nao bate com o gravado no SBS, que compara a string exata.

    Passos: hex -> descarta padding 00 do fim -> corta o cabecalho quando o
    frame passa do limiar -> junta -> descarta os digitos finais de CRC.
    """
    hex_list = ["%02X" % b for b in data]

    while hex_list and hex_list[-1] == "00":
        hex_list.pop()
    if not hex_list:
        return None

    # Frames curtos nao tem cabecalho para cortar; cortar apagaria a tag.
    if len(hex_list) > offset_threshold:
        hex_list = hex_list[offset:]

    texto = "".join(hex_list)
    if trim and len(texto) > trim:
        texto = texto[:-trim]
    return texto or None


def calibrar_offset_trim(frame, codigo_esperado, limiar=20):
    """
    Descobre tag_offset/tag_trim que fazem parse_tag_frame devolver o codigo
    esperado, ou None se nenhum par servir.

    Tira o chute da calibracao: em vez de ajustar numeros no escuro, le-se uma
    tag ja cadastrada, informa-se o codigo dela e os cortes saem por busca.

    Devolve tambem o limiar, porque parse_tag_frame so aplica o offset em
    frames longos — num frame curto o corte nunca valeria e a busca falharia
    sem explicacao. Nesse caso a segunda passada zera o limiar.
    """
    esperado = str(codigo_esperado).strip().upper()
    if not frame or not esperado:
        return None

    for tentativa in (limiar, 0):
        for offset in range(0, len(frame) + 1):
            for trim in range(0, 17):
                if parse_tag_frame(frame, offset=offset, trim=trim,
                                   offset_threshold=tentativa) == esperado:
                    return {"tag_offset": offset, "tag_trim": trim,
                            "tag_offset_threshold": tentativa}
    return None


class TagReader:
    """
    Um leitor RFID: uma UART, um sentido, seu proprio buffer e dedup.

    Frames EPC sao binarios e nao tem terminador, entao o fim do frame e
    detectado por silencio: passados frame_gap_ms sem chegar byte, o que
    estiver no buffer e um frame completo.
    """

    MAX_FRAME = 128

    def __init__(self, config_manager, uart_id, rx_pin, direction):
        self.config = config_manager
        self.uart_id = uart_id
        self.rx_pin = rx_pin
        self.direction = direction
        self.uart = None
        self.last_tag = None
        self.last_tag_time = 0
        self._last_tag_ticks = -999999
        self._buf = b""
        self._last_byte_ticks = 0
        self.last_frame = b""  # ultimo frame bruto, base da calibracao
        self.setup()

    def setup(self):
        baudrate = self.config.get("reader_baudrate", 115200)
        try:
            self.uart = UART(self.uart_id, baudrate=baudrate,
                             rx=Pin(self.rx_pin), timeout=10)
            print("[LEITOR %s] UART%d RX GP%d a %d bps"
                  % (self.direction, self.uart_id, self.rx_pin, baudrate))
        except Exception as exc:
            print("[LEITOR %s] NAO inicializou:" % self.direction, exc)
            self.uart = None

    def poll(self):
        """Devolve um codigo de tag novo, ou None. Nunca bloqueia."""
        if self.uart is None:
            return None
        try:
            if self.uart.any():
                data = self.uart.read()
                if data:
                    self._buf += data
                    self._last_byte_ticks = ticks_ms()
                    if len(self._buf) > self.MAX_FRAME:
                        self._buf = self._buf[-self.MAX_FRAME:]
                    return None  # ainda pode vir mais desta rajada

            if not self._buf:
                return None
            if ticks_diff(ticks_ms(), self._last_byte_ticks) < self.config.get("frame_gap_ms", 30):
                return None

            frame = self._buf
            self._buf = b""
            return self._handle_frame(frame)
        except Exception as exc:
            print("[LEITOR %s] erro de leitura:" % self.direction, exc)
            self._buf = b""
            return None

    def _handle_frame(self, frame):
        self.last_frame = frame
        codigo = parse_tag_frame(
            frame,
            offset=self.config.get("tag_offset", 0),
            trim=self.config.get("tag_trim", 4),
            offset_threshold=self.config.get("tag_offset_threshold", 20),
        )
        if self.config.get("tag_debug", 0):
            # Como calibrar tag_offset/tag_trim: o valor certo depende do
            # leitor e so aparece comparando o HEX bruto com uma tag conhecida.
            print("[LEITOR %s] HEX %s -> codigo %s"
                  % (self.direction, "".join(["%02X" % b for b in frame]), codigo))
        if not codigo:
            return None
        return self._accept(codigo)

    def _accept(self, codigo):
        """Ignora releituras do mesmo cartao dentro da janela de dedup."""
        agora = ticks_ms()
        janela = int(self.config.get("rfid_dedup_seconds", 2)) * 1000
        if codigo == self.last_tag and ticks_diff(agora, self._last_tag_ticks) < janela:
            return None
        self.last_tag = codigo
        self._last_tag_ticks = agora
        self.last_tag_time = time.time()
        return codigo

    def get_status(self):
        return {
            "direction": self.direction,
            "uart": self.uart_id,
            "rx_pin": self.rx_pin,
            "ready": self.uart is not None,
            "last_tag": self.last_tag if self.last_tag else "Nenhuma",
            "timestamp": self.last_tag_time,
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
                for key, value in data.items():
                    self.config[key] = value
            self._migrar_hall(data)
        except Exception as exc:
            print("Aviso ao carregar config.json, usando padrão:", exc)
            self.save()

    def _migrar_hall(self, data):
        """
        pin_hall (sensor unico) passa a ser o fim de curso FECHADO.

        Sem isto, um dispositivo em campo com pin_hall num GPIO diferente do
        padrao herdaria o 3 do DEFAULT_CONFIG em silencio: a chave nova existe
        no default, entao o get() nunca cairia no valor que o operador gravou.
        """
        if "pin_hall" in data and "pin_hall_closed" not in data:
            self.config["pin_hall_closed"] = data["pin_hall"]
            print("[CONFIG] pin_hall", data["pin_hall"], "adotado como fim de curso FECHADO")

    def save(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.config, f)
            return True
        except Exception as exc:
            print("Erro ao salvar config.json:", exc)
            return False

    def get(self, key, default=None):
        if default is None:
            default = DEFAULT_CONFIG.get(key)
        return self.config.get(key, default)

    def update(self, new_data):
        for key, value in new_data.items():
            if key not in DEFAULT_CONFIG:
                continue
            # O tipo do default manda na coercao: nenhum campo numerico novo
            # vira string por ter sido esquecido numa lista a parte.
            default = DEFAULT_CONFIG[key]
            if isinstance(default, int):
                try:
                    self.config[key] = int(value)
                except (TypeError, ValueError):
                    pass
            else:
                self.config[key] = str(value)
        return self.save()


# Codigos de network.WLAN.status() no port rp2 (driver CYW43).
# Os negativos sao TERMINAIS: esperar mais nao muda o resultado.
# 1 e 2 sao progresso — e o 2 (associado, DHCP pendente) e o que estoura
# timeout curto em rede lenta, parecendo falha de credencial sem ser.
WLAN_STATUS = {
    0: "desconectado",
    1: "associando a rede",
    2: "associado - aguardando IP do DHCP",
    3: "conectado (IP obtido)",
    -1: "falha na conexao",
    -2: "rede nao encontrada",
    -3: "senha incorreta",
}
WLAN_TERMINAL = (-1, -2, -3)

WIFI_OCIOSO = "ocioso"
WIFI_ASSOCIANDO = "associando"
WIFI_CONECTADO = "conectado"
WIFI_AGUARDANDO = "aguardando"
WIFI_AP = "ap"


class WifiManager:


    def __init__(self, config_manager):
        self.config = config_manager
        self.ip_address = "0.0.0.0"
        self.mode = "STA"
        self.state = WIFI_OCIOSO
        self.wlan = None
        self._deadline = 0
        self._backoff = 0
        self._last_code = None
        # Ligado quando o IP fixo falha; a partir dai as tentativas vao em DHCP.
        self._dhcp_forcado = False
        self._ip_fixo_ativo = False

    @property
    def is_connected(self):
        """
        Estado real do radio, nao o resultado do ultimo connect().

        Como atributo simples, isto ficava True para sempre: uma queda de rede
        depois do boot passava despercebida e o modo AP se declarava conectado.
        """
        if self.wlan is None:
            return False
        try:
            if self.mode == "AP":
                return bool(self.wlan.active())
            return bool(self.wlan.isconnected())
        except Exception:
            return False

    # --- entrada publica ---

    def connect(self):
        """Inicia a associacao e volta na hora. Nao promete sucesso."""
        self._iniciar_sta()

    def tick(self):
        """Uma transicao por volta do loop principal."""
        if self.state == WIFI_ASSOCIANDO:
            self._em_associando()
        elif self.state == WIFI_CONECTADO:
            self._em_conectado()
        elif self.state == WIFI_AGUARDANDO:
            self._em_aguardando()
        elif self.state == WIFI_OCIOSO:
            self._iniciar_sta()
        # WIFI_AP e terminal: so reconfigurado() sai dele.

    def reconfigurado(self):
        """
        Credenciais mudaram na tela: tenta de novo agora.

        Sem isto o operador corrigiria a senha pelo proprio AP e ainda
        precisaria reiniciar na mao — o modo AP nao serviria para nada.
        """
        self._backoff = 0
        self._dhcp_forcado = False
        self._iniciar_sta()

    # --- transicoes ---

    def _iniciar_sta(self):
        ssid = self.config.get("wifi_ssid", "").strip()
        if not ssid:
            print("[WIFI] Nenhum SSID configurado.")
            self.start_ap()
            return

        if self.mode == "AP" and self.wlan is not None:
            try:
                self.wlan.active(False)  # desliga o AP antes de voltar para STA
            except Exception:
                pass

        self.mode = "STA"
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self._aplicar_ip_fixo()
        print("Tentando conectar a rede Wi-Fi:", ssid)
        try:
            self.wlan.connect(ssid, self.config.get("wifi_password", "").strip())
        except Exception as exc:
            print("[WIFI] Erro ao iniciar conexao:", exc)

        self._last_code = None
        self.state = WIFI_ASSOCIANDO
        self._deadline = ticks_add(ticks_ms(), int(self.config.get("wifi_timeout", 30)) * 1000)

    def _aplicar_ip_fixo(self):
        """
        Fixa o IP antes do connect(), quando configurado.

        Depois de associado nao adianta: o DHCP ja respondeu e trocar o endereco
        derruba a sessao. Por isso o ifconfig vem antes, e a validacao dos campos
        tambem — IP fixo sem gateway nao roteia, e melhor cair em DHCP avisando.
        """
        self._ip_fixo_ativo = False

        ip = str(self.config.get("wifi_static_ip", "") or "").strip()
        if not ip:
            return
        if self._dhcp_forcado:
            print("[WIFI] IP fixo desativado nesta sessao; usando DHCP.")
            return

        mask = str(self.config.get("wifi_subnet_mask", "") or "").strip()
        gw = str(self.config.get("wifi_gateway", "") or "").strip()
        dns = str(self.config.get("wifi_dns", "") or "").strip() or gw

        if not mask or not gw:
            print("[WIFI] IP fixo ignorado: mascara ou gateway em branco. Usando DHCP.")
            return

        try:
            self.wlan.ifconfig((ip, mask, gw, dns))
            self._ip_fixo_ativo = True
            print("[WIFI] IP fixo", ip, "| mascara", mask, "| gateway", gw, "| DNS", dns)
        except Exception as exc:
            print("[WIFI] Erro ao aplicar IP fixo:", exc, "- usando DHCP.")

    def _em_associando(self):
        if self.is_connected:
            self._virar_conectado()
            return

        code = self._codigo()
        if code != self._last_code:
            print("[WIFI]  ...", self._status_text(code))
            self._last_code = code

        # Codigo terminal: nenhuma espera resolve senha errada ou rede ausente.
        if code in WLAN_TERMINAL:
            print("[WIFI] Erro de configuracao:", self._status_text(code))
            self.start_ap()
            return

        if ticks_diff(ticks_ms(), self._deadline) >= 0:
            if self._ip_fixo_ativo and not self._dhcp_forcado:
                # Conferir a config aqui e impossivel: o radio nao diz "esse IP
                # ja e de outro host". So sobra tentar sem ele.
                self._dhcp_forcado = True
                self._ip_fixo_ativo = False
                print("[WIFI] IP fixo falhou, tentando DHCP.")
            else:
                print("[WIFI] Rede indisponivel no momento.")
            self._virar_aguardando()

    def _em_conectado(self):
        if self.is_connected:
            return
        print("[WIFI] Conexao caiu.")
        self._virar_aguardando()

    def _em_aguardando(self):
        if ticks_diff(ticks_ms(), self._deadline) >= 0:
            self._iniciar_sta()

    def _virar_conectado(self):
        self.state = WIFI_CONECTADO
        self._backoff = 0
        cfg = self.wlan.ifconfig()
        self.ip_address = cfg[0]
        print("Conectado ao Wi-Fi! Acesse http://%s:%s"
              % (self.ip_address, self.config.get("web_port", 80)))
        print("[WIFI] gateway", cfg[2], "| mascara", cfg[1], "| DNS", cfg[3])

    def _virar_aguardando(self):
        base = int(self.config.get("wifi_retry_base_seconds", 5))
        teto = int(self.config.get("wifi_retry_max_seconds", 60))
        self._backoff = base if not self._backoff else min(self._backoff * 2, teto)
        self.state = WIFI_AGUARDANDO
        self._deadline = ticks_add(ticks_ms(), self._backoff * 1000)
        print("[WIFI] Nova tentativa em", self._backoff, "s")

    # --- apoio ---

    def _codigo(self):
        try:
            return self.wlan.status()
        except Exception:
            return None

    def _status_text(self, code=None):
        """Traduz o codigo. Recebe o valor ja lido para nao reler o radio e
        acabar reportando um estado diferente do que a logica avaliou."""
        if code is None:
            code = self._codigo()
        if code is None:
            return "desconhecido"
        return "%s (%s)" % (WLAN_STATUS.get(code, "codigo %s" % code), code)

    def start_ap(self, ap_ssid="GateAutomation-AP", ap_password=""):
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        try:
            ap.config(essid=ap_ssid, password=ap_password)
        except Exception as exc:
            print("[WIFI] Erro ao configurar AP:", exc)
        self.wlan = ap
        self.mode = "AP"
        self.state = WIFI_AP
        self.ip_address = ap.ifconfig()[0]
        print("Modo AP ativado! Conecte-se em", ap_ssid, "- IP:", self.ip_address)
        print("[WIFI] Corrija a rede na tela; ao salvar, ele tenta de novo sozinho.")

    def get_status(self):
        return {
            "connected": self.is_connected,
            "state": self.state,
            "ip": self.ip_address,
            "mode": self.mode,
            "ip_mode": self.get_ip_mode(),
            "ssid": self.config.get("wifi_ssid", ""),
        }

    def get_ip_mode(self):
        if self._ip_fixo_ativo:
            return "static"
        if self._dhcp_forcado:
            return "dhcp (fallback)"
        return "dhcp"


# Estados do portao derivados dos dois fins de curso.
GATE_FECHADO = "Fechado"
GATE_ABERTO = "Aberto"
GATE_MOVIMENTO = "Em movimento"
GATE_ERRO = "Erro nos sensores"
GATE_INDISPONIVEL = "Hall indisponivel"


class SensorManager:
    """
    Dois halls de fim de curso dizem onde o portao esta.

    Um sensor so nao distingue "fechado" de "no meio do curso": ele apenas nega
    o unico ponto que conhece. Com um sensor em cada extremo, o meio do curso
    vira um estado proprio (nenhum ativo) e a fiacao quebrada tambem (os dois
    ativos ao mesmo tempo, o que fisicamente nao acontece).
    """

    def __init__(self, config_manager):
        self.config = config_manager
        self.barrier_pin = None
        self.hall_closed_pin = None
        self.hall_open_pin = None
        self.aux_pin = None
        self.setup_hardware()

    def setup_hardware(self):
        pin_b = self.config.get("pin_barrier", 2)
        # O sensor unico antigo (pin_hall) vira este; ver ConfigManager._migrar_hall.
        pin_hc = self.config.get("pin_hall_closed", 3)
        pin_ho = self.config.get("pin_hall_open", 4)
        pin_a = self.config.get("pin_aux", 4)

        try:
            self.barrier_pin = Pin(pin_b, Pin.IN, Pin.PULL_UP)
            print("Sensor de barreira no GPIO", pin_b)
        except Exception as exc:
            print("Erro ao configurar pino da barreira:", exc)

        try:
            self.hall_closed_pin = Pin(pin_hc, Pin.IN, Pin.PULL_UP)
            print("Hall de fim de curso FECHADO no GPIO", pin_hc)
        except Exception as exc:
            print("Erro ao configurar pino Hall fechado:", exc)

        try:
            self.hall_open_pin = Pin(pin_ho, Pin.IN, Pin.PULL_UP)
            print("Hall de fim de curso ABERTO no GPIO", pin_ho)
        except Exception as exc:
            print("Erro ao configurar pino Hall aberto:", exc)

        try:
            self.aux_pin = Pin(pin_a, Pin.IN, Pin.PULL_UP)
            print("Sensor auxiliar no GPIO", pin_a)
        except Exception as exc:
            print("Erro ao configurar pino auxiliar:", exc)


    def is_barrier_clear(self):
        if self.barrier_pin is None:
            return True
        return self.barrier_pin.value() == 1

    def get_barrier_status(self):
        if self.barrier_pin is None:
            return "Barreira indisponivel"
        return "Veículo no caminho" if self.barrier_pin.value() == 0 else "Acesso livre"

    def _fim_de_curso_atingido(self, pin):
        """True quando o ima esta na frente do sensor."""
        if pin is None:
            return None
        ativo_em_zero = bool(int(self.config.get("hall_active_low", 1)))
        return pin.value() == (0 if ativo_em_zero else 1)

    def get_gate_state(self):
        fechado = self._fim_de_curso_atingido(self.hall_closed_pin)
        aberto = self._fim_de_curso_atingido(self.hall_open_pin)

        if fechado is None and aberto is None:
            return GATE_INDISPONIVEL
        # Um sensor so: mantem a leitura antiga em vez de chamar tudo de
        # "em movimento" quando o segundo hall ainda nao foi instalado.
        if aberto is None:
            return GATE_FECHADO if fechado else GATE_ABERTO
        if fechado is None:
            return GATE_ABERTO if aberto else GATE_FECHADO

        if fechado and aberto:
            return GATE_ERRO
        if fechado:
            return GATE_FECHADO
        if aberto:
            return GATE_ABERTO
        return GATE_MOVIMENTO

    def get_hall_status(self):
        """Nome antigo, agora devolvendo o estado dos dois fins de curso."""
        return self.get_gate_state()

    def is_aux_pressed(self):
        return False

    def get_aux_status(self):
        return "Desativada"

    def get_all_status(self):
        estado = self.get_gate_state()
        return {
            "barrier": {"clear": self.is_barrier_clear(), "label": self.get_barrier_status()},
            "hall": {"label": estado, "state": estado, "is_closed": estado == GATE_FECHADO},
            "aux": {"pressed": self.is_aux_pressed(), "label": self.get_aux_status()},
        }


class GateRelay:
    """
    Aciona o rele com pulso NAO bloqueante.

    O fechamento e agendado por deadline e conferido pelo loop principal em
    update(). Nao usa _thread: no Pico W o driver CYW43 do Wi-Fi nao e seguro
    entre os dois cores, e um time.sleep(5) no core principal congelaria o
    servidor web e a leitura de RFID durante toda a abertura.
    """

    def __init__(self, config_manager, sensor_manager=None):
        self.config = config_manager
        self.sensor_manager = sensor_manager
        self.is_busy = False
        self.last_action_time = 0
        self.last_action_status = "Pronto"
        self.trigger_count = 0
        self._close_at = None
        self.setup_gpio()

    def setup_gpio(self):
        pin_num = self.config.get("relay_pin", 16)
        try:
            Pin(pin_num, Pin.IN)  # repouso em alta impedancia
            print("GPIO do rele configurado no pino", pin_num)
        except Exception as exc:
            print("Erro ao configurar GPIO do rele:", exc)

    def trigger_open(self, duration=None, ignore_barrier=False):
        if self.is_busy:
            return False, "Portao ja esta em processo de abertura"

        if not ignore_barrier and self.sensor_manager and not self.sensor_manager.is_barrier_clear():
            self.last_action_status = "Bloqueado: veiculo no caminho"
            print("[SEGURANCA] Abertura bloqueada: veiculo no caminho")
            return False, "Bloqueado pelo sensor de barreira"

        if duration is None:
            duration = self.config.get("gate_open_duration", 5)

        pin_num = self.config.get("relay_pin", 16)
        try:
            relay = Pin(pin_num, Pin.OUT)
            relay.value(0)
            print("Portao ABERTO - sinal LOW no pino", pin_num)
        except Exception as exc:
            print("Erro no acionamento do rele:", exc)
            self.last_action_status = "Erro no rele: " + str(exc)
            return False, "Erro no rele: " + str(exc)

        self.is_busy = True
        self.trigger_count += 1
        self.last_action_time = time.time()
        self.last_action_status = "Abrindo portao..."
        self._close_at = ticks_add(ticks_ms(), int(duration * 1000))
        return True, "Acionamento do portao iniciado"

    def update(self):
        """Fecha o portao quando o pulso expira. Chamado a cada volta do loop."""
        if not self.is_busy or self._close_at is None:
            return
        if ticks_diff(self._close_at, ticks_ms()) > 0:
            return
        self._close()

    def _close(self):
        pin_num = self.config.get("relay_pin", 16)
        try:
            Pin(pin_num, Pin.IN)  # volta para alta impedancia
            print("Portao FECHADO - alta impedancia no pino", pin_num)
            self.last_action_status = "Portao acionado com sucesso"
        except Exception as exc:
            print("Erro ao fechar o rele:", exc)
            self.last_action_status = "Erro no rele: " + str(exc)
        finally:
            self._close_at = None
            self.is_busy = False

    def get_status(self):
        return {
            "is_busy": self.is_busy,
            "relay_pin": self.config.get("relay_pin", 16),
            "gate_open_duration": self.config.get("gate_open_duration", 5),
            "last_status": self.last_action_status,
        }


class ServerClient:
    """
    Cliente HTTP do SB Gatehouse.

    Contrato (AccessController@store):
        POST {base}/api/raspberry/access   {"tag_code": "..."}
        -> 200 {"decision": "allowed"|"denied", "open": bool, "reason"?: str}

    ATENCAO: 200 NAO significa autorizado. A decisao vem no corpo, em "open".
    """

    def __init__(self, config_manager):
        self.config = config_manager
        # Nem toda versao do urequests aceita 'timeout'. Descobrimos na primeira
        # requisicao e lembramos, para nao pagar a excecao a cada tag lida.
        self._aceita_timeout = True

    def _endpoint(self):
        base = self.config.get("server_base_url", DEFAULT_CONFIG["server_base_url"])
        return base.rstrip("/") + self.config.get("access_path", ACCESS_PATH)

    def _post(self, payload):
        """Envia o payload e devolve (status_code, corpo_json). (0, None) em falha."""
        if requests is None:
            print("[SERVER] Sem cliente HTTP disponivel.")
            return 0, None

        headers = {"Content-Type": "application/json"}
        auth = self.config.get("auth_header", "")
        if auth:
            headers["Authorization"] = auth

        res = None
        try:
            res = self._enviar(payload, headers)
            status = res.status_code
            try:
                body = res.json()
            except Exception:
                body = None
            return status, body
        except Exception as exc:
            print("[SERVER] Falha na requisicao:", exc)
            return 0, None
        finally:
            # urequests so devolve o socket no close(); sem isso o Pico vaza socket
            # a cada tag e para de conseguir abrir conexoes.
            if res is not None:
                try:
                    res.close()
                except Exception:
                    pass

    def _enviar(self, payload, headers):
        """
        Faz o POST, contornando urequests sem suporte a 'timeout'.

        Sem esta saida o TypeError derrubaria TODA consulta: nenhuma requisicao
        chegaria ao servidor, toda tag cairia no fallback offline e o sintoma
        no campo seria "o portao nao abre para ninguem e o servidor nao registra
        nada" — apontando para a rede quando a causa e o cliente HTTP.
        """
        url = self._endpoint()
        if self._aceita_timeout:
            try:
                return requests.post(url, json=payload, headers=headers,
                                     timeout=self.config.get("server_timeout", 1))
            except TypeError:
                self._aceita_timeout = False
                print("[SERVER] Este urequests nao aceita 'timeout'.")
                print("[SERVER] Seguindo sem ele: uma requisicao travada pode")
                print("[SERVER] segurar o loop principal ate o servidor responder.")
        return requests.post(url, json=payload, headers=headers)

    def check_tag(self, tag_code, direction="entrada"):
        """Devolve (autorizado, info, status_type) para o TagManager."""
        tag_code = str(tag_code).strip()
        # direction viaja como extra: o AccessController valida so tag_code e
        # ignora o resto, entao e inofensivo hoje e pronto quando ele aceitar.
        status, body = self._post({"tag_code": tag_code, "direction": direction})

        if status != 200 or not isinstance(body, dict):
            print("[SERVER] Sem decisao (status", status, ") para tag", tag_code)
            return False, {"status": status, "mode": "server_error"}, "server_error"

        # "open" e a fonte da verdade; "decision" e o fallback. Ausentes = negado.
        if "open" in body:
            authorized = body.get("open") is True
        else:
            authorized = str(body.get("decision", "")).lower() == "allowed"

        print("[SERVER] Tag", tag_code, "->", "LIBERADA" if authorized else "NEGADA")
        info = {"status": 200, "mode": "online", "reason": body.get("reason")}
        return authorized, info, "online_success" if authorized else "online_denied"

    def sync_outbox_item(self, item, overflow_count=0):
        """
        Reenvia uma passagem liberada offline.

        O gatehouse nao tem endpoint proprio de sincronizacao: ele reavalia a tag
        e grava um novo AccessRecord com o horario de agora. Os campos offline_*
        seguem como metadado e hoje sao ignorados pelo servidor.
        """
        payload = {
            "tag_code": item.get("tag_code"),
            "source": item.get("source", "RFID_OFFLINE"),
            "direction": item.get("direction", "entrada"),
            "offline_timestamp": item.get("timestamp"),
            "offline_pass": True,
        }
        if overflow_count > 0:
            payload["outbox_overflow_count"] = overflow_count

        status, _body = self._post(payload)
        return status == 200


class TagManager:
    def __init__(self, config_manager, server_client, sensor_manager, gate_relay, storage_manager=None):
        self.config = config_manager
        self.server_client = server_client
        self.sensor_manager = sensor_manager
        self.gate_relay = gate_relay
        self.storage_manager = storage_manager
        self.access_logs = []
        self.max_logs = 50
        self.last_authorized_time = 0

    def process_tag(self, tag_code, source="RFID", direction="entrada"):
        tag_code = str(tag_code).strip()
        if not tag_code:
            return {"authorized": False, "reason": "Código de tag inválido"}

        is_valid, server_info, status_type = self.server_client.check_tag(tag_code, direction=direction)
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
            reason = server_info.get("reason") or "Tag negada pelo servidor"
            if self.storage_manager:
                self.storage_manager.add_to_history(tag_code, authorized=False)
        else:
            mode = "offline_fallback"
            if self.storage_manager and self.storage_manager.is_tag_authorized_offline(tag_code):
                authorized = True
                reason = "Autorizado em modo offline (historico local)"
                self.storage_manager.add_to_outbox(tag_code, source=source)
            else:
                authorized = False
                reason = "Servidor indisponivel e tag nao autorizada no historico local"

        barrier_clear = self.sensor_manager.is_barrier_clear() if self.sensor_manager else True
        gate_state = self.sensor_manager.get_gate_state() if self.sensor_manager else GATE_FECHADO
        gate_triggered = False

        if authorized:
            self.last_authorized_time = time.time()

        if not authorized:
            if not reason:
                reason = "Tag não autorizada pelo servidor local"
        elif not barrier_clear:
            reason = "Tag válida, mas portão bloqueado: veículo no caminho"
        elif gate_state == GATE_ABERTO:
            reason = "Acesso concedido. Portão já está aberto!"
        elif gate_state == GATE_MOVIMENTO:
            # Pulso no meio do curso inverte ou trava o motor na maioria das
            # centrais. O portao ja esta indo; deixa terminar.
            reason = "Acesso concedido. Portão em movimento, aguarde!"
        elif gate_state == GATE_ERRO:
            print("[SEGURANCA] Os dois fins de curso estao ativos: confira a fiacao dos halls")
            reason = "Tag válida, mas os dois fins de curso estão ativos: verifique os sensores"
        else:
            success, message = self.gate_relay.trigger_open()
            gate_triggered = success
            reason = "Acesso concedido. Portão acionado!" if success else "Erro ao acionar portão: " + str(message)

        log_entry = {
            "timestamp": time.time(),
            "tag_code": tag_code,
            "authorized": authorized,
            "gate_triggered": gate_triggered,
            "barrier_clear": barrier_clear,
            "gate_state": gate_state,
            "source": source,
            "direction": direction,
            "reason": reason,
            "mode": mode,
            "server_status": server_info.get("status", 0),
        }
        self.add_log(log_entry)
        return log_entry

    def add_log(self, entry):
        self.access_logs.insert(0, entry)
        if len(self.access_logs) > self.max_logs:
            self.access_logs.pop()

    def get_logs(self):
        return self.access_logs


class WebServer:
    def __init__(self, config_manager, wifi_manager, sensor_manager, gate_relay, tag_manager, readers=None, port=None):
        self.config = config_manager
        self.wifi = wifi_manager
        self.sensors = sensor_manager
        self.relay = gate_relay
        self.tags = tag_manager
        self.readers = readers or []
        self.port = port if port is not None else self.config.get("web_port", 80)
        self.server_socket = None

    def start(self):
        try:
            addr = socket.getaddrinfo("0.0.0.0", self.port)[0][-1]
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(addr)
            self.server_socket.listen(2)
            self.server_socket.settimeout(0)
            print("Servidor web na porta", self.port, "- http://%s:%d" % (self.wifi.ip_address, self.port))
        except Exception as exc:
            print("Erro ao iniciar servidor socket:", exc)
            self.server_socket = None

    def poll(self):
        """Aceita no maximo uma conexao por iteracao, sem bloquear o loop."""
        if self.server_socket is None:
            return
        client_sock = None
        try:
            client_sock, _addr = self.server_socket.accept()
        except Exception:
            return  # nenhuma conexao pendente
        try:
            self.handle_client(client_sock)
        except Exception as exc:
            print("Erro ao tratar requisicao:", exc)
        finally:
            try:
                client_sock.close()
            except Exception:
                pass
            gc.collect()

    # --- parsing da requisicao ---

    def _read_request(self, client_sock):
        """
        Le cabecalhos e corpo. Devolve (metodo, caminho, auth, corpo) ou None.

        O corpo e lido ate completar o Content-Length: um unico recv() corta
        payloads que o cliente manda em mais de um pacote.
        """
        client_sock.settimeout(2.0)
        data = client_sock.recv(1024)
        if not data:
            return None

        while b"\r\n\r\n" not in data and len(data) < 4096:
            more = client_sock.recv(1024)
            if not more:
                break
            data += more

        head, _sep, body = data.partition(b"\r\n\r\n")
        lines = head.decode("utf-8", "ignore").split("\r\n")
        parts = lines[0].split()
        if len(parts) < 2:
            return None
        method, path = parts[0], parts[1]

        auth = ""
        length = 0
        for line in lines[1:]:
            low = line.lower()
            if low.startswith("authorization:"):
                auth = line.split(":", 1)[1].strip()
            elif low.startswith("content-length:"):
                try:
                    length = int(line.split(":", 1)[1].strip())
                except ValueError:
                    length = 0

        while len(body) < length:
            more = client_sock.recv(min(512, length - len(body)))
            if not more:
                break
            body += more

        return method, path, auth, body.decode("utf-8", "ignore")

    def handle_client(self, client_sock):
        req = self._read_request(client_sock)
        if req is None:
            return
        method, path, auth, body = req

        if method == "GET" and path in ("/", "/index.html"):
            self._send_file(client_sock, INDEX_FILE)

        elif method == "GET" and path == "/health":
            # Contrato do gatehouse: indicador de "Pi online" no dashboard.
            self._send_json(client_sock, {"status": "ok"})

        elif method == "POST" and path == "/open":
            self._handle_open(client_sock, auth, body)

        elif method == "GET" and path == "/api/status":
            self._send_json(client_sock, {
                "sensors": self.sensors.get_all_status(),
                "readers": [r.get_status() for r in self.readers],
                "wifi": self.wifi.get_status(),
                "relay": self.relay.get_status(),
            })

        elif method == "GET" and path == "/api/config":
            cfg = dict(self.config.config)
            cfg["wifi_password"] = "******" if cfg.get("wifi_password") else ""
            cfg["open_token"] = "******" if cfg.get("open_token") else ""
            self._send_json(client_sock, cfg)

        elif method == "POST" and path == "/api/config":
            try:
                payload = json.loads(body or "{}")
                for masked in ("wifi_password", "open_token"):
                    if payload.get(masked) == "******":
                        del payload[masked]
                antes = self._chaves_de_rede()
                self.config.update(payload)
                # Mudou a rede? Tenta agora — inclusive para sair do modo AP,
                # que e justamente onde o operador corrige a senha. O IP fixo
                # entra na comparacao: salvar o endereco e so ver efeito depois
                # de reiniciar na mao seria uma armadilha.
                if self._chaves_de_rede() != antes:
                    self.wifi.reconfigurado()
                self._send_json(client_sock, {"success": True, "message": "Configuracoes salvas com sucesso!"})
            except Exception as exc:
                self._send_json(client_sock, {"success": False, "error": str(exc)}, status=400)

        elif method == "GET" and path == "/api/tags":
            self._send_json(client_sock, self.tags.get_logs())

        elif method == "POST" and path == "/api/scan":
            try:
                payload = json.loads(body or "{}")
                result = self.tags.process_tag(payload.get("code", ""), source="WEB_MANUAL",
                                               direction=payload.get("direction", "entrada"))
                self._send_json(client_sock, result)
            except Exception as exc:
                self._send_json(client_sock, {"success": False, "error": str(exc)}, status=400)

        elif method == "POST" and path == "/api/calibrar":
            self._handle_calibrar(client_sock, body)

        elif method == "POST" and path == "/api/trigger":
            success, message = self.relay.trigger_open()
            self._send_json(client_sock, {"success": success, "message": message},
                            status=200 if success else 400)
        else:
            self._send_response(client_sock, 404, "text/plain", "404 Not Found")

    def _handle_calibrar(self, client_sock, body):
        """
        Deduz tag_offset/tag_trim a partir da ultima tag lida.

        O operador aproxima uma tag ja cadastrada, digita o codigo dela e o
        sistema descobre os cortes sozinho, gravando na config.
        """
        try:
            esperado = str(json.loads(body or "{}").get("tag_code", "")).strip()
        except Exception:
            self._send_json(client_sock, {"success": False, "error": "JSON invalido"}, status=400)
            return
        if not esperado:
            self._send_json(client_sock, {"success": False,
                                          "error": "Informe o codigo da tag cadastrada"}, status=400)
            return

        limiar = self.config.get("tag_offset_threshold", 20)
        lidos = 0
        for leitor in self.readers:
            if not leitor.last_frame:
                continue
            lidos += 1
            achado = calibrar_offset_trim(leitor.last_frame, esperado, limiar)
            if achado:
                self.config.update(achado)
                print("[CALIBRACAO] %s -> offset %d, trim %d, limiar %d"
                      % (leitor.direction, achado["tag_offset"], achado["tag_trim"],
                         achado["tag_offset_threshold"]))
                self._send_json(client_sock, {
                    "success": True,
                    "direction": leitor.direction,
                    "frame": "".join(["%02X" % b for b in leitor.last_frame]),
                    "tag_offset": achado["tag_offset"],
                    "tag_trim": achado["tag_trim"],
                    "tag_offset_threshold": achado["tag_offset_threshold"],
                    "message": "Calibrado pelo leitor de %s e salvo." % leitor.direction,
                })
                return

        if lidos == 0:
            msg = "Nenhuma tag foi lida ainda. Aproxime a tag de um leitor e tente de novo."
        else:
            msg = ("O codigo informado nao aparece no ultimo frame lido. "
                   "Confira o codigo cadastrado ou leia a tag novamente.")
        self._send_json(client_sock, {"success": False, "error": msg,
                                      "frames": ["".join(["%02X" % b for b in r.last_frame])
                                                 for r in self.readers if r.last_frame]},
                        status=400)

    def _chaves_de_rede(self):
        return tuple(self.config.get(chave) for chave in (
            "wifi_ssid", "wifi_password",
            "wifi_static_ip", "wifi_subnet_mask", "wifi_gateway", "wifi_dns",
        ))

    def _handle_open(self, client_sock, auth, body):
        """
        Abertura manual comandada pelo SB Gatehouse (ADR 0011).
            POST /open  {"portaria": 1}  ->  200 {"opened": true}
        """
        token = self.config.get("open_token", "")
        if token and auth != token:
            print("[OPEN] Recusado: token invalido")
            self._send_json(client_sock, {"opened": False, "reason": "unauthorized"}, status=401)
            return

        success, message = self.relay.trigger_open()
        print("[OPEN] Abertura manual do gatehouse:", message)
        self._send_json(client_sock, {"opened": success, "reason": None if success else message},
                        status=200 if success else 409)

    # --- respostas ---

    def _send_file(self, client_sock, path, content_type="text/html; charset=utf-8"):
        """
        Envia o arquivo em blocos, direto do flash.

        Nunca carrega o conteudo inteiro na RAM. E o que permite servir 28KB de
        HTML num heap de ~190KB sem MemoryError por fragmentacao.
        """
        try:
            size = os.stat(path)[6]
        except Exception:
            # A UI vive no flash, nao mais embutida no main.py. Se a pasta wwwroot/
            # nao subiu para o dispositivo, um 404 seco nao diz o que houve.
            if path == INDEX_FILE:
                self._send_response(client_sock, 200, "text/html; charset=utf-8", FALLBACK_HTML)
            else:
                self._send_response(client_sock, 404, "text/plain", "404 Not Found")
            return
        self._send_headers(client_sock, 200, content_type, size)
        with open(path, "rb") as f:
            while True:
                chunk = f.read(512)
                if not chunk:
                    break
                client_sock.sendall(chunk)

    def _send_headers(self, client_sock, status, content_type, length):
        reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized",
                  404: "Not Found", 409: "Conflict"}.get(status, "OK")
        header = "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n"
        client_sock.sendall(header.format(status, reason, content_type, length).encode("utf-8"))

    def _send_json(self, client_sock, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self._send_headers(client_sock, status, "application/json", len(body))
        client_sock.sendall(body)

    def _send_response(self, client_sock, status_code, content_type, body_text):
        body = body_text.encode("utf-8")
        self._send_headers(client_sock, status_code, content_type, len(body))
        client_sock.sendall(body)


def diagnostico(config, wifi, web_server, readers=()):
    """
    Estado de cada camada em um unico boot: sem isso, uma falha do servidor web
    e indistinguivel de uma falha de arquivo, de RAM ou de rede.
    """
    print("\n===== DIAGNOSTICO =====")

    print("Wi-Fi   :", wifi.state, "| IP", wifi.ip_address, "| modo", wifi.mode)
    if wifi.state != WIFI_CONECTADO:
        print("          ainda sem rede - o resto do sistema ja esta no ar")

    # A UI e servida do flash; sem o arquivo, GET / responde 404.
    try:
        tamanho = os.stat(INDEX_FILE)[6]
        print("UI      :", INDEX_FILE, "OK -", tamanho, "bytes")
    except Exception:
        print("UI      : FALTA", INDEX_FILE, "- envie a pasta wwwroot/ para o dispositivo")
        try:
            print("          raiz do flash:", os.listdir())
        except Exception:
            pass

    if requests is None:
        print("HTTP    : SEM CLIENTE - instale urequests (mpremote mip install urequests)")
        print("          sem ele nenhuma tag e consultada no servidor")
    else:
        print("HTTP    : cliente disponivel")
    print("Servidor:", config.get("server_base_url") + config.get("access_path"))

    for leitor in readers:
        if leitor.uart is None:
            print("LEITOR  : %-8s NAO INICIALIZOU (UART%d RX GP%d)"
                  % (leitor.direction, leitor.uart_id, leitor.rx_pin))
        else:
            print("LEITOR  : %-8s UART%d RX GP%d a %d bps"
                  % (leitor.direction, leitor.uart_id, leitor.rx_pin,
                     config.get("reader_baudrate", 115200)))
    if config.get("tag_debug", 0):
        print("          tag_debug LIGADO - cada frame imprime o HEX bruto")
        print("          calibre tag_offset/tag_trim comparando com uma tag conhecida")

    if web_server.server_socket is None:
        print("WEB     : NAO INICIOU - veja o erro de socket acima")
    else:
        print("WEB     : escutando em http://%s:%d" % (wifi.ip_address, web_server.port))

    print("RAM     :", gc.mem_free(), "bytes livres")
    print("=======================\n")


def main():
    gc.collect()

    print("Iniciando sistema Gate Automation...")

    config = ConfigManager()
    wifi = WifiManager(config)
    wifi.connect()
    sensors = SensorManager(config)
    relay = GateRelay(config, sensor_manager=sensors)
    server_client = ServerClient(config)
    storage_manager = StorageManager(config) if StorageManager else None
    tag_mgr = TagManager(config, server_client, sensors, relay, storage_manager=storage_manager)
    readers = [
        TagReader(config, config.get("reader_in_uart", 1),
                  config.get("reader_in_rx", 5), "entrada"),
        TagReader(config, config.get("reader_out_uart", 0),
                  config.get("reader_out_rx", 1), "saida"),
    ]
    web_server = WebServer(config, wifi, sensors, relay, tag_mgr, readers=readers)
    web_server.start()

    diagnostico(config, wifi, web_server, readers)

    last_sync = ticks_ms()
    sync_interval = 10000

    try:
        while True:
            for leitor in readers:
                tag_code = leitor.poll()
                if tag_code:
                    print("Tag lida (%s):" % leitor.direction, tag_code)
                    tag_mgr.process_tag(tag_code, source="UART_RFID",
                                        direction=leitor.direction)

            # Fecha o portao quando o pulso expira (nao bloqueia o loop).
            relay.update()

            # Avanca a maquina de estados do Wi-Fi (uma transicao por volta).
            wifi.tick()

            web_server.poll()

            # Worker de sincronizacao da outbox.
            if ticks_diff(ticks_ms(), last_sync) > sync_interval:
                last_sync = ticks_ms()
                if wifi.mode == "STA" and wifi.is_connected and storage_manager:
                    outbox = storage_manager.get_outbox()
                    if outbox:
                        overflow = storage_manager.get_overflow_count()
                        item = outbox[0]
                        if server_client.sync_outbox_item(item, overflow_count=overflow):
                            storage_manager.remove_from_outbox([item.get("id")])
                            if overflow > 0:
                                storage_manager.reset_overflow_count()

            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nEncerrando sistema...")


if __name__ == "__main__":
    main()
