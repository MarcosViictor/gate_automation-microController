"""WifiManager como maquina de estados nao-bloqueante."""
import main

ok = []
def chk(n, c, d=""):
    ok.append((n, c)); print(("  OK  " if c else " FALHA") + " | " + n + ("  " + d if d else ""))

CLOCK = {"t": 0}
main.ticks_ms = lambda: CLOCK["t"]
main.ticks_diff = lambda a, b: a - b
main.ticks_add = lambda t, d: t + d
def avanca_s(s): CLOCK["t"] += int(s * 1000)

class FakeWLAN:
    """seq = codigos de status() consumidos um por tick; ip_em = tick do IP."""
    def __init__(self, seq=(0,), ip_em=None):
        self.seq = list(seq); self.ip_em = ip_em
        self.ticks = 0; self.on = False; self.conectou = 0
    def active(self, v=None):
        if v is not None: self.on = v
        return self.on
    def connect(self, s, p): self.conectou += 1; self.ticks = 0
    def status(self):
        return self.seq[min(self.ticks, len(self.seq) - 1)]
    def isconnected(self):
        return self.ip_em is not None and self.ticks >= self.ip_em
    def config(self, **kw): pass
    def ifconfig(self):
        return ("192.168.10.230", "255.255.255.0", "192.168.10.1", "192.168.10.1")

def monta(ssid="STB_teste_Visitantes", **extra):
    cfg = main.ConfigManager()
    cfg.config.update({"wifi_ssid": ssid, "wifi_password": "x", "wifi_timeout": 30,
                       "wifi_retry_base_seconds": 5, "wifi_retry_max_seconds": 60})
    cfg.config.update(extra)
    w = main.WifiManager(cfg)
    return cfg, w

def instala(w, wlan):
    """Aponta o WifiManager para uma WLAN falsa (o network real nao existe no PC)."""
    main.network = type("N", (), {"STA_IF": 0, "AP_IF": 1, "WLAN": staticmethod(lambda i: wlan)})()
    w.wlan = wlan

def roda(w, wlan, segundos, passo=1):
    for _ in range(int(segundos / passo)):
        avanca_s(passo); wlan.ticks += passo; w.tick()

print("--- boot nao bloqueia ---")
cfg, w = monta(); wlan = FakeWLAN([2] * 60, ip_em=None); instala(w, wlan)
w.connect()
chk("connect() volta na hora, em ASSOCIANDO", w.state == main.WIFI_ASSOCIANDO, w.state)
chk("ja disparou o connect no radio", wlan.conectou == 1)

print("\n--- nenhum caminho bloqueia (time.sleep proibido) ---")
class Boom(Exception): pass
real_sleep = main.time.sleep
main.time.sleep = lambda s: (_ for _ in ()).throw(Boom("bloqueou"))
try:
    cfg, w = monta(); wlan = FakeWLAN([2] * 60, ip_em=40); instala(w, wlan)
    w.connect(); roda(w, wlan, 45)
    chk("connect + 45 ticks sem nenhum sleep", True)
except Boom:
    chk("connect + 45 ticks sem nenhum sleep", False, "chamou time.sleep")
finally:
    main.time.sleep = real_sleep

print("\n--- DHCP lento (o caso real do log) ---")
cfg, w = monta(); wlan = FakeWLAN([2] * 60, ip_em=23); instala(w, wlan)
w.connect(); roda(w, wlan, 22)
chk("aos 22s ainda associando, sem cair para AP", w.state == main.WIFI_ASSOCIANDO, w.state)
roda(w, wlan, 3)
chk("aos 25s conecta normalmente", w.state == main.WIFI_CONECTADO, w.state)
chk("aprendeu o IP", w.ip_address == "192.168.10.230")
chk("modo segue STA", w.mode == "STA")

print("\n--- erro de configuracao vai para AP na hora ---")
cfg, w = monta(); wlan = FakeWLAN([1, -3, -3], ip_em=None); instala(w, wlan)
w.connect(); roda(w, wlan, 3)
chk("senha incorreta (-3) -> AP", w.state == main.WIFI_AP, w.state)
chk("nao esperou o prazo de 30s", CLOCK["t"] < 999999999)

cfg, w = monta(); wlan = FakeWLAN([-2], ip_em=None); instala(w, wlan)
w.connect(); roda(w, wlan, 2)
chk("rede nao encontrada (-2) -> AP", w.state == main.WIFI_AP, w.state)

cfg, w = monta(ssid=""); wlan = FakeWLAN([0], ip_em=None); instala(w, wlan)
w.connect()
chk("SSID em branco -> AP", w.state == main.WIFI_AP, w.state)

print("\n--- rede indisponivel NUNCA vai para AP ---")
cfg, w = monta(); wlan = FakeWLAN([0] * 200, ip_em=None); instala(w, wlan)
w.connect(); roda(w, wlan, 31)
chk("estourou o prazo -> AGUARDANDO, nao AP", w.state == main.WIFI_AGUARDANDO, w.state)
roda(w, wlan, 300)
chk("5 minutos depois segue tentando STA, nunca AP", w.state != main.WIFI_AP, w.state)

print("\n--- backoff exponencial com teto ---")
cfg, w = monta(); wlan = FakeWLAN([0] * 4000, ip_em=None); instala(w, wlan)
w.connect()
esperas = []
for _ in range(6):
    while w.state != main.WIFI_AGUARDANDO:
        avanca_s(1); wlan.ticks += 1; w.tick()
    esperas.append(w._backoff)
    while w.state == main.WIFI_AGUARDANDO:
        avanca_s(1); w.tick()
chk("dobra e respeita o teto", esperas == [5, 10, 20, 40, 60, 60], str(esperas))

print("\n--- queda depois de conectado ---")
cfg, w = monta(); wlan = FakeWLAN([2] * 60, ip_em=1); instala(w, wlan)
w.connect(); roda(w, wlan, 3)
chk("conectou", w.state == main.WIFI_CONECTADO, w.state)
wlan.ip_em = None
roda(w, wlan, 1)
chk("link caiu -> AGUARDANDO", w.state == main.WIFI_AGUARDANDO, w.state)
wlan.ip_em = 0
roda(w, wlan, 10)
chk("rede voltou -> reconecta sozinho", w.state == main.WIFI_CONECTADO, w.state)

print("\n--- AP e terminal, mas reconfigurar tira dele ---")
cfg, w = monta(); wlan = FakeWLAN([-3], ip_em=None); instala(w, wlan)
w.connect(); roda(w, wlan, 2)
chk("esta em AP", w.state == main.WIFI_AP)
roda(w, wlan, 600)
chk("10 minutos de ticks nao tiram do AP sozinho", w.state == main.WIFI_AP, w.state)
wlan.seq = [2]; wlan.ip_em = 1
w.reconfigurado()
chk("salvar credenciais volta para ASSOCIANDO", w.state == main.WIFI_ASSOCIANDO, w.state)
roda(w, wlan, 3)
chk("e conecta com a senha corrigida", w.state == main.WIFI_CONECTADO, w.state)

print("\n--- traducao dos codigos do CYW43 ---")
chk("codigo 2 nao e 'senha incorreta'", "senha" not in main.WLAN_STATUS[2], main.WLAN_STATUS[2])
chk("codigo 2 fala de DHCP", "DHCP" in main.WLAN_STATUS[2])
chk("codigo -3 e senha incorreta", main.WLAN_STATUS[-3] == "senha incorreta")
chk("so os negativos sao terminais", main.WLAN_TERMINAL == (-1, -2, -3))
chk("1 e 2 nao sao terminais",
    1 not in main.WLAN_TERMINAL and 2 not in main.WLAN_TERMINAL)

print("\n--- status para a tela ---")
st = w.get_status()
chk("get_status expoe o estado", st.get("state") == main.WIFI_CONECTADO, str(st.get("state")))
chk("mantem as chaves antigas",
    all(k in st for k in ("connected", "ip", "mode", "ssid")))

print("\n%d/%d" % (sum(1 for _, c in ok if c), len(ok)))
raise SystemExit(0 if all(c for _, c in ok) else 1)
