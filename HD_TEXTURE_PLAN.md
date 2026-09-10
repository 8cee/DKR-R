# Plano: a textura de uma pista custom em alta resolução

## O desejo do usuário

Este é o objetivo de tudo o que segue, nas palavras de quem pediu:

> Fiz minha pista. Dei `Ctrl+J` pra dar merge em tudo. Cliquei pra fazer pista
> a partir da track. As texturas permaneceram. Exportei pro DKR-R. Funcionou.

Em passos, é isso que tem de ser verdade:

1. O autor faz a pista no Blender, com materiais texturizados.
2. `Ctrl+J` junta tudo numa malha só.
3. Um clique em **Track From Mesh**.
4. **As texturas permanecem** — na tela e no arquivo.
5. Export para o DKR-R.
6. A pista funciona no jogo, com as texturas do autor.

Hoje os passos 1-3 e 5-6 já funcionam; **o 4 falha** — a conversão descarta as
texturas. As duas metades deste documento servem esse desejo:

- a extensão *"fazer a conversão no próprio Track From Mesh"* torna o passo 4
  verdadeiro, com as texturas reduzidas a 64×32;
- o pack HD, que é o corpo original do plano, faz essas texturas aparecerem no
  jogo na resolução em que o autor as fez.

Qualquer decisão abaixo que conflite com este fluxo perde para ele.

---

Quando um autor traz uma imagem para a sua pista, o `.dkrmap` leva uma versão de
**64×32**. Não é escolha do addon: a RDP tem 4 KiB de TMEM e `material_init`
carrega a textura de nível como um bloco único, então 2048 texels é o teto de um
formato de 16 bits. Uma foto de 2752×1536 tem 4,2 milhões.

Este plano descreve como fazer o jogo **desenhar a imagem original** mesmo assim,
sem mexer em nada do que já funciona: o addon emite, junto do `.dkrmap`, um
texture pack Rice cuja identidade é a da textura reduzida que ele acabou de
gerar. O jogo carrega os 64×32; o RT64 troca pela imagem cheia na hora de
desenhar.

Estado: **implementado no addon** (2026-09-10), com a verificação 4a feita e a
4b — carregar no jogo — pendente. O que foi feito, o que foi medido e o que o
código mostrou de diferente do texto abaixo está em
[Implementação](#implementação-2026-09-10), no fim.

---

## Por que isso é possível, e por que é seguro

A identidade que o RT64 usa para decidir uma substituição é **função pura** dos
bytes da textura mais quatro números. O patch
`patches/rt64/0011-enable-runtime-rice-texture-aliases.patch` a calcula assim:

```cpp
const uint32_t textureCRC = riceCRC32(textureBytes, width, height,
                                      drawTile.siz, bytesPerRow);
std::snprintf(identityBuffer, sizeof(identityBuffer),
              "%08x#%u#%u", textureCRC, drawTile.fmt, drawTile.siz);
```

O addon tem exatamente esses insumos — acabou de escrevê-los em
`textures/N.bin`. Então pode calcular a mesma identidade offline.

**A objeção usual a texture packs não se aplica aqui.** Packs substituem
globalmente, por hash, e por isso são a ferramenta errada para "mudar uma
textura só nesta pista". Mas a textura que este pack substitui é uma que o addon
*inventou*: ela não existe em nenhum outro lugar da ROM. Substituí-la
globalmente atinge só a pista que a trouxe.

**Falha de forma limpa.** Se o hash não bater, o RT64 simplesmente não acha
substituição e o jogo desenha os 64×32. Não corrompe geometria, não trava, não
deixa a pista em estado inválido. Isso é o que torna o risco desta feature
aceitável.

---

## O que já está pronto no repositório

Nada disto precisa ser escrito:

| peça | onde |
|---|---|
| `riceCRC32`, `reverseDXT`, `txl2Words` | `patches/rt64/0011-...patch` |
| `native_alias` (FNV-1a + finalizador murmur, domínio `dkr-r:rice:`) | `runtime-recomp/src/game/rice_texture_pack_policy.hpp` |
| `valid_identity`, `parse_filename` | idem |
| Importação, conversão Rice→nativo, UI | `runtime_rice_texture_import.cpp`, Graphics > Custom Texture Packs |
| Geração da textura 64×32 | `tools/blender/dkr_track_editor/textures.py` |

O trabalho é **só o lado do addon**, mais a verificação. O runtime não muda.

---

## O formato exato que o addon precisa produzir

Levantado da fonte, não de memória.

### A identidade

```
<crc>#<fmt>#<siz>
```

- `crc` — 8 dígitos hexadecimais minúsculos, `riceCRC32` sobre os bytes da imagem
- `fmt` — `G_IM_FMT_*` do tile: RGBA=0, YUV=1, CI=2, IA=3, I=4
- `siz` — `G_IM_SIZ_*`: 4b=0, 8b=1, 16b=2, 32b=3

`valid_identity` aceita 3 ou 4 componentes (o quarto é o CRC da paleta, só para
CI). Como texturas custom **não podem ser CI** — a paleta viria de
`ASSET_EMPTY_14`, que uma pista não pode estender — sempre serão 3.

Mapeamento a partir de `FORMAT_CODES` do addon:

| formato | fmt | siz |
|---|---|---|
| RGBA32 | 0 | 3 |
| RGBA16 | 0 | 2 |
| IA16 | 3 | 2 |
| IA8 | 3 | 1 |
| IA4 | 3 | 0 |
| I8 | 4 | 1 |
| I4 | 4 | 0 |

### O CRC

```cpp
uint32_t riceCRC32(const uint8_t *source, int width, int height,
                   int size, int rowStride) {
    uint32_t result = 0;
    const int bytesPerLine = width << size >> 1;
    for (int y = height - 1; y >= 0; y--) {          // de baixo para cima
        uint32_t value = 0;
        for (int x = bytesPerLine - 4; x >= 0; x -= 4) {
            std::memcpy(&value, source + x, sizeof(value));   // little endian!
            value ^= uint32_t(x);
            result = (result << 4) + ((result >> 28) & 15);
            result += value;
        }
        value ^= uint32_t(y);
        result += value;
        source += rowStride;
    }
    return result;
}
```

Três armadilhas para a transcrição em Python:

1. **`memcpy` de 4 bytes é little-endian** na máquina onde roda. Os bytes da
   textura são big-endian (N64), mas o CRC os lê como palavra nativa. A
   transcrição tem de usar `int.from_bytes(..., "little")`.
2. **Aritmética é `uint32` com wraparound.** Toda soma precisa de `& 0xFFFFFFFF`.
3. **As linhas são percorridas de baixo para cima**, e dentro de cada linha da
   direita para a esquerda, em passos de 4.

Para o nosso caso `rowStride == bytesPerLine` (o bloco é contíguo, sem folga),
o que simplifica: é a imagem inteira, linha a linha, sem buracos.

### O nome do arquivo

`parse_filename` ignora tudo antes do primeiro `#` e derruba para minúsculas:

```
Diddy Kong Racing#<identidade>_all.png
```

O sufixo decide como o alfa é lido:

- `_all` — RGBA completo numa imagem só. **É o que devemos emitir.**
- `_rgb` + `_a` — cor e alfa separados, o alfa vindo do canal vermelho
- `_rgb` sozinho — tratado como opaco

### O pacote

Um `.zip` com os PNGs na raiz (ou dentro de um único diretório). A importação
converte para um diretório nativo gerenciado e gera o `rt64.json` sozinha —
o addon **não** precisa escrever JSON nem calcular `native_alias`.

---

## Trabalho, em ordem

### 1. `rice_identity.py` — o cálculo, livre de `bpy`

Novo módulo em `tools/blender/dkr_track_editor/`, no mesmo espírito de
`textures.py`: aritmética pura do formato, testável sem Blender.

```python
def rice_crc32(texels, width, height, siz) -> int
def rice_identity(texels, width, height, texture_format) -> str
def tile_format(texture_format) -> tuple[int, int]   # (fmt, siz)
```

Entrada: os bytes que `encode_texels` já produz. Nada mais.

### 2. `rice_pack.py` — montar o `.zip`

```python
def write_pack(path, entries) -> str
```

Cada entrada é `(identidade, imagem_original)`. Escreve
`Diddy Kong Racing#<id>_all.png` para cada uma. A imagem original é a que o
autor escolheu, **antes** da redução — que hoje o addon guarda apenas como
`source` (uma anotação de procedência, nunca lida).

Isto obriga uma mudança pequena em `operators/custom_textures.py`: guardar
também uma cópia em resolução cheia, como PNG, ao lado da reduzida. Sem isso
o pack não pode ser reconstruído a partir do `.blend` — que é a propriedade que
o resto do addon mantém com cuidado.

### 3. Emissão no export

Em `operators/pack.py`, depois de `_encode_textures`, escrever
`<track>-hd.zip` **ao lado** do `.dkrmap`, não dentro dele. Motivos:

- o `.dkrmap` é servido byte a byte pelo runtime; um zip dentro dele seria
  carga morta
- packs e pistas são instalados por caminhos diferentes na UI
- um autor pode querer distribuir a pista sem o pack

O relatório do export deve dizer as duas coisas em uma linha, e o
`HOW-TO-BUILD.md` ganha uma seção com o passo de importar o pack.

### 4. Verificação — a parte que decide se isto funciona

Duas provas independentes. **A segunda é a que importa.**

**a) A transcrição está certa.** Compilar `riceCRC32` do patch como um
executável pequeno com MSVC (o mesmo padrão já usado nesta sessão para
`custom_tracks.cpp`), rodar sobre alguns milhares de buffers pseudoaleatórios de
tamanhos e formatos variados, e exigir igualdade com a versão Python. Isto prova
a aritmética, e nada além dela.

**b) Os campos derivados estão certos.** Esta é a única que prova a feature, e
não pode ser feita offline: `width`, `height`, `siz`, `fmt` e `bytesPerRow` no
cálculo ao vivo saem do `LoadOperation` e do `drawTile`, montados por
`gDPLoadTextureBlock` dentro de `material_init`. Minha leitura é que para um
bloco de textura completa eles coincidem com as dimensões próprias da textura e
`bytesPerRow == width << siz >> 1` — **mas isso é dedução, não medição.**

O jeito de medir: carregar a pista de demonstração no jogo com um log das
identidades calculadas ao vivo, e comparar com a que o addon escreveu. Se
baterem, a feature está provada de ponta a ponta. Se não, a diferença aponta
exatamente qual campo foi deduzido errado.

Se o runtime ainda não registra a identidade calculada, adicionar esse log é
pré-requisito da verificação — e é útil por si só para depurar packs.

### 5. Documentação

- `docs/TEXTURE_PACKS.md` — uma seção sobre packs gerados por pista
- `tools/blender/README.md` — o passo extra no fluxo
- `docs/CUSTOM_TRACKS.md` — nota em "A track's own artwork" apontando para cá

---

## O que este plano deliberadamente não faz

- **Não muda o `.dkrmap`.** A pista continua carregando e desenhando sem o pack.
- **Não mexe no runtime**, além possivelmente do log de verificação.
- **Não tenta cobrir texturas da ROM.** Se o autor escolher uma das 1401, ela
  fica na resolução dela; substituí-la seria global de verdade, e aí a objecção
  volta a valer.
- **Não tenta CI4/CI8.** A identidade ganharia um quarto componente (CRC da
  paleta) e uma pista não pode adicionar paletas.

---

## Riscos, do maior para o menor

1. **Os campos derivados não baterem** (passo 4b). É o risco central. Mitigação:
   medir antes de construir o resto — o passo 4b pode ser feito primeiro, à mão,
   com a pista `leaked-road` que já existe.
2. **Preset.** Packs valem no Modern; o Accurate sempre usa as texturas
   originais, por design. A pista fica correta nos dois, em resoluções
   diferentes.
3. **Colisão de identidade.** Duas texturas custom com os mesmos bytes geram a
   mesma identidade — o que é correto (são a mesma textura), mas se tiverem
   originais HD diferentes, uma vence. O export deve detectar e avisar.
4. **Tamanho.** O pack carrega as imagens originais; um autor com vinte fotos
   de 4 MB gera um zip de 80 MB. Vale avisar, não impedir.

---

## Esforço

O grosso é o passo 4. Os passos 1-3 são pequenos e mecânicos; o cálculo tem umas
quarenta linhas e o zip umas vinte.

**Sugestão de ordem:** fazer o 4b primeiro, à mão, sobre a `leaked-road` que já
está instalada. Se a identidade que o addon calcularia bater com a que o jogo
calcula, o resto é trabalho previsível. Se não bater, descobrimos isso em uma
tarde em vez de depois de construir tudo.

---

## Revisão da proposta (2026-09-10)

Lida contra `0011-enable-runtime-rice-texture-aliases.patch` e `textures.py`, não
contra a memória. A ideia central se sustenta — a identidade é calculável
offline, e a justificativa de por que um pack global é seguro aqui está certa.
O que segue são três erros no texto acima, um bug que o plano herdaria, e quatro
coisas que o melhoram.

### 1. A ordem das linhas está descrita ao contrário

A armadilha 3 diz "as linhas são percorridas de baixo para cima". Não são. No
laço, `y` **conta para trás** mas `source` **avança**:

```cpp
for (int y = height - 1; y >= 0; y--) {
    ...
    source += rowStride;     // para a FRENTE
}
```

A memória é lida da primeira linha para a última, na ordem em que está; o que
decresce é só o número XORado ao fim de cada linha. A primeira linha da imagem
é combinada com `y == height-1`.

Uma transcrição que siga a armadilha como está escrita vai inverter as linhas e
produzir um CRC diferente — e, pior, um CRC *plausível*, que só falha na hora de
casar no jogo. Como a armadilha 3 é exatamente a instrução que o transcritor vai
seguir, ela é hoje o defeito mais provável de todo o plano.

**Redação correta:** as linhas são lidas em ordem de memória; dentro de cada
linha, da direita para a esquerda em passos de 4; o índice da linha entra
invertido.

### 2. `rowStride == bytesPerLine` não vale por contiguidade

O texto justifica a simplificação dizendo que "o bloco é contíguo, sem folga".
Não é assim que o `bytesPerRow` é obtido. Para um load do tipo `Block` — que é o
que `gDPLoadTextureBlock` emite — o patch tem três caminhos, e nenhum deles é a
largura da textura:

```cpp
if (drawTile.siz == G_IM_SIZ_32b)  bytesPerRow = drawTile.line << 4;
else if (loadOp.tile.lrt == 0)     bytesPerRow = drawTile.line << 3;
else { dxt = reverseDXT(loadOp.tile.lrt, ...); bytesPerRow = dxt << 3; }
```

O caminho normal de um RGBA16 é o terceiro: `bytesPerRow` sai do **DXT**, o
recíproco arredondado que o `gDPLoadTextureBlock` guarda, revertido por busca.

A igualdade **vale mesmo assim**, e vale por um motivo melhor do que o alegado:
`check_size` só aceita potências de dois até 64, e para essas `txl2Words` é
exata, então `reverseDXT` devolve o número de words da linha e
`bytesPerRow == width << siz >> 1` sai idêntico. Para 64×32 RGBA16: 128 bytes =
16 words → dxt reverte para 16 → `16 << 3 == 128`. ✔

Isso muda o plano para melhor: **o argumento é estático, não precisa de
medição.** Mas ele depende de uma invariante do addon (potência de dois ≤ 64),
não da natureza do bloco — e por isso merece um teste que amarre as duas coisas,
não um comentário.

### 3. `width` e `height` não são os da textura

O trecho que o plano não cita é onde mora o risco 4b de verdade:

```cpp
width  = (clampS && tileWidth <= 256) ? min(maskWidth, tileWidth) : maskWidth;
height = ((clampT && tileHeight <= 256) || maskHeight > 256)
       ? min(maskHeight, tileHeight) : maskHeight;
```

Ou seja: o retângulo que entra no CRC sai de `masks`/`maskt` e dos bits de clamp
do tile — que por sua vez saem dos **flags de wrap que o próprio addon escreve
no `TextureHeader`**. Não das dimensões da imagem.

Na prática coincidem, porque o addon escreve o mask a partir do tamanho. Mas a
consequência é que a identidade depende de um campo que hoje ninguém trata como
tendo efeito observável. Se alguém mudar a política de wrap em `texture_header`,
todos os packs já distribuídos param de casar, silenciosamente.

**Isso pertence ao plano como uma invariante declarada em `textures.py`**, ao
lado de `MAX_WRAP_SIZE`, e não como uma dedução no documento.

### 4. Um bug que o plano herdaria: textura de 4 de largura em 4 bits

`usable_sizes` aceita de 4 a 64 nos dois lados. Para I4/IA4 com largura 4:

```
bytesPerLine = 4 << 0 >> 1 = 2
for (x = 2 - 4 = -2; x >= 0; x -= 4)   // nunca executa
```

O laço interno não roda uma vez sequer. O CRC vira a soma dos `y` — **função só
da altura, independente de todo pixel**. Toda textura 4×N de 4 bits colide com
toda outra da mesma altura.

Não é um problema do RT64 (lá isso nunca acontece com textura de ROM); é um
problema de o addon poder gerar essas. O passo 1 deve **recusar** emitir
identidade quando `bytesPerLine < 4`, e o export deve dizer que aquela textura
não terá versão HD. Uma linha, mas é a diferença entre "sem HD" e "a textura
errada aparece na pista".

### 5. Melhoria: emitir identidades candidatas em vez de apostar numa

O risco 1 do plano ("os campos derivados não baterem") é tratado como algo a
medir no jogo. Dá para quase eliminá-lo: um pack é um diretório indexado por
identidade, e **escrever entradas a mais é grátis em risco** — as que não casam
ficam mortas.

Então, para cada textura, emitir a mesma PNG HD sob as poucas identidades que as
derivações plausíveis produzem (mask *vs* tile para o retângulo; `drawTile.line`
*vs* DXT para o stride). Seja qual for a que o jogo calcular, ela existe.

Isso troca "provar antes de construir" por "cobrir e depois estreitar". O custo
é PNG duplicada no zip; vale atrás de um flag, ligado só até a medição existir.

**Cuidado com o que isso *não* dá de graça:** o `rt64.json` é escrito na
importação (`runtime_rice_texture_import.cpp`), a partir dos arquivos presentes
— é um banco de substituições, não um registro do que foi usado em cena. E o
patch 0012 só guarda um contador de geração para invalidar cache, não a decisão.
Então cobrir o espaço faz a pista **aparecer certa**, mas não diz qual derivação
venceu.

Diz, se as candidatas forem distinguíveis a olho: emitir cada candidata com a
mesma imagem HD tingida de uma cor chapada diferente, carregar a pista uma vez e
olhar a tela. A cor identifica a derivação sem tocar no runtime. Feita a leitura,
fixa-se a derivação e o flag cai. É o passo 4b do plano, custando uma tarde e
nenhum código de log.

Se isso for adotado, o passo 4b deixa de ser pré-requisito e vira confirmação.

### 6. Melhoria: colisão de identidade dá para corrigir, não só avisar

O risco 3 propõe detectar e avisar. Mas a identidade é função pura de bytes que
**o addon produz**: duas texturas reduzidas idênticas com HD diferentes podem
ser separadas invertendo o bit menos significativo de um texel de uma delas.
Num 64×32 isso é invisível, e transforma um aviso que o autor não sabe resolver
numa não-ocorrência.

### 7. Falta uma invariante: o pack e o `.dkrmap` saem juntos

A identidade é o hash da saída do nosso próprio pipeline com perdas. Os dois
lados hoje são consistentes por construção — ambos leem a PNG reduzida que já
está no disco — mas nada impede um autor de distribuir um pack de um export e o
`.dkrmap` de outro, depois de ter reimportado a imagem. O resultado é silencioso:
o jogo desenha 64×32 e ninguém sabe por quê.

Barato de resolver: carimbar o mesmo identificador de build no `manifest.json` e
num arquivo do zip, e a UI de importação avisar quando não bate.

### 8. Nota sobre o alfa que o `_all` não cobre

RGBA16 carrega **1 bit** de alfa; a PNG HD carrega 8. O render mode e o combiner
foram escolhidos para o original de 1 bit. Uma substituição com alfa suave pode
desenhar diferente do que o thumbnail do addon mostra — não é defeito, mas é a
primeira coisa que um autor vai reportar como bug. Merece uma linha em
`docs/TEXTURE_PACKS.md`.

### Ordem que eu sugeriria em vez da atual

1. §4 (a guarda dos 4 bytes) e §1 (a redação da armadilha) — antes de qualquer
   código, porque os dois são erros que se propagam para dentro da transcrição.
2. Passo 1 + verificação 4a, com o teste amarrando também a invariante do §2.
3. Passo 2/3 com as identidades candidatas do §5 ligadas.
4. Carregar a pista uma vez e ler do `rt64.json` qual candidata casou. Aí
   desligar o flag e fixar a derivação.

O 4b continua sendo o passo que decide a feature — mas com o §5 ele deixa de ser
um bloqueio no início e vira uma leitura no fim.

---

## Extensão: fazer a conversão no próprio *Track From Mesh*

Pedido: ao clicar em converter a malha para DKR, as texturas dos materiais já
deveriam virar texturas da pista, sem passo manual depois.

Isso fecha o fluxo que este documento existe para servir. Hoje o autor tem uma
malha texturizada, converte, recebe uma pista **sem textura nenhuma**, e só
então escolhe imagem por imagem — e é depois disso tudo que o pack HD entra.
Com a conversão automática, "converter" passa a significar o que diz: entra uma
malha texturizada, sai uma pista que desenha aquela arte, e o pack devolve a
resolução que os 64×32 jogaram fora.

### O fluxo que tem de funcionar (requisito)

Este é o desejo do usuário, registrado no topo do documento, e é o critério de aceite da extensão:

1. Faço a pista no Blender, com materiais texturizados.
2. `Ctrl+J` para juntar tudo numa malha só.
3. Clico em **Track From Mesh**.
4. **As texturas permanecem** — na tela e no arquivo.
5. Exporto para o DKR-R.
6. Funciona no jogo.

Hoje o passo 4 falha: a pista sai sem nenhuma das texturas. Os passos 1-3 e 5-6
já funcionam; o que falta é só o 4, e a próxima seção diz exatamente onde.

### Onde isso encaixa — é uma função, não um subsistema

A costura já existe. `read_source_mesh` percorre os polígonos da malha de origem
com o material e a UV **na mão**, antes de qualquer triangulação, e delega a um
único ponto:

```python
def _texture_for(material, slot: int, count: int) -> int:
    """Which entry of the starting texture table a material draws.
    ...
    A material an author made does not, so it falls back to its slot position -
    which is arbitrary...
    """
```

A mudança é o *fallback* dessa função: em vez de devolver a posição do slot,
importar a imagem do material como textura própria da pista e devolver o índice
da entrada que ela ganhou. Nada mais precisa mudar, porque `_raw_uv` já divide
pelo tamanho da textura escolhida:

```python
int(round(u * level_model.UV_FRACTIONAL_BITS * texture.width))
```

Ou seja, escolhida a textura certa, **a UV do autor já sai correta de graça**.

Mas não é o único ponto a mudar. A leitura do código achou **três** lugares
onde a textura se perde — ver a seção seguinte.

Vale marcar o contraste com o protótipo que já existe,
`tools/blender/apply_material_textures.py` (testado headless, transferência
exata). Ele precisa de BVH e casamento por centróide porque roda *depois* — a
conversão já triangulou e re-dividiu, e a correspondência polígono→polígono foi
destruída. Dentro do operador essa correspondência ainda está viva. **O caminho
automático é mais exato e mais simples que o manual, não menos.**

O script continua útil, e não vira redundante: ele serve o caso de retexturizar
geometria que já existe, onde o momento da conversão passou.

### Onde a textura se perde hoje (lido no código, 2026-09-10)

1. **No arquivo — `new_track._texture_for`.** Nunca olha a imagem do material.
   Sem donor devolve `NO_TEXTURE`; com donor devolve a posição do slot na tabela
   do donor. É aqui que a textura some do `-geometry.bin`.
2. **Na tela — `geometry._build_geometry`.** Depois de escrever o modelo, a
   conversão o reimporta, e o PNG de cada entrada vem de
   `tree.texture_3d_png(id)`, que só conhece a ROM e devolve `None` para um id
   próprio da pista (`0x7000+`). Mesmo com o ponto 1 corrigido, a pista
   apareceria **sem imagem no viewport** — o autor veria "descartou" com o
   arquivo certo. Este é o mais traiçoeiro dos três.
3. **No export — `pack._encode_textures`.** A checagem que impede exportar uma
   textura pendurada só varre `extra_textures`. Com o ponto 1, as texturas
   próprias passam a morar na tabela **base** do modelo, e a checagem tem de
   cobrir as duas, ou uma imagem apagada do disco só aparece como defeito no
   jogo.

### Mudanças, uma por ponto

- `operators/custom_textures.py` — extrair o miolo do operador *Add Custom
  Texture* (reamostrar, validar pelo encoder, gravar o registro) numa função
  `add_image(context, source, formato, tamanho)`. O botão e a conversão passam a
  usar a mesma, em vez de a conversão ter uma segunda cópia.
- `operators/new_track.py` — antes de `read_source_mesh`, varrer os materiais
  que têm imagem e não têm `dkr_texture_index`; importar cada imagem uma vez
  (duas materiais com o mesmo arquivo dão uma textura); anexar um
  `TextureRef(custom_id, w, h, formato, superfície)` à tabela inicial; e fazer
  `_texture_for` consultar esse mapa antes do fallback. `blank_model` →
  `rebuild` já acerta `texture_count_field`, e `_raw_uv` já usa o tamanho certo.
  Formato e tamanho vêm de `custom_format`/`custom_size` da cena — a mesma
  escolha que o botão lembra.
- `operators/geometry.py` — em `_build_geometry`, um id próprio resolve por
  `custom_textures.by_id` antes de perguntar à árvore da ROM.
- `operators/pack.py` — a checagem de textura pendurada passa a varrer base e
  extras.
- Os dois operadores de conversão ganham a opção **Manter as texturas da
  malha**, ligada por padrão.

### Uma armadilha do próprio fluxo: o `Ctrl+J`

Juntar objetos casa as camadas de UV **pelo nome**. Se as peças da pista tinham
mapas com nomes diferentes (`UVMap` num, `UVMap.001` noutro), a malha junta fica
com mais de uma camada, e `read_source_mesh` só lê a ativa — parte da pista
perde o mapeamento sem erro nenhum. A conversão deve avisar quando a malha tem
mais de uma camada de UV, dizendo quantas faces ficariam sem mapa.

### Teste

O teste atual de `track_from_mesh_blank` (`test_blender_operators.py`, "every
face is untextured until the author picks one") usa uma grade **sem materiais**,
então continua valendo como está. Falta o caso novo: grade com dois materiais de
imagem → *Track From Mesh* → duas entradas próprias na tabela, UV de cada canto
igual ao unwrap, material com imagem no viewport, export termina. O roteiro de
teste headless usado para validar `apply_material_textures.py` já é quase
exatamente isso.

### O que isto contraria, e por isso não pode ser silencioso

O docstring acima não é omissão, é decisão: *"the author picks the textures
afterwards, in the Textures panel, where the whole ROM is available rather than
one track's table."* Uma malha com materiais sem imagem continua devendo sair
sem textura — esse raciocínio segue válido para ela.

Então: **opção no operador**, ligada quando a malha de origem tem materiais com
imagem e sem efeito quando não tem. Não uma troca de comportamento por baixo.

### O que a conversão automática não pode adivinhar

O tipo de superfície. Um material diz qual é a imagem, não se aquilo é asfalto,
grama ou gelo — e isso é um byte na entrada da tabela, não no triângulo. Tudo
entra no padrão e o autor ajusta no painel Surface depois. O relatório do
operador deve dizer isso em uma linha, senão o autor descobre dirigindo.

### Limites que o operador tem de reportar em vez de estourar

- **255 texturas próprias** (`CUSTOM_ID_COUNT`) e o teto da tabela do modelo
  (`MAX_TEXTURES`). Uma malha importada de outro jogo passa dos dois com
  facilidade. Ao bater no teto: parar, dizer quantos materiais ficaram de fora e
  quais, e deixar a pista válida — nunca meio convertida.
- **`.blend` não salvo.** As PNGs reduzidas são escritas ao lado dele. Sem
  arquivo, a conversão automática tem de se recusar e pedir para salvar, não
  escrever no temporário.
- **A guarda do §4** vale aqui também: material cujo tamanho escolhido dê
  `bytesPerLine < 4` entra como textura normal, mas fica marcado como sem versão
  HD possível.
- **Custo.** Quarenta materiais são quarenta reamostragens dentro de um clique.
  Vale reportar progresso; não vale bloquear.

### Efeito sobre este plano

Passa a existir um caminho de um clique da malha texturizada até a pista, e o
pack HD deixa de ser um extra para virar a segunda metade óbvia dele. Sugiro que
o `HOW-TO-BUILD.md` gerado no export passe a descrever os dois na mesma ordem em
que o autor os viveu: converteu, exportou, importou o pack.

---

## Extensão maior: a mesma ideia para a malha

Pedido: uma malha que estoure os limites do N64 levaria as duas versões ao mesmo
tempo — a reduzida e a de alta — e, se todas acabarem reduzidas, não se perdeu
nada: foi só uma conversão de malha como hoje.

O argumento de degradação está certo e é o mesmo que torna o pack de textura
aceitável: sem a metade de alta, o resultado é exatamente o comportamento atual.
Isso deve ficar registrado como a razão pela qual o risco é tolerável.

**Mas o mecanismo não é o mesmo, e é aí que a analogia engana.**

### Para textura, o RT64 é a única saída. Para malha, ele não entra

O teto de 2048 texels é a TMEM da RDP — hardware, que o recomp continua
emulando fielmente no nível da RDP. Nada do lado do jogo contorna isso; por isso
a substituição tem de acontecer no renderizador, por hash, e por isso este
documento inteiro existe.

Geometria não tem nada disso. O RT64 desenha as display lists que o jogo monta —
não há hash de malha, não há pack de malha, não existe gancho equivalente. E
**não precisa haver**, porque o limite de geometria não é hardware:

```python
BUDGET = 0x82A00          # level_model_layout.py
```

São 535.552 bytes que *o jogo reserva* — cerca de 5.900 triângulos com colisão a
90 bytes cada, ou uns 20.000 de decoração a 26. É um número no nosso código, num
recompilado nativo, não um limite físico. Mais triângulo é só mais display list,
e o RT64 desenha sem saber a diferença.

Então a versão honesta de "alta e baixa ao mesmo tempo" para malha **não é uma
substituição no renderizador**. É o jogo carregar um modelo maior quando pode.
Isso é mais simples do que o caminho da textura num aspecto — não há CRC, não há
identidade, não há pack — e mais caro em outro, abaixo.

### O que continua sendo limite de verdade

Elevar a reserva não mexe nas larguras de campo, e essas são o formato:

- `NO_TEXTURE = 0xFF`, e `MAX_TEXTURES` é o mesmo byte — 255 entradas de textura,
  sentinela inclusa
- UV é `s16` com cinco bits fracionários: 1024 texels de alcance por face
- coordenadas de vértice são `s16`
- contagens de batch e segmento são `u16`

Uma pista que estoura *esses* não é uma pista maior, é outro formato. A divisão
que o plano precisa fazer é essa: o orçamento é elástico, as larguras não são.

### A diferença que importa: geometria tem consequência de jogo

Textura é segura de substituir porque trocar a imagem não muda nada além do que
se vê. Malha não: dela saem **colisão, tipo de superfície, linhas de AI e os
segmentos de culling**. Duas malhas divergentes é uma classe de bug que hoje não
existe — ver uma parede que não se bate, cair através de um chão que aparece.

Regra que resolve, e é a padrão em motor moderno: **a de alta é só visual.**
Colisão, superfície, AI e segmentação saem sempre da reduzida, sem exceção e sem
opção. A de alta reutiliza os limites de segmento da reduzida em vez de calcular
os seus, para que o culling continue concordando.

Com essa regra, "se todas forem reduzidas foi só uma conversão" vale de verdade:
a metade de alta não participa de nada que decida jogo.

### Custo, dito com clareza

Isto **mexe no runtime**, coisa que o plano da textura deliberadamente evita
("Não mexe no runtime, além possivelmente do log"). É preciso: uma segunda
carga de modelo, a escolha por preset, e o desvio no caminho de desenho. Não
cabe no mesmo orçamento de risco que o pack de textura — merece documento
próprio, não um parágrafo aqui.

E há uma pergunta de projeto anterior a qualquer código: **duas cargas, ou uma
pista que declara "só Modern"?** Se o limite é a nossa reserva, uma pista pode
simplesmente passar dela e ser recusada no preset Accurate — sem duplicar nada.
Duas cargas só se paga se a mesma pista tiver de rodar nos dois. Vale decidir
isso antes, porque as duas respostas levam a implementações que não se parecem.

### Sugestão

Manter fora deste plano. O pack de textura fecha sozinho, não toca no runtime, e
tem um passo de verificação claro; misturar a malha nele troca uma proposta
pequena e provável por uma grande e incerta. Quando a textura estiver medida
(§5), a malha vira o documento seguinte — e começa pela pergunta de duas cargas
*vs.* pista Modern, não pela implementação.

---

## Implementação (2026-09-10)

Tudo no addon; o runtime não mudou. A extensão maior (a malha) ficou fora, como
a sugestão acima pede.

### O passo 4 do fluxo: as texturas permanecem

- **`operators/new_track.py`** — os dois operadores de conversão ganharam
  **Keep The Mesh's Textures**, ligada por padrão e sem efeito numa malha sem
  imagens. `_adopt_images` faz de cada imagem desenhada por um material usado
  uma textura própria: uma por imagem (dois materiais com o mesmo arquivo dão
  uma), uma entrada de tabela por (imagem, superfície), reaproveitando a que a
  cena já tem. Os dois tetos (255 próprias, 255 na tabela) são checados **antes**
  de escrever qualquer coisa e recusam a conversão inteira nomeando os
  materiais; se algo falhar depois, as texturas adicionadas são desfeitas. Uma
  imagem ilegível deixa só as faces dela sem textura, com aviso.
- **O botão.** `dkr.track_from_mesh_blank` passou a se chamar **Track From
  Mesh** — "No Textures" dizia o oposto do que ele agora faz. A variante com
  doador aparece no painel como *Track From Mesh + A Track's Textures*.
- **`Ctrl+J`** — resolvido, não só avisado: uma face sem mapa na camada ativa
  toma o mapa da camada que o tem, e o relatório diz quantas e de qual. UV fora
  do `s16` é deslocada por repetições inteiras (invisível numa textura que
  repete); só a que não cabe nem assim é travada, e contada.
- **Os três lugares onde a textura se perdia:** `_texture_for` consulta o mapa
  de materiais; `geometry.texture_png` resolve um id próprio por
  `custom_textures.entries` antes da árvore da ROM (e um material reaproveitado
  por nome passa a mostrar a imagem nova); a checagem de textura pendurada em
  `pack._encode_textures` varre base e extras. A **remoção** de textura também
  precisava disso: ela agora recusa quando a tabela base nomeia a textura, ou
  uma posterior que a remoção renumeraria.
- **`custom_textures.add_image`** é o único import: o botão, a conversão e
  `apply_material_textures.py` o usam. Ele guarda o original em resolução cheia
  em `dkr_textures/original/`.
- **Superfície:** uma linha no relatório — tudo entra como estrada.

### O pack HD

- **`rice_identity.py`** — `riceCRC32` e `reverseDXT` transcritos; e também a
  derivação de `width`/`height`/`bytesPerRow`, emulando o que
  `gDPLoadTextureBlock` (`gbi.h`) e `material_init` põem nos tiles e o ramo
  `Block` do patch lê. A identidade sai dessa emulação, não da dedução.
- **`rice_pack.py`** — o zip (`Diddy Kong Racing#<id>_all.png`), escrito num
  temporário e movido; o carimbo `dkr-r-track.json`; o digest dos payloads; os
  limites do importador (uma imagem acima de 256 MB ou 64 Mpx derrubaria a
  importação inteira, então fica de fora com aviso).
- **Export** — `<track>-hd.zip` ao lado da `.dkrmap`; identidades calculadas dos
  bytes dos payloads recém-escritos; `manifest.json` ganha `hdTexturePack`
  com o mesmo digest do carimbo (§7, lado do addon); `HOW-TO-BUILD.md` ganha a
  seção na ordem converteu → exportou → importou; o relatório diz as duas
  coisas numa linha. Nada no pack pode falhar o export.
- **Colisão (§6)** — resolvida como a revisão propôs: `nudge_texels` flipa o bit
  mais baixo do azul (ou da intensidade; nunca alfa) e o nudge fica gravado na
  textura.

### Verificação

- **4a — feita.** Com g++ (w64devkit; MSVC não está instalado). O teste extrai
  `calculateDXT`…`riceCRC32` **do texto do patch**, compila, e compara: 3008
  buffers de todo tamanho e stride, 65.536 casos de `reverseDXT`, e o
  `parse_filename` do próprio `rice_texture_pack_policy.hpp` lendo de volta
  todo nome que o pack escreve. Valores conhecidos gerados pelo patch compilado
  ficam no teste para quem roda sem compilador (`DKR_CXX` liga a comparação).
- **O retângulo (§2, §3) — provado estaticamente**, para todo tamanho × formato
  × combinação de flags de wrap: a derivação do patch cai no tamanho da própria
  imagem. E mais do que a revisão supunha — a identidade **não depende dos
  flags de wrap**: com clamp, `masks = 0` e o retângulo é o tile, que
  `gDPSetTileSize` faz igual à imagem; sem clamp, `1 << masks` é o lado. O
  risco do §3 não existe para os tamanhos aceitos; a invariante fica declarada
  ao lado de `MAX_WRAP_SIZE` e testada mesmo assim.
- **Blender** — fluxo completo (malha de dois materiais com imagem →
  *Track From Mesh* → 0 de 96 cantos com UV diferente do unwrap → viewport com
  as imagens → export → zip cujos nomes são a identidade dos payloads, digest
  igual no manifest e no carimbo) e `Ctrl+J` (o join deixou dois mapas; nenhuma
  face perdeu o mapeamento). Todas as 16 suítes passam.
- **4b — pendente.** Precisa do jogo com a ROM. Com a derivação transcrita do
  código, o que ele ainda prova é que o RT64 em execução faz o que o patch diz —
  mas é a única prova de ponta a ponta. Como fazer: exportar a pista demo
  (`make_texture_demo_track.py --image tools/blender/leaked.jpeg`), instalar a
  `.dkrmap`, importar o `-hd.zip` em Graphics > Custom Texture Packs, ativar,
  preset Modern, reiniciar e carregar a pista. Foto nítida = provado. Se não, o
  runtime não registra a identidade calculada; esse log continua sendo o
  próximo passo de diagnóstico.

### O que o código mostrou de diferente do texto acima

1. **A guarda do §4 é linha < 8 bytes, não < 4.** `LoadBlock` move words de 8
   bytes: com linha menor, `txl2Words` arredonda para 1, o jogo lê com stride 8
   e o CRC passa do fim da imagem, para memória que só existe em execução. E
   em 4 bits com menos de 16 texels de largura é pior: `TXL2WORDS_4b` não tem o
   `MAX(1, …)` que `TXL2WORDS` tem, e `CALC_DXT_4b` divide por zero.
2. **Nem todo nudge muda o nome.** `riceCRC32` soma a word `x == 0` de cada
   linha duas vezes — a segunda com `^ y` — e um flip num bit que `y` também tem
   se anula. A exportação testa nudges em sequência (`free_nudge`) até achar um
   nome livre.
3. **Candidatas (§5) não foram implementadas**: as derivações plausíveis
   coincidem em todo tamanho aceito — é o que o teste do retângulo prova —, então
   emitir candidatas escreveria a mesma entrada duas vezes. A cor-por-candidata
   não teria o que distinguir.
4. **§7, lado do runtime:** o carimbo existe nos dois arquivos, mas a UI de
   importação ainda não compara. Seria a primeira mudança de runtime desta
   feature.

### Achado fora do escopo, para decidir

As larguras que o item 1 exclui do HD — I4/IA4 com 4 ou 8 texels, I8/IA8 com 4 —
são aceitas hoje por `usable_sizes`/`check_size`, e estão quebradas **na própria
pista**, com ou sem pack: a linha fica menor que uma word de TMEM, e em 4 bits o
`CALC_DXT_4b` divide por zero dentro de `material_init`. A conversão automática
nunca as gera (usa o maior tamanho, 64 de largura); só um tamanho digitado à
mão chega lá. Não mudei `check_size`, porque é comportamento existente; a
correção é uma linha — recusar linha < 8 bytes — e merece ser feita.
