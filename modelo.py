"""Dados e interpolação do mapa Wi-Fi. Coordenadas em pixels da planta."""
import base64
import csv
import io
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import QhullError


def leituras(texto):
    partes = re.split(r'[;\s]+', texto.strip().replace('−', '-'))
    valores = [float(p.replace(',', '.')) for p in partes if p]
    if any(not np.isfinite(v) or not -150 <= v <= 0 for v in valores):
        raise ValueError('Informe valores finitos entre -150 e 0 dBm.')
    return valores


def estatisticas(valores):
    if not valores:
        return None, None
    return float(np.median(valores)), float(np.percentile(valores, 75) - np.percentile(valores, 25))


def interpolar(pontos, campanha, largura, altura, resolucao=450, escala=None):
    dados = [(p['x'], p['y'], estatisticas(p['campanhas'].get(campanha, {}).get('leituras', []))[0]) for p in pontos]
    dados = [p for p in dados if p[2] is not None]
    if len(dados) < 3:
        raise ValueError('São necessários pelo menos 3 pontos com leituras nesta campanha.')
    xy = np.array(dados)[:, :2]
    if len(np.unique(xy, axis=0)) != len(xy):
        raise ValueError('Há pontos na mesma posição. Reúna as leituras em um único ponto.')
    if np.linalg.matrix_rank(xy - xy[0]) < 2:
        raise ValueError('Os pontos não podem estar todos na mesma linha.')
    nx = max(2, round(resolucao * largura / max(largura, altura)))
    ny = max(2, round(resolucao * altura / max(largura, altura)))
    x, y = np.meshgrid(np.linspace(0, largura, nx), np.linspace(0, altura, ny))
    try:
        sx, sy = fatores_escala(escala)
        z = LinearNDInterpolator(xy * [sx, sy], np.array(dados)[:, 2])(x * sx, y * sy)
    except QhullError as exc:
        raise ValueError('Distribuição dos pontos insuficiente para interpolar em 2D.') from exc
    return x, y, z


def fatores_escala(escala):
    if escala is None:
        return 1, 1
    if np.isscalar(escala):
        return escala, escala
    return escala


def escala_xy(a, b, distancia_x, distancia_y, escala_anterior=None):
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    if any(not np.isfinite(v) or v < 0 for v in (distancia_x, distancia_y)):
        raise ValueError('As distâncias X e Y devem ser finitas e não negativas.')
    if distancia_x == 0 and distancia_y == 0:
        raise ValueError('Informe uma distância maior que zero em pelo menos um eixo.')
    if (distancia_x > 0 and dx < 1) or (distancia_y > 0 and dy < 1):
        raise ValueError('Os pontos precisam estar separados no eixo cuja distância é maior que zero.')
    sx = distancia_x / dx if distancia_x > 0 else None
    sy = distancia_y / dy if distancia_y > 0 else None
    # Zero indica eixo não medido, inclusive quando o clique tem pequeno desvio.
    anterior_x, anterior_y = fatores_escala(escala_anterior)
    if sx is None:
        sx = anterior_x if escala_anterior is not None else sy
    if sy is None:
        sy = anterior_y if escala_anterior is not None else sx
    return sx, sy


def coordenadas(x, y, escala, origem=(0, 0), y_para_cima=False):
    sx, sy = fatores_escala(escala)
    return ((x - origem[0]) * sx,
            (y - origem[1]) * sy * (-1 if y_para_cima else 1))


def medir_distancia(a, b, escala):
    if escala is None:
        raise ValueError('Defina a escala em metros antes de usar a régua.')
    sx, sy = fatores_escala(escala)
    dx, dy = abs(b[0] - a[0]) * sx, abs(b[1] - a[1]) * sy
    return float(np.hypot(dx, dy)), float(dx), float(dy)


def posicao_pixels(x, y, escala, origem, y_para_cima, tamanho, pontos=(), id_atual=None):
    if not np.isfinite(x) or not np.isfinite(y):
        raise ValueError('As coordenadas X e Y devem ser números finitos.')
    sx, sy = fatores_escala(escala)
    px = origem[0] + x / sx
    py = origem[1] + y / sy * (-1 if y_para_cima else 1)
    largura, altura = tamanho
    if not (-1e-7 <= px <= largura + 1e-7 and -1e-7 <= py <= altura + 1e-7):
        raise ValueError('As coordenadas informadas ficam fora da planta.')
    px, py = float(np.clip(px, 0, largura)), float(np.clip(py, 0, altura))
    if any(p['id'] != id_atual and np.hypot(p['x'] - px, p['y'] - py) < 1e-6 for p in pontos):
        raise ValueError('Já existe outro ponto nessa posição. Edite o ponto existente.')
    return px, py


def importar_posicoes(pontos, escala_fonte, origem_fonte, y_fonte, escala_destino,
                      origem_destino, y_destino, tamanho, existentes=()):
    if escala_fonte is None or escala_destino is None:
        raise ValueError('Os dois projetos precisam ter escala em metros definida.')
    if not pontos:
        raise ValueError('O projeto selecionado não contém pontos.')
    novos = []
    ids = {p['id'] for p in existentes}
    proximo = max([p['id'] for p in [*existentes, *pontos]], default=0) + 1
    for p in pontos:
        x, y = coordenadas(p['x'], p['y'], escala_fonte, origem_fonte, y_fonte)
        try:
            px, py = posicao_pixels(x, y, escala_destino, origem_destino, y_destino,
                                   tamanho, [*existentes, *novos])
        except ValueError as exc:
            raise ValueError(f'Ponto P{p["id"]}: {exc} Nenhum ponto foi importado.') from exc
        identificador = p['id']
        if identificador in ids:
            identificador = proximo
            proximo += 1
        ids.add(identificador)
        novos.append(dict(id=identificador, x=px, y=py, campanhas={}))
    return novos


def salvar(caminho, imagem, pontos, escala, origem=(0, 0), y_para_cima=False, opacidade=.25, origem_definida=False):
    buffer = io.BytesIO()
    imagem.save(buffer, format='PNG')
    documento = dict(versao=3, planta_png=base64.b64encode(buffer.getvalue()).decode('ascii'),
                     pontos=pontos, metros_por_pixel=escala, origem=list(origem),
                     y_para_cima=y_para_cima, opacidade=opacidade, origem_definida=origem_definida)
    destino = Path(caminho)
    temporario = destino.with_suffix(destino.suffix + '.tmp')
    temporario.write_text(json.dumps(documento, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
    temporario.replace(destino)


def abrir(caminho, com_configuracao=False):
    d = json.loads(Path(caminho).read_text(encoding='utf-8'))
    if d.get('versao') not in (1, 2, 3):
        raise ValueError('Versão de projeto não reconhecida.')
    imagem = Image.open(io.BytesIO(base64.b64decode(d['planta_png'], validate=True))).convert('RGB')
    escala = d['metros_por_pixel']
    if escala is not None and (np.asarray(escala).shape not in ((), (2,)) or not np.all(np.isfinite(escala)) or np.any(np.asarray(escala) <= 0)):
        raise ValueError('Escala inválida.')
    ids = set()
    for p in d['pontos']:
        if not isinstance(p['id'], int) or p['id'] <= 0 or p['id'] in ids:
            raise ValueError('Identificador de ponto inválido ou repetido.')
        ids.add(p['id'])
        if not (0 <= p['x'] <= imagem.width and 0 <= p['y'] <= imagem.height):
            raise ValueError('Ponto fora da planta.')
        for c, m in p['campanhas'].items():
            if c not in ('Antes', 'Depois'):
                raise ValueError('Campanha não reconhecida.')
            leituras(' '.join(map(str, m['leituras'])))
            if not isinstance(m.get('horario', ''), str) or not isinstance(m.get('observacao', ''), str):
                raise ValueError('Metadados inválidos.')
    origem = d.get('origem', [0, 0])
    opacidade = d.get('opacidade', .25)
    y_para_cima = d.get('y_para_cima', False)
    origem_definida = d.get('origem_definida', False)
    if not isinstance(origem_definida, bool):
        raise ValueError('Estado da origem inválido.')
    if (len(origem) != 2 or not all(np.isfinite(v) for v in origem)
            or not 0 <= origem[0] <= imagem.width or not 0 <= origem[1] <= imagem.height):
        raise ValueError('Origem inválida.')
    if not np.isfinite(opacidade) or not 0 <= opacidade <= 1 or not isinstance(y_para_cima, bool):
        raise ValueError('Configuração visual inválida.')
    resultado = (imagem, d['pontos'], escala)
    if com_configuracao:
        return (*resultado, dict(origem=origem, y_para_cima=y_para_cima, opacidade=opacidade, origem_definida=origem_definida))
    return resultado


def numero_csv(valor, casas=2):
    """Número para Excel pt-BR; arredondamento apenas na exportação."""
    if valor is None:
        return ''
    arredondado = round(float(valor), casas)
    if arredondado == 0:
        arredondado = 0.0
    return f'{arredondado:.{casas}f}'.replace('.', ',')


def exportar_csv(caminho, pontos, escala, origem=(0, 0), y_para_cima=False):
    with open(caminho, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['ponto', 'x_px', 'y_px', 'x_m', 'y_m', 'campanha', 'leituras_dBm', 'n', 'mediana_dBm', 'IQR_dB', 'horario', 'observacao'])
        for p in pontos:
            xm, ym = coordenadas(p['x'], p['y'], escala, origem, y_para_cima)
            for c in ('Antes', 'Depois'):
                m = p['campanhas'].get(c, {})
                valores = m.get('leituras', [])
                mediana, iqr = estatisticas(valores)
                w.writerow([p['id'], numero_csv(p['x'], 3), numero_csv(p['y'], 3),
                            numero_csv(xm) if escala is not None else '', numero_csv(ym) if escala is not None else '',
                            c, ' '.join(str(v).replace('.', ',') for v in valores), len(valores),
                            numero_csv(mediana), numero_csv(iqr), m.get('horario', ''), m.get('observacao', '')])
