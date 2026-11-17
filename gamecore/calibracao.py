"""Da posição na imagem da câmera para a posição no chão projetado.

A plataforma T-TEA já faz a calibração câmera -> projetor (menu Calibração):
ela guarda 4 pontos, que são os cantos da tela projetada vistos pela câmera,
e os dados do hardware (resolução da câmera, monitor do projetor, tamanho e
proporção da área projetada). Esta classe lê esses dados e monta a
transformação de perspectiva que o KarTEA também usa: o ponto *i* da
calibração corresponde ao canto *i* da tela do jogo, na ordem
superior esquerdo, superior direito, inferior esquerdo, inferior direito.
"""

import importlib
from typing import Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

# Proporção da tela lógica do jogo (800 x 600).
PROPORCAO_JOGO = 4 / 3


class Calibracao:
    """Converte coordenadas normalizadas da câmera (0 a 1) em coordenadas
    normalizadas da tela do jogo (0 a 1)."""

    def __init__(
        self,
        pontos: Sequence[Sequence[float]],
        camera_tamanho: Tuple[int, int] = (640, 480),
        area_projetada: Tuple[int, int] = (4, 3),
        espelhada: bool = True,
        monitor: Optional[int] = None,
    ):
        """
        Parameters
        ----------
        pontos
            Os 4 pontos (x, y), em pixels da imagem da câmera.
        camera_tamanho
            Largura e altura em pixels da imagem em que os pontos foram
            marcados.
        area_projetada
            Largura e altura (ou só a proporção) da área projetada.
        espelhada
            Se a imagem em que os pontos foram marcados estava espelhada.
        monitor
            Índice do monitor do projetor, se a plataforma o guardou.
        """
        self.pontos = np.float32(pontos).reshape(4, 2)
        self.camera_tamanho = (int(camera_tamanho[0]), int(camera_tamanho[1]))
        self.area_projetada = (float(area_projetada[0]), float(area_projetada[1]))
        self.espelhada = bool(espelhada)
        self.monitor = monitor

        if not self.valida(self.pontos):
            raise ValueError("pontos de calibração inválidos")

        largura, altura = self.camera_tamanho
        normalizados = self.pontos / np.float32([largura, altura])
        destino = np.float32([[0, 0], [1, 0], [0, 1], [1, 1]])
        self._matriz = cv2.getPerspectiveTransform(normalizados, destino)

        # A tela do jogo ocupa o centro da área projetada (com faixas nas
        # laterais se a área for mais larga que 4:3, como na tela cheia).
        proporcao_area = self.area_projetada[0] / self.area_projetada[1]
        if proporcao_area >= PROPORCAO_JOGO:
            self._fx, self._fy = PROPORCAO_JOGO / proporcao_area, 1.0
        else:
            self._fx, self._fy = 1.0, proporcao_area / PROPORCAO_JOGO

    # ====================== Validação ======================
    @staticmethod
    def valida(pontos) -> bool:
        """Os 4 pontos formam um quadrilátero de verdade (não estão todos
        em zero, nem repetidos, nem alinhados)."""
        pontos = np.float32(pontos).reshape(4, 2)
        if len({tuple(p) for p in pontos.tolist()}) < 4:
            return False
        # Área do quadrilátero na ordem de contorno (0, 1, 3, 2).
        contorno = pontos[[0, 1, 3, 2]]
        x, y = contorno[:, 0], contorno[:, 1]
        area = 0.5 * abs(
            float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        )
        return area > 100.0

    # ====================== Conversão ======================
    def converter(
        self, x: float, y: float, espelhado: bool = True
    ) -> Tuple[float, float]:
        """Posição normalizada na câmera -> posição normalizada no jogo.

        ``espelhado`` diz se a imagem *atual* da câmera está espelhada. Se
        for diferente de como estava na calibração, o x é invertido antes de
        converter, então ligar ou desligar o espelho não bagunça o mapeamento.
        O resultado fica limitado à tela (0 a 1).
        """
        if espelhado != self.espelhada:
            x = 1.0 - x
        ponto = np.float64([x, y, 1.0])
        u, v, w = self._matriz @ ponto
        if abs(w) < 1e-9:
            return 0.0, 0.0
        u, v = u / w, v / w
        gx = (u - (1 - self._fx) / 2) / self._fx
        gy = (v - (1 - self._fy) / 2) / self._fy
        return min(1.0, max(0.0, float(gx))), min(1.0, max(0.0, float(gy)))

    def pontos_na_imagem(
        self, largura: int, altura: int, espelhado: bool = True
    ) -> List[Tuple[int, int]]:
        """Os 4 pontos em pixels de uma imagem ``largura`` x ``altura`` da
        câmera (para desenhá-los na prévia)."""
        resultado = []
        for x, y in self.pontos / np.float32(self.camera_tamanho):
            if espelhado != self.espelhada:
                x = 1.0 - x
            resultado.append((int(x * largura), int(y * altura)))
        return resultado

    # ====================== Leitura da plataforma ======================
    @classmethod
    def carregar(cls) -> Optional["Calibracao"]:
        """Lê a calibração da plataforma T-TEA; ``None`` se não houver (por
        exemplo, jogo aberto fora da plataforma ou calibração ainda não
        feita)."""
        from ttea.games.cortea.gameutil import GameSettings

        dados = cls._ler_plataforma()
        if not dados:
            return None
        try:
            return cls(
                dados["pontos"],
                camera_tamanho=dados.get("camera_tamanho") or (640, 480),
                area_projetada=dados.get("area_projetada") or (4, 3),
                espelhada=GameSettings.CALIBRACAO_ESPELHADA,
                monitor=dados.get("monitor"),
            )
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _ler_plataforma() -> Optional[Dict]:
        """Pontos e dados do hardware gravados pela plataforma."""
        try:
            dao_pontos = importlib.import_module(
                "ttea.dao.calibrationpointcsvdao"
            ).CalibrationPointCsvDAO
            ponto = dao_pontos().select(1)
        except Exception:
            return None
        if ponto is None:
            return None
        dados: Dict = {
            "pontos": [
                (ponto.pointx1, ponto.pointy1),
                (ponto.pointx2, ponto.pointy2),
                (ponto.pointx3, ponto.pointy3),
                (ponto.pointx4, ponto.pointy4),
            ]
        }
        try:
            dao_hardware = importlib.import_module(
                "ttea.dao.calibrationinidao"
            ).CalibrationIniDAO
            hw = dao_hardware().select(1)
        except Exception:
            hw = None
        if hw is not None:
            if hw.camera_width > 0 and hw.camera_height > 0:
                dados["camera_tamanho"] = (hw.camera_width, hw.camera_height)
            if hw.content_width > 0 and hw.content_height > 0:
                dados["area_projetada"] = (hw.content_width, hw.content_height)
            else:
                try:
                    a, b = str(hw.content_proportion).split(":")
                    dados["area_projetada"] = (float(a), float(b))
                except ValueError:
                    pass
            if hw.screen_position is not None and int(hw.screen_position) >= 0:
                dados["monitor"] = int(hw.screen_position)
        return dados
