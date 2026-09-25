import tempfile
import copy
import json
import csv
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from PIL import Image

from modelo import abrir, coordenadas, escala_xy, estatisticas, exportar_csv, importar_posicoes, interpolar, leituras, medir_distancia, posicao_pixels, salvar


def ponto(i, x, y, valores):
    return dict(id=i, x=x, y=y, campanhas={'Antes': dict(leituras=valores, horario='2026-09-22T10:00:00-03:00', observacao='DADOS SINTÉTICOS')})


class ModeloTest(unittest.TestCase):
    def test_importacao_sem_medicoes_e_sem_mutacao(self):
        ps = [ponto(1, 100, 100, [-40]), ponto(3, 200, 150, [-60])]
        originais = copy.deepcopy(ps)
        existentes = [ponto(1, 10, 10, [-80])]
        novos = importar_posicoes(ps, (.1, .2), (50, 150), True,
                                  (.05, .1), (100, 100), False, (500, 500), existentes)
        self.assertEqual(novos, [dict(id=4, x=200, y=200, campanhas={}), dict(id=3, x=400, y=100, campanhas={})])
        self.assertEqual(ps, originais)
        self.assertEqual(existentes, [ponto(1, 10, 10, [-80])])
        with self.assertRaises(ValueError):
            importar_posicoes(ps, None, (0, 0), False, .1, (0, 0), False, (500, 500))
        with self.assertRaises(ValueError):
            importar_posicoes(ps, .1, (0, 0), False, None, (0, 0), False, (500, 500))
        with self.assertRaisesRegex(ValueError, 'Nenhum ponto'):
            importar_posicoes(ps, .1, (0, 0), False, .01, (0, 0), False, (500, 500))
        self.assertEqual(ps, originais)

    def test_edicao_posicao(self):
        for cima in (False, True):
            xy = coordenadas(50, 80, (.05, .1), (100, 100), cima)
            self.assertEqual(posicao_pixels(*xy, (.05, .1), (100, 100), cima, (200, 200)), (50, 80))
        self.assertEqual(posicao_pixels(10, -5, None, (20, 20), False, (200, 200)), (30, 15))
        for x, y in [(float('nan'), 0), (0, float('inf')), (-1, 0), (201, 0)]:
            with self.assertRaises(ValueError):
                posicao_pixels(x, y, None, (0, 0), False, (200, 200))
        with self.assertRaises(ValueError):
            posicao_pixels(50, 80, None, (0, 0), False, (200, 200), [ponto(1, 50, 80, [-50])], 2)

    def test_regua_em_metros(self):
        self.assertEqual(medir_distancia((10, 20), (310, 220), (.01, .02)), (5, 3, 4))
        self.assertEqual(medir_distancia((310, 220), (10, 20), (.01, .02)), (5, 3, 4))
        self.assertEqual(medir_distancia((10, 20), (10, 20), .01), (0, 0, 0))
        self.assertEqual(medir_distancia((0, 0), (100, 0), .055), (5.5, 5.5, 0))
        self.assertEqual(medir_distancia((0, 0), (0, 100), .03), (3, 0, 3))
        with self.assertRaises(ValueError):
            medir_distancia((0, 0), (100, 100), None)

    def test_escalas_independentes(self):
        escala = escala_xy((20, 30), (120, 230), 5, 20)
        self.assertEqual(escala, (.05, .1))
        self.assertEqual(coordenadas(120, 230, escala, (20, 30)), (5, 20))
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'xy.json'
            salvar(caminho, Image.new('RGB', (250, 250)), [], escala)
            self.assertEqual(abrir(caminho)[2], [.05, .1])
        for a, b, x, y in [((0, 0), (0, 100), 5, 5), ((0, 0), (100, 100), 0, 0), ((0, 0), (100, 100), 5, float('nan')), ((0, 0), (100, 100), -5, 0)]:
            with self.assertRaises(ValueError):
                escala_xy(a, b, x, y)

    def test_referencias_horizontais_e_verticais(self):
        self.assertEqual(escala_xy((0, 0), (100, 0), 5.5, 0), (.055, .055))
        self.assertEqual(escala_xy((0, 100), (0, 0), 0, 3), (.03, .03))
        self.assertEqual(escala_xy((0, 0), (100, 2), 5.5, 0, (.02, .04)), (.055, .04))
        self.assertEqual(escala_xy((0, 0), (1, 100), 0, 3, (.02, .04)), (.02, .03))
        self.assertEqual(escala_xy((0, 0), (100, 0), 5.5, 0, .04), (.055, .04))

    def test_origem_escala_persistencia_e_projeto_antigo(self):
        self.assertEqual(coordenadas(150, 60, .1, (100, 100), True), (5, 4))
        ps = [ponto(1, 150, 60, [-55])]
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'projeto.json'
            salvar(caminho, Image.new('RGB', (200, 200)), ps, .1, (100, 100), True, .15)
            _, _, _, config = abrir(caminho, com_configuracao=True)
            self.assertEqual(config, dict(origem=[100, 100], y_para_cima=True, opacidade=.15, origem_definida=False))
            exportar_csv(Path(pasta) / 'pontos.csv', ps, .1, (100, 100), True)
            with open(Path(pasta) / 'pontos.csv', encoding='utf-8-sig') as f:
                linha = next(csv.DictReader(f, delimiter=';'))
            self.assertEqual(linha['x_m'], '5,00')
            self.assertEqual(linha['y_m'], '4,00')
            d = json.loads(caminho.read_text('utf-8'))
            d['versao'] = 1
            for chave in ('origem', 'y_para_cima', 'opacidade'):
                del d[chave]
            caminho.write_text(json.dumps(d), encoding='utf-8')
            _, _, _, config = abrir(caminho, com_configuracao=True)
            self.assertEqual(config['origem'], [0, 0])
            self.assertFalse(config['y_para_cima'])

    def test_mediana_resiste_outlier(self):
        self.assertEqual(estatisticas(leituras('-55 -56 -54 -55 -100'))[0], -55)
        self.assertEqual(leituras('−55,5; -54.5'), [-55.5, -54.5])
        self.assertEqual(leituras(''), [])
        for invalido in ('nan', 'inf', '1', '-151', 'texto'):
            with self.assertRaises(ValueError):
                leituras(invalido)

    def test_interpolacao_plano_e_fora_contorno(self):
        ps = [ponto(1, 0, 0, [-40]), ponto(2, 10, 0, [-60]), ponto(3, 0, 10, [-80])]
        x, y, z = interpolar(ps, 'Antes', 10, 10, 11)
        self.assertAlmostEqual(z[0, 0], -40)
        self.assertAlmostEqual(z[2, 2], -52)
        self.assertTrue(np.isnan(z[-1, -1]))
        with self.assertRaises(ValueError):
            interpolar(ps, 'Depois', 10, 10)
        with self.assertRaises(ValueError):
            interpolar([ponto(i, i, i, [-50]) for i in range(3)], 'Antes', 10, 10)

    def test_projeto_e_csv_preservam_amostras(self):
        ps = [ponto(1, 2, 3, [-55, -57, -54])]
        ps[0]['campanhas']['Depois'] = dict(leituras=[-40, -41], horario='', observacao='porta aberta')
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'projeto.json'
            salvar(caminho, Image.new('RGB', (20, 10), 'white'), ps, .1)
            im, recuperados, escala = abrir(caminho)
            self.assertEqual(im.size, (20, 10))
            self.assertEqual(recuperados, ps)
            self.assertEqual(escala, .1)
            exportar_csv(Path(pasta) / 'pontos.csv', ps, escala)
            texto = (Path(pasta) / 'pontos.csv').read_text('utf-8-sig')
            self.assertIn('-55 -57 -54', texto)
            self.assertIn('Depois', texto)

    def test_csv_excel_portugues(self):
        ps = [ponto(1, 22.999999999999996, 45.99999999999999, [-36.5, -37, -36])]
        ps[0]['campanhas']['Antes']['observacao'] = 'porta; fechada\nmedição'
        original = copy.deepcopy(ps)
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / 'excel.csv'
            exportar_csv(caminho, ps, .1)
            self.assertTrue(caminho.read_bytes().startswith(b'\xef\xbb\xbf'))
            with caminho.open(encoding='utf-8-sig', newline='') as f:
                antes, depois = list(csv.DictReader(f, delimiter=';'))
            self.assertEqual(antes['x_m'], '2,30')
            self.assertEqual(antes['y_m'], '4,60')
            self.assertEqual(antes['x_px'], '23,000')
            self.assertEqual(antes['mediana_dBm'], '-36,50')
            self.assertEqual(antes['IQR_dB'], '0,50')
            self.assertEqual(antes['leituras_dBm'], '-36,5 -37 -36')
            self.assertEqual(antes['observacao'], 'porta; fechada\nmedição')
            self.assertEqual(depois['mediana_dBm'], '')
            self.assertEqual(depois['n'], '0')
            exportar_csv(caminho, ps, None)
            with caminho.open(encoding='utf-8-sig', newline='') as f:
                linha = next(csv.DictReader(f, delimiter=';'))
            self.assertEqual(linha['x_m'], '')
            self.assertEqual(linha['y_m'], '')
        self.assertEqual(ps, original)


class InterfaceTest(unittest.TestCase):
    def test_importar_posicoes_com_pre_requisitos(self):
        import tkinter as tk
        from app import Aplicativo
        root = tk.Tk()
        root.withdraw()
        try:
            app = Aplicativo(root, Path(__file__).parent.parent / 'planta1.png')
            self.assertTrue(app.botao_importar.instate(['disabled']))
            with patch('app.messagebox.showinfo'), patch('app.filedialog.askopenfilename') as seletor:
                app.importar_pontos()
                seletor.assert_not_called()
            app.escala = (.05, .1)
            app.desenhar()
            self.assertTrue(app.botao_importar.instate(['disabled']))
            app.definir_origem()
            app.clicar(SimpleNamespace(inaxes=app.ax, button=1, xdata=100, ydata=100))
            self.assertTrue(app.origem_definida)
            self.assertFalse(app.botao_importar.instate(['disabled']))
            with tempfile.TemporaryDirectory() as pasta:
                fonte = Path(pasta) / 'fonte.json'
                ps = [ponto(7, 100, 100, [-45, -50])]
                ps[0]['campanhas']['Depois'] = dict(leituras=[-55], horario='ontem', observacao='não importar')
                salvar(fonte, Image.new('RGB', (300, 300)), ps, (.1, .2), (50, 150), True)
                original = fonte.read_bytes()
                with patch('app.filedialog.askopenfilename', return_value=str(fonte)):
                    app.importar_pontos()
                self.assertEqual(app.pontos, [dict(id=7, x=200, y=200, campanhas={})])
                self.assertEqual(app.lista.get(0).split()[1:3], ['a', 'medir'])
                self.assertEqual(fonte.read_bytes(), original)
                antes = copy.deepcopy(app.pontos)
                with patch('app.filedialog.askopenfilename', return_value=str(fonte)), patch('app.messagebox.showerror') as erro:
                    app.importar_pontos()
                    erro.assert_called_once()
                self.assertEqual(app.pontos, antes)
                destino = Path(pasta) / 'destino.json'
                with patch('app.filedialog.asksaveasfilename', return_value=str(destino)):
                    app.salvar_projeto()
                self.assertTrue(abrir(destino, com_configuracao=True)[3]['origem_definida'])
                with patch('app.filedialog.askopenfilename', return_value=str(destino)):
                    app.abrir_projeto()
                self.assertFalse(app.botao_importar.instate(['disabled']))
            app.alterado = False
            app.carregar_planta(Path(__file__).parent.parent / 'planta1.png')
            self.assertFalse(app.origem_definida)
            self.assertTrue(app.botao_importar.instate(['disabled']))
        finally:
            root.destroy()

    def test_visualizacao_preserva_projeto(self):
        import tkinter as tk
        from app import Aplicativo
        root = tk.Tk()
        root.withdraw()
        try:
            app = Aplicativo(root)
            ps = [ponto(1, 100, 100, [-55, -57]), ponto(2, 500, 100, [-40]), ponto(3, 300, 500, [-80])]
            with tempfile.TemporaryDirectory() as pasta:
                arquivo = Path(pasta) / 'existente.json'
                imagem = Image.open(Path(__file__).parent.parent / 'planta1.png').convert('RGB')
                salvar(arquivo, imagem, ps, (.04, .06), (50, 600), True, .4)
                original = arquivo.read_bytes()
                with patch('app.filedialog.askopenfilename', return_value=str(arquivo)):
                    app.abrir_projeto()
                estado = copy.deepcopy((app.pontos, app.escala, app.origem, app.y_para_cima.get(), app.opacidade.get()))
                app.gerar()
                self.assertEqual(app.camada.get_clim(), (-60, -30))
                np.testing.assert_array_equal(app.camada.to_rgba(-80), app.camada.to_rgba(-60))
                largura = app.imagem.width
                app.aplicar_zoom(.5)
                self.assertAlmostEqual(np.ptp(app.ax.get_xlim()), largura / 2)
                limites = (app.ax.get_xlim(), app.ax.get_ylim())
                app.mostrar_nomes.set(False)
                app.desenhar()
                self.assertEqual((app.ax.get_xlim(), app.ax.get_ylim()), limites)
                textos = [t.get_text() for t in app.ax.texts]
                self.assertIn('-56 dBm', textos)
                self.assertFalse(any(t.startswith('P1') for t in textos))
                self.assertEqual(len(app.ax.lines), 4)  # Três pontos e a origem.
                centro = tuple(np.mean(lim) for lim in limites)
                app.zoom_mouse(SimpleNamespace(inaxes=app.ax, xdata=centro[0], ydata=centro[1], button='up'))
                self.assertLess(np.ptp(app.ax.get_xlim()), largura / 2)
                app.zoom_mouse(SimpleNamespace(inaxes=None, xdata=None, ydata=None, button='up'))
                app.restaurar_visao()
                self.assertEqual(app.ax.get_xlim(), (0, imagem.width))
                self.assertEqual(app.ax.get_ylim(), (imagem.height, 0))
                app.fig.savefig(Path(__file__).parent / 'teste_visualizacao.png', dpi=120)
                self.assertEqual((app.pontos, app.escala, app.origem, app.y_para_cima.get(), app.opacidade.get()), estado)
                self.assertFalse(app.alterado)
                self.assertEqual(arquivo.read_bytes(), original)
                app.mostrar_nomes.set(True)
                app.desenhar()
                self.assertIn('P1\n-56 dBm', [t.get_text() for t in app.ax.texts])
        finally:
            root.destroy()

    def test_fluxo_com_planta_real(self):
        import tkinter as tk
        from app import Aplicativo
        root = tk.Tk()
        root.withdraw()
        app = Aplicativo(root, Path(__file__).parent.parent / 'planta1.png')
        try:
            with patch('app.messagebox.showinfo') as aviso:
                app.iniciar_regua()
                aviso.assert_called_once()
            self.assertIsNone(app.regua)
            w, h = app.imagem.size
            for i, (x, y, vs) in enumerate([(.2, .2, [-40, -42, -41]), (.8, .2, [-60, -58, -59]), (.5, .8, [-80, -78, -79])], 1):
                with patch('app.Medicao', return_value=SimpleNamespace(result=dict(posicao=(x*w, y*h), medicao=dict(leituras=vs, horario='', observacao='TESTE')))):
                    app.editar(dict(id=i, x=x*w, y=y*h, campanhas={}), novo=True)
            app.gerar()
            self.assertTrue(app.mapa)
            app.calibrar()
            def clique(x, y):
                app.clicar(SimpleNamespace(inaxes=app.ax, button=1, xdata=x, ydata=y))
            clique(20, 20)
            self.assertEqual(len(app.marcas_calibracao), 2)
            # Pontos sobrepostos mantêm A; uma linha horizontal abre o formulário.
            clique(20, 20)
            self.assertEqual(app.calibracao, [(20, 20)])
            def horizontal(parent, a, b, anterior):
                return SimpleNamespace(result=escala_xy(a, b, 5.5, 0, anterior))
            with patch('app.DistanciasXY', side_effect=horizontal):
                clique(120, 20)
            self.assertEqual(app.escala, (.055, .055))
            app.calibrar()
            clique(20, 20)
            def vertical(parent, a, b, anterior):
                return SimpleNamespace(result=escala_xy(a, b, 0, 3, anterior))
            with patch('app.DistanciasXY', side_effect=vertical):
                clique(20, 120)
            self.assertEqual(app.escala, (.055, .03))
            app.calibrar()
            clique(20, 20)
            def distancias(parent, a, b, anterior):
                self.assertEqual(len(app.calibracao), 2)
                self.assertEqual(len(app.marcas_calibracao), 9)
                app.fig.savefig(Path(__file__).parent / 'teste_calibracao.png', dpi=120)
                return SimpleNamespace(result=escala_xy(a, b, 5, 12))
            with patch('app.DistanciasXY', side_effect=distancias):
                clique(120, 220)
            self.assertEqual(app.escala, (.05, .06))
            self.assertEqual(len(app.marcas_calibracao), 0)
            app.calibrar()
            clique(20, 20)
            with patch('app.DistanciasXY', return_value=SimpleNamespace(result=None)):
                clique(120, 220)
            self.assertEqual(app.escala, (.05, .06))
            app.calibrar()
            clique(20, 20)
            app.cancelar_marcacao()
            self.assertEqual(len(app.marcas_calibracao), 0)
            app.definir_origem()
            clique(w * .1, h * .9)
            self.assertEqual(app.origem, (w * .1, h * .9))
            self.assertEqual(len(app.pontos), 3)
            app.y_para_cima.set(True)
            app.mudar_eixo()
            app.mudar_transparencia(100)
            self.assertEqual(app.camada.get_alpha(), 0)
            app.mudar_transparencia(75)
            self.assertEqual(app.camada.get_alpha(), .25)
            app.canvas.draw()
            saida = Path(__file__).parent / 'teste_mapa.png'
            app.fig.savefig(saida, dpi=120)
            app.alterado = False
            app.iniciar_regua()
            clique(120, 120)
            self.assertEqual(len(app.marcas_regua), 2)
            clique(180, 120 + 4 / .06)
            self.assertIn('5.00 m', app.status.get())
            self.assertEqual(len(app.pontos), 3)
            self.assertFalse(app.alterado)
            self.assertEqual(len(app.marcas_regua), 6)
            app.fig.savefig(Path(__file__).parent / 'teste_regua.png', dpi=120)
            clique(30, 30)
            self.assertEqual(app.regua, [(30, 30)])
            app.cancelar_marcacao()
            self.assertIsNone(app.regua)
            self.assertEqual(len(app.marcas_regua), 0)
            app.iniciar_regua()
            clique(30, 30)
            app.calibrar()
            self.assertIsNone(app.regua)
            self.assertEqual(len(app.marcas_regua), 0)
            app.cancelar_marcacao()
            app.campanha.set('Depois')
            app.trocar_campanha()
            self.assertFalse(app.mapa)
            self.assertEqual(len(app.pontos), 3)
            self.assertEqual(app.pontos[0]['campanhas']['Antes']['leituras'], [-40, -42, -41])
            # O botão sai da régua mesmo com zoom ativo e o próximo clique adiciona.
            app.iniciar_regua()
            clique(20, 20)
            self.assertEqual(app.modo_ativo.get(), 'Modo: régua')
            app.toolbar.zoom()
            app.botao_pontos.invoke()
            self.assertFalse(app.toolbar.mode)
            self.assertIsNone(app.regua)
            self.assertEqual(len(app.marcas_regua), 0)
            self.assertEqual(app.modo_ativo.get(), 'Modo: adicionar/editar pontos')
            app.canvas.draw()
            sx, sy = app.ax.transData.transform((40, 40))
            with patch('app.Medicao', return_value=SimpleNamespace(result=dict(posicao=(40, 40), medicao=dict(leituras=[-65], horario='', observacao='TESTE')))):
                app.clicar(SimpleNamespace(inaxes=app.ax, button=1, xdata=40, ydata=40, x=sx, y=sy))
            self.assertEqual(len(app.pontos), 4)
            self.assertEqual(app.pontos[-1]['campanhas']['Depois']['leituras'], [-65])
            app.calibrar()
            clique(20, 20)
            app.botao_pontos.invoke()
            self.assertIsNone(app.calibracao)
            self.assertEqual(len(app.marcas_calibracao), 0)
            app.definir_origem()
            app.botao_pontos.invoke()
            self.assertFalse(app.definindo_origem)
            # Mover o ponto conserva as amostras da outra campanha e redesenha.
            antes = app.pontos[0]['campanhas']['Antes'].copy()
            with patch('app.Medicao', return_value=SimpleNamespace(result=dict(posicao=(70, 90), medicao=dict(leituras=[-60], horario='', observacao='movido')))):
                app.editar(app.pontos[0])
            self.assertEqual((app.pontos[0]['x'], app.pontos[0]['y']), (70, 90))
            self.assertEqual(app.pontos[0]['campanhas']['Antes'], antes)
            with patch('app.Medicao', return_value=SimpleNamespace(result=None)):
                app.editar(app.pontos[0])
            self.assertEqual((app.pontos[0]['x'], app.pontos[0]['y']), (70, 90))
        finally:
            root.destroy()

    def test_formulario_coordenadas(self):
        import tkinter as tk
        from app import Medicao
        root = tk.Tk()
        root.withdraw()
        try:
            p = ponto(1, 100, 100, [-55])
            with patch('app.simpledialog.Dialog.__init__', return_value=None):
                dialogo = Medicao(root, p, 'Antes', (.1, .2), (50, 150), True, (500, 500), [p])
            frame = tk.Frame(root)
            dialogo.body(frame)
            self.assertEqual([c.get() for c in dialogo.campos_posicao], ['5', '10'])
            for campo, texto in zip(dialogo.campos_posicao, ['2,5', '-4']):
                campo.delete(0, 'end')
                campo.insert(0, texto)
            self.assertTrue(dialogo.validate())
            self.assertEqual(dialogo.result['posicao'], (75, 170))
            self.assertEqual(dialogo.result['medicao']['leituras'], [-55])
            self.assertEqual((p['x'], p['y']), (100, 100))
            dialogo.campos_posicao[0].delete(0, 'end')
            dialogo.campos_posicao[0].insert(0, '9999')
            with patch('app.messagebox.showerror'):
                self.assertFalse(dialogo.validate())
            with patch('app.simpledialog.Dialog.__init__', return_value=None):
                sem_escala = Medicao(root, p, 'Antes', None, (0, 0), False, (500, 500), [p])
            sem_escala.body(tk.Frame(root))
            self.assertTrue(all(c.instate(['disabled']) for c in sem_escala.campos_posicao))
            self.assertEqual([c.get() for c in sem_escala.campos_posicao], ['', ''])
            self.assertTrue(sem_escala.validate())
            self.assertEqual(sem_escala.result['posicao'], (100, 100))
            self.assertEqual(sem_escala.result['medicao']['leituras'], [-55])
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
