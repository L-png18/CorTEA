import sys
import threading
import time
from typing import List, Optional, Tuple

import cv2

from ttea.games.cortea.gamecore.calibracao import Calibracao
from ttea.games.cortea.gamecore.camera import Camera
from ttea.games.cortea.gameutil import GameSettings

_ERRO_MEDIAPIPE = ""  # por que o MediaPipe não carregou (mostrado na tecla C)

if sys.platform == "win32":
    # No Windows, o MediaPipe precisa de uma versão recente das DLLs do
    # Visual C++. Computadores com a versão antiga instalada no sistema dão
    # "DLL load failed while importing _framework_bindings". O PySide6 (que a
    # plataforma já instala) traz essas DLLs atualizadas; carregando-o antes,
    # o MediaPipe usa as mesmas. A própria plataforma carrega nessa ordem.
    try:
        import PySide6.QtCore  # noqa: F401
    except Exception:  # pragma: no cover - depende do ambiente
        pass

try:  # O jogo continua funcionando (com mouse) se o MediaPipe falhar.
    import mediapipe as mp

    _mp_drawing = mp.solutions.drawing_utils
except Exception as erro:  # pragma: no cover - depende do ambiente
    import traceback

    _ERRO_MEDIAPIPE = f"{type(erro).__name__}: {erro}"
    print("[CorTEA] Erro ao carregar o MediaPipe:")
    traceback.print_exc()
    mp = None
    _mp_drawing = None

try:
    _mp_hands = mp.solutions.hands
except Exception:  # pragma: no cover - depende do ambiente
    _mp_hands = None

try:
    _mp_pose = mp.solutions.pose
except Exception:  # pragma: no cover - depende do ambiente
    _mp_pose = None

# Landmarks do MediaPipe Hands usados para o centro da palma:
# punho (0) e base dos dedos (5, 9, 13, 17).
_PALMA = (0, 5, 9, 13, 17)
_PONTA_INDICADOR = 8

# Landmarks do MediaPipe Pose usados nos pés: calcanhar e ponta do pé de cada
# lado (esquerdo 29 e 31, direito 30 e 32). Eles ficam no chão, então a
# transformação de perspectiva do chão projetado vale para eles (o tornozelo
# fica no alto e daria erro de paralaxe).
_PES = ((29, 31), (30, 32))

MODOS = ("pes", "maos")


class Rastreamento:
    """Captura o movimento do jogador pela webcam (classe ``Rastreamento``
    do diagrama de classes).

    Uma thread própria lê a câmera e roda o MediaPipe, para que a tela do
    jogo não trave esperando a webcam. O jogo consulta o resultado mais
    recente com ``capturar_movimento``.

    Dois modos (``GameSettings.MODO_RASTREAMENTO``, trocável a qualquer
    momento):

    * ``"pes"`` - MediaPipe Pose: um ponto por pé, no centro entre o
      calcanhar e a ponta. É o modo do T-TEA com o jogo projetado no chão;
      usa a calibração da plataforma para levar a posição na imagem da
      câmera até a posição na tela projetada.
    * ``"maos"`` - MediaPipe Hands: um ponto por mão, para testar na mesa.
    """

    def __init__(
        self,
        tamanho_tela: Tuple[int, int],
        indice_camera: int = 0,
        calibracao: Optional[Calibracao] = None,
        backend: Optional[int] = None,
    ):
        self.largura, self.altura = tamanho_tela
        self.calibracao = calibracao
        self._lock = threading.Lock()
        self._parar = threading.Event()
        self._pontos: List[Tuple[int, int]] = []
        self._previa = None  # imagem RGB (numpy) reduzida da webcam
        self._ultimo_frame = 0.0
        self._pontos_suavizados: List[Tuple[float, float]] = []
        self.gerar_previa = GameSettings.MOSTRAR_PREVIA_CAMERA
        self.posicao_usuario: Optional[Tuple[int, int]] = None

        self.camera: Optional[Camera] = None
        self._thread: Optional[threading.Thread] = None
        self.motivo_inativo = ""

        if _mp_hands is None and _mp_pose is None:
            self.motivo_inativo = "MediaPipe indisponível"
            if _ERRO_MEDIAPIPE:
                self.motivo_inativo += " - " + _ERRO_MEDIAPIPE[:60]
            return
        if calibracao is not None:
            largura, altura = calibracao.camera_tamanho
            self.camera = Camera(indice_camera, largura, altura, backend)
        else:
            self.camera = Camera(indice_camera, backend=backend)
        self.camera.espelhar = GameSettings.ESPELHAR_CAMERA
        if not self.camera.aberta:
            self.motivo_inativo = f"Webcam {indice_camera} não abriu"
            return
        self._thread = threading.Thread(
            target=self._laco, name="cortea-rastreamento", daemon=True
        )
        self._thread.start()

    # ====================== API usada pelo jogo ======================
    @property
    def ativo(self) -> bool:
        """True se a webcam está entregando imagens agora."""
        return (
            self._thread is not None
            and self._thread.is_alive()
            and time.monotonic() - self._ultimo_frame < 1.0
        )

    @property
    def modo(self) -> str:
        return (
            GameSettings.MODO_RASTREAMENTO
            if GameSettings.MODO_RASTREAMENTO in MODOS
            else "pes"
        )

    @property
    def usa_calibracao(self) -> bool:
        """True se a posição dos pés passa pela calibração da plataforma."""
        return (
            self.modo == "pes"
            and self.calibracao is not None
            and GameSettings.USAR_CALIBRACAO
        )

    def capturar_movimento(self) -> List[Tuple[int, int]]:
        """Posições (na tela do jogo) das mãos ou dos pés detectados no
        último frame."""
        with self._lock:
            pontos = list(self._pontos)
        self.posicao_usuario = pontos[0] if pontos else None
        return pontos

    def detectar_posicao(self, grid) -> Optional[int]:
        """Índice do quadrado da grade sob o primeiro ponto, ou ``None``."""
        pontos = self.capturar_movimento()
        return grid.indice_em(pontos[0]) if pontos else None

    def obter_previa(self):
        """Última imagem da webcam (RGB, numpy) ou ``None``."""
        with self._lock:
            return self._previa

    def alternar_espelho(self) -> bool:
        """Espelha / desespelha a imagem da câmera (e, junto, o movimento do
        jogador). Devolve o novo valor."""
        GameSettings.ESPELHAR_CAMERA = not GameSettings.ESPELHAR_CAMERA
        if self.camera is not None:
            self.camera.espelhar = GameSettings.ESPELHAR_CAMERA
        return GameSettings.ESPELHAR_CAMERA

    def alternar_modo(self) -> str:
        """Troca entre acompanhar os pés e as mãos. Devolve o novo modo."""
        GameSettings.MODO_RASTREAMENTO = "maos" if self.modo == "pes" else "pes"
        with self._lock:
            self._pontos = []
        self._pontos_suavizados = []
        return GameSettings.MODO_RASTREAMENTO

    def close(self) -> None:
        self._parar.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self.camera is not None:
            self.camera.close_camera()

    # ====================== Conversões ======================
    def mapear(self, x: float, y: float) -> Tuple[int, int]:
        """Converte coordenadas normalizadas (0 a 1) da câmera para a tela.

        Nos pés, com calibração da plataforma, usa a transformação de
        perspectiva dela. Nos demais casos, descarta uma margem nas bordas da
        imagem, para que os cantos da grade sejam alcançáveis sem a mão sair
        do enquadramento.
        """
        if self.usa_calibracao:
            nx, ny = self.calibracao.converter(
                x, y, espelhado=GameSettings.ESPELHAR_CAMERA
            )
        else:
            m = GameSettings.MARGEM_CAMERA
            escala = max(1e-6, 1.0 - 2 * m)
            nx = min(1.0, max(0.0, (x - m) / escala))
            ny = min(1.0, max(0.0, (y - m) / escala))
        return (
            min(self.largura - 1, int(nx * self.largura)),
            min(self.altura - 1, int(ny * self.altura)),
        )

    def _extrair_pontos(self, resultados) -> List[Tuple[float, float]]:
        """Um ponto normalizado (x, y) por mão detectada."""
        pontos = []
        if not resultados.multi_hand_landmarks:
            return pontos
        for mao in resultados.multi_hand_landmarks:
            lm = mao.landmark
            if GameSettings.PONTO_DA_MAO == "indicador":
                pontos.append((lm[_PONTA_INDICADOR].x, lm[_PONTA_INDICADOR].y))
            else:
                pontos.append(
                    (
                        sum(lm[i].x for i in _PALMA) / len(_PALMA),
                        sum(lm[i].y for i in _PALMA) / len(_PALMA),
                    )
                )
        return pontos

    def _extrair_pontos_pes(self, resultados) -> List[Tuple[float, float]]:
        """Um ponto normalizado (x, y) por pé: o meio entre o calcanhar e a
        ponta do pé. Marcações em que o MediaPipe não confia (``visibility``
        baixa) ou fora da imagem são ignoradas."""
        pontos = []
        if not resultados.pose_landmarks:
            return pontos
        lm = resultados.pose_landmarks.landmark
        for calcanhar, ponta in _PES:
            validos = [
                lm[i]
                for i in (calcanhar, ponta)
                if getattr(lm[i], "visibility", 1.0)
                >= GameSettings.VISIBILIDADE_MIN_PE
                and -0.05 <= lm[i].x <= 1.05
                and -0.05 <= lm[i].y <= 1.05
            ]
            if validos:
                pontos.append(
                    (
                        sum(p.x for p in validos) / len(validos),
                        sum(p.y for p in validos) / len(validos),
                    )
                )
        return pontos

    def _suavizar(
        self, novos: List[Tuple[int, int]]
    ) -> List[Tuple[int, int]]:
        """Média móvel exponencial por ponto, para reduzir o tremor."""
        alfa = GameSettings.SUAVIZACAO
        anteriores = list(self._pontos_suavizados)
        resultado = []
        for x, y in novos:
            melhor = None
            for ant in anteriores:
                d = (ant[0] - x) ** 2 + (ant[1] - y) ** 2
                if d < 150**2 and (melhor is None or d < melhor[0]):
                    melhor = (d, ant)
            if melhor is not None:
                anteriores.remove(melhor[1])
                x = alfa * melhor[1][0] + (1 - alfa) * x
                y = alfa * melhor[1][1] + (1 - alfa) * y
            resultado.append((x, y))
        self._pontos_suavizados = resultado
        return [(int(x), int(y)) for x, y in resultado]

    # ====================== Detectores ======================
    @staticmethod
    def _criar_detector(modo: str):
        """Cria o detector do MediaPipe do ``modo`` (ou ``None``)."""
        if modo == "pes" and _mp_pose is not None:
            return _mp_pose.Pose(
                static_image_mode=False,
                model_complexity=0 if GameSettings.MODELO_POSE == 0 else 1,
                smooth_landmarks=True,
                enable_segmentation=False,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        if modo == "maos" and _mp_hands is not None:
            return _mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=2,
                min_detection_confidence=0.6,
                min_tracking_confidence=0.6,
            )
        return None

    # ====================== Prévia ======================
    def _desenhar_previa(self, rgb, resultados, modo, espelhado, normalizados):
        """Marca na imagem da câmera o que o jogo está enxergando: esqueleto
        ou mãos, o ponto usado em cada pé/mão e, nos pés, a área calibrada
        com os cantos numerados na ordem da calibração (1 a 4)."""
        if modo == "pes" and resultados.pose_landmarks:
            _mp_drawing.draw_landmarks(
                rgb, resultados.pose_landmarks, _mp_pose.POSE_CONNECTIONS
            )
        elif modo == "maos" and resultados.multi_hand_landmarks:
            for mao in resultados.multi_hand_landmarks:
                _mp_drawing.draw_landmarks(
                    rgb, mao, _mp_hands.HAND_CONNECTIONS
                )

        altura, largura = rgb.shape[:2]
        for x, y in normalizados:
            cv2.circle(rgb, (int(x * largura), int(y * altura)), 9, (255, 220, 0), 3)

        if modo != "pes":
            return
        if not self.usa_calibracao:
            cv2.putText(
                rgb, "SEM CALIBRACAO", (10, altura - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 60, 60), 2,
            )
            return
        cantos = self.calibracao.pontos_na_imagem(largura, altura, espelhado)
        for a, b in ((0, 1), (1, 3), (3, 2), (2, 0)):
            cv2.line(rgb, cantos[a], cantos[b], (0, 255, 0), 2)
        for numero, canto in enumerate(cantos, start=1):
            cv2.circle(rgb, canto, 7, (0, 120, 255), -1)
            cv2.putText(
                rgb, str(numero), (canto[0] + 8, canto[1] - 8),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2,
            )

    # ====================== Thread ======================
    def _laco(self) -> None:
        detectores = {}
        try:
            while not self._parar.is_set():
                ok, frame = self.camera.ler()
                if not ok:
                    time.sleep(0.02)
                    continue

                modo = self.modo
                if modo not in detectores:
                    detectores[modo] = self._criar_detector(modo)
                detector = detectores[modo]
                if detector is None:  # MediaPipe sem esse modo
                    time.sleep(0.05)
                    continue

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                resultados = detector.process(rgb)
                rgb.flags.writeable = True

                if modo == "pes":
                    normalizados = self._extrair_pontos_pes(resultados)
                else:
                    normalizados = self._extrair_pontos(resultados)
                telas = [self.mapear(x, y) for x, y in normalizados]
                telas = self._suavizar(telas)

                previa = None
                if self.gerar_previa:
                    self._desenhar_previa(
                        rgb,
                        resultados,
                        modo,
                        GameSettings.ESPELHAR_CAMERA,
                        normalizados,
                    )
                    previa = cv2.resize(
                        rgb,
                        (GameSettings.PREVIA_LARGURA, GameSettings.PREVIA_ALTURA),
                    )

                with self._lock:
                    self._pontos = telas
                    self._previa = previa
                    self._ultimo_frame = time.monotonic()
        finally:
            for detector in detectores.values():
                if detector is not None:
                    detector.close()
