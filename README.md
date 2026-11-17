# CorTEA

Exergame de projeção no solo para crianças com Transtorno do Espectro Autista (TEA), desenvolvido para a plataforma [T-TEA](https://github.com/larvattea/ttea).

O jogo projeta no chão uma grade de 12 quadrados coloridos, mostra um caminho de cores e pede que a criança o reproduza pisando nos quadrados na ordem certa. Os pés são detectados por uma webcam com MediaPipe e levados até a área projetada pela calibração câmera–projetor da plataforma.

Projeto Integrador II – Curso Técnico em Desenvolvimento de Sistemas, IFSC Câmpus Jaraguá do Sul – Rau, 2026.

- Autores: Ighor Henrique Lima Barbosa e Leonardo Rodrigues Martins
- Orientador: Alexandre Altair de Melo

## Como se joga

1. Um caminho de quadrados acende, um de cada vez, com uma nota musical.
2. Na vez do jogador, ele pisa nos quadrados na mesma ordem. Para selecionar, basta ficar parado sobre o quadrado por cerca de 0,7 s: o anel em volta do quadrado vai se completando. Passar por cima de um quadrado no caminho não conta como resposta.
3. Cada acerto tem reforço visual e sonoro. O erro tem uma mensagem neutra, sem punição.
4. Se o jogador ficar 6 s parado, o próximo quadrado pisca (ajuda).
5. Ao fim de cada fase, o índice de desempenho decide se o jogador avança ou repete a fase. São oito fases de dificuldade crescente.

## Instalação

O CorTEA roda dentro da plataforma T-TEA.

1. Baixe e configure a plataforma seguindo o README do repositório [larvattea/ttea](https://github.com/larvattea/ttea) (Python 3.10 a 3.12 e uv).
2. Copie todo o conteúdo deste repositório para a pasta `src/ttea/games/cortea` da plataforma. O nome da pasta deve ser `cortea`, em minúsculas.
3. Na pasta da plataforma, execute:

   ```bash
   uv run dev
   ```

4. Faça a calibração câmera–projetor na plataforma, selecione o jogador e o profissional e abra o CorTEA.

Para testar sem a plataforma, com o mouse:

```bash
uv run python src/ttea/games/cortea/cortea.py --lang pt_BR
```

## Teclas

| Tecla | Função |
|-------|--------|
| F2 | Jogar |
| F3 | Continuar (pausa) |
| F4 / F6 | Retroceder / avançar fase (pausa) |
| F5 | Reiniciar (tela de conclusão) |
| F7 | Sair (na partida, pede confirmação; na tela inicial, fecha o jogo) |
| F8 / F9 | Configurações / Controles |
| Esc | Pausar, continuar ou voltar |
| C | Mostra a imagem da câmera com a detecção dos pés |
| H | Painel do terapeuta (acertos, erros, índice, ajudas, tempo) |
| M | Liga ou desliga o som |
| F11 | Alterna a tela cheia |

No menu Controles, os botões **Espelho** e **Detecção** espelham a imagem da câmera e alternam entre detecção dos pés e das mãos.

## Configuração

O arquivo `cortea.ini` reúne os parâmetros ajustáveis: fase inicial, tempo de permanência, ajudas, som, câmera, modo de detecção, visibilidade mínima dos pés, uso da calibração, tela cheia e monitor. Cada opção está comentada no próprio arquivo.

## Relatórios

Cada sessão gera um arquivo `relatorio_cortea_<id_jogador>_<data>.csv` na pasta de exportação da plataforma (`data/exports`), com uma linha por tentativa de fase: `id_sessao`, `nome_usuario`, `data_hora`, `acertos`, `erros`, `acertos_consecutivos`, `fase` e `tempo_medio_resposta`.

## Estrutura

| Pasta | Conteúdo |
|-------|----------|
| `cortea.py` | Ponto de entrada e laço principal |
| `gamecontroller/` | Controle da partida, fases e telas |
| `gamecore/` | Câmera, detecção com MediaPipe, calibração, seleção por permanência e sons |
| `gamemodel/` | Sessão, atividade, desempenho e sistema de ajuda |
| `gameview/`, `gameui/` | Menus, botões e desenho das telas |
| `gameutil/` | Configurações, textos em três idiomas e gravação do CSV |

## Observação para Windows

No Windows, o MediaPipe pode falhar com `DLL load failed while importing _framework_bindings` quando é carregado antes da PySide6. O arquivo `gamecore/rastreamento.py` já carrega a PySide6 primeiro para evitar esse erro.
