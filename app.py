"""Editor desktop de medições Wi-Fi manuais. Execute: python app.py [planta.png]."""
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import numpy as np
from PIL import Image
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from modelo import abrir, coordenadas, escala_xy, fatores_escala, exportar_csv, estatisticas, importar_posicoes, interpolar, leituras, medir_distancia, posicao_pixels, salvar

COR_MIN_DBM = -60
COR_MAX_DBM = -30


class DistanciasXY(simpledialog.Dialog):
    def __init__(self, parent, a, b, escala_anterior=None):
        self.a, self.b = a, b
        self.escala_anterior = escala_anterior
        super().__init__(parent, 'Escala • distâncias entre A e B')

    def body(self, frame):
        regra = ('O eixo com zero mantém sua escala atual.' if self.escala_anterior is not None
                 else 'Na primeira calibração, a medida de um eixo vale para os dois (escala uniforme).')
        ttk.Label(frame, text='Informe as separações horizontal e vertical entre A e B, não a diagonal.\nLinha horizontal: X = 5,5 e Y = 0. Linha vertical: X = 0 e Y = 3.\n' + regra).grid(row=0, column=0, columnspan=2, pady=8)
        self.campos = []
        for i, nome in enumerate(('Distância X — horizontal (m)', 'Distância Y — vertical (m)'), 1):
            ttk.Label(frame, text=nome).grid(row=i, column=0, sticky='w', padx=6, pady=6)
            campo = ttk.Entry(frame, width=16)
            campo.grid(row=i, column=1, padx=6)
            self.campos.append(campo)
            if abs(self.b[i - 1] - self.a[i - 1]) < 1:
                campo.insert(0, '0')
        return self.campos[0]

    def validate(self):
        try:
            valores = [float(c.get().strip().replace(',', '.')) for c in self.campos]
            self.result = escala_xy(self.a, self.b, *valores, escala_anterior=self.escala_anterior)
            return True
        except ValueError as exc:
            messagebox.showerror('Distâncias inválidas', str(exc), parent=self)
            return False


class Medicao(simpledialog.Dialog):
    def __init__(self, parent, ponto, campanha, escala, origem, y_para_cima, tamanho, pontos):
        self.medicao = ponto['campanhas'].get(campanha, {})
        self.ponto = ponto
        self.escala, self.origem, self.y_para_cima = escala, origem, y_para_cima
        self.tamanho, self.pontos = tamanho, pontos
        super().__init__(parent, f'Ponto {ponto["id"]} • {campanha}')

    def body(self, frame):
        x, y = coordenadas(self.ponto['x'], self.ponto['y'], self.escala, self.origem, self.y_para_cima)
        ttk.Label(frame, text='Posição em metros, relativa à origem escolhida.\nMover altera a malha nas duas campanhas.').pack(anchor='w')
        linha = ttk.Frame(frame)
        linha.pack(fill='x', pady=8)
        self.campos_posicao = []
        for eixo, valor in [('X', x), ('Y', y)]:
            ttk.Label(linha, text=f'{eixo} (m)').pack(side='left', padx=(0, 6))
            campo = ttk.Entry(linha, width=20)
            if self.escala is not None:
                campo.insert(0, format(valor, '.15g'))
            else:
                campo.state(['disabled'])
            campo.pack(side='left', padx=(0, 12))
            self.campos_posicao.append(campo)
        if self.escala is None:
            ttk.Label(frame, text='Para editar X e Y em metros, feche esta janela, use\n“1. Definir escala em metros” e abra o ponto novamente.', foreground='#a34a00').pack(anchor='w', pady=(0, 8))
        # Mantém os pixels exatos quando somente leituras/observações são editadas.
        self.textos_posicao = [c.get() for c in self.campos_posicao]
        ttk.Label(frame, text='Leituras em dBm (espaço ou ponto e vírgula entre valores)\nEx.: -55 -57 -54 -56 -55. Vazio = ponto a medir.').pack(anchor='w')
        self.valores = ttk.Entry(frame, width=65)
        self.valores.insert(0, ' '.join(map(str, self.medicao.get('leituras', []))))
        self.valores.pack(fill='x', pady=8)
        self.resumo = ttk.Label(frame)
        self.resumo.pack(anchor='w')
        self.valores.bind('<KeyRelease>', lambda e: self.atualizar())
        ttk.Label(frame, text='Horário da medição (edite se estiver transcrevendo depois)').pack(anchor='w', pady=(12, 0))
        self.horario = ttk.Entry(frame, width=65)
        self.horario.insert(0, self.medicao.get('horario') or datetime.now().astimezone().isoformat(timespec='seconds'))
        self.horario.pack(fill='x')
        ttk.Label(frame, text='Observações: rede/BSSID, aparelho, altura, orientação, pessoas, portas…').pack(anchor='w', pady=(12, 0))
        self.obs = tk.Text(frame, height=4, width=65, wrap='word')
        self.obs.insert('1.0', self.medicao.get('observacao', ''))
        self.obs.pack(fill='x')
        self.atualizar()
        return self.valores

    def atualizar(self):
        try:
            vs = leituras(self.valores.get())
            med, iqr = estatisticas(vs)
            texto = 'Sem leitura: ponto planejado.' if med is None else f'{len(vs)} leitura(s) • Mediana: {med:g} dBm • IQR: {iqr:g} dB'
            if len(vs) == 1:
                texto += '\nValor único: pode ser uma mediana já calculada; registre isso nas observações.'
            self.resumo.config(text=texto)
        except ValueError:
            self.resumo.config(text='Use números de -150 a 0; decimal com ponto ou vírgula.')

    def validate(self):
        try:
            textos = [c.get().strip() for c in self.campos_posicao]
            if self.escala is None or textos == self.textos_posicao:
                posicao = (self.ponto['x'], self.ponto['y'])
            else:
                x, y = [float(t.replace('−', '-').replace(',', '.')) for t in textos]
                posicao = posicao_pixels(x, y, self.escala, self.origem, self.y_para_cima, self.tamanho, self.pontos, self.ponto['id'])
            medicao = dict(leituras=leituras(self.valores.get()), horario=self.horario.get().strip(), observacao=self.obs.get('1.0', 'end').strip())
            self.result = dict(posicao=posicao, medicao=medicao)
            return True
        except ValueError as exc:
            messagebox.showerror('Dados inválidos', str(exc), parent=self)
            return False


class Aplicativo:
    def __init__(self, root, planta=None):
        self.root = root
        root.title('Mapa Wi-Fi • medições manuais')
        root.geometry('1280x850')
        root.minsize(950, 650)
        self.imagem = None
        self.pontos = []
        self.escala = None
        self.origem = (0, 0)
        self.origem_definida = False
        self.definindo_origem = False
        self.y_para_cima = tk.BooleanVar(value=False)
        self.alterado = False
        self.mapa = False
        self.calibracao = None
        self.marcas_calibracao = []
        self.regua = None
        self.marcas_regua = []
        self.campanha = tk.StringVar(value='Antes')
        self.status = tk.StringVar(value='Abra uma planta PNG para começar.')
        self.modo_ativo = tk.StringVar(value='Modo: adicionar/editar pontos')
        self.opacidade = tk.DoubleVar(value=.25)
        self.transparencia = tk.DoubleVar(value=75)
        self.texto_transparencia = tk.StringVar(value='Transparência: 75%')
        self.texto_escala = tk.StringVar(value='Escala ainda não definida (pixels).')
        self.mostrar_nomes = tk.BooleanVar(value=True)
        self.fig = Figure(figsize=(9, 6), dpi=100, layout='constrained')
        topo = ttk.Frame(root, padding=8)
        topo.pack(fill='x')
        for nome, func in [('Abrir planta PNG', self.nova_planta), ('Abrir projeto', self.abrir_projeto), ('Salvar projeto', self.salvar_projeto), ('Exportar CSV', self.csv), ('Exportar PNG', self.png)]:
            ttk.Button(topo, text=nome, command=func).pack(side='left', padx=3)
        self.botao_importar = ttk.Button(topo, text='Importar posições (JSON)', command=self.importar_pontos, state='disabled')
        self.botao_importar.pack(side='left', padx=3)
        corpo = ttk.Frame(root)
        corpo.pack(fill='both', expand=True)
        lateral = ttk.Frame(corpo, padding=12, width=285)
        lateral.pack(side='left', fill='y')
        ttk.Label(lateral, text='CAMPANHA', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        combo = ttk.Combobox(lateral, textvariable=self.campanha, values=['Antes', 'Depois'], state='readonly')
        combo.pack(fill='x', pady=6)
        combo.bind('<<ComboboxSelected>>', lambda e: self.trocar_campanha())
        ttk.Label(lateral, text='A mesma malha é usada nas duas campanhas.\nClique na planta para adicionar pontos.\nClique num ponto para editar sua leitura.', wraplength=255).pack(anchor='w', pady=8)
        self.botao_pontos = ttk.Button(lateral, text='Adicionar/editar pontos', command=self.ativar_pontos)
        self.botao_pontos.pack(fill='x', pady=3)
        ttk.Label(lateral, textvariable=self.modo_ativo, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=3)
        for nome, func in [('Gerar mapa de calor', self.gerar), ('Mostrar só os pontos', self.so_pontos), ('1. Definir escala em metros', self.calibrar), ('2. Escolher origem (0, 0)', self.definir_origem), ('Régua: medir distância', self.iniciar_regua)]:
            ttk.Button(lateral, text=nome, command=func).pack(fill='x', pady=3)
        ttk.Label(lateral, textvariable=self.texto_escala, wraplength=255).pack(anchor='w')
        ttk.Checkbutton(lateral, text='Eixo Y positivo para cima', variable=self.y_para_cima, command=self.mudar_eixo).pack(anchor='w')
        ttk.Label(lateral, textvariable=self.texto_transparencia).pack(anchor='w', pady=(8, 0))
        ttk.Scale(lateral, from_=0, to=100, variable=self.transparencia, command=self.mudar_transparencia).pack(fill='x')
        ttk.Label(lateral, text='0% = cores sólidas • 100% = só a planta').pack(anchor='w')
        ttk.Label(lateral, text='PONTOS • mediana da campanha', font=('Segoe UI', 10, 'bold')).pack(anchor='w', pady=(14, 4))
        self.lista = tk.Listbox(lateral, width=36, height=7, exportselection=False)
        self.lista.pack(fill='both', expand=True)
        self.lista.bind('<Double-Button-1>', lambda e: self.editar_selecionado())
        ttk.Button(lateral, text='Editar ponto selecionado', command=self.editar_selecionado).pack(fill='x', pady=4)
        ttk.Button(lateral, text='Excluir ponto das duas campanhas', command=self.excluir).pack(fill='x')
        ttk.Label(lateral, text=f'Cores: {COR_MIN_DBM} a {COR_MAX_DBM} dBm, iguais nos dois mapas.\n{COR_MIN_DBM} dBm ou menos: vermelho.\nInterpolação linear entre medianas.\nSem estimativa fora do contorno dos pontos.\nParedes não são detectadas automaticamente.', wraplength=255).pack(anchor='w', pady=12)
        painel = ttk.Frame(corpo)
        painel.pack(side='left', fill='both', expand=True)
        visualizacao = ttk.Frame(painel, padding=5)
        visualizacao.pack(side='top', fill='x')
        ttk.Button(visualizacao, text='Zoom +', command=lambda: self.aplicar_zoom(1 / 1.3)).pack(side='left', padx=3)
        ttk.Button(visualizacao, text='Zoom −', command=lambda: self.aplicar_zoom(1.3)).pack(side='left', padx=3)
        ttk.Button(visualizacao, text='Restaurar visão', command=self.restaurar_visao).pack(side='left', padx=3)
        ttk.Checkbutton(visualizacao, text='Mostrar nomes dos pontos', variable=self.mostrar_nomes, command=self.desenhar).pack(side='left', padx=10)
        self.canvas = FigureCanvasTkAgg(self.fig, master=painel)
        self.toolbar = NavigationToolbar2Tk(self.canvas, painel, pack_toolbar=False)
        self.toolbar.pack(side='bottom', fill='x')
        self.canvas.get_tk_widget().pack(fill='both', expand=True)
        self.canvas.mpl_connect('button_press_event', self.clicar)
        self.canvas.mpl_connect('scroll_event', self.zoom_mouse)
        ttk.Label(root, textvariable=self.status, padding=8).pack(fill='x')
        root.protocol('WM_DELETE_WINDOW', self.fechar)
        root.bind('<Escape>', lambda e: self.cancelar_marcacao())
        self.desenhar()
        if planta:
            self.carregar_planta(planta)

    def confirmar(self):
        if not self.alterado:
            return True
        resposta = messagebox.askyesnocancel('Salvar alterações?', 'Salvar o projeto antes de continuar?', parent=self.root)
        if resposta is None:
            return False
        return self.salvar_projeto() if resposta else True

    def nova_planta(self):
        if not self.confirmar():
            return
        caminho = filedialog.askopenfilename(filetypes=[('Planta PNG', '*.png')])
        if caminho:
            self.carregar_planta(caminho)

    def carregar_planta(self, caminho):
        try:
            with Image.open(caminho) as im:
                imagem = im.convert('RGB')
            self.imagem, self.pontos, self.escala = imagem, [], None
            self.origem, self.definindo_origem = (0, 0), False
            self.origem_definida = False
            self.alterado, self.mapa, self.calibracao = True, False, None
            self.regua = None
            self.status.set('Clique para marcar um ponto. Pode deixar as leituras vazias para planejar a malha.')
            self.desenhar(restaurar=True)
        except Exception as exc:
            messagebox.showerror('Não foi possível abrir a planta', str(exc))

    def desenhar(self, restaurar=False):
        pode_importar = self.imagem is not None and self.escala is not None and self.origem_definida
        self.botao_importar.state(['!disabled'] if pode_importar else ['disabled'])
        limites = None
        if not restaurar and self.imagem is not None and hasattr(self, 'ax'):
            limites = self.ax.get_xlim(), self.ax.get_ylim()
        sx, sy = fatores_escala(self.escala)
        self.texto_escala.set(f'Escala: X = {sx:.5g} m/px • Y = {sy:.5g} m/px' if self.escala else 'Escala ainda não definida (pixels).')
        self.fig.clear()
        self.marcas_calibracao = []
        self.marcas_regua = []
        self.ax = self.fig.add_subplot(111)
        self.camada = None
        self.lista.delete(0, 'end')
        if self.imagem is None:
            self.ax.text(.5, .5, 'Abra uma planta PNG\nMarque pontos • Digite leituras • Gere o mapa', ha='center', va='center', transform=self.ax.transAxes, fontsize=16)
            self.ax.set_axis_off()
        else:
            w, h = self.imagem.size
            self.ax.imshow(self.imagem, extent=(0, w, h, 0))
            if self.mapa:
                try:
                    x, y, z = interpolar(self.pontos, self.campanha.get(), w, h, escala=self.escala)
                    self.camada = self.ax.imshow(np.ma.masked_invalid(z), extent=(0, w, h, 0), origin='upper', cmap='RdYlGn', vmin=COR_MIN_DBM, vmax=COR_MAX_DBM, alpha=self.opacidade.get(), interpolation='nearest', zorder=1)
                    # Barra opaca para que os valores da escala não dependam da planta.
                    from matplotlib.cm import ScalarMappable
                    from matplotlib.colors import Normalize
                    self.fig.colorbar(ScalarMappable(norm=Normalize(COR_MIN_DBM, COR_MAX_DBM), cmap='RdYlGn'), ax=self.ax, label='Potência recebida (dBm)', shrink=.8)
                except ValueError as exc:
                    self.mapa = False
                    self.status.set(str(exc))
            for p in self.pontos:
                med, _ = estatisticas(p['campanhas'].get(self.campanha.get(), {}).get('leituras', []))
                valor = 'a medir' if med is None else f'{med:g} dBm'
                cx, cy = coordenadas(p['x'], p['y'], self.escala, self.origem, self.y_para_cima.get())
                unidade = 'm' if self.escala else 'px'
                self.lista.insert('end', f'P{p["id"]:02d}  {valor}  ({cx:.2f}; {cy:.2f}) {unidade}')
                self.ax.plot(p['x'], p['y'], 'o', color='#172a46' if med is not None else '#888888', markersize=5, markeredgecolor='white')
                rotulo = f'P{p["id"]}\n{valor}' if self.mostrar_nomes.get() else valor
                self.ax.annotate(rotulo, (p['x'], p['y']), xytext=(5, 6), textcoords='offset points', fontsize=8, bbox=dict(facecolor='white', alpha=.85, edgecolor='none', pad=2))
            self.ax.set(xlim=(0, w), ylim=(h, 0), title=f'Wi-Fi • {self.campanha.get()} • ' + ('medianas / interpolação linear' if self.mapa else 'malha de medição'))
            self.ax.set_aspect('equal')
            from matplotlib.ticker import FuncFormatter
            self.ax.xaxis.set_major_formatter(FuncFormatter(lambda v, pos: f'{coordenadas(v, 0, self.escala, self.origem, self.y_para_cima.get())[0]:.2f}'))
            self.ax.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f'{coordenadas(0, v, self.escala, self.origem, self.y_para_cima.get())[1]:.2f}'))
            self.ax.plot(*self.origem, marker='+', color='#0066cc', markersize=14, markeredgewidth=2, zorder=5)
            self.ax.annotate('0, 0', self.origem, xytext=(7, -14), textcoords='offset points', color='#0066cc', fontsize=9, zorder=5, bbox=dict(facecolor='white', alpha=.85, edgecolor='none'))
            unidade = 'm' if self.escala else 'px'
            self.ax.set_xlabel(f'x ({unidade}) • positivo para a direita')
            self.ax.set_ylabel(f'y ({unidade}) • positivo para ' + ('cima' if self.y_para_cima.get() else 'baixo'))
            if limites is not None:
                self.ax.set_xlim(limites[0])
                self.ax.set_ylim(limites[1])
        self.desenhar_calibracao()
        self.desenhar_regua()
        self.canvas.draw_idle()
        self.toolbar.update()

    def aplicar_zoom(self, fator, centro=None):
        if self.imagem is None:
            return
        w, h = self.imagem.size
        x0, x1 = self.ax.get_xlim()
        y1, y0 = self.ax.get_ylim()  # A imagem tem Y invertido.
        largura, altura = x1 - x0, y1 - y0
        if largura <= 0 or altura <= 0:
            return
        fator = float(np.clip(fator, max(w / 100 / largura, h / 100 / altura), min(w / largura, h / altura)))
        cx, cy = centro if centro is not None else ((x0 + x1) / 2, (y0 + y1) / 2)
        nova_largura, nova_altura = largura * fator, altura * fator
        esquerda = float(np.clip(cx - (cx - x0) * fator, 0, max(0, w - nova_largura)))
        topo = float(np.clip(cy - (cy - y0) * fator, 0, max(0, h - nova_altura)))
        self.ax.set_xlim(esquerda, esquerda + nova_largura)
        self.ax.set_ylim(topo + nova_altura, topo)
        self.canvas.draw_idle()

    def zoom_mouse(self, event):
        if self.imagem is None or event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            return
        if event.button in ('up', 'down'):
            self.aplicar_zoom(1 / 1.3 if event.button == 'up' else 1.3, (event.xdata, event.ydata))

    def restaurar_visao(self):
        if self.imagem is not None:
            self.ax.set_xlim(0, self.imagem.width)
            self.ax.set_ylim(self.imagem.height, 0)
            self.canvas.draw_idle()

    def desenhar_calibracao(self):
        self.atualizar_modo()
        for artista in self.marcas_calibracao:
            artista.remove()
        self.marcas_calibracao = []
        if self.calibracao:
            for nome, (x, y) in zip(('A', 'B'), self.calibracao):
                self.marcas_calibracao.extend(self.ax.plot(x, y, 'o', color='#ff00aa', markersize=9, markeredgecolor='white', zorder=10))
                self.marcas_calibracao.append(self.ax.annotate(nome, (x, y), xytext=(9, 9), textcoords='offset points', weight='bold', color='#a00070', zorder=11, bbox=dict(facecolor='white', edgecolor='#a00070', pad=3)))
            if len(self.calibracao) == 2:
                (ax, ay), (bx, by) = self.calibracao
                self.marcas_calibracao.extend(self.ax.plot([ax, bx], [ay, by], '--', color='#a00070', zorder=9))
                for inicio, fim, nome, cor in [((ax, ay), (bx, ay), 'X (m)', '#0066cc'), ((bx, ay), (bx, by), 'Y (m)', '#a00070')]:
                    self.marcas_calibracao.append(self.ax.annotate('', xy=fim, xytext=inicio, arrowprops=dict(arrowstyle='<->', color=cor, lw=2), zorder=10))
                    meio = ((inicio[0] + fim[0]) / 2, (inicio[1] + fim[1]) / 2)
                    self.marcas_calibracao.append(self.ax.annotate(nome, meio, xytext=(5, 5), textcoords='offset points', color=cor, zorder=11, bbox=dict(facecolor='white', edgecolor='none', alpha=.9)))
        self.canvas.draw_idle()

    def iniciar_regua(self):
        if self.imagem is None:
            return
        if self.escala is None:
            messagebox.showinfo('Defina a escala', 'Use “Definir escala em metros” antes de medir distâncias.', parent=self.root)
            return
        self.preparar_marcacao()
        self.calibracao = None
        self.definindo_origem = False
        self.desenhar_calibracao()
        self.regua = []
        self.desenhar_regua()
        self.status.set('Régua: clique no primeiro ponto. Esc limpa a régua e volta à edição.')

    def desenhar_regua(self):
        self.atualizar_modo()
        for artista in self.marcas_regua:
            artista.remove()
        self.marcas_regua = []
        if self.regua:
            for nome, ponto in zip(('R1', 'R2'), self.regua):
                self.marcas_regua.extend(self.ax.plot(*ponto, 'o', color='#007e87', markersize=8, markeredgecolor='white', zorder=12))
                self.marcas_regua.append(self.ax.annotate(nome, ponto, xytext=(7, 7), textcoords='offset points', color='#00646b', weight='bold', zorder=13, bbox=dict(facecolor='white', edgecolor='none', alpha=.9)))
            if len(self.regua) == 2:
                a, b = self.regua
                distancia, dx, dy = medir_distancia(a, b, self.escala)
                self.marcas_regua.append(self.ax.annotate('', xy=b, xytext=a, arrowprops=dict(arrowstyle='<->', color='#007e87', lw=2), zorder=12))
                meio = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
                texto = f'{distancia:.2f} m\nΔX: {dx:.2f} m • ΔY: {dy:.2f} m'
                self.marcas_regua.append(self.ax.annotate(texto, meio, xytext=(8, -30), textcoords='offset points', fontsize=9, zorder=13, bbox=dict(facecolor='white', edgecolor='#007e87', alpha=.95, pad=4)))
        self.canvas.draw_idle()

    def limpar_regua(self):
        self.regua = None
        self.desenhar_regua()

    def clicar(self, event):
        if self.imagem is None or event.inaxes != self.ax or event.button != 1 or self.toolbar.mode:
            return
        x, y = event.xdata, event.ydata
        if not (0 <= x <= self.imagem.width and 0 <= y <= self.imagem.height):
            return
        if self.regua is not None:
            if len(self.regua) == 2:
                self.regua = []
            self.regua.append((x, y))
            self.desenhar_regua()
            if len(self.regua) == 2:
                distancia, dx, dy = medir_distancia(*self.regua, self.escala)
                self.status.set(f'Distância: {distancia:.2f} m • ΔX: {dx:.2f} m • ΔY: {dy:.2f} m. Outra medida: clique. Para sair: “Adicionar/editar pontos” ou Esc.')
            else:
                self.status.set('Régua: primeiro ponto marcado. Clique no segundo ponto; Esc cancela.')
            return
        if self.definindo_origem:
            self.origem = (x, y)
            self.origem_definida = True
            self.definindo_origem = False
            self.alterado = True
            self.desenhar()
            self.status.set('Origem (0, 0) definida. As coordenadas dos pontos foram atualizadas.')
            return
        if self.calibracao is not None:
            self.calibracao.append((x, y))
            self.desenhar_calibracao()
            self.canvas.draw()  # Exibe A/B e os trechos antes de abrir o diálogo modal.
            if len(self.calibracao) == 2:
                a, b = self.calibracao
                if abs(b[0] - a[0]) < 1 and abs(b[1] - a[1]) < 1:
                    self.calibracao.pop()
                    self.desenhar_calibracao()
                    self.status.set('Escolha B em outro local da planta. Os pontos estão sobrepostos. Esc cancela.')
                    return
                dialogo = DistanciasXY(self.root, a, b, self.escala)
                self.calibracao = None
                if dialogo.result is not None:
                    self.escala = dialogo.result
                    self.alterado = True
                    self.status.set('Escalas X e Y calibradas em metros. Use “Escolher origem (0, 0)” para posicionar o zero.')
                else:
                    self.status.set('Calibração cancelada. A escala anterior foi mantida.')
                self.desenhar()
            else:
                self.status.set('Ponto A marcado. Clique em B: pode ser uma linha horizontal, vertical ou diagonal. Esc cancela.')
            return
        for p in self.pontos:
            sx, sy = self.ax.transData.transform((p['x'], p['y']))
            if np.hypot(sx - event.x, sy - event.y) < 12:
                self.editar(p)
                return
        ponto = dict(id=max((p['id'] for p in self.pontos), default=0) + 1, x=round(x, 3), y=round(y, 3), campanhas={})
        self.editar(ponto, novo=True)

    def editar(self, ponto, novo=False):
        dialogo = Medicao(self.root, ponto, self.campanha.get(), self.escala, self.origem, self.y_para_cima.get(), self.imagem.size, self.pontos)
        if dialogo.result is not None:
            ponto['x'], ponto['y'] = dialogo.result['posicao']
            ponto['campanhas'][self.campanha.get()] = dialogo.result['medicao']
            if novo:
                self.pontos.append(ponto)
            self.alterado = True
            self.desenhar()

    def editar_selecionado(self):
        if self.lista.curselection():
            self.editar(self.pontos[self.lista.curselection()[0]])

    def excluir(self):
        if self.lista.curselection() and messagebox.askyesno('Excluir ponto', 'Excluir este ponto e suas leituras nas duas campanhas?'):
            del self.pontos[self.lista.curselection()[0]]
            self.alterado = True
            self.desenhar()

    def gerar(self):
        if self.imagem is None:
            return
        try:
            interpolar(self.pontos, self.campanha.get(), *self.imagem.size, escala=self.escala)
        except ValueError as exc:
            messagebox.showinfo('Ainda não é possível gerar o mapa', str(exc))
            return
        self.calibracao = None
        self.definindo_origem = False
        self.limpar_regua()
        self.mapa = True
        self.status.set('Mapa estimado entre pontos. Áreas sem cor ficam fora da região interpolada; não representam sinal zero.')
        self.desenhar()

    def so_pontos(self):
        self.mapa = False
        self.desenhar()

    def trocar_campanha(self):
        self.limpar_regua()
        self.calibracao = None
        self.definindo_origem = False
        self.desenhar()

    def mudar_opacidade(self, valor):
        if getattr(self, 'camada', None) is not None:
            self.camada.set_alpha(float(valor))
            self.canvas.draw_idle()

    def mudar_transparencia(self, valor):
        porcentagem = float(valor)
        self.opacidade.set(1 - porcentagem / 100)
        self.texto_transparencia.set(f'Transparência: {porcentagem:.0f}%')
        self.mudar_opacidade(self.opacidade.get())
        if self.imagem is not None:
            self.alterado = True

    def mudar_eixo(self):
        self.alterado = self.imagem is not None
        self.desenhar()

    def atualizar_modo(self):
        if self.regua is not None:
            modo = 'régua'
        elif self.calibracao is not None:
            modo = 'calibração da escala'
        elif self.definindo_origem:
            modo = 'definir origem'
        else:
            modo = 'adicionar/editar pontos'
        self.modo_ativo.set(f'Modo: {modo}')

    def ativar_pontos(self):
        self.preparar_marcacao()
        self.limpar_regua()
        self.calibracao = None
        self.definindo_origem = False
        self.desenhar_calibracao()
        self.status.set('Adição de pontos habilitada. Clique num local vazio para adicionar ou num ponto existente para editar.')

    def cancelar_marcacao(self):
        self.ativar_pontos()

    def preparar_marcacao(self):
        if self.toolbar.mode == 'pan/zoom':
            self.toolbar.pan()
        elif self.toolbar.mode == 'zoom rect':
            self.toolbar.zoom()

    def definir_origem(self):
        if self.imagem is not None:
            self.limpar_regua()
            self.preparar_marcacao()
            self.calibracao = None
            self.desenhar_calibracao()
            self.definindo_origem = True
            self.atualizar_modo()
            self.status.set('Clique na planta onde deve ficar (0, 0). Esc cancela.')

    def calibrar(self):
        if self.imagem is not None:
            self.limpar_regua()
            self.preparar_marcacao()
            self.definindo_origem = False
            self.calibracao = []
            self.desenhar_calibracao()
            self.status.set('Clique em A e B. Informe X e Y em metros; use zero no eixo não medido. Esc cancela.')

    def salvar_projeto(self):
        if self.imagem is None:
            return False
        caminho = filedialog.asksaveasfilename(defaultextension='.json', filetypes=[('Projeto Wi-Fi', '*.json')])
        if not caminho:
            return False
        try:
            salvar(caminho, self.imagem, self.pontos, self.escala, self.origem, self.y_para_cima.get(), self.opacidade.get(), self.origem_definida)
            self.alterado = False
            self.status.set(f'Projeto salvo: {caminho}')
            return True
        except Exception as exc:
            messagebox.showerror('Erro ao salvar', str(exc))
            return False

    def abrir_projeto(self):
        if not self.confirmar():
            return
        caminho = filedialog.askopenfilename(filetypes=[('Projeto Wi-Fi', '*.json')])
        if caminho:
            try:
                imagem, pontos, escala, config = abrir(caminho, com_configuracao=True)
                self.imagem, self.pontos, self.escala = imagem, pontos, escala
                self.origem = config['origem']
                self.origem_definida = config['origem_definida']
                self.y_para_cima.set(config['y_para_cima'])
                self.transparencia.set((1 - config['opacidade']) * 100)
                self.mudar_transparencia(self.transparencia.get())
                self.definindo_origem = False
                self.alterado, self.mapa, self.calibracao = False, False, None
                self.regua = None
                self.desenhar(restaurar=True)
                self.status.set('Projeto aberto. Selecione a campanha para consultar ou editar as leituras.')
            except Exception as exc:
                messagebox.showerror('Projeto inválido', str(exc))

    def importar_pontos(self):
        if self.imagem is None or self.escala is None or not self.origem_definida:
            messagebox.showinfo('Defina escala e origem', 'Abra a planta de destino, defina a escala em metros e escolha a origem (0,0) antes de importar.', parent=self.root)
            return
        caminho = filedialog.askopenfilename(title='Importar somente posições de outro projeto', filetypes=[('Projeto Wi-Fi', '*.json')])
        if not caminho:
            return
        try:
            _, pontos, escala, config = abrir(caminho, com_configuracao=True)
            novos = importar_posicoes(pontos, escala, config['origem'], config['y_para_cima'],
                                      self.escala, self.origem, self.y_para_cima.get(), self.imagem.size, self.pontos)
        except Exception as exc:
            messagebox.showerror('Não foi possível importar', str(exc), parent=self.root)
            return
        self.pontos.extend(novos)
        self.alterado = True
        self.ativar_pontos()
        self.desenhar()
        self.status.set(f'{len(novos)} posições importadas, sem potências ou observações. Confira os locais e salve o projeto de destino.')

    def csv(self):
        caminho = filedialog.asksaveasfilename(defaultextension='.csv', filetypes=[('Planilha CSV', '*.csv')])
        if caminho:
            try:
                exportar_csv(caminho, self.pontos, self.escala, self.origem, self.y_para_cima.get())
                self.status.set(f'Planilha exportada: {caminho}')
            except Exception as exc:
                messagebox.showerror('Erro na exportação', str(exc))

    def png(self):
        if self.imagem is None:
            return
        caminho = filedialog.asksaveasfilename(defaultextension='.png', filetypes=[('Mapa PNG', '*.png')])
        if caminho:
            try:
                self.fig.savefig(caminho, dpi=220, bbox_inches='tight', facecolor='white')
                self.status.set(f'Imagem exportada: {caminho}')
            except Exception as exc:
                messagebox.showerror('Erro na exportação', str(exc))

    def fechar(self):
        if self.confirmar():
            self.root.destroy()


if __name__ == '__main__':
    root = tk.Tk()
    app = Aplicativo(root, sys.argv[1] if len(sys.argv) > 1 else None)
    root.mainloop()
