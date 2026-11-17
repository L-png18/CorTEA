import argparse
import os
import sys

import pygame
from ttea.games.cortea.gamecontroller import GameController
from ttea.games.cortea.gamecore import (
    Calibracao,
    Rastreamento,
    SeletorPermanencia,
)
from ttea.games.cortea.gameutil import GameSettings, GameState
from ttea.games.cortea.gameview import Menu

INI_PADRAO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortea.ini")
ICONE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cortea.ico")


def carregar_icone(caminho: str = ICONE, tamanho: int = 32):
    """Lê do arquivo .ico a imagem mais próxima de ``tamanho`` pixels.

    O ``cortea.ico`` guarda as imagens em formato PNG, que o
    ``pygame.image.load`` não abre direto de um .ico; por isso a imagem é
    tirada do arquivo e carregada como PNG. Devolve ``None`` se não der.
    """
    import io
    import struct

    try:
        with open(caminho, "rb") as arquivo:
            dados = arquivo.read()
        _, tipo, quantidade = struct.unpack_from("<HHH", dados, 0)
        if tipo != 1 or quantidade == 0:
            return None
        melhor = None
        for i in range(quantidade):
            largura, _, _, _, _, _, tam, inicio = struct.unpack_from(
                "<BBBBHHII", dados, 6 + 16 * i
            )
            largura = largura or 256
            chave = (abs(largura - tamanho), -largura)
            if melhor is None or chave < melhor[0]:
                melhor = (chave, inicio, tam)
        _, inicio, tam = melhor
        return pygame.image.load(io.BytesIO(dados[inicio : inicio + tam]), "icone.png")
    except Exception:
        return None


class CorTEA:
    """Classe principal: janela, entrada (teclado, mouse e webcam) e o loop
    do jogo. A regra do jogo fica no ``GameController``."""

    def __init__(self, argumentos=None):
        """Inicializa o jogo, a janela, os objetos e as variáveis de estado."""
        # 1. Argumentos vindos da plataforma T-TEA
        parser = argparse.ArgumentParser(description="CorTEA Exergame")
        parser.add_argument(
            "--lang", type=str, default="pt_BR", help="Idioma do app"
        )
        parser.add_argument(
            "--player_id", type=int, default=0, help="ID do Jogador"
        )
        parser.add_argument(
            "--professional_id", type=int, default=0, help="ID do Profissional"
        )
        parser.add_argument(
            "--phase", type=int, default=0, help="Fase inicial (0 = padrão)"
        )
        parser.add_argument(
            "--camera", type=int, default=0, help="Índice da webcam"
        )
        parser.add_argument(
            "--rastreamento",
            choices=("pes", "maos"),
            default=None,
            help="O que a webcam acompanha: pés (chão projetado) ou mãos",
        )
        parser.add_argument(
            "--janela",
            action="store_true",
            help="Abre em janela, mesmo com o projetor calibrado",
        )
        parser.add_argument(
            "--monitor",
            type=int,
            default=None,
            help="Monitor onde o jogo abre (0 = principal)",
        )
        args = parser.parse_args(argumentos)

        # 2. Configurações: padrões -> cortea.ini -> argumentos da plataforma
        GameSettings.load_ini(INI_PADRAO)
        GameSettings.setup(args)

        # Calibração câmera -> projetor feita na plataforma T-TEA
        self.calibracao = (
            Calibracao.carregar() if GameSettings.USAR_CALIBRACAO else None
        )

        # 3. Inicialização do Pygame
        pygame.init()
        tamanho = (GameSettings.SCREEN_WIDTH, GameSettings.SCREEN_HEIGHT)
        self.screen = self._abrir_janela(tamanho)
        pygame.display.set_caption(GameSettings.WINDOW_NAME)
        icone = carregar_icone()
        if icone is not None:
            pygame.display.set_icon(icone)
        self.clock = pygame.time.Clock()
        GameSettings.load_fonts()

        # 4. Criação dos objetos principais
        self.rastreamento = Rastreamento(
            tamanho, GameSettings.CAMERA_INDEX, self.calibracao
        )
        if self.rastreamento.motivo_inativo:
            print(
                f"[CorTEA] {self.rastreamento.motivo_inativo}: "
                "jogando apenas com o mouse."
            )
        elif GameSettings.MODO_RASTREAMENTO == "pes" and self.calibracao is None:
            print(
                "[CorTEA] Calibração da plataforma não encontrada: os pés "
                "serão mapeados de forma simples, sem corrigir a perspectiva "
                "do projetor. Faça a calibração no T-TEA antes de jogar no chão."
            )
        self.game = GameController(self.screen)
        self.menu = Menu(self.screen)
        self.seletor = SeletorPermanencia(
            GameSettings.TEMPO_PERMANENCIA, GameSettings.TOLERANCIA_PERDA_MAO
        )
        self._estado_anterior = None
        self.running = True

    # ====================== Janela / projetor ======================
    def _monitor_escolhido(self) -> int:
        """Índice do monitor onde o jogo abre: o pedido (ini / --monitor), ou
        o do projetor guardado na calibração, ou o principal."""
        quantidade = max(1, pygame.display.get_num_displays())
        monitor = GameSettings.MONITOR
        if monitor < 0 and self.calibracao is not None:
            monitor = self.calibracao.monitor if self.calibracao.monitor is not None else -1
        if monitor < 0 or monitor >= quantidade:
            if monitor >= quantidade:
                print(
                    f"[CorTEA] Monitor {monitor} não existe (há {quantidade}): "
                    "abrindo no principal."
                )
            return 0
        return monitor

    def _tela_cheia(self) -> bool:
        """Tela cheia pedida, ou, no modo automático, quando o projetor já
        foi calibrado na plataforma."""
        if GameSettings.TELA_CHEIA == "auto":
            return self.calibracao is not None
        return bool(GameSettings.TELA_CHEIA)

    def _abrir_janela(self, tamanho) -> pygame.Surface:
        """Abre a janela do jogo, em tela cheia no projetor quando for o caso.

        SCALED: o jogo continua desenhando em 800x600 e o SDL escala para a
        tela, mantendo a proporção 4:3 e centralizando (a mesma área central
        que a calibração da plataforma usa).
        """
        monitor = self._monitor_escolhido()
        cheia = self._tela_cheia()
        flags = pygame.SCALED | (
            pygame.FULLSCREEN if cheia else pygame.RESIZABLE
        )
        tentativas = [
            dict(flags=flags, display=monitor),
            dict(flags=flags),
            dict(flags=0),
        ]
        tela = None
        for tentativa in tentativas:
            try:
                tela = pygame.display.set_mode(tamanho, **tentativa)
                break
            except pygame.error:
                continue
        if tela is None:  # pragma: no cover - sem vídeo nenhum
            raise RuntimeError("Não foi possível abrir a janela do jogo.")
        self._ajustar_cursor()
        return tela

    def _ajustar_cursor(self) -> None:
        """Esconde o cursor do mouse em tela cheia (no chão ele só atrapalha)."""
        superficie = pygame.display.get_surface()
        cheia = bool(superficie and superficie.get_flags() & pygame.FULLSCREEN)
        pygame.mouse.set_visible(not cheia)

    # ====================== Eventos ======================
    def handle_events(self):
        """Gerencia os eventos de entrada (teclado, mouse)."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._encerrar()
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._handle_click(event.pos)

    def _handle_key(self, key) -> None:
        estado = self.game.estado
        # Teclas de atalho dos botões (aparecem entre colchetes no botão)
        if estado in GameState.MENUS:
            acao = self.menu.acao_da_tecla(estado, key)
            if acao and self.menu.habilitado(estado, acao, self.game):
                self._executar_acao(acao)
                return
        if key == pygame.K_F7 and estado in GameState.PAUSAVEIS:
            # Sair durante a partida: pausa e pede a confirmação
            self.game.pausar()
            self.game.pedir_saida()
            return
        if key == pygame.K_ESCAPE:
            if estado in GameState.PAUSAVEIS:
                self.game.pausar()
            elif estado == GameState.PAUSADO:
                self.game.continuar()
            elif estado in (GameState.CONFIGURACOES, GameState.CONTROLES):
                self.game.ir_para(GameState.INICIO)
            elif estado == GameState.CONFIRMAR_SAIDA:
                self.game.cancelar_saida()
        elif key in (pygame.K_RETURN, pygame.K_SPACE):
            if estado == GameState.INICIO:
                self.game.iniciar_jogo()
            elif estado == GameState.PAUSADO:
                self.game.continuar()
            elif estado == GameState.CONCLUSAO:
                self.game.reiniciar()
        elif key == pygame.K_c:
            self.game.alternar_previa()
            self.rastreamento.gerar_previa = self.game.mostrar_previa
        elif key == pygame.K_h:
            self.game.alternar_painel()
        elif key == pygame.K_m:
            self.game.alternar_som()
        elif key == pygame.K_F11:
            pygame.display.toggle_fullscreen()
            self._ajustar_cursor()

    def _handle_click(self, pos) -> None:
        """Clique do mouse: escolhe botão (menus) ou quadrado (partida)."""
        estado = self.game.estado
        if estado in GameState.MENUS:
            acao = self.menu.acao_em(estado, pos)
            if acao and self.menu.habilitado(estado, acao, self.game):
                self._executar_acao(acao, pos)
        elif estado in GameState.SELECAO_NA_GRADE:
            indice = self.game.grid.indice_em(pos)
            if indice is not None:
                self.game.selecionar_quadrado(indice)

    def _executar_acao(self, acao: str, pos=(0, 0)) -> None:
        """Executa a ação de um botão (vinda do mouse ou da mão)."""
        g = self.game
        if acao in ("volume_menos", "volume_mais", "barra_volume"):
            self.menu.ajustar_volume(acao, pos)
            g.sons.ajustar_volume()
        elif acao == "jogar":
            g.iniciar_jogo()
        elif acao == "fechar":
            self._encerrar()  # tela inicial: fecha o jogo
        elif acao == "configuracoes":
            g.ir_para(GameState.CONFIGURACOES)
        elif acao == "controles":
            g.ir_para(GameState.CONTROLES)
        elif acao == "voltar":
            g.ir_para(GameState.INICIO)
        elif acao == "som":
            g.alternar_som()
        elif acao == "espelhar":
            self.rastreamento.alternar_espelho()
        elif acao == "modo":
            self.rastreamento.alternar_modo()
            self.seletor.reiniciar()
        elif acao == "continuar":
            g.continuar()
        elif acao == "retroceder":
            g.mudar_fase(-1)
        elif acao == "avancar":
            g.mudar_fase(+1)
        elif acao == "sair":
            if g.estado == GameState.PAUSADO:
                g.pedir_saida()  # pede confirmação (Quadro 6 do artigo)
            else:
                g.voltar_ao_inicio()  # fim do jogo: volta à tela inicial
        elif acao == "sim":
            g.voltar_ao_inicio()  # o jogo fecha pelo Sair da tela inicial
        elif acao == "nao":
            g.cancelar_saida()
        elif acao == "reiniciar":
            g.reiniciar()

    # ====================== Atualização ======================
    def update(self):
        """Atualiza a lógica do jogo a cada frame."""
        pontos = self.rastreamento.capturar_movimento()
        self.game.pontos_maos = pontos
        self.game.camera_ativa = self.rastreamento.ativo
        self.game.previa_surface = self._previa_surface()
        self.game.atualizar()
        self._atualizar_selecao(pontos)
        if self.game.estado == GameState.ENCERRADO:
            self.running = False

    def _previa_surface(self):
        if not self.game.mostrar_previa:
            return None
        quadro = self.rastreamento.obter_previa()
        if quadro is None:
            return None
        altura, largura = quadro.shape[:2]
        return pygame.image.frombuffer(quadro.tobytes(), (largura, altura), "RGB")

    def _alvos_selecionaveis(self) -> dict:
        """Alvos que a mão do jogador pode selecionar na tela atual."""
        estado = self.game.estado
        if estado in GameState.SELECAO_NA_GRADE:
            return {
                ("quad", indice): retangulo
                for indice, retangulo in self.game.grid.quadrados
            }
        if estado in GameState.MENUS:
            return {
                ("acao", acao): retangulo
                for acao, retangulo in self.menu.botoes(estado).items()
                if self.menu.habilitado(estado, acao, self.game)
            }
        return {}

    def _atualizar_selecao(self, pontos) -> None:
        """Seleção por permanência da mão sobre quadrados e botões."""
        estado = self.game.estado
        if estado != self._estado_anterior:
            self.seletor.reiniciar()
            self._estado_anterior = estado

        alvos = self._alvos_selecionaveis()
        agora = self.game.tempo_real()
        escolhido = self.seletor.atualizar(agora, pontos, alvos)

        progresso = {}
        for chave in alvos:
            fracao = self.seletor.progresso(chave, agora)
            if fracao > 0:
                progresso[chave] = fracao
        self.game.progresso_selecao = progresso

        if escolhido is not None:
            tipo, valor = escolhido
            if tipo == "quad":
                self.game.selecionar_quadrado(valor)
            else:
                self._executar_acao(valor)

    # ====================== Desenho ======================
    def draw(self):
        """Desenha todos os elementos na tela."""
        if self.game.estado == GameState.ENCERRADO:
            return
        self.screen.fill(GameSettings.COR_FUNDO)

        if self.game.estado in GameState.MENUS:
            self.menu.draw(
                self.game.estado, self.game.progresso_selecao, self.game
            )
            self.game.draw_maos()
        else:
            self.game.draw()

        pygame.display.flip()

    # ====================== Loop principal ======================
    def run(self):
        """Loop principal do jogo."""
        try:
            while self.running:
                self.handle_events()
                if not self.running:
                    break
                self.update()
                if not self.running:
                    break
                self.draw()
                self.clock.tick(GameSettings.FPS)
        finally:
            self.cleanup()
        sys.exit()

    def _encerrar(self) -> None:
        self.game.encerrar()
        self.running = False

    def cleanup(self):
        """Libera a webcam, fecha o Pygame e informa onde o CSV foi salvo."""
        self.game.encerrar()  # salva a tentativa em andamento, se houver
        self.rastreamento.close()
        pygame.quit()

        print("\n--- RESUMO DA SESSÃO ---")
        caminho = self.game.csv.caminho_arquivo
        if caminho:
            print(f"Relatório salvo com sucesso em: {caminho}")
            print(f"Tentativas de fase registradas: {len(self.game.csv.linhas)}")
        else:
            print("Nenhuma jogada foi registrada.")


# ====================== EXECUÇÃO DO JOGO ======================
if __name__ == "__main__":
    cortea = CorTEA()
    cortea.run()
