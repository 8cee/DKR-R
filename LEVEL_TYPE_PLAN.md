# Plano: tipo de nível, catálogo contextual e grelha de largada

## O desejo do usuário

Três pedidos, nesta ordem de importância:

1. **Um interruptor mestre, e o primeiro contato.** Escolher o modo da track é
   a primeira coisa que o autor faz no addon — antes de importar, colocar
   objetos ou exportar. *Level Type*: Race, Boss Race, Challenge, Hub, e um
   grupo *Special* avançado para o que não é jogo normal. Quando for Boss Race,
   aparece logo abaixo um seletor de chefe. Tudo o resto do addon passa a
   obedecer a essa escolha.
2. **Um catálogo que obedece ao interruptor.** A lista de objetos esconde o que
   não serve para o tipo de nível escolhido (ex.: o Egg Creator só aparece num
   Challenge de ovos), as abas Structure / Collectables separam de fato a lista,
   o Colored Balloon e o Green Balloon aparecem na lista, e todo botão tem
   tooltip.
3. **Um gerador de grelha de largada.** Um botão que lê o interruptor e cria a
   quantidade certa de spawners (8 na corrida, 4 na batalha, 2 no chefe), todos
   filhos de um objeto raiz para mover a grelha inteira de uma vez, com os
   índices já preenchidos.

Estado: **implementado** (revisão 2: o modo virou o primeiro contato; Horseshoe
Gulch e as cenas foram para um grupo *Special*), com o layout de
`tools/blender/ui_mockup.html`. Fora do escopo por ora: o Minimap e o AI Node
Graph ficam na sidebar marcados *in development*, e o player de música troca a
faixa pelo nome mas ainda não toca áudio. A galeria de skybox é real
(`skyboxes.py`): panorâmicas dos 18 domos e o domo escolhido no viewport.
Os números vêm de um levantamento feito sobre os 65 headers e os 136 object maps
retail extraídos em `extern/dkr-decomp/assets/.vanilla/us.v77` e do código do
decomp; cada fato cita a sua fonte.

---

## O que o jogo realmente faz

Tudo neste plano apoia-se nisto; se um destes fatos estiver errado, o desenho
muda.

### Os tipos de nível são valores de `race_type`

O byte `0x4C` do header (`level_header.py:153`, enum `RaceType`) é o que decide
o modo. Os 65 headers retail se distribuem assim:

| Família (o dropdown) | `race_type` | Valor | Níveis retail |
|---|---|---|---|
| Race | `RACETYPE_DEFAULT` | 0 | 20 corridas |
| Boss Race | `RACETYPE_BOSS` | 8 | 10 (Tricky, Bluey, Bubbler, Smokey, Wizpig; 1 e 2) |
| Challenge | `RACETYPE_CHALLENGE_BATTLE` | 64 | Darkwater Beach, Icicle Pyramid |
| | `RACETYPE_CHALLENGE_BANANAS` | 65 | Smokey Castle |
| | `RACETYPE_CHALLENGE_EGGS` | 66 | Fire Mountain |
| Hub | `RACETYPE_HUBWORLD` | 5 | 6 hubs + 10 sequências |
| Special (avançado) | `RACETYPE_CUTSCENE_1` | 6 | 10 cenas (seleção de personagem, tela título, troféus) |
| | `RACETYPE_CUTSCENE_2` | 7 | 4 fundos de menu (FrontEnd, opções, amuletos) |
| | `RACETYPE_HORSESHOE_GULCH` | 3 | Horseshoe Gulch, a corrida de teste |
| fora de todo menu | `RACETYPE_UNK1` | 1 | nenhum |
| fora de todo menu | `RACETYPE_CHALLENGE` | 64 | é a máscara `0x40`, não um tipo |

O que os tipos fora do jogo normal fazem, pelo decomp:

- **Cutscene (6)** não spawna corredores — a montagem da largada retorna logo
  no começo (`objects.c:1096`) — e desenha a pista com antialiasing
  (`tracks.c:325`).
- **Menu Backdrop (7)** também não spawna corredores e **não desenha a
  geometria da pista**, só os objetos (`tracks.c:321-323`).
- **Test Race (3)**, o tipo da Horseshoe Gulch: corre como uma corrida (HUD,
  fanfarra, largada travada — `game_ui.c:720-754`, `racer.c:4353`), mas não
  tem time trial (`objects.c:1104`), não conta como corrida (`game.c:482`) e
  não salva recordes nem progresso (`save_data.c:381`, `save_data.c:434`). Era
  uma pista de teste; o addon não a recomenda para nada.
- **`RACETYPE_UNK1` (1):** o único efeito achado é o HUD aparecer sem animação
  (`game_ui.c:403`); nenhum nível usa.
- **`RACETYPE_CHALLENGE`** é a máscara que o código usa para perguntar "é
  challenge?" (`enums.h:90`), com o mesmo valor de `CHALLENGE_BATTLE`. Hoje ela
  aparece como opção no picker de *Race type* do painel de header, que ainda
  ordena por nome em vez de valor (`operators/header.py:84-90`).

**Consequência de desenho:** "Challenge" não é um valor, são três. O jogo trata
64, 65 e 66 de formas diferentes, e a regra pedida ("Egg Creator só num
Challenge / Eggs") só é expressável se o addon souber qual dos três. Por isso
Challenge ganha um segundo seletor condicional (Battle / Bananas / Eggs), com o
mesmo comportamento do seletor de chefe — e Special também (Cutscene / Menu
Backdrop / Test Race).

O chefe é o byte `0xB8`, `/boss-race-id` (`level_header.py:217`, enum
`BossSetupTypes`, 10 membros). Hoje ele nem aparece no painel de header: está na
parte "defaulted" do template (`data/level_header_defaults.json:76`, sempre
`BOSS_RACE_TRICKY1`).

### Quantos corredores cada modo spawna

`objects.c`, na função que monta a largada:

- `gNumRacers = 8` por padrão (`objects.c:1149`);
- `if (raceType & RACETYPE_CHALLENGE) gNumRacers = 4;` (`objects.c:1174-1176`);
- `if (raceType == RACETYPE_BOSS) gNumRacers = 2;` (`objects.c:1178-1179`);
- hub: `gNumRacers = numPlayers` (`objects.c:1164-1165`).

Isso bate com o retail: as 20 corridas têm grupos de 8, os 10 chefes grupos de
2, os 4 challenges grupos de 4, e os hubs um ponto por entrada.

### Um índice que falta põe um corredor na origem do mapa

```c
for (j = 0; j < ARRAY_COUNT(spawnZ); j++) { spawnX[j] = 0; spawnY[j] = 0; spawnZ[j] = 0; }
...
if (entranceID == racerObj->properties.setupPoint.entranceID) {
    if (racerObj->properties.setupPoint.racerIndex < 8) {
        spawnX[racerObj->properties.setupPoint.racerIndex] = racerObj->trans.x_position;
        ...
        spawnAngle[racerObj->properties.setupPoint.racerIndex] = racerObj->trans.rotation.y_rotation;
```

(`objects.c:1121-1136`). A posição é zerada e o ângulo **não**: se a grelha de
uma corrida não tem o `racerIndex` 5, o sexto corredor nasce em `(0, 0, 0)`
olhando para uma direção indefinida. E um `racerIndex` ≥ 8 é ignorado. É por
isso que "índices já configurados" não é conforto, é correção.

### A forma da grelha retail, medida

Nas 20 corridas, a direção de corrida (checkpoint *k* → *k+1* mais próximo da
grelha) é **sempre `angleY + 180°`** no plano XZ do mapa (desvio máximo 18°), e
a linha do corredor 0 ao 3 é **perpendicular** a ela (|cos| ≤ 0,27). Então a
grelha é **4 lado a lado × 2 fileiras escalonadas**, fileira 0–3 na frente.

Traduzido para o referencial local de um Empty no Blender (via
`blender = (x, -z, y)` de `scene.py` e `rotation_euler.z = radians(angleY)`):
**o carro olha para o +Y local, +X é a direita**. Mediana das 20 pistas,
centrada na grelha, em unidades de mapa:

| `racerIndex` | X local | Y local | |
|---|---|---|---|
| 0 | −199 | +39 | frente, esquerda |
| 1 | −78 | +36 | |
| 2 | +30 | +34 | |
| 3 | +137 | +34 | frente, direita |
| 4 | +195 | −38 | trás, direita |
| 5 | +81 | −36 | |
| 6 | −29 | −35 | |
| 7 | −139 | −32 | trás, esquerda |

A fileira de trás está deslocada ~60 para a direita (escalonamento), e os
índices fazem uma "cobra": 0→3 na frente, 4→7 de volta atrás. Variação entre
pistas: o passo lateral vai de 91 a 136, a distância entre fileiras de 20 a 109.

**Chefe (2):** lado a lado, 136–180 de distância (Wizpig 1, Tricky, Bubbler);
Bluey é diagonal. O corredor 1 fica à direita em 2 de 3 casos.

**Challenge (4):** não é grelha. Os quatro ficam num círculo em volta da arena,
**cada um olhando para o centro** (Icicle Pyramid, Fire Mountain, Darkwater
Beach: desvio ≤ 5°; Smokey Castle gira 45° a mais, num "cata-vento"). Raio:
~1200 (Icicle), ~2000 (Fire Mountain), ~3400 (Darkwater). Ordem anti-horária
vista de cima: 0 em −Y, 1 em +X, 2 em +Y, 3 em −X.

**Hub:** um ponto por entrada (`entranceID` 0–7), `racerIndex` 0, e o `vehicle`
geralmente preenchido (carro, hovercraft, avião, conforme o hub).

### Onde cada tipo aparece no retail

Tipos "de jogo" (categorias `racing`, `pickups`, `hub` do catálogo) e em que
famílias o retail os usa (R = corrida, B = chefe, C = challenge, H = hub):

| Tipo | Famílias | Tipo | Famílias |
|---|---|---|---|
| SETUPPOINT | R B C H | EGGCREATOR | C (ovos) |
| CHECKPOINT | R B H | HEADFORPOINT | C (ovos) |
| AINODE | R C H (não B) | COINCREATOR | C (bananas) |
| GROUNDZIPPER | R B | TREASURESUCKER | C (bananas) |
| AIRZIPPERS, WATERZIPPERS | R | CHARACTERFLAG | C (bananas, ovos) |
| COIN (bananas) | R, C (bananas) | FIREBALLATTRACT | B |
| SILVERCOIN, GOLDCOIN | R | GOLDENBALLOON | B H |
| WEAPONBALLOON | R B C (não H) | TRIGGER | R B |
| WORLDKEY, MODECHANGE, RAMPSWITCH | R | OVERRIDEPOS | B H |
| EXIT | H (+1 em R) | STOPWATCHMAN, RANGETRIGGER | H |
| LEVELDOOR, WORLDGATE, BOSSDOOR, BIGBOSSDOOR, CHALDOOR, TTDOOR, TELEPORT, LEVELNAME, TROPHYCAB, PWSAFETELEPOINT | H | BOOST | só cutscene |

Cenário, áudio, efeitos, câmera e atores genéricos (árvores, peixes,
borboletas, luzes) aparecem espalhados por todas as famílias e não carregam
regra de modo.

### A cor de um balão é o `balloonType`

`obj_init_weaponballoon` (`object_functions.c:4658-4679`) mostra a
correspondência pelos próprios nomes dos cheats, e usa o tipo como índice de
modelo:

| Cheat | `balloonType` | Cor |
|---|---|---|
| `CHEAT_ALL_BALLOONS_ARE_RED` | `BALLOON_TYPE_MISSILE` | vermelho |
| `CHEAT_ALL_BALLOONS_ARE_BLUE` | `BALLOON_TYPE_BOOST` | azul |
| `CHEAT_ALL_BALLOONS_ARE_GREEN` | `BALLOON_TYPE_TRAP` | **verde** |
| `CHEAT_ALL_BALLOONS_ARE_YELLOW` | `BALLOON_TYPE_SHIELD` | amarelo |
| `CHEAT_ALL_BALLOONS_ARE_RAINBOW` | `BALLOON_TYPE_MAGNET` | arco-íris |

O catálogo só tem **um** `WEAPONBALLOON`, com default `BALLOON_TYPE_MISSILE`
(`catalog.json:8246-8266`) — é por isso que "faltam" balões: só existe o
vermelho na lista, e a cor só se troca depois, num dropdown de campo. O preview
já desenha a cor certa a partir do `balloonType` (`preview.py:382-414`), então
basta o objeto nascer com o tipo certo.

**Interpretação:** *Green Balloon* = `TRAP`; *Colored Balloon* = o arco-íris,
`MAGNET` ("balão colorido"). O plano adiciona as cinco cores de uma vez, o que
cobre também a leitura alternativa ("um balão de cor escolhível").

### Structure / Collectables não é semântico

`scene.py:46-50` já diz: o jogo carrega os dois mapas do mesmo jeito. O retail
confirma e mostra o tamanho da mistura — `AINODE` está 75% no mapa de
collectables, `ANIMATION` 88%, `CHECKPOINT` 9%. Mas os pickups são nítidos:
`SILVERCOIN` 100%, `GOLDCOIN` 98%, `COIN` 97%, `WEAPONBALLOON` 88% em
collectables. A exceção é `EGGCREATOR` (3 de 3 em structure).

---

## O que está quebrado ou falta hoje

Achados da leitura do código, que o plano corrige no caminho:

1. **O dropdown de categoria pode abrir vazio.** `category_items`
   (`props.py:25-35`) devolve uma lista nova a cada chamada **sem** `_keep` —
   exatamente o sintoma que o próprio arquivo documenta nas linhas 13-17.
   `object_type_items` (`edit.py:62-86`) tem o mesmo padrão.
2. **As "abas" Structure / Collectables não filtram nada.** `slot`
   (`props.py:209-221`) só decide para qual mapa vai o próximo objeto colocado;
   a lista (`panels.py:395-414`) ignora-o e mostra tudo, cortado em 60.
3. **Todo botão de colocar tem o mesmo tooltip**, a docstring de
   `DKR_OT_place_object` (`edit.py:90`): "Add a DKR object at the 3D cursor".
4. **`is_racing_track` é um interruptor mestre pela metade** (`props.py:200-207`):
   um booleano, só lido pela validação (`checks.py:26`, `pack.py:50`), sem
   relação com o `race_type` que o header escreve.
5. **Bug: *Refresh Object Artwork* apaga todos os objetos.** Em
   `edit.py:279-287` os objetos são removidos e só **depois** se lê
   `slots = [scene.slot_of(o) for o in scene.iter_dkr_objects(context)]` — que
   já está vazio, então o `zip` não recria nada. (Achado na leitura, não
   reproduzido; mesmo corrigida a ordem, `existing` vem ordenado por
   `dkr_order` e `slots` na ordem da cena.)
6. **Nada preserva parentesco.** O ângulo exportado é
   `math.degrees(empty.rotation_euler.z)` (`scene.py:316-321`), que é **local**:
   um spawner filho de uma raiz girada exportaria o ângulo errado. *Drop To
   Surface* faz `obj.location = landing` (`geometry.py:1483`), coordenada local
   num filho. *Import Track* limpa só objetos com `dkr_id`
   (`io_objects.py:168-170`), então uma raiz ficaria órfã.

A posição já está certa para filhos: a exportação usa
`matrix_world.translation` depois de `view_layer.update()` (`scene.py:332`,
`scene.py:360`).

---

## 1. O interruptor mestre

### O primeiro contato

Uma cena nova **não tem modo**. Enquanto não tiver:

- o addon mostra um único painel, *Level Type*, no topo da sidebar
  (`bl_order = 0`, registrado antes de `DKR_PT_track`), com a pergunta e um
  botão grande por família;
- os outros painéis (*Track* e os seus filhos, *DKR Object*, *AI Node Graph*,
  *Validate*, *Package*) ficam ocultos pelo `poll` — não há o que colocar,
  validar ou exportar antes de saber o que a track é;
- a única outra ação oferecida é *Import Retail Track*, porque um nível retail
  já traz o seu modo e o import o preenche.

```
 DKR ─────────────────────────────────
 ┌ Level Type ───────────────────────┐
 │ What kind of level is this?       │
 │ ┌───────────────┐┌──────────────┐ │
 │ │     Race      ││  Boss Race   │ │
 │ └───────────────┘└──────────────┘ │
 │ ┌───────────────┐┌──────────────┐ │
 │ │   Challenge   ││     Hub      │ │
 │ └───────────────┘└──────────────┘ │
 │  ▸ Special (advanced)             │
 │ ───────────────────────────────── │
 │  or  [ Import Retail Track ]      │
 └───────────────────────────────────┘
```

Cada botão tem tooltip dizendo o que o modo é e o que muda no addon ("8 start
positions, checkpoints required, weapons and coins available"). *Special* fica
recolhido por padrão, e dentro dele Test Race vem por último, com aviso.

Depois da escolha o cartão encolhe para uma linha, e os painéis aparecem:

```
 ┌ Level Type ───────────────────────┐
 │ [ Boss Race                    ▼ ]│
 │   Boss [ Bluey (first race)    ▼ ]│   ← só em Boss Race
 │   Hovercraft, as in the retail    │
 └───────────────────────────────────┘
 ▸ Track
 ▸ Place
 ...
```

O segundo seletor depende da família: *Boss* em Boss Race, *Challenge* (Battle /
Bananas / Eggs) em Challenge, *Kind* (Cutscene / Menu Backdrop / Test Race) em
Special. Race e Hub não têm.

**Trocar de modo depois** passa por um operador, não por uma propriedade
solta: o dropdown é `layout.operator_menu_enum("dkr.set_level_type", "mode")`,
e o operador, se já há objetos na cena, abre uma confirmação com as
consequências antes de aplicar — "8 objects are not used in a Hub
(Checkpoint ×8). They stay in the scene; validation will warn. The start grid
has 8 positions; a Hub uses 1." — com *Regenerate Start Grid* ali mesmo. Com
undo, como todo operador do addon.

**Cenas criadas antes deste recurso** abrem sem modo, com objetos. O cartão não
adivinha em silêncio (um painel não pode escrever dados no `draw`, e não
deveria): se a cena veio de um nível retail (`source_path` →
`AssetTree.level_using`) ou já tem uma resposta de *Race type* no header, o
cartão mostra um botão de sugestão — "This scene was imported from Bluey 1.
[Use Boss Race]".

### Dados

Um módulo novo, **sem `bpy`**, `dkr_track_editor/level_types.py`, dono de tudo o
que depende do modo — no mesmo espírito de `level_header_template.py`:

```python
NONE, RACE, BOSS, CHALLENGE, HUB, SPECIAL = ...
CHALLENGES = ("BATTLE", "BANANAS", "EGGS")
SPECIALS = ("CUTSCENE", "BACKDROP", "TEST_RACE")

def race_type(mode, sub=None) -> str                     # ("CHALLENGE", "EGGS") -> "RACETYPE_CHALLENGE_EGGS"
def mode_of(race_type) -> Tuple[str, Optional[str]]      # "RACETYPE_HORSESHOE_GULCH" -> ("SPECIAL", "TEST_RACE")
def spawn_count(mode, sub=None) -> int                   # 8 / 2 / 4 / 1; Special: 0, 0, 8
def needs_checkpoints(mode, sub=None) -> bool            # Race, Boss Race, Test Race
def header_overrides(mode, sub, boss) -> dict            # {"/race-type": ..., "/boss-race-id": ...}
BOSSES = [("BOSS_RACE_TRICKY1", "Tricky (first race)", "VEHICLE_CAR"), ...]  # 10, com o veículo retail
```

Todo `race_type` que um nível retail usa vira **exatamente um** par (família,
sub-tipo), então `race_type(*mode_of(x)) == x` para os 65 headers. É isso que
deixa o import preservar o valor exato sem estado escondido.

A tabela de chefes carrega o veículo que o retail usa (Tricky e Wizpig 1: carro;
Bluey e Bubbler: hovercraft; Smokey e Wizpig 2: avião), medido nos headers.

### Propriedades (`props.py`)

- `level_type: EnumProperty` — `NONE` (default), `RACE`, `BOSS`, `CHALLENGE`,
  `HUB`, `SPECIAL`, cada item com descrição. Só `dkr.set_level_type` e o import
  escrevem nela.
- `challenge_type`, `special_type`, `boss: EnumProperty` — enums **estáticos**,
  um por família, com default por nome. Um único enum "variante" dinâmico
  mudaria de significado a cada troca de família, porque o Blender guarda o
  índice, não o nome.
- `show_incompatible: BoolProperty`.
- Ao mudar qualquer um deles: zera o filtro de categoria e marca redraw.
- `is_racing_track` sai da UI e do código; tudo que o lia passa a perguntar a
  `level_types`. Um `.blend` antigo simplesmente ignora a propriedade ao
  carregar.

### Header

- `header_ops.overrides()` (`operators/header.py:51-65`) passa a mesclar
  `level_types.header_overrides(...)` por cima das respostas do painel. O
  `template.document()` já aceita qualquer ponteiro do `LAYOUT`
  (`level_header_template.py:248-250`), então `/boss-race-id` não precisa virar
  um `Choice`.
- No painel *Level Header*, a linha *Race type* vira só um rótulo "set by Level
  Type" — duas fontes de verdade para o mesmo byte é o que não pode existir. O
  picker dos outros campos enum passa a ordenar por valor e a esconder aliases
  de máscara como `RACETYPE_CHALLENGE`.
- Ao escolher um chefe num header autoral, se o autor ainda não respondeu
  `/default-vehicle` e `/avaliable-vehicles`, preenche com o veículo do chefe.
  Nunca sobrescreve uma resposta.
- **Import e remix.** *Import Track* (`io_objects.py:381-383`) chama
  `mode_of(level.race_type)` e grava família, sub-tipo e chefe. Como o par
  volta ao mesmo valor, o header herdado (`pack.py:125`) recebe o override sem
  mudar nada — Horseshoe Gulch continua 3, uma cutscene continua 6 — e um remix
  que troca de modo (uma corrida virando arena) muda o byte certo.
- **Sem modo, sem header.** `/race-type` continua "unanswered" enquanto o modo
  for `NONE`, que é o que o template já defende
  (`level_header_template.py:271-278`: zero é um modo de verdade, não uma
  ausência). O export recusa com "choose the level type first".

### Validação

- `validate.validate()` troca `require_racing_track` por `mode` e `sub`.
- Modo `NONE`: um único erro, "choose the level type first".
- Checkpoints: aviso "sem checkpoints" só em Race, Boss Race e Test Race (o
  retail não tem nenhum nos challenges).
- Special / Cutscene e Menu Backdrop: nenhuma exigência de largada — o jogo nem
  spawna corredores. Menu Backdrop avisa que a geometria não será desenhada.
- Test Race: aviso permanente de que o tipo não salva recordes nem tem time
  trial.
- Grelha: ver a seção 3.
- Tipo incompatível presente (ex.: `EGGCREATOR` numa corrida): **aviso**, com o
  motivo — é o que pega um objeto colocado com "Show incompatible" ligado.

---

## 2. Catálogo: contexto, abas, balões e tooltips

### Visibilidade por modo

Dois ingredientes:

1. **Dados, não gosto.** `generate_catalog.py` passa a registrar, por tipo,
   em que famílias e em que mapa o retail o usa. Hoje `survey_object_maps`
   (`generate_catalog.py:253-294`) percorre os `.gltf` sem saber a que nível
   cada um pertence; o gerador passa a usar `assets.AssetTree.levels()` (que
   já é sem `bpy`) para ligar cada mapa ao seu header. Cada entrada do
   `catalog.json` ganha:

   ```json
   "modes": {"RACE": 340, "BOSS": 87, "CHALLENGE_BATTLE": 32, "CHALLENGE_BANANAS": 25, "CHALLENGE_EGGS": 16},
   "slots": {"structure": 61, "collectables": 439}
   ```

   Chaves opcionais, lidas com `.get` — o `SUPPORTED_SCHEMA` não muda.
2. **Uma regra curta em `level_types.visible(object_type, mode, sub)`:**
   - Tipos das categorias `racing`, `pickups`, `hub`, mais uma lista curta de
     atores/efeitos presos a um modo (`TREASURESUCKER`, `CHARACTERFLAG`,
     `FIREBALLATTRACT`, `PARKWARDEN`, `PIGHEADCOLOURS`, `RANGETRIGGER`), são
     visíveis **onde o retail os usa**.
   - Tipos que o retail só usa em cutscene (`BOOST`) ficam ocultos.
   - Um tipo de jogo que o retail nunca usa fica visível em todo lugar — não
     há prova de incompatibilidade.
   - Todo o resto (cenário, áudio, efeitos, câmera) é sempre visível.
   - Uma tabela `OVERRIDES` escrita à mão para os casos que o dado não prova,
     começando vazia.
   - Em **Special** o filtro não se aplica: é o modo avançado, e as cenas
     retail usam de tudo.

   O resultado é a tabela da seção "Onde cada tipo aparece". Em particular:
   `EGGCREATOR` só em Challenge / Eggs, as portas e placas de hub só em Hub,
   zíperes e moedas de prata/ouro só em corrida, balões de arma em tudo menos
   Hub.

Um checkbox **Show incompatible types** (desligado por padrão) mostra tudo,
marcando os incompatíveis com ícone de aviso. É o que mantém a promessa do addon
de nunca bloquear um valor que o jogo aceita (`catalog.py:208-213`,
`scene.py:201-202`).

### Abas Structure / Collectables

- `layout.prop(settings, "slot", expand=True)` desenha as duas abas no topo do
  painel *Place*.
- **Collectables** = a categoria `pickups` (moedas, bananas, balões, chave,
  Egg Creator); **Structure** = todo o resto. Semântico, porque o jogo não é
  (ver acima), e o dado retail concorda nos pickups.
- A aba escolhida **é** o mapa de destino, como já é hoje: o que se vê é para
  onde vai. O botão *Object map* por objeto (`panels.py:451-459`) continua para
  a exceção.
- Dentro de cada aba, o dropdown *Category* lista só categorias que ainda têm
  tipos visíveis naquela aba e naquele modo, com contagem — e passa a usar
  `_keep` (achado 1).
- O corte em 60 fica; com o filtro, nenhuma combinação real passa disso.

A lista é montada por uma função pura, `level_types.visible_types(catalog,
mode, sub, tab, category, show_all)`, que o painel chama e o teste
exercita sem UI.

### Balões que faltam: presets

Um preset é `(id, rótulo, object_id, campos)`. Os cinco balões:

| Preset | Campos |
|---|---|
| Red Balloon (Missile) | `balloonType = BALLOON_TYPE_MISSILE` |
| Blue Balloon (Boost) | `BALLOON_TYPE_BOOST` |
| **Green Balloon (Trap)** | `BALLOON_TYPE_TRAP` |
| Yellow Balloon (Shield) | `BALLOON_TYPE_SHIELD` |
| **Colored Balloon (Magnet)** | `BALLOON_TYPE_MAGNET` — o arco-íris |

- Definidos em `level_types.py` (ou `presets.py`, também sem `bpy`).
- `DKR_OT_place_object` ganha `preset: StringProperty`; os campos do preset
  sobrescrevem `fresh_fields()` antes de `_assign_free_index`.
- Na aba Collectables os presets substituem a linha genérica "WeaponBalloon", e
  entram na grade *Common* no lugar do `WEAPONBALLOON` de hoje.
- O viewport já mostra a cor certa (`preview.variant_for`).

### Tooltips

- **Por botão, não por operador.** `DKR_OT_place_object` e
  `DKR_OT_select_by_type` ganham `@classmethod description(cls, context,
  properties)`, que o Blender chama para cada botão com as propriedades dele
  (disponível muito antes da 4.2 que o addon exige). O texto vem de:
  1. `data/object_help.json`, escrito à mão em inglês (a língua da UI), uma
     frase por tipo e por preset, começando pelos em destaque e pelos presos a
     um modo;
  2. na falta dela, um texto gerado do catálogo: rótulo, categoria, "used 514
     times in retail races, 7 in banana challenges", "usually in the
     collectables map" e, se for o caso, "not used in Hub levels".
- Todo `EnumProperty` novo tem descrição por item; toda propriedade nova tem
  `description`.
- O operador da grelha descreve o que vai fazer no modo atual ("Place 8 start
  positions in two staggered rows...").
- Os tooltips de campo no painel N já existem (`scene._describe`,
  `scene.py:228-241`) e não mudam.

---

## 3. Grelha de largada

### O que um clique produz

`dkr.generate_start_grid`, no 3D cursor, girado pela rotação Z do cursor
(arredondada para 5,625°, o passo que um `angleY` u8 consegue guardar):

- **Um Empty raiz**, `DKR Start Grid` (ou `DKR Start Grid e2` para a entrada
  2), display `ARROWS` — o eixo Y é "para frente na pista", e o tooltip diz
  isso. Carrega `dkr_grid_root`, `dkr_grid_mode`, `dkr_grid_entrance`, e
  **não** carrega `dkr_id`, então nunca é exportado. Rotação travada em X e Y,
  escala travada (espaçamento se ajusta pelo painel de redo).
- **N filhos `SETUPPOINT`**, criados por `scene.create_empty` como qualquer
  objeto colocado (artwork, `dkr_order`, slot structure — o retail põe 88%
  deles lá), depois parentados com `matrix_parent_inverse` identidade, então a
  `location` local é o template:

| Modo | N | Template local | Yaw local |
|---|---|---|---|
| Race | 8 | a mediana retail acima, × *Spacing* | 0 |
| Boss Race | 2 | (−70, 0), (+70, 0) | 0 |
| Challenge (os três) | 4 | (0, −R), (+R, 0), (0, +R), (−R, 0); R = 1200 | 0°, 90°, 180°, 270° — olhando o centro (+ *Facing Offset*, 45° imita Smokey Castle) |
| Hub | 1 | (0, 0) na próxima `entranceID` livre | 0 |
| Special / Test Race | 8 | como Race | 0 |
| Special / Cutscene, Menu Backdrop | — | botão desabilitado, com o motivo: "no racers are spawned in a cutscene" (`objects.c:1096`) | — |

- `racerIndex` = 0…N−1 na ordem do template, `entranceID` do operador (0 por
  padrão), `vehicle = VEHICLE_NO_OVERRIDE` (no Hub, opcionalmente o veículo do
  header).
- Com geometria na cena, cada filho é derrubado na superfície (opção *Drop To
  Surface*, ligada por padrão) — cada um separadamente, porque uma reta de
  largada pode ser inclinada.
- Hub não estava no pedido; o plano usa 1 por entrada, que é o que os 6 hubs
  retail fazem, e o botão vira *Add Entrance Point*.

### Regenerar em vez de duplicar

- Se já existe raiz para aquela entrada, *Replace* (ligado por padrão) apaga os
  filhos dela e qualquer `SETUPPOINT` solto com o mesmo `entranceID`, e
  **reaproveita a posição e a rotação da raiz**. Trocar de Race para Boss e
  clicar de novo leva a grelha de 8 para 2 no mesmo lugar.
- O painel compara cada raiz com o modo atual e avisa quando não batem ("this
  grid has 8 start positions; a Boss Race uses 2") com um botão *Regenerate*.
- `UNIQUE_FIELDS` (`edit.py:25-28`) ganha
  `"ASSET_OBJECT_SETUPPOINT": ("racerIndex", ("entranceID",))`: um spawner
  colocado à mão também nasce com o próximo índice livre.

### O que precisa mudar fora do operador

Sem isto a raiz é decorativa e o export fica errado:

1. **Ângulo pelo mundo, só quando há pai.** Em `scene.read_object`, o campo de
   ângulo passa a ser `rotation_euler.z` somado ao longo da cadeia de pais.
   Para um objeto sem pai é exatamente a expressão de hoje — o que preserva o
   round trip byte a byte dos mapas retail, onde um ângulo como −410,625° não
   pode virar −50,625°. Pai com rotação fora de Z gera aviso na validação.
2. **`refresh_artwork` recria com o pai** — e deixa de apagar tudo (achado 5):
   montar a lista `(objeto, MapObject, slot, pai)` antes de remover, na mesma
   ordem, e reparentar mantendo o transform.
3. **`drop_to_surface`** escreve `obj.matrix_world.translation`, não
   `obj.location`.
4. **`_clear_existing`** apaga também as raízes de grelha.
5. **Apagar a raiz à mão**: o Blender mantém os filhos no lugar; o painel lista
   spawners soltos daquela entrada para o autor regenerar ou deixar.

### Validação de largada

`_check_setup_points` (`validate.py:303-345`) passa a receber o modo:

- **Erro:** a entrada 0 não tem `racerIndex k` para algum `k < N` —
  "racer k would start at the map origin, facing an undefined direction"
  (`objects.c:1121-1136`).
- **Aviso:** `racerIndex ≥ 8`, que o jogo ignora (`objects.c:1131`).
- **Info:** índices entre N e 7, que o modo não usa.
- A regra de duplicados atual fica. Atenção: Smokey 1 e 2 somam 3 spawners na
  entrada 0 com dois `racerIndex 0` (contando os dois mapas) — qualquer regra
  nova é testada contra os 65 mapas retail no próprio modo antes de virar erro.

---

## Arquivos

| Arquivo | Mudança |
|---|---|
| `dkr_track_editor/level_types.py` | **novo**, sem `bpy`: modos, header, visibilidade, presets, templates |
| `dkr_track_editor/operators/start_grid.py` | **novo**: gerar, regenerar, selecionar grelha |
| `dkr_track_editor/operators/level_type.py` | **novo**: `dkr.set_level_type` (com a confirmação) e a sugestão para cenas antigas |
| `dkr_track_editor/data/object_help.json` | **novo**: tooltips à mão |
| `dkr_track_editor/props.py` | `level_type` (com `NONE`), `challenge_type`, `special_type`, `boss`, `show_incompatible`; `_keep`; sai `is_racing_track` |
| `dkr_track_editor/ui/panels.py` | painel *Level Type* (cartão de primeiro contato, `bl_order = 0`), `poll` dos outros painéis, abas, filtro, presets, subpainel *Start Grid*, header "set by Level Type" |
| `dkr_track_editor/operators/edit.py` | `preset`, `description()`, `UNIQUE_FIELDS`, `refresh_artwork` |
| `dkr_track_editor/scene.py` | ângulo pela cadeia de pais |
| `dkr_track_editor/operators/header.py` | mescla os overrides do modo; picker ordenado por valor, sem aliases de máscara |
| `dkr_track_editor/operators/pack.py`, `checks.py` | validação por modo; override em header herdado |
| `dkr_track_editor/operators/io_objects.py` | import grava família, sub-tipo e chefe via `mode_of`; limpa raízes |
| `dkr_track_editor/operators/geometry.py` | `drop_to_surface` em coordenada de mundo |
| `dkr_track_editor/validate.py` | checkpoints e largada por modo; tipos incompatíveis |
| `dkr_track_editor/catalog.py` | `ObjectType.modes`, `.slots` |
| `generate_catalog.py`, `data/catalog.json` | levantamento por família e por mapa; regenerar |
| `dkr_track_editor/__init__.py` | registrar os operadores novos |
| `run_tests.py` | `test_level_types.py` em `PLAIN_SUITES` |
| `tools/blender/README.md` | seções *Level type*, *Start grid*, abas |

## Testes

**Sem Blender — `tests/test_level_types.py` (novo):**

- `race_type(*mode_of(x)) == x` para os 65 headers retail; Horseshoe Gulch
  cai em Special / Test Race; `RACETYPE_UNK1` e a máscara `RACETYPE_CHALLENGE`
  nunca aparecem entre as opções.
- **Nada que o retail usa fica oculto:** todo objeto de todo mapa retail é
  visível no modo do seu nível. É o teste que impede a tabela de exagerar.
- `EGGCREATOR` visível só em Challenge / Eggs; portas de hub só em Hub.
- Templates: N e índices por modo; o template de corrida, convertido para o
  mapa com um yaw qualquer e medido do jeito que o levantamento mediu, bate com
  a mediana retail — pega erro de eixo ou de sinal; no challenge, cada spawner
  olha para o centro.
- `header_overrides` + `level_header.encode`: byte `0x4C` = 0/8/64/65/66/5/6/7/3
  conforme o par escolhido, byte `0xB8` = o chefe escolhido.
- Validação: mapas sintéticos por modo, e os 65 retail no próprio modo sem
  erro novo.

**No Blender — `tests/test_blender_operators.py`:**

- Registro dos operadores novos.
- Cena nova: só o painel *Level Type* passa no `poll`; depois de
  `dkr.set_level_type`, os outros aparecem.
- `/race-type` continua "unanswered" até o autor escolher (as linhas 1476 e
  1483 seguem valendo) e deixa de ser depois; trocar o modo muda o header.
- `set_level_type` com objetos na cena lista os incompatíveis; *Import Track*
  de Bluey 1 deixa Boss Race / Bluey 1; de Horseshoe Gulch, Special / Test
  Race.
- Preset verde → `balloonType == BALLOON_TYPE_TRAP`; colorido → `MAGNET`.
- `description()` devolve texto específico do tipo.
- Grelha: 8 / 2 / 4 / 1; todos com pai = raiz; índices 0…N−1; girar a raiz 90°
  gira as posições exportadas e soma 90 ao `angleY`; mover a raiz move todos;
  regenerar mantém o transform da raiz; *Refresh Object Artwork* mantém objetos
  e pais (regressão do achado 5); *Drop To Surface* num filho cai no lugar
  certo; *Import Track* não deixa raiz órfã; apagar o spawner 3 dá o erro de
  origem.
- `test_validation` (linhas 189-210) troca `is_racing_track` por `level_type`,
  e `test_dkrmap_export` escolhe um modo antes de exportar — sem modo, o export
  recusa.
- As suítes de round trip não mudam e têm de continuar passando — é a prova de
  que o caminho sem pai ficou intacto.

## Ordem de implementação

Cada passo deixa o addon funcionando e com testes verdes:

1. **Correções que já valem sozinhas:** `_keep` nos enums, *Refresh Object
   Artwork*, *Drop To Surface* em coordenada de mundo, `_clear_existing`.
2. **`level_types.py` + levantamento no `generate_catalog.py`** e
   `catalog.json` regenerado, com `test_level_types.py`.
3. **Interruptor mestre:** o cartão de primeiro contato e o `poll` dos outros
   painéis, `dkr.set_level_type` com a confirmação, propriedades, header
   (incluindo o picker sem a máscara), import, validação por modo; sai
   `is_racing_track`.
4. **Catálogo:** abas, filtro por modo, *Show incompatible*, presets de balão,
   tooltips.
5. **Grelha:** ângulo pela cadeia de pais, templates, operador, subpainel,
   validação de largada.
6. **Docs.**

## Decisões em aberto

As recomendações já estão aplicadas acima; mudar qualquer uma é barato antes do
passo 3.

1. **Challenge com sub-tipo** (Battle / Bananas / Eggs). Necessário para o
   byte do header e para a regra do Egg Creator.
2. **"Colored Balloon" = arco-íris (Magnet).** As cinco cores entram de todo
   jeito.
3. **Hub = 1 spawner por entrada.** Não estava no pedido.
4. **Esconder com escape**, não desabilitar: *Show incompatible types*.
5. **Sem modo até o autor escolher.** Nenhuma família é default; enquanto for
   `NONE`, os outros painéis ficam ocultos, o header não tem `/race-type` e o
   export recusa. (Substitui a primeira versão deste plano, em que Standard
   Race era o default.)
6. **Horseshoe Gulch é Special / Test Race**, ao lado das cenas: era uma
   corrida de teste, e o tooltip diz para não usar. Fica disponível para
   importar e remixar o que já existe, não como caminho recomendado.
7. **`RACETYPE_UNK1` e a máscara `RACETYPE_CHALLENGE` ficam fora de todo
   menu.**

## Riscos

- **Round trip.** O único ponto que toca a exportação de objetos existentes é o
  ângulo; ele só muda para objetos com pai, e as suítes de round trip retail
  provam isso.
- **Quantização do ângulo.** O `angleY` anda de 5,625° em 5,625°; a raiz é
  arredondada ao gerar, senão as posições (contínuas) e as direções
  (arredondadas) divergem até 2,8°.
- **A grelha é uma mediana.** As pistas variam (passo lateral 91–136); o
  *Spacing* do painel de redo cobre isso.
- **Parentesco feito pelo autor.** Alguém pode parentar spawners a outra coisa,
  girada em X ou Y; a validação avisa em vez de exportar um ângulo errado em
  silêncio.
- **Painéis ocultos confundem quem abre um `.blend` antigo.** O cartão explica
  por que o resto sumiu e, quando dá, oferece o botão de sugestão com o modo do
  nível importado.
