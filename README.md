# Eco Runner

Jogo de voo em visual pseudo-3D, feito em Python e Pygame. O jogador pilota um avião de papel
por uma pista e coleta lixo para restaurar o ambiente. Conforme a restauração sobe, a paisagem
muda: da cidade dieselpunk poluída ao cenário solarpunk Art Nouveau.

## O jogo

### Avião e piloto

O avião de papel voa em todas as direções: para os lados (← / →), para cima e para baixo. O lixo
e os obstáculos aparecem em três faixas da pista, mas o avião não fica preso a elas. Ele fica dentro
dos limites laterais da pista e com a altura (ALT, mostrada no HUD) entre 22 e 155.

Os aviões vêm do "Estúdio 3D Aviões, 14-Bis & Piloto Customizável", na versão com os **modelos
refinados** (malhas mais detalhadas, dobras e marcas do papel). São 11 modelos:

1. Jato Alongado (Com Clipe)
2. Planador Largo
3. Asa Curta e Ponta Larga
4. Avião de Fichário
5. Bico Agulha
6. Hoverboard (Asa Retangular)
7. Tsuru / Pássaro
8. Sanfona
9. Caça Realista
10. Planador de Haste Longa
11. 14-Bis (Miniatura de Papelão)

O boneco em cima do avião é só customização e não muda a jogabilidade. São 7 opções de piloto:

- Sem piloto
- Boneco montado
- Boneco surfando
- Boneco zen
- Boneco acenando
- Boneco super-herói
- Boneco na cadeira de rodas

A escolha de avião e piloto é feita no **Hangar** (tela inicial). Ao decolar (ENTER ou ESPAÇO), a
escolha é salva em `eco_runner_config.json`, na pasta de dados (ver "Onde ficam o recorde, os logs
e os relatórios"), e é reaberta na próxima vez que o jogo iniciar. O padrão é o Jato Alongado com o
boneco montado.

### Oficina de pintura

No hangar, a tecla **C** abre a **Oficina de pintura**, onde se escolhe a cor do avião. A cor é
aplicada só ao papel: o piloto, as rodas de madeira e as outras peças que não são de papel continuam
como estão, e as dobras e marcas do papel continuam visíveis por baixo da tinta. A prévia aparece na
hora, em 3/4 (como no hangar) e vista de trás (como no voo).

Cores disponíveis: Original do estúdio, Branco papel, Vermelho, Laranja, Amarelo, Verde, Verde-água,
Ciano, Azul, Anil, Roxo, Rosa, Dourado, Papelão kraft e Grafite. "Original do estúdio" mostra o avião
com as cores padrão do estúdio, sem tinta.

A segunda linha da Oficina traz os **padrões de pintura** do estúdio 3D, com as cores dos presets
dele: Camuflado selva, Camuflado deserto, Camuflado ártico, Chamas hot rod, Chamas de plasma, Galáxia
estelar, Cyberpunk neon, Tigre selvagem, Fibra hexagonal, Prisma (dazzle), Xadrez de corrida, Listras
de corrida, Raios solares, Pop art (retícula) e Brasil. O padrão é "vestido" no papel como no estúdio
(segue as dobras e as faces do avião), e o piloto também não muda. ↑/↓ alternam entre a linha das
cores e a dos padrões; "Liso" usa só a cor. Um padrão já tem as cores próprias, então escolher uma
cor volta ao liso.

Cada avião lembra a sua cor e o seu padrão. ENTER, ESPAÇO ou C confirmam e salvam a escolha em
`eco_runner_config.json` (chaves `cores` e `padroes`); ESC cancela e volta à pintura anterior.

### Modos de jogo: Normal e Difícil

No hangar, **M** alterna entre os dois modos; a escolha aparece no canto do cartão do avião e fica salva
(chave `modo` em `eco_runner_config.json`). Quem nunca escolheu começa no **Normal**.

| | Normal | Difícil (o jogo original) |
|---|---|---|
| Lixo na pista | 1 a cada 4 (`NORMAL_TRASH_EVERY`) | todos |
| Pontos por lixo | 65 fixos, sem combo (`NORMAL_TRASH_POINTS`) | 15 × combo |
| Restauração por lixo | 11,2 (`NORMAL_RESTORATION_PER_TRASH`) | 1,4 (+0,15 com combo ≥ 4) |
| Velocidade | metade (`NORMAL_SPEED_FACTOR` 0,5) | normal |
| Brilho nos coletáveis da era final | não | sim |
| Recorde | `recorde_normal` | `recorde` |

Obstáculos e power-ups aparecem na mesma proporção nos dois modos. Como no Normal há 4× menos lixo por
distância e o avião anda na metade da velocidade (8× menos lixo por segundo), cada lixo restaura 8× mais:
as 3 eras chegam em tempo parecido com o Difícil (~3 lixos por era). Os pontos dos dois modos somam na
mesma carteira da loja. O brilho dos coletáveis fica só no Difícil, reservado para uma mecânica futura.

### Eras

**Três eras**, trocadas conforme a restauração ambiental aumenta:

| Era | Restauração necessária |
|---|---|
| Era I: Dieselpunk Industrial | a partir de 0% (início) |
| Era II: Despertar Ecológico | 33,3% |
| Era III: Solarpunk Art Nouveau (cidade EcoUrbe) | 66,7% |

São 3 eras com o mesmo espaçamento (`ERA_SPAN` = 100/3). No Difícil, cada lixo restaura 1,4 ponto
(`RESTORATION_PER_TRASH`; +0,15 com combo ≥ 4) e o reparo com vidas cheias, 2 pontos:
cerca de 24 lixos por era. A antiga era "Poluição Corporativa" (25%) foi removida em 21/10/2026.

### Restauração, coleta, combo e vidas

**Restauração**: começa em 5%, com teto de 100%. No Difícil, cada lixo coletado soma +1,4%
(+1,55% quando o combo está em x4 ou mais); no Normal, +11,2%.

**Coleta de lixo**: no Difícil, cada lixo vale 15 pontos × o combo atual; no Normal, 65 pontos fixos. O lixo é coletado ao encostar no avião,
ou pelo ímã (ver power-ups).

**Combo** (só no Difícil): a cada 4 lixos coletados em sequência, o combo sobe 1, até x8.
O combo zera ao bater em um obstáculo ou quando passam 2,2 s sem coletar lixo.

**Vidas**: 3. Ao bater em um obstáculo, o jogador perde uma vida, fica invulnerável por
1,25 s e o combo zera. Sem vidas, a partida termina.

### Obstáculos e manobras

| Obstáculo | Modelos (pasta `modelos_3d`) | Como passar |
|---|---|---|
| Tambores, caçamba, sucata e monte de lixo | 05 Tambores, 08 Caçamba, 07 Pilha de sucata, 06 Monte de lixo | **Voe por cima**: acima de cerca de 117 de ALT (tambores), 113 (caçamba) ou 97 (sucata e monte de lixo) |
| Rede de tubos com válvula | 04 Rede de tubos com válvula | **Passe por baixo**: abaixo de cerca de 88 de ALT |
| Chaminé e caldeira | 02 Chaminé, 03 Caldeira | **Desvie para o lado**: ocupam a pista em toda a altura |

Os valores de ALT são aproximados e vêm do tamanho da colisão do avião e do obstáculo.

**Lixo em três alturas**: o lixo flutua em três alturas (baixa, média e alta). Para coletá-lo, o avião
precisa encostar nele. O lixo baixo é alcançado até cerca de ALT 79, o médio entre cerca de 41 e 135,
e o alto a partir de cerca de 93.

**Sombra e altitude**: o avião e o lixo projetam sombra no chão. Quanto maior a distância entre o
objeto e a sombra, mais alto ele está. A sombra do avião fica mais clara à medida que ele sobe. O HUD
mostra a altura exata em `ALT`.

### Power-ups

Aparecem na pista e são pegos ao passar sobre eles:

- **Escudo**: 6 s em que as colisões não tiram vida.
- **Ímã**: 7 s em que o lixo que passa perto do avião é coletado sozinho. Vale para lixo a menos de
  1,1 faixa de distância lateral e a menos de 110 unidades de altura.
- **Reparo**: +1 vida, se o jogador tiver menos de 3. Com as 3 vidas, recupera +3% de restauração.

### Manobras acrobáticas

Ao pegar um power-up, o avião faz uma manobra tirada das animações 3D do pacote de aviões refinados:

| Momento | Manobra | Animação de origem |
|---|---|---|
| Pegar o escudo | Looping vertical (sobe, passa de cabeça para baixo e volta) | 03 Looping Vertical Completo |
| Pegar o ímã | Tonneau: giro de 360° em torno do próprio eixo | 05 Tonneau / Giro Aileron 360 |
| Pegar o reparo | Manobra cobra: o nariz sobe quase na vertical e volta | 06 Manobra Cobra Rasante |
| Decolar | Decolagem: o avião vem de perto e de baixo até a posição de voo | 07 Decolagem Histórica 14-Bis |

As manobras são só visuais: duram de 1 a 1,5 s e não mudam a colisão nem os controles. O avião
continua onde está para fins de jogo.

### Quais modelos aparecem onde

| Elemento | Modelos | Onde aparecem |
|---|---|---|
| Props Dieselpunk | 01 Fábrica, 02 Chaminé, 03 Caldeira, 04 Rede de tubos com válvula, 05 Tambores, 06 Monte de lixo, 07 Pilha de sucata, 08 Caçamba | Fileira de fundo das margens na Era I (e onde a Era II ainda não chegou), intercalados com as estruturas do kit. A caçamba saiu dessa fileira, trocada pela caixa industrial do guia (ver a linha seguinte); ela continua como obstáculo. Chaminé, caldeira, tubos, tambores, monte de lixo, sucata e caçamba também são obstáculos (tabela acima). A fábrica aparece só na margem. |
| Kit Dieselpunk_Scenario | 28 modelos de `modelos_3d/Dieselpunk_Scenario` | Eras I e II. Fileira junto à pista: tambor de combustível, caixa, carretel de cabo, painel de controle, tubos de vapor, gerador, compressor, passarela e luz âmbar. Fileira de fundo: torre industrial, guindaste, silo, chaminé, tanque de pressão, paredes de fábrica, elevador de carga, ventilador, escada, suporte, portão de hangar, torre de energia e fábrica distante. |
| Peças do guia | `SCN_CaixaIndustrial_Cenario`, `SCN_Galpao_Restaurado` e `SCN_TorreChamine_Restaurada` (pasta `scenario_sprites/`) | Caixa industrial: fileira de fundo da Era I, no lugar da caçamba. Galpão e torre restaurados: fileira de fundo da Era II (restauração de 33,3% ou mais), em 1 trecho a cada 6, no lugar de uma árvore. |
| Silhuetas do horizonte | silo, fábrica distante, torre de energia, torre industrial, chaminé, guindaste, tanque e elevador do kit; árvores Solarpunk 01 a 10 | Horizonte, em duas fileiras. As silhuetas industriais viram árvores conforme a restauração sobe. |
| Céu e nuvens | panorama de céu poluído e nuvem de fumaça do kit | Céu das eras poluídas. Somem aos poucos com a restauração, dando lugar ao céu da era e a nuvens claras. |
| Árvores Solarpunk | 01 a 10 | Margens da Era II, com restauração de 33,3% ou mais (na Era III dão lugar aos modelos EcoUrbe), nos trechos já purificados: na fileira de fundo e, menores, na borda da pista. Fora deles, a margem mostra os modelos industriais. |
| Grama | textura gerada por `tools/make_grass_texture.py` | Chão fora da pista nas eras II e III, a partir de 33,3% de restauração, do avião até a frente de restauração: o mesmo trecho em que as árvores aparecem. Além dela, concreto sujo. |
| Concreto sujo | textura gerada por `tools/make_concrete_texture.py` | Chão fora da pista em toda a Era I e, a partir de 33,3%, além da frente de restauração. |
| Lixo coletável | 4 modelos de lixo (lista em `trash_sprites/`, abaixo) | Pista, em três alturas |
| Aviões | 11 modelos do Estúdio (lista na seção Avião e piloto) | Hangar e voo |
| Power-ups | escudo, ímã e reparo (sprites em `powerup_sprites/`) | Pista |

Os modelos de props, árvores, sucata e obstáculos aparecem em **ordem fixa**, sem sorteio: cada
tipo segue sua sequência e se repete em ciclo. Continuam sorteados a cada partida: a faixa e a altura
do lixo, o tipo de obstáculo (baixo, rede ou torre), a faixa de cada obstáculo, o tipo e a faixa dos
power-ups e o espaçamento entre os padrões na pista.

### Câmera, paralaxe e velocidade

A câmera acompanha parte do movimento lateral do avião, e o cenário é dividido em camadas que se
deslocam em ritmos diferentes: quanto mais longe, mais devagar. Assim, ao mover o avião para os lados,
fica claro que é ele que se move, e não o cenário.

| Camada | O que contém | Como se move |
|---|---|---|
| Céu | panorama de céu poluído com o sol | quase parado: desloca-se pouquíssimo com a câmera e tem deriva muito lenta |
| Nuvens | fumaça (eras poluídas) ou nuvens claras | um pouco mais rápidas que o céu, cada nuvem no seu ritmo |
| Distante | duas fileiras de silhuetas dos modelos no horizonte | poucos pixels com a câmera e deriva lenta; a fileira de trás anda pouco mais da metade da da frente |
| Média | fileira de fundo das margens (estruturas grandes ou árvores) | metade do deslocamento lateral da câmera |
| Borda | fileira junto à pista (peças pequenas ou árvores menores) | 80% do deslocamento lateral da câmera |
| Próxima | pista, faixas, lixo, obstáculos, power-ups e avião | deslocamento lateral completo da câmera |

**Neblina**: a pista e os objetos se misturam à cor do horizonte com a distância. Os objetos surgem aos
poucos no fundo, em vez de aparecer de repente no fim da pista.

**Movimento contínuo**: cada trecho da pista mantém a sua cor e os seus objetos até sair da tela. Nas
versões anteriores, as faixas da pista trocavam de cor e os prédios das margens pulavam de posição
cerca de 5 vezes por segundo, o que dava a impressão de tremor. O passo de tempo do jogo também é
suavizado, para o cenário não tremer com as pequenas variações do relógio.

**Desempenho**: os sprites são reduzidos a partir de versões pré-reduzidas, objetos fora da tela não são
desenhados, e as silhuetas do horizonte são refeitas aos poucos, em vários quadros. Os sprites são
preparados enquanto o hangar está aberto. O chão com textura só é desenhado nas laterais da pista. No ambiente de teste, um quadro leva em média
cerca de 11 ms (9 ms antes do cenário novo), com bem mais objetos na tela.

**Concreto sujo**: na fase inicial, o chão fora da pista é de concreto: placas com juntas, manchas de
óleo, rachaduras, fuligem e pontos de ferrugem. As juntas paralelas à pista são desenhadas em perspectiva
e a textura desliza junto com a pista, como a grama.

**Grama**: a partir de 33,3% de restauração, o chão fora da pista vira grama com textura (tufos, manchas
claras e escuras e pequenas flores) desde o avião até a frente de restauração, onde as árvores começam.
Uma linha escura marca essa borda. A grama é desenhada em perspectiva, desliza junto com a pista e
acompanha a câmera como a pista. Quanto mais a restauração sobe, mais longe a grama chega.

O céu poluído e a fumaça vão sumindo entre 20% e 65% de restauração. No mesmo intervalo, as silhuetas
industriais do horizonte se transformam em árvores.

A pista começa a cerca de 463 unidades por segundo e acelera com a restauração (+0,6 por ponto
percentual) e com o tempo de partida (até +50 nos primeiros 3 minutos), até o máximo de 570.

A câmera e a paralaxe mudam só o desenho: as colisões continuam calculadas na posição real do avião.
Os valores podem ser ajustados (ver "Ajustar câmera, paralaxe e velocidade").

## Controles

### No hangar

| Ação | Teclas |
|---|---|
| Trocar de avião | ← / → ou A / D |
| Trocar de piloto | ↑ / ↓ ou W / S |
| Abrir a Oficina de pintura | C |
| Trocar o controle: teclado → corpo → uma mão | V |
| Recalibrar a câmera | R |
| Alternar o modo Normal / Difícil | M |
| Decolar | ENTER ou ESPAÇO |

### Na Oficina de pintura

| Ação | Teclas |
|---|---|
| Ir para a linha das cores ou dos padrões | ↑ / ↓ ou W / S |
| Escolher a cor ou o padrão | ← / → ou A / D |
| Confirmar e salvar | ENTER, ESPAÇO ou C |
| Cancelar | ESC |

### No voo

| Ação | Teclas |
|---|---|
| Ir para a esquerda | ← ou A |
| Ir para a direita | → ou D |
| Subir | ↑, W ou ESPAÇO |
| Descer | ↓ ou S |
| Pausar e continuar | P ou ESC |
| Voltar ao hangar (na pausa ou no game over) | C ou TAB |
| Mostrar hitboxes (depuração) | F3 |

Os comandos de voo são contínuos: o avião responde enquanto a tecla estiver pressionada.
Com o controle por câmera ligado, o corpo e o teclado funcionam juntos (veja "Controle pela webcam").

### Fim de jogo e nova partida

No game over, ENTER ou ESPAÇO voa de novo com o mesmo avião e piloto, e o recorde é mantido. C ou TAB
volta ao hangar para trocar o avião ou o piloto.

## Controle pela webcam

O jogo pode ser comandado pela webcam, no hangar, na Oficina de pintura e no voo, em dois modos.
A técnica vem do T-TEA 2.0: o MediaPipe Pose encontra ombros, quadris e pulsos na imagem.
V no hangar troca o controle: **teclado → corpo → uma mão → teclado**.

### Modo corpo

Usa o centro do tronco e as duas mãos.

| Onde | Gesto | Efeito |
|---|---|---|
| Hangar | Inclinar o corpo para os lados | Troca o avião (← / →) |
| Hangar | Inclinar o corpo para cima / para baixo | Troca o piloto (↑ / ↓) |
| Hangar | Levantar a mão direita | Decolar |
| Hangar | Levantar a mão esquerda | Abre a Oficina de pintura |
| Oficina | Inclinar para os lados / para cima e para baixo | Escolhe cor ou padrão, e troca a linha |
| Oficina | Levantar a mão direita / esquerda | Salva / cancela |
| Voo | Inclinar para a direita ou para a esquerda | Voa para o lado |
| Voo | Levantar o corpo / agachar | Sobe / desce |
| Fim de jogo | Levantar a mão direita / esquerda | Voar de novo / voltar ao hangar |

Nos menus, cada inclinação conta como um passo: volte ao centro para poder mover de novo.
Uma mão precisa ficar levantada por cerca de 0,3 s para contar.

### Modo uma mão

Tudo é feito com uma só mão (a direita, por padrão). O pulso funciona como um joystick em
relação à posição de repouso calibrada.

| Onde | Gesto | Efeito |
|---|---|---|
| Hangar | Mão para a esquerda / direita | Troca o avião |
| Hangar | Mão para cima | Próximo piloto |
| Hangar | Mão para baixo | Abre a Oficina de pintura |
| Hangar | Mão levantada acima do ombro | Decolar |
| Oficina | Mão para a esquerda / direita | Escolhe a cor ou o padrão |
| Oficina | Mão para cima | Alterna entre a linha de cores e a de padrões |
| Oficina | Mão levantada / mão para baixo | Salva / cancela |
| Voo | Mão para os lados, para cima, para baixo | O avião segue a mão |
| Fim de jogo | Mão levantada / mão para baixo | Voar de novo / voltar ao hangar |

Nos menus, a mão precisa ficar um instante (cerca de 0,3 s) na posição para o gesto contar, então
movimentos de passagem não disparam nada. Depois de cada gesto, volte a mão ao centro.
"Mão para baixo" pede um movimento maior e cerca de 0,7 s, para não disparar quando você relaxa o braço.

Para usar a mão esquerda, troque `HAND = "right"` por `HAND = "left"` em `webcam_control.py`.

### Como ativar

1. Instale as bibliotecas opcionais (Python 3.10 a 3.13): `pip install -r requirements-webcam.txt`.
   No `.exe` pronto elas já vêm incluídas, se o build tiver sido feito com o `requirements-webcam.txt` instalado.
2. No hangar, aperte V até aparecer o modo desejado (corpo ou uma mão). A linha de status mostra o modo e se a câmera está ligada.
3. Fique de frente para a câmera e fique parado (no modo uma mão, mantenha a mão parada na posição de repouso)
   por cerca de 2 segundos enquanto o jogo calibra (porcentagem no status). A posição de repouso vale para o hangar e para o voo.
4. Se mudar de lugar, aperte **R** no hangar para recalibrar.

Uma miniatura da câmera aparece no hangar (canto superior direito) e no voo (canto inferior esquerdo).

Se a câmera ou as bibliotecas não estiverem disponíveis, o hangar mostra o motivo e o jogo segue com o teclado.
O teclado funciona em todos os modos. A escolha fica salva em `eco_runner_config.json`
(chave `controle`, valores `teclado`, `camera` ou `mao`), e a câmera já inicia ao abrir o jogo se estiver escolhida.

### Sensibilidade

Os limites de movimento estão em `webcam_control.py`: `PoseMapper` (modo corpo) e `HandMapper` (modo uma mão).
`RANGE_X` e `RANGE_Y` dizem quanto o tronco ou a mão precisa se deslocar para o avião chegar ao máximo, e
`DEAD_X` / `DEAD_Y` são a zona morta contra tremor. Os gestos de menu estão em `MenuNavigator` (corpo) e
`HandNavigator` (uma mão: `ON`, `OFF` e `DWELL`, o tempo de permanência em leituras da câmera).
Valores menores deixam o controle mais sensível. Se algo reagir sem você querer, aumente a zona morta ou o `DWELL`.

O modelo de pose fica em `assets/pose_model/pose_landmarker_lite.task`. O arquivo é do MediaPipe (Google)
e foi copiado do T-TEA 2.0.

## Ajustar câmera, paralaxe e velocidade

Os valores ficam em constantes no começo do `eco_runner.py`. Depois de mudar, rode pelo Python para
conferir e recompile para atualizar o executável: o `.exe` em `dist\` não muda sozinho.

| Constante | Valor | Efeito |
|---|---|---|
| `CAMERA_FOLLOW` | 0.35 | Fração do deslocamento lateral do avião que a câmera acompanha. 0 deixa a câmera fixa; valores maiores deixam o avião mais centralizado e fazem o cenário deslizar mais. |
| `MARGIN_PARALLAX` | 0.8 | Fração do deslocamento da câmera aplicada à fileira junto à pista. |
| `MID_PARALLAX` | 0.5 | Fração do deslocamento da câmera aplicada à fileira de fundo das margens. 1 iguala essa fileira à pista; 0 deixa as margens sem deslocamento lateral. |
| `FAR_SHIFT_PX` | 0.25 | Pixels que as silhuetas do horizonte (fileira da frente) se deslocam por unidade de deslocamento da câmera. |
| `FAR_DRIFT_PX` | 0.03 | Deriva das silhuetas do horizonte, em pixels por unidade de distância percorrida. 0 desliga a deriva. |
| `FAR_BACK_RATIO` | 0.55 | Velocidade da fileira de trás das silhuetas em relação à da frente. |
| `CLOUD_SHIFT_PX` | 0.15 | Pixels que as nuvens se deslocam por unidade de deslocamento da câmera (multiplicado pelo ritmo de cada nuvem). |
| `SKY_SHIFT_PX` | 0.08 | Pixels que o panorama do céu se desloca por unidade de deslocamento da câmera. |
| `SKY_DRIFT_PX` | 0.004 | Deriva do panorama do céu por unidade de distância percorrida. |
| `FOG_START` e `FOG_END` | 900 e 2450 | Distância em que a neblina começa e em que os objetos somem por completo. |
| `POLLUTION_CLEAR_START` e `POLLUTION_CLEAR_END` | 20 e 65 | Faixa de restauração (%) em que o céu poluído e a fumaça somem e o horizonte vira árvores. |
| `GRASS_START_RESTORATION` | 50 | Restauração (%) a partir da qual a grama aparece (a mesma das árvores). |
| `CONCRETE_TILE_X` e `CONCRETE_TILE_Z` | 400 e 200 | Tamanho no mundo de cada repetição da textura de concreto (cada placa tem metade disso). |
| `CONCRETE_JOINTS_X` | 560, 860 e 1200 | Distância das juntas paralelas à pista até o centro (as mesmas dos dois lados). |
| `GRASS_TILE_X` e `GRASS_TILE_Z` | 240 e 120 | Tamanho no mundo de cada repetição da textura de grama (largura e profundidade). Valores menores deixam os tufos menores. |
| `MARGIN_X` e `MID_ROW_X` | 480 e 690 | Distância lateral das duas fileiras das margens até o centro da pista. |
| `BASE_SPEED` | 460 | Velocidade inicial da pista. Valor anterior: 560. |
| `RESTORATION_SPEED_GAIN` | 0.6 | Velocidade somada por ponto percentual de restauração. Valor anterior: 1.8. |
| `DIFFICULTY_SPEED_GAIN` | 50 | Velocidade somada ao longo dos primeiros 3 minutos de partida. Valor anterior: 80. |

As velocidades foram reduzidas porque, com os valores anteriores, o fluxo da pista na tela chegava a ser
mais rápido que o movimento lateral do avião e dava a impressão de que o cenário se movia sozinho.

Para voltar ao movimento anterior, use `CAMERA_FOLLOW = 0`, `FAR_DRIFT_PX = 0`, `SKY_DRIFT_PX = 0` e as
velocidades 560, 1.8 e 80. O céu, as nuvens e as silhuetas continuam aparecendo, sem acompanhar a
câmera; as nuvens mantêm a deriva própria.

## Como executar o jogo pronto (Windows)

1. Copie a pasta **`EcoRunner`** inteira (com a subpasta `_internal` e todos os arquivos).
2. Dê dois cliques em `EcoRunner.exe`.

Não é preciso instalar Python. Distribua a pasta inteira: o `.exe` sozinho não
funciona no modo onedir. Se o build tiver sido feito com `onefile`, o arquivo
`EcoRunner.exe` é único e basta ele.

## Como executar pelo Python

Requisitos: Python 3 e Pygame entre 2.5 e 3 (`pygame>=2.5,<3`).

```bash
pip install -r requirements.txt
python eco_runner.py
```

No Linux, use `python3` no lugar de `python` se necessário.

## Nova partida

Veja "Fim de jogo e nova partida" na seção Controles.

## Gerar o modelo 3D da árvore

O jogo pode gerar o modelo Art Nouveau da árvore fotovoltaica em formato OBJ/MTL
(`solarpunk_tree_alphonse.obj` e `.mtl`).

- **Executável** (Windows): `EcoRunner.exe --generate-3d`
  grava em `%APPDATA%\EcoRunner\modelos_3d\` e mostra uma janela com os caminhos dos arquivos.
- **Python**: `python eco_runner.py --generate-3d`
  grava em `modelos_3d/`, dentro da pasta do projeto.
- Para escolher outra pasta, acrescente `--output-dir PASTA`, por exemplo:
  `EcoRunner.exe --generate-3d --output-dir C:\Modelos`.

## Onde ficam o recorde, os logs e os relatórios

| Como o jogo roda | Pasta de dados |
|---|---|
| Executável no Windows | `%APPDATA%\EcoRunner\` |
| Executável no Linux | `~/.local/share/EcoRunner/` (ou `$XDG_DATA_HOME/EcoRunner/`) |
| Python | `save/` dentro do projeto, se for gravável; caso contrário, a pasta do sistema |

Arquivos gerados nessa pasta:

- `eco_runner_recorde.json`: os recordes (`recorde` = Difícil, `recorde_normal` = Normal), a carteira da
  loja (`pontos`) e os padrões comprados.
- `eco_runner_config.json`: o avião e o piloto escolhidos no hangar (chaves `aviao` e `piloto`), a cor
  e o padrão de pintura de cada avião (chaves `cores` e `padroes`), o controle (`controle`) e o modo
  de jogo (`modo`: `normal` ou `dificil`).
- `eco_runner_erro.log`: detalhes técnicos quando o jogo fecha por erro inesperado.
  A mensagem de erro indica esse arquivo.
- `self_test.json`: relatório do `--self-test`.

Se existir um `eco_runner_recorde.json` ao lado do script (de versões anteriores), ele também é lido,
e vale o maior recorde encontrado entre os dois. Os novos recordes são gravados só na pasta de dados.
A variável de ambiente `ECO_RUNNER_DATA_DIR` substitui essa pasta.

## Teste de fumaça (`--self-test`)

```bash
EcoRunner.exe --self-test 60
```

Passa pelo hangar e pela Oficina de pintura (testa uma cor e um padrão, sem alterar a pintura salva), inicia
uma partida, desenha cada manobra em três fases e roda N quadros (padrão: 180) com comandos simulados nas
quatro direções. Grava `self_test.json` com versões, caminhos, sprites carregados e status. Serve para
verificar se um executável empacotado abre e roda. Não testa a jogabilidade.

## Como recompilar

Requisitos para o build: Python 3 (recomendado 3.10 a 3.13, versões para as quais o Pygame 2.6 publica pacotes prontos) e internet (para baixar `requirements-build.txt`). Se o `pip` tentar compilar o Pygame a partir do código-fonte, instale uma dessas versões do Python.

**Windows** (rode no Windows, dentro da pasta do projeto):

```bat
build_windows.bat
build_windows.bat onefile
build_windows.bat nopause
```

- `build_windows.bat` gera `dist\EcoRunner\EcoRunner.exe` (onedir, recomendado).
- `onefile` gera o arquivo único `dist\EcoRunner.exe`.
- `nopause` não espera tecla no final, útil em automação. Os argumentos podem ser combinados.

**Linux**:

```bash
./build_linux.sh
```

Gera `dist/EcoRunner/EcoRunner` (somente onedir).

Os dois scripts apagam `build/` e `dist/` antes de gerar. Eles criam o `.venv` na primeira execução,
instalam `requirements-build.txt` e rodam o `--self-test`. O `.venv` do Windows e o do Linux não devem ser compartilhados.

O PyInstaller não faz compilação cruzada: o `.exe` precisa ser gerado no Windows, e o binário Linux no Linux.
Para manter a janela de console (útil para depurar), defina `ECO_CONSOLE=1` antes do build.

## Sprites

Os sprites são PNGs opcionais. Cada arquivo é procurado separadamente, então um sprite faltando não
impede o jogo de abrir.

| Pasta | Arquivos `.png` esperados | Gerado por | Se faltar |
|---|---|---|---|
| `plane_sprites/` | `<modelo>__<piloto>.png`: avião visto de trás, usado na partida (além de `catalog.json`) | `extract_planes.py` | usa o mesmo avião sem piloto (`<modelo>__none`); se também faltar, desenha o avião por código |
| `plane_menu/` | `<modelo>__<piloto>.png`: avião em 3/4, usado no hangar | `extract_planes.py` | desenha o avião por código |
| `plane_paint/` e `plane_menu_paint/` | `<modelo>__<piloto>.png`: camada de pintura (o papel visível em branco), do mesmo tamanho do sprite correspondente | `extract_planes.py` | a cor escolhida não aparece no sprite (o avião fica com as cores originais) |
| `plane_uv/` e `plane_menu_uv/` | `<modelo>__<piloto>.png`: mapa UV do papel (R = coluna, G = linha da textura), do mesmo tamanho do sprite correspondente | `extract_planes.py` | o padrão não aparece; o avião usa a cor escolhida (ou as cores originais) |
| `plane_patterns/` | `<padrão>.png`: textura 256×256 de cada padrão de pintura | `extract_planes.py` | o padrão não aparece (miniatura com "?" na Oficina) |
| `maneuvers/` | `maneuvers.json`: curvas das manobras (giro, nariz, deslocamentos) | `extract_maneuvers.py` | usa curvas simples embutidas no código |
| `trash_sprites/` | `COL_Lixo_Cubo`, `COL_Lixo_Lata`, `COL_Lixo_Piramide`, `COL_Semente` (os 10 PNG antigos, como `rusty_can`, ainda estão na pasta, mas não são usados) | modelos do guia (`modelos_guia/`) | lixo desenhado como círculo |
| `solarpunk_sprites/` | `01_art_nouveau_solar_tree` até `10_arvore_cristalina` | `render_models.py` (grupo `trees`) | árvore desenhada por código |
| `dieselpunk_sprites/` | `fabrica`, `chamine`, `caldeira`, `tubos_valvula`, `tambores`, `lixo`, `sucata`, `cacamba` | `render_models.py` (grupo `props`); `fabrica`, `chamine`, `tambores` e `cacamba` vêm dos modelos do guia | props como retângulo escuro; obstáculos como blocos |
| `powerup_sprites/` | `shield`, `magnet`, `repair` | arquivos próprios | círculo colorido |
| `scenario_sprites/` | 31 PNG: 28 peças do kit Dieselpunk_Scenario, como `fuel_barrel` e `industrial_tower_a`, e 3 peças do guia (`SCN_*`). Lista completa em `SCENARIO_SPRITES`, no código | `render_models.py` (grupo `scenario`) para o kit; as peças `SCN_*` e `steam_pipe_corner` vêm dos modelos do guia | a peça é pulada; a fileira de fundo usa os props Dieselpunk e, sem eles, retângulos escuros |
| `skyline_sprites/` | `background_silo`, `distant_factory`, `power_pylon`, `industrial_tower_a`, `industrial_chimney`, `fixed_crane`, `pressure_tank`, `cargo_elevator` | `render_models.py` (grupo `scenario`) | silhueta do horizonte desenhada por código |
| `ground/` | `grass`, `concrete` | `make_grass_texture.py` e `make_concrete_texture.py` | sem grama: grama em duas cores lisas, alternadas por trecho; sem concreto: chão liso na cor da era |
| `atmosphere/` | `sky_panorama`, `smog_cloud` | copiados do kit por `render_models.py` (grupo `scenario`) | céu só em degradê, sem nuvens |

Os nomes dos arquivos são os mesmos usados pelo código: `<modelo>` é a chave do avião (por exemplo,
`dart`, `bis14`) e `<piloto>` é `none`, `riding`, `surfing`, `zen`, `waving`, `superman` ou `wheelchair`.

Há duas formas de usar sprites:

- **Embutidos no build**: coloque as pastas em `assets/<pasta>/` antes de gerar o executável.
- **Sem recompilar**: coloque as pastas em `<pasta do exe>\assets\<pasta>\` (ou, no Python, em `assets/<pasta>/` ao lado do script).
  Um PNG dessa pasta substitui o embutido.

**Jogar sem sprites**: remova as pastas que quiser de `assets/` antes do build,
ou apague essas pastas dentro de `_internal\assets\` no executável. O código desenha uma versão de reserva para cada sprite ausente.

A pasta `powerup_models/` contém OBJ/MTL de referência (escudo, ímã e reparo). Ela não é usada na partida:
o spec a copia para o pacote, mas o código não a carrega.

## Loja de padrões na Oficina (21/10/2026)

- Cada lixo coletado soma, além do placar da partida, numa **carteira de pontos** que acumula entre as partidas e fica salva junto do recorde (`pontos` em `eco_runner_recorde.json`, na pasta de dados do jogo).
- Na Oficina de pintura, os padrões (menos o Liso) aparecem com cadeado e preço. Dá para ver a prévia de qualquer padrão; confirmar (ENTER, ESPAÇO, C ou o gesto de salvar) num padrão com cadeado **compra** e desconta da carteira; confirmar de novo salva a pintura. Sem pontos suficientes, aparece quanto falta. As 15 cores continuam livres.
- Preços (`PATTERN_PRICES` no topo do `eco_runner.py`): Camuflado selva, deserto e ártico 300; Listras e Xadrez 500; Fibra hexagonal e Tigre 700; Chamas hot rod e Raios solares 900; Pop art e Prisma 1.100; Brasil 1.300; Cyberpunk 1.600; Chamas de plasma 1.800; Galáxia estelar 2.200.
- Padrão comprado vale para todos os aviões. Quem já usava um padrão antes da loja fica com ele liberado. O hangar e a tela de fim de jogo mostram a carteira.

### Texturas de papel na loja (21/10/2026)

- Entraram 10 texturas do pacote `texturas_aviao_papel` (`assets/plane_patterns/`, 512×512, reduzidas para 256 no carregamento, como os demais padrões): Kraft pardo, Papel reciclado, Folhas ecológicas, Caderno pautado, Jornal, Bolinhas, Listras de papel, Origami seigaiha, Planta técnica e Aquarela.
- Preços mais altos, de 2.500 a 6.000 pontos: Kraft pardo 2.500; Papel reciclado 2.800; Folhas ecológicas e Caderno pautado 3.000; Jornal e Bolinhas 3.500; Listras de papel 3.800; Origami seigaiha 5.000; Planta técnica 5.500; Aquarela 6.000.
- Ficaram de fora 5 texturas parecidas com padrões que já estavam na loja ou quase lisas: Xadrez de papel (igual ao Xadrez de corrida), Quadriculado (quase igual ao Caderno pautado), Folha branca (quase o liso), Vintage (muito parecida com o Papel reciclado) e Camuflagem de papel (camuflagem verde parecida com o Camuflado selva). Os 5 PNG correspondentes (`folha_branca`, `quadriculado`, `xadrez_papel`, `vintage`, `camuflagem`) não são mais carregados pelo jogo; podem ser apagados de `assets/plane_patterns/`.
- A chave `listras_papel` foi separada da `listras` já existente, para não substituir o arquivo atual.
- A Oficina mostra os padrões em duas fileiras de 13. A escolha com as setas segue a ordem da lista. O aviso de compra ocupa a linha do texto de escolha enquanto está na tela.
- Os padrões antigos que se parecem entre si (Chamas hot rod e Chamas de plasma; Xadrez de corrida e Listras de corrida, que são de cores diferentes) foram mantidos, porque quem já comprou algum deles perderia os pontos gastos.

## Transição de cenário suavizada (21/10/2026)

- O cenário (cores do céu e da pista, poluição, chão e margens) segue a restauração aos poucos: cada lixo coletado soma na hora no placar, mas o desenho alcança o valor em cerca de 3 s (`VISUAL_RESTORATION_TIME` = 2,8 s), sem degrau a cada coleta. Velocidade, placar e nome da era usam o valor real.
- A era verde chega **do horizonte para o avião**: a partir de 33,3% (no valor do cenário), os trechos de pista que entram lá longe, na neblina (além de `GREEN_CONVERT_Z`), passam a vir restaurados. A parcela de trechos restaurados sobe de 0 a 100% entre 33,3% e 63,3% (`GREEN_SWEEP_RESTORATION` = 30 pontos), espalhada ao longo da pista. Os trechos que já estavam perto continuam como estão até passar pelo avião; nada vira verde de repente na frente do jogador.
- Num trecho restaurado, a peça industrial afunda no chão e a árvore cresce enquanto o trecho vem chegando (`GREEN_GROW_DISTANCE`, cerca de 2 s); o chão do trecho vira grama junto.
- A pista passa da cor suja para a purificada com gradiente (`ROAD_PURIFY_BAND`), e as silhuetas do horizonte trocam com fade de 0,6 s (`SKYLINE_FADE_S`).
- Backup: pasta `eco_runner_backup_antes_transicao_20261021` (estado antes da primeira suavização) e `eco_runner_backup_transicao_etapa1_20261021` (primeira suavização, com o verde saindo da câmera), ao lado da pasta do jogo.

## Era final: cidade EcoUrbe Solarpunk (21/10/2026)

A última era (Era III desde a redução para 3 eras; restauração ≥ 66,7%) é a fase completa da cidade.
Ela chega por trechos, do horizonte para o avião, como a varredura verde (`FINAL_START_RESTORATION` =
2 × `ERA_SPAN`, `FINAL_SWEEP_RESTORATION` 10: em 76,7% todos os trechos novos já chegam na era final).
A grama e as árvores começam no início da Era II (33,3%) e o céu poluído some entre 15% e 45%.

- **Paralaxe em 3 camadas:** horizonte (fileira de trás vira a silhueta da cidade `FINAL_SKYLINE`),
  camada média 0,5 (prédios EcoUrbe alternados com árvores, `FINAL_MID_SPECS`, marco Edifício Art Nouveau
  1 a cada `FINAL_MARCO_A_CADA` trechos) e borda 0,8 (postes, floreiras, bancos, bicicletário, totem,
  estação e árvores, `FINAL_MARGIN_SPECS`). A peça antiga afunda enquanto a nova cresce.
- **Obstáculos novos** (`FINAL_OBSTACLE_SPECS`): por cima = Lótus Solar, Canteiro de Biorretenção, Compostor;
  por baixo = Passarela de Fauna, Pérgola, Viaduto Pomar, Arco Trepadeira; de lado = Torre Eólica, Cipreste
  Fotovoltaico, Torre Warka, Fotobiorreator. A colisão foi medida nos próprios sprites (vão livre dos
  portais ≥ 110; a Torre Eólica só tem o mastro na faixa de voo, por isso é estreita).
- **Coletável x colisão:** no Difícil, tudo que se pega tem halo ciano-dourado pulsante (o Normal não tem
  brilho); nos dois modos, tudo que colide tem chevrons
  âmbar pintados no chão da faixa e o friso dourado no modelo.
- **Decoração móvel (só visual):** dirigível solar e balões cruzando o céu, pássaros, bonde VLT no horizonte.
- **Chão com textura:** prado florido nas laterais (`assets/ground/meadow.png`) e pista de piso drenante
  com meio-fio dourado (`assets/ground/paver_road.png`).
- **Assets:** `assets/era_final_sprites/` (33 sprites renderizados dos modelos 3D EcoUrbe) e
  `assets/era_final_fx/` (halo, chevrons, ícones). Ambas as pastas entram no `.spec`.
- **Testes:** `tests/test_era_final.py`; modos em `tests/test_modos.py` (14). Sem as texturas novas, o jogo volta ao polígono liso.

## Modelos do guia aplicados (21/10/2026)

Nesta versão, alguns sprites foram trocados pelos modelos do guia de modelos (`modelos_guia/`):

- **Lixo coletável**: eram 10 modelos de sucata; agora são 4 (`COL_Lixo_Cubo`, `COL_Lixo_Lata`, `COL_Lixo_Piramide` e `COL_Semente`). Os 10 PNG antigos continuam em `trash_sprites/`, sem uso.
- **Sprites com o mesmo nome, substituídos**: `fabrica`, `chamine`, `tambores` e `cacamba` (em `dieselpunk_sprites/`) e `steam_pipe_corner` (em `scenario_sprites/`).
- **Sprites novos** em `scenario_sprites/`: `SCN_CaixaIndustrial_Cenario`, `SCN_Galpao_Restaurado` e `SCN_TorreChamine_Restaurada` (ver "Quais modelos aparecem onde").
- **Alturas**: na fileira de fundo, a fábrica foi de 250 para 186 e os tambores de 165 para 119. Na borda, `steam_pipe_corner` foi de 76 para 70. Os obstáculos mantêm altura e colisão.

**Backup do estado anterior**: pasta `eco_runner_backup_original_20261021`, ao lado da pasta do jogo. Ela guarda os arquivos que foram sobrescritos: `eco_runner.py`, `README.md`, `tests/test_eco_runner.py`, os 4 PNG de `assets/dieselpunk_sprites/` (`fabrica`, `chamine`, `tambores`, `cacamba`) e `assets/scenario_sprites/steam_pipe_corner.png`.

**Como voltar ao estado anterior**: copie o conteúdo da pasta de backup por cima da pasta do jogo, mantendo a mesma estrutura. Os 7 PNG novos (`COL_*` em `trash_sprites/` e `SCN_*` em `scenario_sprites/`) podem ficar ou ser apagados: o código antigo não os usa, mas eles entram no pacote do PyInstaller se ficarem.

## Regenerar os sprites a partir dos modelos

Os sprites já vêm prontos em `assets/`. Os scripts de `tools/` servem só para regenerá-los quando os
modelos 3D ou o estúdio mudarem. Eles não são necessários para jogar nem para gerar o `.exe`.

Instale as dependências dos scripts (separadas das do jogo):

```bash
pip install -r tools/requirements-tools.txt
python -m playwright install chromium    # só para extract_planes.py
```

`tools/requirements-tools.txt` traz numpy, Pillow e playwright. O `extract_planes.py` abre o HTML do
estúdio num Chromium sem janela, pelo Playwright.

### Cenário, lixo e árvores: `tools/render_models.py`

```bash
python tools/render_models.py --models PASTA_MODELOS_3D [--only GRUPOS] [--out PASTA_ASSETS]
```

- `--models`: pasta com os OBJ/MTL (`modelos_3d`). Obrigatório. Se houver `texturas/textura_rusty_scrap_dieselpunk.jpg`
  dentro dela, os modelos de sucata usam essa textura.
- `--only`: renderiza só os grupos indicados: `trees`, `props`, `trash` e `scenario`. Sem `--only`, gera tudo.
- `--scenario`: pasta do kit `Dieselpunk_Scenario`. O padrão é `PASTA_MODELOS_3D/Dieselpunk_Scenario`.
  O grupo `scenario` gera `scenario_sprites/` (as 28 peças do kit; as 3 `SCN_*` do guia não são geradas aqui), `skyline_sprites/` (8 silhuetas) e copia o
  panorama do céu e a nuvem de fumaça para `atmosphere/`.
- `--out`: pasta de saída. O padrão é a `assets/` do projeto.

Os pilotos (boneco) não são gerados aqui: eles vêm do próprio estúdio de aviões, por `extract_planes.py`,
já posicionados em cima de cada avião.

### Grama: `tools/make_grass_texture.py`

```bash
python tools/make_grass_texture.py [--out assets/ground/grass.png] [--seed 7]
```

Gera a textura de grama do chão (256x128, contínua nas bordas, vista de cima). Mude `--seed` para
outra variação. Usa numpy e Pillow.

### Concreto: `tools/make_concrete_texture.py`

```bash
python tools/make_concrete_texture.py [--out assets/ground/concrete.png] [--seed 11]
```

Gera a textura de concreto sujo do chão (256x128, contínua nas bordas, vista de cima). Mude `--seed`
para outra variação. Usa numpy e Pillow.

### Aviões e pilotos: `tools/extract_planes.py`

```bash
python tools/extract_planes.py --html ESTUDIO.html --three three.min.js --jszip jszip.min.js
```

- `--html`: o arquivo HTML do "Estúdio 3D Aviões, 14-Bis & Piloto Customizável".
- `--three`: three.js r128 (`three.min.js`). Pode vir do npm: `npm install three@0.128.0` e use
  `node_modules/three/build/three.min.js`.
- `--jszip`: JSZip 3.10.1 (`npm install jszip@3.10.1` e use `node_modules/jszip/dist/jszip.min.js`).
- `--out`: pasta de saída. O padrão é a `assets/` do projeto.
- `--game-size` (padrão 300) e `--menu-size` (padrão 260): tamanho em pixels dos sprites da partida e do hangar.

- `--models` e `--pilots`: gera só os modelos e pilotos indicados (padrão: todos).
- `--passes`: o que gravar entre `sprites`, `paint` e `uv` (padrão: tudo).

Gera 77 sprites em `plane_sprites/` e 77 em `plane_menu/` (11 aviões × 7 pilotos), além de
`plane_sprites/catalog.json` com os nomes dos modelos e dos pilotos. Para cada sprite, gera também a
camada de pintura em `plane_paint/` e `plane_menu_paint/`: o mesmo avião, com a mesma câmera e o mesmo
recorte, com o papel em branco e transparente onde aparecem o piloto e as peças que não são de papel. O
jogo multiplica essa camada pela cor escolhida na Oficina de pintura.

Gera ainda o **mapa UV** de cada sprite em `plane_uv/` e `plane_menu_uv/`: cada pixel do papel guarda a
coordenada da textura do estúdio naquele ponto (R = coluna, G = linha). As 15 texturas dos padrões vão
para `plane_patterns/`, desenhadas pela própria função do estúdio (`drawSchemeBackground`) com as
cores dos presets dele. O jogo consulta a textura pelo mapa UV pixel a pixel, então cada padrão segue
as dobras do avião sem precisar de uma imagem por padrão e por combinação. Leva cerca de 25 minutos.

Os sprites atuais foram gerados com o estúdio do pacote "novos aviões refinados"
(`Codigo_Fonte_Aplicacao_3D/estudio_avioes_14bis_e_piloto_3d.html` dentro do .zip).

Depois de regenerar os sprites, recompile o jogo para embuti-los, ou copie os PNGs para a pasta do executável.

### Manobras: `tools/extract_maneuvers.py`

```bash
python tools/extract_maneuvers.py --gltf-dir CAMINHO/01_Animacoes_3D_Prontas_GLTF_8_Manobras
```

Lê as animações glTF do pacote (posição e rotação do avião quadro a quadro) e grava
`assets/maneuvers/maneuvers.json`. Para cada manobra usada no jogo, recorta um ciclo (o giro de 360° do
tonneau, a volta completa do looping, a animação inteira da cobra e o final da decolagem) e o converte
para o referencial do avião: `roll` (giro), `pitch` (nariz), `dx`, `dy` e `dz` (deslocamentos
normalizados). O ciclo é ajustado para começar e terminar na posição normal. O jogo aplica essas
curvas ao sprite visto de trás: roll vira rotação, pitch vira achatamento (e inversão no topo do
looping), dx/dy viram deslocamento na tela e dz vira escala. Duração e amplitude de cada manobra no
jogo ficam em `MANEUVER_STYLES` (`eco_runner.py`). Não precisa de dependências além do Python.

## Alertas de antivírus e SmartScreen

Executáveis gerados com PyInstaller costumam receber alertas de falso positivo do antivírus ou do
Windows SmartScreen. Para reduzir o problema:

- Prefira o modo **onedir** (padrão do `build_windows.bat`).
- **Assine digitalmente** o executável com um certificado de assinatura de código.
- Se o antivírus bloquear o arquivo, envie-o para análise ao fornecedor do antivírus.

## Estrutura da pasta

```
eco_runner/
├── eco_runner.py           código do jogo, gerador 3D e --self-test
├── EcoRunner.spec          configuração do PyInstaller
├── requirements.txt        dependências para executar (pygame)
├── requirements-webcam.txt dependências opcionais do controle pela webcam (mediapipe, opencv)
├── webcam_control.py       controle pela webcam: leitura da câmera, calibração e eixos do voo
├── requirements-build.txt  dependências para gerar o executável (pygame + pyinstaller)
├── build_windows.bat       build no Windows
├── build_linux.sh          build no Linux
├── tests/                  testes automatizados (pytest)
├── tools/                  scripts para regenerar os sprites (não usados pelo jogo)
│   ├── render_models.py    modelos OBJ -> sprites de árvores, props, sucata e cenário
│   ├── extract_planes.py   estúdio de aviões (HTML + three.js) -> sprites, pintura, mapas UV e padrões
│   ├── extract_maneuvers.py  animações glTF do pacote -> curvas das manobras
│   ├── make_grass_texture.py     textura de grama do chão
│   ├── make_concrete_texture.py  textura de concreto sujo do chão
│   └── requirements-tools.txt
├── README.md
├── assets/
│   ├── plane_sprites/      aviões vistos de trás, com piloto (usados na partida)
│   ├── plane_menu/         aviões em 3/4 (hangar)
│   ├── plane_paint/        camadas de pintura dos aviões vistos de trás (Oficina de pintura)
│   ├── plane_menu_paint/   camadas de pintura dos aviões em 3/4
│   ├── plane_uv/           mapas UV do papel (vista de trás) para os padrões de pintura
│   ├── plane_menu_uv/      mapas UV do papel (vista 3/4)
│   ├── plane_patterns/     15 texturas de padrões de pintura do estúdio
│   ├── maneuvers/          curvas das manobras (maneuvers.json)
│   ├── trash_sprites/      4 modelos de lixo coletáveis
│   ├── solarpunk_sprites/  10 árvores (Era II)
│   ├── dieselpunk_sprites/ 8 props (margens da Era I e obstáculos)
│   ├── powerup_sprites/    escudo, ímã e reparo
│   ├── scenario_sprites/   31 peças: 28 do kit Dieselpunk_Scenario e 3 do guia (margens e fileira de fundo)
│   ├── skyline_sprites/    silhuetas do horizonte (kit Dieselpunk_Scenario)
│   ├── atmosphere/         panorama do céu poluído e nuvem de fumaça
│   ├── ground/             texturas do chão: grama e concreto sujo
│   └── powerup_models/     OBJ/MTL de referência (não usados na partida)
└── save/                   recorde ao rodar pelo Python (criada automaticamente)
```

`build/`, `dist/` e `.venv/` são gerados pelo build e podem ser apagados.

## Testes

A suíte de testes está em `tests/` (pytest) e roda sem janela nem áudio.
Não está incluída em `requirements.txt`, então instale o pytest antes:

```bash
pip install pytest
python -m pytest tests
```

A suíte cobre hangar, voo nas quatro direções, limites, colisões de cada tipo de obstáculo, coleta
em alturas diferentes, power-ups, recorde, seleção salva, fallbacks sem sprites, cenário em camadas
(trechos da pista estáveis ao serem reciclados, neblina, concreto na fase inicial, grama a partir da
frente de restauração, desenho em todas as eras, pastas no spec), Oficina de pintura (prévia, cancelar,
confirmar, cor e padrão salvos por avião, tinta e padrão só no papel, padrão sem mapa UV), manobras
(curvas do pacote, reserva sem o JSON, disparo por power-up e na decolagem, colisão inalterada,
looping invertido no topo), `--generate-3d` e `--self-test`
(133 testes aprovados e 1 comportamento conhecido marcado como `xfail`).

Para validar um executável empacotado, use também o `--self-test` descrito acima.

### Checklist manual (no Windows, com o `.exe`)

Os testes automáticos não substituem voar de verdade. Depois de cada build, confira:

1. `EcoRunner.exe` abre por duplo clique, sem console, numa janela de 1100x650, e mostra o hangar.
2. No hangar, ←/→ e A/D trocam o avião pelos 11 modelos; ↑/↓ e W/S trocam o piloto pelas 7 opções; ENTER ou ESPAÇO decola.
   C abre a Oficina de pintura: ←/→ mudam a cor na prévia (o piloto não muda de cor), ↓ vai para os padrões
   (camuflado, chamas, galáxia...) e ↑ volta às cores; ENTER confirma, ESC cancela.
   Decole e confira que o avião voa com a pintura escolhida; feche e reabra o jogo e confira que cada avião manteve a sua.
3. No voo, cada direção responde: ←/A esquerda, →/D direita, ↑/W/ESPAÇO sobem, ↓/S descem. O avião inclina ao se mover para os lados.
4. Voando acima de cerca de ALT 97 (ou 113 para a caçamba e 117 para os tambores), tambores, caçamba, sucata e monte de lixo não colidem. Abaixo desses valores, o avião colide.
5. A rede de tubos com válvula colide acima de cerca de ALT 88 e não colide abaixo dela.
6. Chaminé e caldeira colidem em qualquer altura; desviando para o lado, não colidem.
7. Pegue lixo nas três alturas (baixa, média e alta), voando na altura de cada um: cada coleta soma pontos e restauração.
8. Bater tira uma vida (a tela pisca). Escudo, ímã (coleta lixo perto do avião) e reparo funcionam.
   Ao pegar cada um, o avião faz a manobra: looping (escudo), tonneau (ímã) e cobra (reparo); ao decolar, a decolagem.
9. Após 3 colisões aparece "FIM DE JOGO"; ENTER ou ESPAÇO voa de novo com o mesmo avião; C ou TAB volta ao hangar.
10. Na pausa (P ou ESC), C ou TAB volta ao hangar.
11. Feche e reabra o jogo: o recorde (`%APPDATA%\EcoRunner\eco_runner_recorde.json`) e a escolha de avião e piloto (`eco_runner_config.json`) continuam os mesmos.
12. `EcoRunner.exe --generate-3d` mostra a mensagem com os caminhos do `.obj` e do `.mtl`.
13. Copie a pasta `EcoRunner` para um caminho com espaços (ex.: `C:\Jogos Teste\Eco Runner\`) e para um PC sem Python, e repita o item 1.
14. Numa cópia, apague `_internal\assets\ground`, `_internal\assets\dieselpunk_sprites`, `_internal\assets\plane_sprites`, `_internal\assets\trash_sprites`, `_internal\assets\scenario_sprites`, `_internal\assets\skyline_sprites` e `_internal\assets\atmosphere`, e confira que o jogo abre com os desenhos de reserva.
15. Mova o avião de um lado para o outro: a pista desliza mais que as margens, a fileira de fundo menos que a da borda, e as silhuetas do horizonte e o céu quase não se movem.
16. Durante o voo, as faixas da pista e os objetos das margens deslizam sem piscar nem trocar de lugar, e os objetos surgem aos poucos na neblina, sem aparecer de repente no fim da pista.
17. Com a restauração subindo, o céu poluído e a fumaça somem aos poucos e as silhuetas do horizonte viram árvores.
18. Ao passar de 33,3% de restauração, o chão fora da pista vira grama do avião até onde as árvores começam; a grama desliza junto com a pista e chega mais longe conforme a restauração sobe.
19. Na fase inicial, o chão fora da pista é concreto sujo (placas, juntas, manchas de óleo e rachaduras) e desliza junto com a pista; depois de 33,3%, o concreto continua só além da grama.
20. Numa cópia, apague `_internal\assets\plane_uv` e `_internal\assets\maneuvers`: a Oficina continua abrindo (o padrão não aparece e o avião fica com a cor) e as manobras usam as curvas de reserva.
21. Com a câmera (V no hangar), a barra de calibração aparece no status; depois de calibrar, "pessoa detectada" (modo corpo) ou "mão detectada" (modo uma mão) aparece.
22. Modo corpo: inclinar o corpo de leve troca o avião e o piloto no hangar, um passo por inclinação; levantar a mão direita decola; a mão esquerda abre a Oficina.
23. Modo corpo, na Oficina: inclinar escolhe cor e padrão, a mão direita salva e a esquerda cancela.
24. Modo uma mão: mão para os lados troca o avião, para cima troca o piloto, para baixo abre a Oficina, levantada decola. Na Oficina, para cima alterna cores e padrões.
25. Modo uma mão, no voo: o avião segue a mão; no fim de jogo, mão levantada voa de novo e mão para baixo volta ao hangar.
26. Sem a câmera ou sem as bibliotecas, o hangar mostra o motivo e o teclado continua funcionando.
