# Mapa de pinos

Estado do código em `main.py` (`DEFAULT_CONFIG`). Os valores são **padrões**: o
`config.json` do dispositivo sobrepõe qualquer um deles, e é ele que vale de
verdade. Para ver o que está gravado no Pico:

```python
import json; print(json.load(open("config.json")))
```

## Em uso

| GPIO | Pino físico | Função | Modo | Chave de config |
|---|---|---|---|---|
| GP1 | 2 | Leitor RFID **saída** (UART0 RX) | UART RX | `reader_out_rx` |
| GP2 | 4 | Sensor de barreira | `IN` + `PULL_UP` | `pin_barrier` |
| GP3 | 5 | Hall **A** (posição do portão) | `IN` + `PULL_UP` | `pin_hall_a` |
| GP4 | 6 | Hall **B** (posição do portão) | `IN` + `PULL_UP` | `pin_hall_b` |
| GP5 | 7 | Leitor RFID **entrada** (UART1 RX) | UART RX | `reader_in_rx` |
| GP16 | 21 | Relé do portão | ver abaixo | `relay_pin` |

Não existe mais sensor auxiliar / botoeira. A chave `pin_aux` foi removida do
firmware, do formulário e do payload de `/api/status` — era código morto desde
o commit `bd38e59`, e o GP4 que ela reservava agora é o fim de curso de ABERTO.

> **Dispositivo já em campo:** duas gerações de chaves precederam estas —
> `pin_hall` (sensor único) e o par `pin_hall_closed`/`pin_hall_open` (fins de
> curso em extremos opostos). O `ConfigManager._migrar_hall` converte as duas
> para `pin_hall_a`/`pin_hall_b` no boot, avisando no console. Suba o
> `config.json` novo ou corrija pela tela de configuração.

## Níveis lógicos

Todas as entradas usam `PULL_UP` interno: **o pino fica em 1 solto e vai a 0
quando o sensor fecha para o GND.**

**Barreira** (`is_barrier_clear`)

| Leitura | Significado | Efeito |
|---|---|---|
| `1` | Acesso livre | abertura liberada |
| `0` | Veículo no caminho | **bloqueia** a abertura |

**Halls** — os dois ficam **no mesmo ponto, empilhados**, e não são fins de
curso em extremos opostos. Quem codifica a posição é o arranjo dos ímãs no
portão, e o estado sai da **contagem** de quantos halls veem ímã — nunca de
qual deles vê. Por isso `pin_hall_a` e `pin_hall_b` são **intercambiáveis**:
trocar os fios entre GP3 e GP4 não muda nada.

`hall_active_low` (padrão `1`) define qual nível é "ímã presente". Com o
padrão, **ímã presente = `0`**. Se os estados aparecerem trocados na tela,
inverta essa chave em vez de mexer no código.

| Halls vendo ímã | Estado | Acesso por tag aciona? |
|---|---|---|
| 2 | `Fechado` — os dois ímãs alinhados | **sim** |
| 1 (qualquer um) | `Em movimento` — um ímã já saiu | não — deixa terminar o curso |
| 0 | `Aberto` — os dois ímãs longe | não — já está aberto |
| um dos `Pin()` falhou | `Hall indisponivel` | sim — sensor quebrado não tranca o portão |

Não existe mais o estado `Erro nos sensores`. Ele significava "os dois
atingidos ao mesmo tempo, fisicamente impossível"; com os halls juntos, essa
passou a ser a condição normal de portão fechado. Nenhuma combinação é
impossível agora, então sensor colado ou ímã caído só aparece com checagem
por tempo — que ainda não existe.

Um `Pin()` que falha no boot torna a contagem mentirosa (1 ímã seria "aberto"
ou um "fechado" pela metade), então o estado vira `Hall indisponivel` em vez
de escolher. O acionamento por tag segue liberado nesse caso.

**Relé** (`GP16`) não é um `OUT` permanente:

- **Repouso:** `Pin(16, Pin.IN)` — alta impedância, o pino flutua livre.
- **Acionado:** `Pin(16, Pin.OUT)` + `value(0)` — **nível BAIXO abre.**
- Volta à alta impedância depois de `gate_open_duration` (padrão 5s), fechando
  por prazo dentro do loop principal, sem `sleep`.

O pulso manual (`/api/trigger` e `/open`) ignora os fins de curso de propósito:
com o portão aberto, o pulso é o comando de fechar. Só a barreira o bloqueia.

## Restrição das UARTs (RP2040)

Os pinos dos leitores não são livres — o silício amarra cada UART a poucos pinos:

- **UART0 RX:** GP1, GP13 ou GP17
- **UART1 RX:** GP5 ou GP9

Só o RX é configurado: os leitores transmitem sozinhos e nunca recebem comando,
então os TX ficam livres — é por isso que o GP16, TX da UART0, serve de relé
sem conflitar com o leitor de saída, que usa o GP1 como RX.

## Pinos livres

GP0, GP6 a GP15, GP17 a GP22, GP26 a GP28.

GP26–GP28 também servem como entradas analógicas (ADC0–ADC2), caso apareça
sensor analógico. GP23, GP24, GP25 e GP29 são internos no Pico W e não devem
ser usados.

## Onde mudar

Tudo pela tela de configuração (aba **Configurações** em `http://<ip>/`), que
grava no `config.json` e sobrevive ao reboot. O `config.example.json` é só
modelo — o arquivo real fica fora do versionamento.
