# Plano: triangulação e edição de geometria de pista no addon

## O desejo do usuário

Nas palavras de quem pediu, dois problemas relacionados:

> Toda vez que converto uma mesh pra track, ele faz uma triangulação e no meio
> do caminho alguns vértices não ficam juntos. É como se existissem vértices
> coplanares.

> Caso eu precise dar um merge ou inserir algo na pista, ela para de ser
> reconhecida. Ou alguns vértices param. Preciso que exista uma forma de
> contornar isso.

São a mesma família de defeito: o addon triangula a malha com um algoritmo que
só está certo para polígono convexo e planar, e o caminho de export da geometria
editada recusa a pista inteira em vez de contornar edições que cruzam a
segmentação. Este documento cobre os dois.

Tudo abaixo foi lido no código e medido no Blender 5.2, não recuperado de
memória. As medições estão em [O que foi medido](#o-que-foi-medido).

---

## Onde está o código

| peça | arquivo | linha |
|---|---|---|
| triangulação em leque, malha → pista | `tools/blender/dkr_track_editor/operators/new_track.py` | 229-240 |
| triangulação em leque, geometria editada → modelo | `tools/blender/dkr_track_editor/operators/geometry_export.py` | 437-447 |
| recusa "face spans segments" | `geometry_export.py` | 419-425 |
| recusa "vértice não-colocável" (`_unplaceable_message`) | `geometry_export.py` | 249-326 |
| recusa "N malhas de geometria, tem de haver uma" | `geometry_export.py` | 586-595 |
| o `.dkrmap` inteiro aborta com `GeometryExportError` | `operators/pack.py` | 165-169 |
| reconstrução por segmento (não cobre cross-segmento) | `geometry_export.py` `_rebuild` | 724-796 |
| reconstrução do zero + re-segmentação (já existe) | `new_track.build_track` | 648-652 |
| `resegment` / `_partition` / `_dissolve` | `level_model_layout.py` | 519-736 |

Não há um helper de triangulação compartilhado: os dois locais repetem
`for corner in range(1, len(v) - 1): picks = (0, corner, corner + 1)`.

---

## Problema 1 — a triangulação em leque

### Por que quebra

`read_source_mesh` (e o gêmeo em `read_mesh`) transforma cada polígono de N lados
em N-2 triângulos com um **leque a partir do vértice 0**:

```python
vertices = list(polygon.vertices)
for corner in range(1, len(vertices) - 1):
    picks = (0, corner, corner + 1)
    faces.append(level_model_layout.Face(key, tuple(vertices[p] for p in picks), ...))
```

Um leque a partir de um vértice só cobre o polígono exatamente quando esse
vértice **enxerga** todos os outros — condição suficiente: polígono convexo. Para
qualquer polígono côncavo, alguns triângulos do leque saem para fora do
contorno, se sobrepõem, e deixam a reentrância sem cobrir. Para um quad
não-planar, o leque sempre corta na diagonal 0→2, seja qual for a forma.

Os dois sintomas que o usuário descreve saem daí:

- **"vértices coplanares"** — os triângulos sobrepostos do leque de um n-gon
  côncavo são coplanares e se cruzam. No jogo isso é z-fighting; no viewport,
  faces empilhadas no mesmo plano.
- **"vértices não ficam juntos"** — o leque de um polígono côncavo produz
  triângulos cujos vértices ficam fora da silhueta que o autor modelou (a
  reentrância "vaza"), e a diagonal fixa 0→2 em quads não-planares adjacentes
  pode discordar entre um quad e o vizinho, dobrando a superfície de dois jeitos
  ao longo da aresta compartilhada — uma costura.

### O que foi medido

`repro_fan.py` / `repro_fan2.py`, Blender 5.2, chamando `new_track.read_source_mesh`
direto e comparando com `mesh.loop_triangles`:

| polígono | área verdadeira | soma das áreas do leque | soma via `loop_triangles` |
|---|---:|---:|---:|
| dardo (quad côncavo) | 45 000 | **315 000** (7×) | 45 000 |
| chevron (6-gon) | 87 500 | **132 500** | 87 500 |
| pente (10-gon, 3 dentes) | 140 000 | **327 500** (2,3×) | 140 000 |

No dardo, os dois triângulos do leque têm o centroide **fora** do polígono. No
quad em sela, o leque corta 0→2 e o Blender corta 1→3; em dois quads em sela lado
a lado, as diagonais do leque discordam ao longo da aresta comum.

`mesh.loop_triangles` acerta os três casos.

### Correção

Trocar o leque pela tesselação do próprio Blender, `mesh.loop_triangles`
(ear-clipping + *beauty*, o mesmo que o viewport usa):

- **preserva os índices de vértice** — não cria nem funde vértice nenhum, então a
  identidade `dkr_segment` / `dkr_vertex` continua intacta;
- **o export passa a bater com o que o autor vê** na tela;
- o mapeamento de dados por canto fica mais simples, não mais complexo: cada
  `MeshLoopTriangle` traz `.vertices` (3 índices de vértice), `.loops` (3 índices
  de loop, para UV e `dkr_uv`) e `.polygon_index` (para material, `dkr_flags`,
  `dkr_serial`, `dkr_texture`, `dkr_opaque`, `dkr_tri_flags`).

Detalhes:

- guarda de versão: `if hasattr(mesh, "calc_loop_triangles"): mesh.calc_loop_triangles()`
  antes de ler `mesh.loop_triangles` (removido como método no Blender 5, presente
  no 4.2);
- a lógica de resgate de UV de `_polygon_uvs` (achar o mapa não-ativo quando o
  ativo está achatado, resíduo de `Ctrl+J`) continua **por polígono de origem**;
  para cada looptri desse polígono, indexa-se pelos `.loops`;
- filtro de triângulo degenerado (3 colineares) com contagem, espelhando o
  `BuildStats.degenerate` de `geometry.py` — o leque atual não checa isso e um
  triângulo de área zero vira uma face de colisão inútil;
- `_fit` / `_raw_uv` / clamp continuam por triângulo, sem mudança.

### Ordem, e por que é segura

1. **`new_track.read_source_mesh` primeiro.** Não afeta a byte-exatidão de nada:
   a conversão de malha sempre escreve um modelo novo e re-importa. O teste
   `test_track_from_mesh` afirma `model.triangle_count == quads * 2` para uma
   grade plana — continua valendo (quad plano → 2 triângulos). O teste
   `test_track_from_mesh` compara contagem, não a ordem dos triângulos.

2. **`geometry_export.read_mesh` depois.** É seguro para o round-trip byte-exato:
   uma malha importada e intocada já é **toda triângulos** (a importação constrói
   triângulos), e a tesselação de um triângulo é ele mesmo, com o mesmo
   *winding*. Então `read.faces` não muda para um import intocado → o caminho
   in-place (`_patch_in_place`) continua byte-idêntico. Só a geometria **nova**
   que o autor adicionou é triangulada de outro jeito, e essa já força o caminho
   de reconstrução. `test_geometry_add_geometry` afirma contagem ("7 triangles"),
   não diagonais — continua valendo.

### Consideração à parte: modificadores

`read_source_mesh` lê `obj.data` — a malha base, **sem** modificadores. Um autor
com Mirror, Subdivision Surface ou Array vê no viewport uma coisa e converte
outra; um Mirror sem *Clip*/merge deixa as duas metades separadas na costura, que
é mais um jeito de "vértices não ficarem juntos".

Opção **Aplicar Modificadores** (usar `obj.evaluated_get(depsgraph).to_mesh()`),
ligada por padrão, nos dois operadores de conversão. `material_images` e
`_read_colours` continuam lendo os materiais e a cor pela malha avaliada. Fica
como item separado, de risco menor que a triangulação.

---

## Problema 2 — merge/insert faz a pista "parar de ser reconhecida"

### O que "para de ser reconhecida" quer dizer, no código

`build_edited_model` chama `read_mesh`, que levanta `GeometryExportError`; o
export do `.dkrmap` inteiro aborta em `pack.py:165` com *"the track geometry
cannot be exported"*. Do ponto de vista do autor, a pista sumiu.

### As causas, lidas no código

**a. Merge entre segmentos.** `read_mesh` (linha 419):

```python
home = {owner[v] for v in polygon.vertices}
if len(home) != 1:
    raise GeometryExportError("face %d spans segments %s. ...")
```

A malha importada tem **pares de vértices coincidentes em toda fronteira de
segmento e de batch** — o formato duplica vértices por batch (índice de vértice é
`u8` local ao batch), e `test_geometry_import` confirma `len(mesh.vertices) ==
model.vertex_count`, duplicatas incluídas. Um autor que vê os "dobrados" e roda
**Merge by Distance na malha toda** solda esses pares; os que cruzam segmento
viram faces que pertencem a dois → recusa dura, export inteiro cai.

**b. Inserir (Subdivide / Knife / Inset / nova face).** Vértices novos.
`_segment_of_vertex` espalha a identidade a partir das faces vizinhas; se as
faces de um vértice novo alcançam dois segmentos, `_unplaceable_message`
classifica como *straddling* e recusa. Pior: atributos INT de ponto interpolados
pelo Blender num vértice novo entre o segmento 3 e o 5 podem dar "4" — um id de
segmento **válido mas errado**, e a face é colocada em silêncio no lugar errado.

**c. Separate (P).** Cria um objeto novo **sem** `PROP_GEOMETRY`.
`build_edited_model` então vê mais de uma malha de geometria e recusa (linha 586,
*"there has to be exactly one"*) — ou, se o pedaço separado não for detectado,
some do export.

### A saída: um caminho de export "reconstruir do zero e re-segmentar"

A máquina já existe. `new_track.build_track` faz exatamente isto:

```python
model = level_model_layout.blank_model(textures)
level_model_layout.rebatch_segment(model.segments[0], faces, positions, colours)
segments = level_model_layout.resegment(model)
```

`faces` ali usa um **pool plano** de índices de vértice (os índices da malha), sem
identidade por segmento. Cruzar fronteira de segmento antigo não significa nada
até `resegment` re-derivar a segmentação do zero. A byte-exatidão já foi perdida
no instante em que a topologia mudou, então não há regressão a proteger aqui.

**O trabalho:**

1. **Um leitor plano em `geometry_export`** — como `read_source_mesh`, mas
   preservando os dados de render por face que a importação gravou na malha:
   `dkr_flags`, `dkr_texture`, `dkr_opaque`, `dkr_tri_flags` (por face via
   `lt.polygon_index`), `dkr_uv` (por canto via `lt.loops`), `dkr_colour` (por
   ponto). `dkr_serial` vira dica opcional ou é descartado — um resegment
   re-batcheia tudo de qualquer jeito. `dkr_segment` é **ignorado**.

2. **Semear `model.bounds`** a partir da malha (via
   `level_model_edit.model_bounds` depois de encher o segmento 0) **antes** de
   `resegment`, para que o `_partition` faça a divisão espacial e não só por
   contagem. (`blank_model` deixa `bounds` zerado, e hoje `new_track` sofre do
   mesmo jeito — uma pista de chão plano e espalhado não é dividida
   espacialmente. Vale consertar nos dois.)

3. **Acionamento automático.** `build_edited_model` tenta o caminho ciente de
   segmento; se `read_mesh` bate numa face que cruza segmento ou num vértice
   não-colocável **mas conectado**, refaz com o leitor plano →
   `_rebuild_flat` → `blank_model` + faces no segmento 0 + `resegment`. Uma nota
   no relatório:

   > A edição cruzou fronteiras de segmento, então a pista foi re-segmentada e a
   > identidade dos vértices foi reconstruída. Reshapes byte-exatos a partir
   > daqui exigem re-importar a geometria.

4. **Acionamento explícito.** Um operador **Editar Livremente** (ou **Fundir
   Segmentos**) que reescreve `dkr_segment` para tudo = 1 na malha. A partir daí
   nenhum merge, knife ou inset cruza segmento, porque só há um. Par natural com
   o **Re-segment Track** que já existe (e que já escreve a pista como seu
   próprio `.bin` base). O fluxo passa a ser: *Editar Livremente → mexer à
   vontade → exportar* (o resegment automático entra) ou *→ Re-segment Track*
   quando quiser fixar a nova segmentação como base.

5. **Multi-malha / Separate.** A mensagem de recusa da linha 586 ganha uma frase
   sobre `Separate`, e — baixa prioridade — um helper **Re-juntar Geometria** que
   faz o `Ctrl+J` de volta e restaura `PROP_GEOMETRY`/`PROP_SCHEMA` do objeto que
   sobra.

---

## Geometria não-weld: o que acontece (e por que não é problema)

Pergunta do usuário: *"e se eu tiver uma geometria que não é weld num vértice?
O próprio jogo tem geometria que não é colada."* Está certo — e o addon **não
exige** malha weld/manifold em lugar nenhum. Não há `mesh.validate()`, não há
checagem de manifold.

**O formato também não cola.** `VERTEX_SIZE = 10`: um vértice é só posição
(`s16 x3`) + `rgba` da luz assada, nada mais. Cada batch tem sua própria janela
de vértices e o índice do triângulo é `u8` **local ao batch**, então um vértice
numa fronteira de batch é **duplicado**, não compartilhado
(`level_model_layout.py`, docstring do módulo). Cada segmento tem seu próprio
pool. Os dados retail são cheios de vértices coincidentes e distintos — é o
normal.

**Track From Mesh.** `resegment` → `_dissolve` funde os coincidentes pela chave
`(posição, cor)` só para particionar, e `rebatch_segment` re-duplica por batch
depois. Como `(posição, cor)` é *tudo* que um vértice é, essa fusão não perde
nada que o formato saiba expressar. Na prática:

- coincidentes com a **mesma** cor assada → fundidos no dissolve, re-divididos
  por batch. Sai válido e igual.
- coincidentes com cores assadas **diferentes** → ficam separados. Correto: o
  formato precisa deles separados para segurar a costura de cor.
- ilhas desconectadas / cascas soltas → `_partition` divide por centroide, não
  liga para conectividade. Funciona.
- **T-junction de verdade** (vértice no meio da aresta de outra face, não na
  ponta) → continua T-junction, exatamente como no retail. Não é curada, mas não
  fica pior que os dados do jogo.

**Editando uma pista importada.** Todo vértice importado carrega
`dkr_segment` / `dkr_vertex` — os não-weld inclusive — então não há problema. As
falhas do Problema 2 são sobre vértices **novos** que o autor adiciona ou
**merges que cruzam segmento**, não sobre o caráter não-weld dos dados que já
vieram do arquivo.

**O único custo real:** muitas ilhas minúsculas desconectadas viram muitos
segmentos minúsculos (cada um custa uma bounding box, um nó de BSP e uma linha de
PVS), porque `_partition` para de dividir em `MIN_SEGMENT_TRIANGLES = 8` mas
nunca **funde** grupos pequenos. Não quebra; só incha. Se virar um problema real,
uma passada de fusão de grupos pequenos por proximidade em `_partition` resolve —
fica anotado, fora do escopo imediato.

**Teste:** `test_geometry_from_mesh_unwelded` — grade onde metade dos vértices da
costura central foi separada (não-weld) → conversão produz um modelo válido,
`check_windows` limpo, e o número de segmentos não explode.

---

## O que este plano deliberadamente não faz

- **Não muda o caminho in-place byte-exato** para reshapes que não mexem em
  contagem. Continua sendo a razão de reshapar ser barato, e continua intocado.
- **Não tenta preservar identidade `(segmento, vértice)` através de um
  resegment.** É impossível por design — `resegment` redistribui triângulos entre
  segmentos — e é por isso que o aviso existe.
- **Não aplica modificadores sem uma opção.** A malha do autor é dele.
- **Não triangula com `bmesh.ops.triangulate`.** `mesh.loop_triangles` casa com o
  viewport e não precisa do ciclo de vida de um bmesh; `bmesh` fica como
  alternativa se algum dia `loop_triangles` não bastar.

---

## Testes

Novos casos em `tools/blender/tests/test_blender_operators.py`:

- **`test_track_from_mesh_concave_ngon`** — grade com um n-gon côncavo (um dardo
  ou um pente). Contagem de triângulos = a de `mesh.loop_triangles`; soma das
  áreas dos triângulos ≈ área do polígono (sem *spill*); nenhum triângulo com
  centroide fora do contorno.
- **`test_track_from_mesh_nonplanar_quad`** — quad em sela → a diagonal escolhida
  é a do Blender, não a fixa 0→2.
- **`test_track_from_mesh_applies_modifiers`** — grade + Mirror sem merge →
  conversão com *Aplicar Modificadores* produz a malha espelhada, sem costura na
  origem.
- **`test_geometry_edit_merge_across_segments`** — importar Ancient Lake, Merge
  by Distance na malha toda, export → **não** recusa; re-segmenta; nota no
  relatório; o modelo re-encoda e re-parseia; `check_windows` limpo.
- **`test_geometry_edit_insert`** — Subdivide/Knife em faces de dois segmentos
  diferentes → export OK pelo caminho plano.
- **`test_edit_freely_operator`** — colapsa para um segmento; um merge que antes
  cruzava segmento agora é trivial; export OK.

O `test_track_from_mesh` e o `test_geometry_add_geometry` atuais continuam
valendo (afirmam contagem, não diagonais).

---

## Riscos, do maior para o menor

1. **`read_mesh` plano quebrar a byte-exatidão de algum caminho que hoje é
   in-place.** Mitigação: o caminho plano só é acionado quando o ciente de
   segmento **já falhou** — nunca substitui `_patch_in_place`. E o teste
   `test_geometry_roundtrip` fixa a byte-exatidão de um import intocado.
2. **`resegment` numa pista já grande estourar o orçamento** (`BUDGET =
   0x82A00`). O resegment não adiciona triângulos, mas re-batcheia, e o número de
   segmentos muda a conta da PVS e das reservas de colisão.
   `check_collision_pressure` e `runtime_size` já rodam no fim de `_rebuild`;
   basta rodá-los no caminho plano também e reportar.
3. **`loop_triangles` e o resgate de UV do `Ctrl+J`.** O mapeamento por
   `lt.loops` tem de indexar o mesmo mapa de UV que `_polygon_uvs` escolheu para
   o polígono de origem — testar com a malha de `test_track_from_mesh_survives_ctrl_j`.
4. **Atributo INT interpolado num vértice novo dando um segmento errado mas
   válido** (causa 2b). No caminho plano é irrelevante (segmento ignorado); no
   ciente de segmento, considerar confiar no espalhamento de `_segment_of_vertex`
   em vez do valor guardado quando as faces do vértice discordam.
5. **Blender 5 vs 4.2** — `calc_loop_triangles` removido como método no 5. A
   guarda `hasattr` cobre; o CI roda no 5.2 (memória `dev-toolchain`).

---

## Esforço e ordem sugerida

O grosso é o Problema 2, item 1-3 (o leitor plano e o acionamento). A
triangulação é uma função em cada um dos dois locais.

1. **`new_track.read_source_mesh` → `loop_triangles`**, com o filtro de
   degenerado. Testes do Problema 1. É a correção que o usuário pediu primeiro e
   a de menor risco.
2. **`geometry_export.read_mesh` → `loop_triangles`.** O `test_geometry_roundtrip`
   prova que não regrediu.
3. **Leitor plano + `_rebuild_flat` + acionamento automático** em
   `build_edited_model`, com a nota no relatório e o `model.bounds` semeado.
   Testes de merge/insert.
4. **Operador Editar Livremente**, mensagem de Separate, opção Aplicar
   Modificadores.
5. Doc: `tools/blender/README.md` e `docs/` — o fluxo *Editar Livremente → mexer
   → exportar*, e a nota de que um resegment reconstrói a identidade.
