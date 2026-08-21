"""
Coerencia dos sensores: da leitura da tag ate o acionamento do rele.

Usa pinos GPIO falsos para exercitar os valores reais que o hardware entrega,
em vez do modo de simulacao (que devolve tudo "livre" e esconderia erros).
"""
import main

ok = []
def chk(n, c, d=""):
    ok.append((n, c)); print(("  OK  " if c else " FALHA") + " | " + n + ("  " + d if d else ""))

CLOCK = {"t": 0}
main.ticks_ms = lambda: CLOCK["t"]
main.ticks_diff = lambda a, b: a - b
main.ticks_add = lambda t, d: t + d


class FakePin:
    """PULL_UP: em repouso le 1; acionado/aterrado le 0."""
    IN = "in"; OUT = "out"; PULL_UP = "pu"
    valores = {}

    def __init__(self, num, mode=None, pull=None):
        self.num = num
        FakePin.valores.setdefault(num, 1)

    def value(self, v=None):
        if v is None:
            return FakePin.valores[self.num]
        FakePin.valores[self.num] = v


main.Pin = FakePin
main.UART = type("U", (), {})

BARREIRA, HALL, AUX, RELE = 2, 3, 4, 18
LIVRE, OCUPADA = 1, 0          # barreira: 1 = sem obstrucao
PORTAO_ABERTO, PORTAO_FECHADO = 0, 1   # hall: 0 = "Aberto" segundo o codigo atual


def cenario(autorizado=True, barreira=LIVRE, hall=PORTAO_FECHADO):
    FakePin.valores = {BARREIRA: barreira, HALL: hall, AUX: 1, RELE: 1}
    cfg = main.ConfigManager()
    cfg.config.update({"pin_barrier": BARREIRA, "pin_hall": HALL,
                       "pin_aux": AUX, "relay_pin": RELE,
                       "gate_open_duration": 5})
    sensors = main.SensorManager(cfg)
    relay = main.GateRelay(cfg, sensor_manager=sensors)

    class SC(main.ServerClient):
        def _post(self, payload):
            return 200, {"decision": "allowed" if autorizado else "denied",
                         "open": autorizado, "reason": None if autorizado else "negada"}

    return cfg, sensors, relay, main.TagManager(cfg, SC(cfg), sensors, relay)


print("--- semantica dos pinos ---")
_, s, _, _ = cenario(barreira=LIVRE)
chk("barreira em 1 -> caminho livre", s.is_barrier_clear() is True)
chk("rotulo bate com o booleano", s.get_barrier_status() == "Acesso livre")
_, s, _, _ = cenario(barreira=OCUPADA)
chk("barreira em 0 -> veiculo no caminho", s.is_barrier_clear() is False)
chk("rotulo bate com o booleano", s.get_barrier_status() == "Veículo no caminho")
_, s, _, _ = cenario(hall=PORTAO_ABERTO)
chk("hall em 0 -> portao Aberto", s.get_hall_status() == "Aberto")
_, s, _, _ = cenario(hall=PORTAO_FECHADO)
chk("hall em 1 -> portao Fechado", s.get_hall_status() == "Fechado")

print("\n--- /api/status nao contradiz os sensores ---")
_, s, _, _ = cenario(barreira=OCUPADA, hall=PORTAO_ABERTO)
st = s.get_all_status()
chk("status.barrier.clear == is_barrier_clear()", st["barrier"]["clear"] == s.is_barrier_clear())
chk("status.hall.is_closed é o inverso de Aberto",
    st["hall"]["is_closed"] is False and st["hall"]["label"] == "Aberto")

print("\n--- matriz de decisao: autorizado x barreira x hall ---")
MATRIZ = [
    # autorizado, barreira, hall,           deve acionar, trecho esperado no motivo
    (False, LIVRE,   PORTAO_FECHADO, False, "negada"),
    (False, OCUPADA, PORTAO_FECHADO, False, "negada"),
    (False, LIVRE,   PORTAO_ABERTO,  False, "negada"),
    (True,  LIVRE,   PORTAO_FECHADO, True,  "acionado"),
    (True,  OCUPADA, PORTAO_FECHADO, False, "veículo no caminho"),
    (True,  LIVRE,   PORTAO_ABERTO,  False, "já está aberto"),
    (True,  OCUPADA, PORTAO_ABERTO,  False, "veículo no caminho"),
]
for aut, bar, hal, deve, trecho in MATRIZ:
    _, s, relay, tm = cenario(autorizado=aut, barreira=bar, hall=hal)
    r = tm.process_tag("TAG1", direction="entrada")
    rotulo = "%s | barreira %s | hall %s" % (
        "autorizada" if aut else "negada  ",
        "ocupada" if bar == OCUPADA else "livre  ",
        "aberto " if hal == PORTAO_ABERTO else "fechado")
    chk("%s -> %s" % (rotulo, "ACIONA" if deve else "nao aciona"),
        r["gate_triggered"] is deve and trecho.lower() in r["reason"].lower(),
        r["reason"])
    chk("   rele coerente com a decisao", relay.is_busy is deve)
    chk("   log registra o estado da barreira",
        r["barrier_clear"] == (bar == LIVRE))

print("\n--- o rele nao confia so no TagManager ---")
_, s, relay, tm = cenario(autorizado=True, barreira=LIVRE)
FakePin.valores[BARREIRA] = OCUPADA          # veiculo entra no caminho depois da checagem
sucesso, msg = relay.trigger_open()
chk("segunda barreira, dentro do rele, tambem bloqueia",
    sucesso is False and "barreira" in msg.lower(), msg)
chk("nao energizou o pino do rele", FakePin.valores[RELE] == 1)

print("\n--- pino do rele acompanha o acionamento ---")
_, s, relay, tm = cenario(autorizado=True, barreira=LIVRE)
tm.process_tag("TAG1")
chk("acionou -> pino em LOW", FakePin.valores[RELE] == 0)
chk("portao consta ocupado", relay.is_busy is True)
CLOCK["t"] += 6000
relay.update()
chk("passado o pulso -> volta a alta impedancia e libera", relay.is_busy is False)

print("\n--- nao reabre enquanto o pulso corre ---")
_, s, relay, tm = cenario(autorizado=True, barreira=LIVRE)
tm.process_tag("TAG1")
r2 = tm.process_tag("TAG2")
chk("segunda tag durante o pulso nao reaciona", r2["gate_triggered"] is False)
chk("motivo explica o porque", "abertura" in r2["reason"].lower(), r2["reason"])

print("\n--- sensor que nao inicializou ---")
FakePin.valores = {BARREIRA: OCUPADA, HALL: PORTAO_FECHADO, AUX: 1, RELE: 1}
cfg = main.ConfigManager()
cfg.config.update({"pin_barrier": BARREIRA, "pin_hall": HALL, "pin_aux": AUX, "relay_pin": RELE})
s = main.SensorManager(cfg)
s.barrier_pin = None                          # simula falha na configuracao do pino
chk("barreira ausente reporta CAMINHO LIVRE (fail-open)", s.is_barrier_clear() is True)
chk("e o rotulo assume 'Simulado', escondendo a falha",
    "Simulado" in s.get_barrier_status(), s.get_barrier_status())

print("\n--- botoeira auxiliar ---")
_, s, relay, tm = cenario()
FakePin.valores[AUX] = 0                      # botao pressionado
chk("aux pressionado NAO e detectado", s.is_aux_pressed() is False)
chk("rotulo do aux ignora o pino", s.get_aux_status() == "Desativada")

print("\n--- fluxo completo: leitor -> sensores -> rele ---")
class FakeUART:
    def __init__(self): self.q = []
    def feed(self, b): self.q.append(b)
    def any(self): return len(self.q)
    def read(self): return self.q.pop(0) if self.q else None

def bs(h): return bytes(int(h[i:i+2], 16) for i in range(0, len(h), 2))

for barreira, deve in ((LIVRE, True), (OCUPADA, False)):
    cfg, s, relay, tm = cenario(autorizado=True, barreira=barreira)
    cfg.config.update({"tag_offset": 4, "tag_trim": 4, "tag_offset_threshold": 10,
                       "frame_gap_ms": 30, "rfid_dedup_seconds": 2, "tag_debug": 0})
    leitor = main.TagReader.__new__(main.TagReader)
    leitor.config = cfg; leitor.uart_id = 1; leitor.rx_pin = 5; leitor.direction = "entrada"
    leitor.uart = FakeUART(); leitor.last_tag = None; leitor.last_tag_time = 0
    leitor._last_tag_ticks = -999999; leitor._buf = b""; leitor._last_byte_ticks = 0
    leitor.last_frame = b""

    leitor.uart.feed(bs("BB022200E28011606000020C5E5A12341D7E"))
    leitor.poll(); CLOCK["t"] += 40
    codigo = leitor.poll()
    r = tm.process_tag(codigo, source="UART_RFID", direction=leitor.direction)
    estado = "livre" if barreira == LIVRE else "ocupada"
    chk("tag lida na UART com barreira %s -> %s" % (estado, "abre" if deve else "bloqueia"),
        r["gate_triggered"] is deve and FakePin.valores[RELE] == (0 if deve else 1),
        r["reason"])
    chk("   a direcao do leitor chega no log", r["direction"] == "entrada")

print("\n%d/%d" % (sum(1 for _, c in ok if c), len(ok)))
raise SystemExit(0 if all(c for _, c in ok) else 1)
