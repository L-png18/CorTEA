import math
import random
from typing import Dict, Optional

import pygame
from ttea.games.cortea.gameui import UI
from ttea.games.cortea.gameutil import (
    GameSettings,
    GameState,
    formatar_tempo,
    t,
)


class Menu:
    """Desenha e trata cliques de todas as telas fora da partida: início,
    configurações, controles, pausa, confirmação de saída e conclusão.

    Cada tela é um conjunto de botões identificados por uma *ação* (texto
    curto como ``"jogar"``). O mesmo conjunto serve ao mouse (clique) e à
    mão do jogador (permanência sobre o botão).
    """

    def __init__(self, surface: pygame.Surface):
        self.surface = surface
        self._centro = GameSettings.SCREEN_WIDTH // 2
        self._botoes = self._criar_botoes()
        self.barra_volume = pygame.Rect(285, 270, 230, 50)
        self._fundo_inicio = self._criar_fundo_inicio()

    def _criar_botoes(self) -> Dict[str, Dict[str, pygame.Rect]]:
        cx = self._centro
        altura = GameSettings.SCREEN_HEIGHT
        R = pygame.Rect
        return {
            GameState.INICIO: {
                "jogar": R(cx - 135, 296, 270, 58),
                "configuracoes": R(cx - 135, 368, 270, 46),
                "controles": R(cx - 135, 424, 270, 46),
                "fechar": R(cx - 135, 480, 270, 46),
            },
            GameState.CONFIGURACOES: {
                "volume_menos": R(230, 270, 55, 50),
                "volume_mais": R(515, 270, 55, 50),
                "som": R(cx - 105, 385, 210, 46),
                "voltar": R(cx - 105, altura - 85, 210, 46),
            },
            GameState.CONTROLES: {
                "espelhar": R(cx - 150, 388, 300, 46),
                "modo": R(cx - 150, 446, 300, 46),
                "voltar": R(cx - 105, altura - 85, 210, 46),
            },
            # Pausa (Fig. 16 do artigo): cruz com Continuar em cima
            GameState.PAUSADO: {
                "continuar": R(cx - 120, 250, 240, 50),
                "retroceder": R(cx - 370, 310, 240, 50),
                "avancar": R(cx + 130, 310, 240, 50),
                "sair": R(cx - 120, 370, 240, 50),
                "som": R(20, 20, 190, 44),
                "volume_menos": R(20, 76, 55, 40),
                "volume_mais": R(155, 76, 55, 40),
            },
            GameState.CONFIRMAR_SAIDA: {
                "sim": R(cx - 215, 330, 190, 56),
                "nao": R(cx + 25, 330, 190, 56),
            },
            # Conclusão (Fig. 17): Sair à esquerda, Reiniciar à direita
            GameState.CONCLUSAO: {
                "sair": R(60, altura - 100, 230, 52),
                "reiniciar": R(GameSettings.SCREEN_WIDTH - 290, altura - 100, 230, 52),
            },
        }

    # ====================== Teclas de atalho ======================
    # Mesmo padrão do KarTEA: a tecla aparece entre colchetes no botão
    # (Jogar [F2], Continuar [F3], Retroceder [F4], Reiniciar [F5],
    # Avançar [F6], Sair [F7]).
    ATALHOS = {
        GameState.INICIO: {
            "jogar": pygame.K_F2,
            "configuracoes": pygame.K_F8,
            "controles": pygame.K_F9,
            "fechar": pygame.K_F7,
        },
        GameState.CONFIGURACOES: {"voltar": pygame.K_ESCAPE},
        GameState.CONTROLES: {"voltar": pygame.K_ESCAPE},
        GameState.PAUSADO: {
            "continuar": pygame.K_F3,
            "retroceder": pygame.K_F4,
            "avancar": pygame.K_F6,
            "sair": pygame.K_F7,
        },
        GameState.CONFIRMAR_SAIDA: {"sim": pygame.K_F7, "nao": pygame.K_ESCAPE},
        GameState.CONCLUSAO: {"reiniciar": pygame.K_F5, "sair": pygame.K_F7},
    }
    NOMES_TECLAS = {
        pygame.K_ESCAPE: "Esc",
        pygame.K_F2: "F2",
        pygame.K_F3: "F3",
        pygame.K_F4: "F4",
        pygame.K_F5: "F5",
        pygame.K_F6: "F6",
        pygame.K_F7: "F7",
        pygame.K_F8: "F8",
        pygame.K_F9: "F9",
    }

    def acao_da_tecla(self, estado: str, tecla: int) -> Optional[str]:
        """Ação do botão cuja tecla de atalho é ``tecla``, ou ``None``."""
        for acao, atalho in self.ATALHOS.get(estado, {}).items():
            if atalho == tecla:
                return acao
        return None

    def rotulo(self, estado: str, acao: str, texto: str) -> str:
        """Texto do botão com a tecla de atalho entre colchetes."""
        tecla = self.ATALHOS.get(estado, {}).get(acao)
        if tecla is None:
            return texto
        return f"{texto} [{self.NOMES_TECLAS[tecla]}]"

    # ====================== Botões / cliques ======================
    def botoes(self, estado: str) -> Dict[str, pygame.Rect]:
        """Ação -> retângulo de cada botão da tela."""
        return self._botoes.get(estado, {})

    def habilitado(self, estado: str, acao: str, controle) -> bool:
        """Retroceder/Avançar ficam apagados nas fases das pontas."""
        if estado == GameState.PAUSADO:
            if acao == "retroceder":
                return controle.pode_retroceder
            if acao == "avancar":
                return controle.pode_avancar
        return True

    def acao_em(self, estado: str, pos: tuple) -> Optional[str]:
        """Ação do botão sob ``pos`` (ou ``"barra_volume"``), ou ``None``."""
        for acao, retangulo in self.botoes(estado).items():
            if retangulo.collidepoint(pos):
                return acao
        if estado == GameState.CONFIGURACOES and self.barra_volume.collidepoint(pos):
            return "barra_volume"
        return None

    def ajustar_volume(self, acao: str, pos: tuple = (0, 0)) -> None:
        """Aplica uma ação de volume e avisa os sons."""
        if acao == "volume_menos":
            GameSettings.VOLUME = max(0.0, GameSettings.VOLUME - 0.1)
        elif acao == "volume_mais":
            GameSettings.VOLUME = min(1.0, GameSettings.VOLUME + 0.1)
        elif acao == "barra_volume":
            GameSettings.VOLUME = max(
                0.0,
                min(
                    1.0,
                    (pos[0] - self.barra_volume.left) / self.barra_volume.width,
                ),
            )
        GameSettings.VOLUME = round(GameSettings.VOLUME, 2)

    # ====================== Desenho ======================
    def draw(
        self,
        estado: str,
        progresso: Optional[Dict[object, float]] = None,
        controle=None,
    ) -> None:
        """Desenha a tela do ``estado``. ``progresso`` traz a permanência da
        mão sobre cada botão e ``controle`` é o ``GameController``."""
        self._progresso = progresso or {}
        self._controle = controle
        if estado == GameState.INICIO:
            self._draw_inicio()
        elif estado == GameState.CONFIGURACOES:
            self._draw_configuracoes()
        elif estado == GameState.CONTROLES:
            self._draw_controles()
        elif estado == GameState.PAUSADO:
            self._draw_pausado()
        elif estado == GameState.CONFIRMAR_SAIDA:
            self._draw_confirmar()
        elif estado == GameState.CONCLUSAO:
            self._draw_conclusao()

    def _botao(self, estado: str, acao: str, texto: str) -> None:
        habilitado = True
        if self._controle is not None:
            habilitado = self.habilitado(estado, acao, self._controle)
        UI.button(
            self.surface,
            self.botoes(estado)[acao],
            self.rotulo(estado, acao, texto),
            progresso=self._progresso.get(("acao", acao), 0.0),
            habilitado=habilitado,
        )

    # Tela inicial: o título é feito de quadrados, um por cor da paleta (como
    # os quadrados da grade). Em volta, um mosaico bem claro com as mesmas
    # cores. Se ``INICIO_ANIMADO``, as letras levantam uma a uma, devagar,
    # lembrando o caminho que o jogo mostra.
    _TITULO_LADO = 100
    _TITULO_VAO = 12
    _TITULO_Y = 120
    _PASSO_LETRA_MS = 650
    _PAUSA_CICLO_MS = 2200

    def _criar_fundo_inicio(self) -> pygame.Surface:
        """Mosaico de quadrados bem claros nas cores do jogo (desenhado uma
        única vez; o desenho é sempre o mesmo). Quase some no centro, onde
        ficam o título e os botões, e aparece mais nas bordas."""
        largura = GameSettings.SCREEN_WIDTH
        altura = GameSettings.SCREEN_HEIGHT
        lado, vao = 52, 8
        passo = lado + vao
        colunas = largura // passo + 2
        linhas = altura // passo + 2
        x0 = (largura - (colunas * passo - vao)) // 2
        y0 = (altura - (linhas * passo - vao)) // 2

        fundo = pygame.Surface((largura, altura))
        fundo.fill(GameSettings.COR_FUNDO)
        sorteio = random.Random(7)
        paleta = GameSettings.PALETA
        escolhidas: Dict[tuple, int] = {}
        for linha in range(linhas):
            for coluna in range(colunas):
                vizinhas = {
                    escolhidas.get((linha, coluna - 1)),
                    escolhidas.get((linha - 1, coluna)),
                }
                opcoes = [i for i in range(len(paleta)) if i not in vizinhas]
                cor_i = sorteio.choice(opcoes)
                escolhidas[(linha, coluna)] = cor_i
                x = x0 + coluna * passo
                y = y0 + linha * passo
                distancia = math.hypot(
                    x + lado / 2 - largura / 2, y + lado / 2 - altura / 2
                ) / math.hypot(largura / 2, altura / 2)
                clareza = 0.95 - 0.12 * min(1.0, distancia)
                pygame.draw.rect(
                    fundo,
                    UI.misturar(paleta[cor_i], (255, 255, 255), clareza),
                    (x, y, lado, lado),
                    border_radius=12,
                )
        return fundo

    def _letra_acesa(self, quantidade: int) -> tuple:
        """(índice da letra, de 0 a 1 o quanto ela está levantada)."""
        if not GameSettings.INICIO_ANIMADO or quantidade <= 0:
            return -1, 0.0
        passo = self._PASSO_LETRA_MS
        ciclo = quantidade * passo + self._PAUSA_CICLO_MS
        instante = pygame.time.get_ticks() % ciclo
        if instante >= quantidade * passo:
            return -1, 0.0
        return int(instante // passo), math.sin(math.pi * (instante % passo) / passo)

    def _draw_titulo_inicio(self) -> None:
        titulo = GameSettings.GAME_TITLE
        lado, vao = self._TITULO_LADO, self._TITULO_VAO
        total = len(titulo) * lado + (len(titulo) - 1) * vao
        x0 = (GameSettings.SCREEN_WIDTH - total) // 2
        acesa, subida = self._letra_acesa(len(titulo))
        paleta = GameSettings.PALETA

        for i, letra in enumerate(titulo):
            cor = paleta[i % len(paleta)]
            levantar = int(10 * subida) if i == acesa else 0
            if i == acesa:
                cor = UI.clarear_cor(cor, 0.3 * subida)
            x = x0 + i * (lado + vao)
            base = pygame.Rect(x, self._TITULO_Y, lado, lado)
            pygame.draw.rect(
                self.surface,
                UI.misturar(paleta[i % len(paleta)], (0, 0, 0), 0.4),
                base.move(0, 7),
                border_radius=18,
            )
            quadrado = base.move(0, -levantar)
            pygame.draw.rect(self.surface, cor, quadrado, border_radius=18)
            UI.draw_text(
                self.surface,
                letra,
                quadrado.center,
                UI.cor_texto_sobre(cor),
                GameSettings.FONTS["title"],
            )

    def _draw_inicio(self) -> None:
        """Tela inicial (Fig. 8): título em quadrados coloridos e botões."""
        self.surface.blit(self._fundo_inicio, (0, 0))
        self._draw_titulo_inicio()
        self._botao(GameState.INICIO, "jogar", t("jogar"))
        self._botao(GameState.INICIO, "configuracoes", t("configuracoes"))
        self._botao(GameState.INICIO, "controles", t("controles"))
        self._botao(GameState.INICIO, "fechar", t("sair"))

    def _draw_configuracoes(self) -> None:
        """Tela de configurações: volume e som ligado/desligado."""
        e = GameState.CONFIGURACOES
        cor_texto = GameSettings.COR_TEXTO

        UI.draw_text(
            self.surface,
            t("configuracoes"),
            (self._centro, 125),
            cor_texto,
            GameSettings.FONTS["title"],
        )
        UI.draw_text(
            self.surface,
            t("volume"),
            (self._centro, 225),
            cor_texto,
            GameSettings.FONTS["feedback"],
        )

        self._botao(e, "volume_menos", "-")
        self._botao(e, "volume_mais", "+")

        pygame.draw.rect(
            self.surface, (205, 205, 205), self.barra_volume, border_radius=10
        )
        preenchimento = pygame.Rect(
            self.barra_volume.left,
            self.barra_volume.top,
            int(self.barra_volume.width * GameSettings.VOLUME),
            self.barra_volume.height,
        )
        pygame.draw.rect(
            self.surface, (75, 75, 75), preenchimento, border_radius=10
        )
        UI.draw_text(
            self.surface,
            f"{round(GameSettings.VOLUME * 100)}%",
            (self._centro, 350),
            cor_texto,
        )
        self._botao(
            e,
            "som",
            t("som_ligado") if GameSettings.SOM_LIGADO else t("som_desligado"),
        )
        self._botao(e, "voltar", t("voltar"))

    def _draw_controles(self) -> None:
        """Desenha as teclas e suas funções."""
        cor_texto = GameSettings.COR_TEXTO
        UI.draw_text(
            self.surface,
            t("controles"),
            (self._centro, 85),
            cor_texto,
            GameSettings.FONTS["title"],
        )
        teclas = [
            ("ESC", t("ctrl_pausar")),
            ("F2–F9", t("ctrl_atalhos")),
            ("C", t("ctrl_camera")),
            ("H", t("ctrl_painel")),
            ("M", t("ctrl_som")),
            ("F11", t("ctrl_tela")),
        ]
        y = 132
        for rotulo, descricao in teclas:
            UI.key(self.surface, (200, y, 130, 36), rotulo)
            UI.draw_text(
                self.surface,
                descricao,
                (360, y + 18),
                cor_texto,
                anchor="midleft",
            )
            y += 40
        self._botao(
            GameState.CONTROLES,
            "espelhar",
            t("espelho_ligado")
            if GameSettings.ESPELHAR_CAMERA
            else t("espelho_desligado"),
        )
        self._botao(
            GameState.CONTROLES,
            "modo",
            t("modo_pes")
            if GameSettings.MODO_RASTREAMENTO == "pes"
            else t("modo_maos"),
        )
        self._botao(GameState.CONTROLES, "voltar", t("voltar"))

    def _draw_pausado(self) -> None:
        """Tela de pausa (Fig. 16): Continuar, Retroceder, Avançar, Sair."""
        e = GameState.PAUSADO
        self.surface.fill((235, 235, 235))
        UI.draw_text(
            self.surface,
            GameSettings.GAME_TITLE,
            (self._centro, 135),
            (0, 0, 0),
            GameSettings.FONTS["title"],
        )
        if self._controle is not None:
            UI.draw_text(
                self.surface,
                f"{t('pausado')} - {t('fase')} {self._controle.fase}",
                (self._centro, 205),
                GameSettings.COR_TEXTO,
                GameSettings.FONTS["feedback"],
            )
        self._botao(e, "continuar", t("continuar"))
        self._botao(e, "retroceder", t("retroceder"))
        self._botao(e, "avancar", t("avancar"))
        self._botao(e, "sair", t("sair"))
        self._botao(
            e,
            "som",
            t("som_ligado") if GameSettings.SOM_LIGADO else t("som_desligado"),
        )
        self._botao(e, "volume_menos", "-")
        self._botao(e, "volume_mais", "+")
        UI.draw_text(
            self.surface,
            f"{round(GameSettings.VOLUME * 100)}%",
            (115, 96),
            GameSettings.COR_TEXTO,
        )

    def _draw_confirmar(self) -> None:
        e = GameState.CONFIRMAR_SAIDA
        self.surface.fill((235, 235, 235))
        UI.draw_text(
            self.surface,
            t("confirmar_sair"),
            (self._centro, 250),
            GameSettings.COR_TEXTO,
            GameSettings.FONTS["feedback"],
        )
        self._botao(e, "sim", t("sim"))
        self._botao(e, "nao", t("nao"))

    def _draw_conclusao(self) -> None:
        """Tela de conclusão (Fig. 17): troféu e resumo da sessão."""
        e = GameState.CONCLUSAO
        self.surface.fill((245, 245, 245))
        UI.draw_text(
            self.surface,
            t("parabens"),
            (self._centro, 70),
            (0, 0, 0),
            GameSettings.FONTS["feedback"],
        )
        UI.trofeu(self.surface, (200, 270), 1.5)

        resumo = self._controle.resumo() if self._controle is not None else {}
        linhas = [
            (f"{t('total_pontos')}: {int(resumo.get('pontos', 0))}", "feedback"),
            (
                f"{t('tempo_total')}: "
                f"{formatar_tempo(resumo.get('tempo_total', 0))}",
                "text",
            ),
            (
                f"{t('tempo_medio_fase')}: "
                f"{formatar_tempo(resumo.get('tempo_medio_fase', 0))}",
                "text",
            ),
            (
                f"{t('tempo_medio_resposta')}: "
                f"{resumo.get('tempo_medio_resposta', 0):.1f} s",
                "text",
            ),
        ]
        y = 200
        for texto, fonte in linhas:
            UI.draw_text(
                self.surface,
                texto,
                (360, y),
                GameSettings.COR_TEXTO,
                GameSettings.FONTS[fonte],
                anchor="midleft",
            )
            y += 52 if fonte == "feedback" else 42
        self._botao(e, "sair", t("sair"))
        self._botao(e, "reiniciar", t("reiniciar"))
