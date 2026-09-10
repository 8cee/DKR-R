# Plano: a textura de uma pista custom em alta resolução

Quando um autor traz uma imagem para a sua pista, o `.dkrmap` leva uma versão de
**64×32**. Não é escolha do addon: a RDP tem 4 KiB de TMEM e `material_init`
carrega a textura de nível como um bloco único, então 2048 texels é o teto de um
formato de 16 bits. Uma foto de 2752×1536 tem 4,2 milhões.

Este plano descreve como fazer o jogo **desenhar a imagem original** mesmo assim,
sem mexer em nada do que já funciona: o addon emite, junto do `.dkrmap`, um
texture pack Rice cuja identidade é a da textura reduzida que ele acabou de
gerar. O jogo carrega os 64×32; o RT64 troca pela imagem cheia na hora de
desenhar.

Estado: **proposta**. Nada abaixo foi implementado.

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
