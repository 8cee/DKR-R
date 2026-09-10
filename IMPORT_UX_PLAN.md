# Plano: importar uma corrida e já jogar, em HD

## O desejo do usuário

> Um usuário jamais deveria apertar um monte de botões para jogar sua corrida.
> Se ela tem texturas HD, e o addon já exporta as texturas HD separadamente,
> então o usuário deveria conseguir importar a corrida e começar a jogar em HD —
> sem nenhum clique além disso. E sem um milhão de pastas adjacentes aparecendo
> no layout.

Em passos, é isto que tem de ser verdade:

1. O jogador recebe uma corrida — uma pasta (ou um zip) com a pista e o pack HD
   juntos.
2. Um gesto de importar.
3. A corrida aparece numa lista, com um botão de jogar.
4. Esse botão leva à pista, com as texturas HD do autor.
5. Nenhum outro passo: nada de trocar preset, nada de caçar o pack num
   navegador, nada de saber o que é "L+Z".

Estado: **proposta**. Nada abaixo foi implementado. O escopo é **só o lado do
runtime** — o addon já emite tudo o que este plano precisa (ver
[O que já existe e o runtime ignora](#o-que-já-existe-e-o-runtime-ignora)).

---

## O que já funciona hoje

Track Lab (`runtime_ui.cpp:8364`, `DrawTrackLabControls`) já é quase o que se
pede — para uma pista **sem arte própria**:

- **IMPORT A COPY** (`runtime_ui.cpp:8409`) copia uma pasta `.dkrmap` para
  `custom-tracks/` e re-escaneia (`custom_tracks::install`,
  `custom_tracks.cpp:834`).
- **SET WORKING FOLDER** (`runtime_ui.cpp:8376`) aponta para a pasta do
  exportador, lida no lugar — re-exportar *é* a atualização
  (`custom_tracks.hpp:123-131`).
- cada pista instalada ganha um botão **RACE THIS** (`runtime_ui.cpp:8472`) que
  arma `arm_track_override(track.id)`: qualquer corrida que o jogador começar
  cai naquela pista (`custom_tracks.hpp:152-171`).
- **Skip the menus on the next launch** (`runtime_ui.cpp:8491`, `set_auto_boot`)
  pula logos, título, file select e character select e entra direto na pista
  armada (`custom_tracks.hpp:173-188`).

Ou seja: o "um clique para jogar" **já existe**. O que falta é a arte chegar
junto.

---

## O que está no caminho

Três obstáculos entre *RACE THIS* e ver o HD.

### 1. Accurate esconde tudo

Track Lab e Texture Packs só aparecem no preset **Modern**
(`runtime_ui.cpp:8531-8539` e `:8547-8560`, ambos atrás de
`enhancements::modern_presentation_enabled()`). Em Accurate, a seção do Track
Lab mostra "abra a página GRAPHICS e troque Presentation para Modern". É um
desvio de página inteiro antes de começar.

### 2. O pack HD é um artefato manual, num navegador feito para outra coisa

`<track>-hd.zip` sai **ao lado** da `.dkrmap`, de propósito (`HD_TEXTURE_PLAN.md`
§3: o `.dkrmap` é servido byte a byte pelo runtime; um autor pode querer
distribuir a pista sem o pack). Mas hoje instalá-lo é:

- Mods/Hacks > Texture Packs > **Import Texture Pack** (`runtime_ui.cpp:8097`),
  um seletor de arquivo genérico;
- achar o pack numa lista com busca, filtros e ordenação
  (`DrawTexturePackControls`, `runtime_ui.cpp:7917` — feita para packs Rice/RT64
  de terceiros, com centenas de imagens);
- ligar o toggle **Enabled** (`runtime_ui.cpp:8162`).

Três ações, num lugar que não tem relação nenhuma com a pista que as trouxe.
`docs/TEXTURE_PACKS.md` hoje instrui o jogador: *"export and import the two
together."*

### 3. A tabela de texturas é publicada uma vez, no boot

`tex_init_textures` roda uma vez só, de `thread3_main` (`custom_tracks.hpp:63-71`,
`docs/CUSTOM_TRACKS.md` "The texture table is published once"). Uma pista
descoberta depois do boot não tem nenhuma textura própria na tabela publicada —
os ids do modelo dela caem para a textura 0. Isso vale para os 64×32, não só
para o HD: **qualquer** pista com arte própria precisa de um restart depois de
instalada. É o único passo que nenhum desenho elimina — o plano o torna *um*
clique, não zero.

---

## O que já existe e o runtime ignora

A ligação entre a pista e o seu pack **já está nos dados**, e nada no runtime a
lê (grep por `hdTexturePack` e `dkr-r-track.json` em `runtime-recomp/src`: zero
resultados).

- O `manifest.json` dentro da `.dkrmap` carrega (`dkrmap.py:304-311`):

  ```json
  "hdTexturePack": {
    "file": "ancient-lake-remix-hd.zip",
    "textureDigest": "<hex>"
  }
  ```

- O `<track>-hd.zip` carrega um carimbo `dkr-r-track.json` (`rice_pack.py:46`,
  `STAMP_NAME`) com o **mesmo** `textureDigest`.
- `docs/TEXTURE_PACKS.md`: *"The pack's `dkr-r-track.json` and the track's
  `manifest.json` carry the same texture digest... The importer does not compare
  them yet."*

Então o runtime já tem, de graça: **o nome exato** do arquivo do pack, e **um
jeito de confirmar** que aquele pack é daquele export daquela pista. É esse o
gancho de tudo abaixo.

---

## Desenho: "Import Race" é um verbo, não dois sistemas

A regra: os dois arquivos continuam separados no disco — é decisão do
`HD_TEXTURE_PLAN.md` §3 e não se mexe nela. Quem passa a tratá-los como uma
coisa só é o **instalador**, não o formato.

### a. Detectar na hora de instalar

Todo caminho que adiciona uma pista — IMPORT A COPY, SET WORKING FOLDER +
RESCAN, e o zip-drop que ainda falta (`docs/CUSTOM_TRACKS.md`, "Remaining work"
item 1) — passa a ler `manifest.hdTexturePack.file` e procurar esse arquivo
**ao lado** da origem. Achou, e o `dkr-r-track.json` dele bate com
`textureDigest`: é o pack **daquela** pista, não um pack que o jogador vai
navegar.

Nova consulta no módulo, ao lado de `resolved_level_id`:

```cpp
enum class HdPackState { None, Ready, NeedsRestart, Mismatch };
[[nodiscard]] HdPackState hd_pack_state(const std::string& track_id);
```

### b. Instalar calado, marcar como "da pista", ligar

Esse pack entra pelo `texture_packs::import_archive()` que já existe
(`runtime_texture_packs.hpp:59`) e nasce ligado (`set_enabled(id, true)`,
`:61`). O que ele **não** ganha é uma linha no navegador de Texture Packs —
esse navegador é para os packs Rice/RT64 de terceiros que o jogador coleciona,
e um pack que veio junto de uma pista não é uma dessas coisas.

`hidden` (`runtime_texture_packs.hpp:31`) **não** serve para isto: hoje um pack
`hidden` é forçado a desligar (`runtime_texture_packs.cpp:228`, e `:747` —
`info.enabled = !info.hidden && ...`). É um soft-delete — "arquivei, não
apaguei" — não um "ativo mas fora da lista".

O mecanismo certo é novo e pequeno: um marcador de origem no `PackInfo`:

```cpp
enum class Origin { User, TrackPack };
Origin origin = Origin::User;
std::string owner_track_id;   // vazio quando Origin::User
```

O navegador filtra `origin == TrackPack` da lista padrão; o filtro de
visibilidade (`kVisibilityItems`, hoje `"Visible / All / Hidden"`,
`runtime_ui.cpp:7958`) ganha um "Track packs" para auditoria. O pack fica
ligado o tempo todo; some só da vista.

O item da pista no Track Lab ganha **uma linha de status**, não um segundo
painel:

```
 Ancient Lake Remix
 example  -  level 65
 HD textures: restart to load              [ Manage ]
```

- *ready* — pack ligado, tabela já publicada;
- *restart to load* — pack ligado, mas a tabela foi publicada antes desta pista;
- *pack found but doesn't match this export* — digest não bate (ver §d dos
  riscos);
- (sem linha) — a pista não declara `hdTexturePack`, ou o irmão não está na
  pasta.

**Manage** abre o modal de pack único que já existe
(`DrawTexturePackManagementModal`, `runtime_ui.cpp:7786`) — para o curioso, não
para o fluxo normal.

### c. Modern liga-se sozinho, com aviso

Track Lab e o botão de jogar não dependem mais de o jogador achar a página
GRAPHICS. Duas mudanças:

- **Track Lab passa a desenhar em Accurate também** — a lista, o import, o
  RACE THIS. O que não pode acontecer em Accurate é uma custom track
  *carregar* (aí a *"untouched regression baseline"* de `docs/TEXTURE_PACKS.md`
  quebra), e isso continua impossível pelo ponto seguinte.
- **Importar, armar ou "Restart & play in HD" em Accurate troca o preset para
  Modern na hora**, com um aviso: *"Switched to Modern — custom tracks and
  their HD textures need it. Change back in Graphics."* `PresentationProfile` é
  um enum de dois valores (`presentation_policy.hpp:7-9`) aplicado ao vivo; um
  helper novo ali faz a troca e registra o aviso, sem o Track Lab conhecer o
  formato do setting.

A troca é presa às **ações**, não a abrir a seção: ver o Track Lab não muda
nada; clicar num botão que precisa de Modern muda. A baseline fica intacta —
como armar/jogar sempre passa por Modern, nunca se corre uma custom track em
Accurate.

### d. O restart é real — então que seja UM clique, e que ele faça tudo

Por causa do [obstáculo 3](#3-a-tabela-de-texturas-é-publicada-uma-vez-no-boot),
a primeira vez que se instala uma pista com arte própria precisa de restart, e
o plano não promete zero cliques aí. Promete **um**, e esse um faz a cadeia
inteira:

**Restart & play in HD** →

1. arma a pista (`arm_track_override`), se ainda não estiver armada;
2. troca o preset para Modern, se estiver em Accurate (§c), com o aviso;
3. liga o auto-boot (`set_auto_boot`), para cair direto na pista;
4. dispara o restart-no-lugar — o mesmo caminho do L+Z retail
   (`custom_tracks.hpp:180-183`) — sem o jogador ter de saber que L+Z existe.

Todo boot seguinte: zero cliques. Liga o jogo → auto-boot na pista armada →
pack já ligado, fora da lista → joga.

Quando a tabela de texturas já foi publicada com a pista presente (ela já
estava instalada no boot), o passo 4 é dispensável e o botão é só **Play in
HD**: arma, troca o preset se preciso, e o RACE THIS normal serve.

### e. Nenhuma pasta nova no layout

Nada muda em `custom-tracks/` nem no diretório gerenciado dos packs
(`docs/TEXTURE_PACKS.md`, "Storage"). O ponto é que a UI nunca pede para o
jogador abrir, nomear ou escolher entre essas pastas para o pack de uma pista.
Os seletores de sistema continuam só nos dois pontos que **têm** de ser
manuais: qual `.dkrmap` importar da primeira vez, e o navegador de packs de
terceiros.

---

## O fluxo, ponta a ponta (depois do plano)

1. Jogador baixa `ancient-lake-remix/` — contém `ancient-lake-remix.dkrmap/` e
   `ancient-lake-remix-hd.zip`.
2. Track Lab > **IMPORT A COPY** > escolhe a pasta. O instalador copia a pista,
   acha o pack irmão pelo nome do `manifest`, confere o digest, importa-o
   ligado e marcado como `TrackPack` (fora da lista do navegador).
3. A pista aparece na lista: *"Ancient Lake Remix — HD textures: restart to
   load"*.
4. Um clique em **Restart & play in HD**: arma a pista, troca para Modern se
   preciso (com aviso), liga o auto-boot e reinicia no lugar.
5. O jogo reinicia no lugar, entra na pista, desenha o HD.
6. Da próxima vez: liga o jogo, já está lá.

---

## Arquivos

| Arquivo | Mudança |
|---|---|
| `runtime-recomp/src/game/custom_tracks.hpp` / `.cpp` | `install()`/`scan()`/`reload()` leem `manifest.hdTexturePack`, procuram o irmão, conferem `dkr-r-track.json` contra `textureDigest`; nova consulta `hd_pack_state(track_id)`; `install()` passa a aceitar também um zip que embrulha os dois (hoje é pasta-só, `custom_tracks.cpp:846-853`) |
| `runtime-recomp/src/game/runtime_texture_packs.hpp` / `.cpp` | `PackInfo` ganha `origin` + `owner_track_id`; `import_archive` recebe quem é o dono; o navegador filtra `Origin::TrackPack` da lista padrão e ganha o filtro "Track packs"; idempotência por `textureDigest` — um rescan não reimporta o mesmo pack; `delete_managed` chamado quando a pista dona é removida |
| `runtime-recomp/src/game/runtime_ui.cpp` | `DrawTrackLabControls` (`:8364`) passa a desenhar em Accurate; linha de status HD por pista; botão **Manage**; botão único **Restart & play in HD** / **Play in HD** (arma + troca preset + auto-boot + restart); `ImportTrackWithDialog` (`:8311`) aceita pasta-mãe ou zip e troca o preset se preciso; o gate `modern_presentation_enabled()` em `:8547-8560` sai do Track Lab (continua no navegador de packs de terceiros e no CRT) |
| `runtime-recomp/src/game/presentation_policy.hpp` | helper "set Modern + registrar aviso", chamável do Track Lab e do instalador |
| `docs/CUSTOM_TRACKS.md`, `docs/TEXTURE_PACKS.md` | o fluxo novo; *"import the two together"* deixa de ser instrução ao jogador |
| `tools/blender/README.md`, `HOW-TO-BUILD.md` gerado no export | descrever "importe a pasta, um clique, joga" |

---

## O que este plano não resolve

- **O primeiro restart.** Limite de `tex_init_textures` publicar a tabela uma
  vez. Some só se a tabela de texturas passar a ser reconstruível pós-boot —
  outro documento, outro orçamento de risco.
- **Digest que não bate.** Hoje é silencioso (`HD_TEXTURE_PLAN.md`,
  "Implementação", §7 lado runtime). O plano troca por uma linha de status; não
  por reconciliação automática. O conserto é re-exportar ou baixar o par certo,
  e é o autor/distribuidor quem faz.
- **Remover uma pista.** Não existe hoje (`custom_tracks` só tem
  enable/disable, `custom_tracks.hpp:141`). Quando existir, tem de apagar
  (`texture_packs::delete_managed`, `runtime_texture_packs.hpp:64`) o pack
  `TrackPack` dela junto, senão fica um pack ligado órfão. Dependência anotada,
  não resolvida aqui.
- **Online / Accurate.** Custom track é Modern-only por política
  (`docs/CUSTOM_TRACKS.md`, "Remaining work" item 3); nada aqui muda isso.

---

## Riscos

- **Troca de preset automática.** Quem está em Accurate de propósito e importa
  ou arma uma custom track é levado para Modern sem pedir. Aceitável porque
  (a) custom track já é Modern-only por política e nunca carregaria em Accurate
  de qualquer jeito, (b) o aviso diz o que mudou e como voltar, (c) a troca é
  ao vivo e reversível num clique. O que **não** pode: trocar ao só abrir a
  seção, ou trocar calado.
- **Pack de pista é pack esquecido.** Fora da lista padrão, um jogador com
  muitas pistas HD acumula packs sem os ver. Mitigação: o filtro "Track packs"
  no navegador (o `visibility_filter` já existe, `runtime_ui.cpp:8024`), a
  linha de status na pista, e a limpeza automática quando a pista dona é
  removida (quando "remover pista" existir).
- **Idempotência.** Um rescan a cada save do editor (o loop de autoria) não
  pode reimportar o pack toda vez. A chave é o `textureDigest`: mesmo digest,
  mesmo pack instalado, o rescan não faz nada.
- **Dois formatos de distribuição.** "Zip que embrulha os dois" e "dois irmãos
  soltos numa pasta" são coisas diferentes; o instalador tem de aceitar ambos e
  o `HOW-TO-BUILD.md` tem de dizer qual o exportador produz.
- **`install()` copia; working folder lê no lugar.** No modo working folder o
  pack não é copiado — é importado da pasta do exportador. Um novo export
  reescreve o `-hd.zip`; o rescan tem de detectar o digest novo e substituir o
  pack, não acumular.

---

## Decisões

Tomadas (2026-09-10):

1. **Modern liga-se sozinho, com aviso** — não um clique consciente. A troca é
   presa às ações que precisam de Modern (importar, armar, jogar), não a abrir
   a seção.
2. **Digest que não bate = linha de status + a pista joga em 64×32.** Não
   recusa a pista.
3. **Um botão só faz a cadeia inteira** — arma, troca preset, liga auto-boot,
   reinicia.

Em aberto (baratas de mudar antes de começar):

4. **Detecção no install, não também no RACE THIS.** Detectar o pack também no
   momento de armar cobriria a pista e o pack chegando em momentos diferentes
   (baixou a pista, depois o pack); barato de somar depois.
5. **Pack de pista sai da lista padrão do navegador por `origin`, não por
   `hidden`** — gerenciável pelo Track Lab, visível no filtro "Track packs".
   Alternativa: deixá-lo na lista com uma tag — nada some, mas polui a lista de
   quem tem muitas pistas.
