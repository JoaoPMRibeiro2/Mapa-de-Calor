# Mapa Wi-Fi manual

Aplicativo desktop Python criado do zero. Carrega uma planta PNG, permite clicar
para marcar pontos e digitar leituras de potência recebida em dBm. Não coleta Wi-Fi
automaticamente e não exige ruído, canal ou hardware especial. Funciona offline
depois de instalar as dependências.

## Abrir no Windows

Dê dois cliques em **iniciar_windows.cmd**. Nesta pasta de trabalho ele aproveita
o Python e as bibliotecas já instaladas e abre `../planta1.png`. O código é independente
do repositório anterior: apenas reutiliza seu ambiente Python quando disponível.

Para instalar em outro computador (Python 3.11 ou superior com Tkinter):

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

## Utilização

1. Abra a planta PNG. Clique em qualquer local para criar um ponto numerado.
2. Digite as amostras, por exemplo `-55 -57 -54 -56 -55`. Separe por espaços,
   quebras de linha ou ponto e vírgula. Decimais aceitam ponto ou vírgula.
3. A mediana e a dispersão (IQR) aparecem no formulário. Registre o horário real
   da coleta e observações. Um campo vazio permite planejar a malha antes de medir.
4. Clique novamente no marcador ou dê duplo clique na lista para editar o ponto.
   O formulário permite alterar **X e Y**, além de leituras, horário e observações.
   Os campos X e Y são editados **sempre em metros**, relativos à origem escolhida
   e à orientação do eixo Y. Sem calibração, ficam vazios e desabilitados:
   use **1. Definir escala em metros** e reabra o ponto para habilitá-los.
   As leituras e observações continuam editáveis mesmo sem escala. Aceita vírgula decimal
   e coordenadas negativas, desde que a posição continue dentro da planta.
   Mover um ponto altera sua posição nas **duas campanhas**, preservando suas
   leituras; posições fora da planta ou sobre outro ponto são rejeitadas.
5. Se já calculou a mediana em outra ferramenta, pode inserir só esse valor;
   anote que se trata de uma mediana externa. Nesse caso o programa não conhece
   o número original de amostras nem sua dispersão (n e IQR referem-se ao que digitou).
6. Para obter coordenadas em metros, use **1. Definir escala em metros**: clique
   em A e B (linha horizontal, vertical ou diagonal). Cada clique aparece na planta. Após B, as setas
   identificam os trechos X e Y e um formulário pede as duas distâncias reais
   em metros: largura horizontal e altura vertical, **não a diagonal**.
   Para uma linha horizontal de 5,5 m, preencha **X = 5,5; Y = 0**. Para uma
   vertical de 3 m, **X = 0; Y = 3**. Zero indica que aquele eixo não foi medido:
   sua escala anterior é preservada. Na primeira calibração, sem escala anterior,
   a escala do eixo medido é aplicada aos dois (pressupõe escala uniforme).
   Pequenos desvios do clique no eixo informado como zero são ignorados.
   Não são aceitos dois zeros, distâncias negativas ou pontos sobrepostos.
   Aceita vírgula decimal. As duas escalas são independentes, permitindo corrigir
   uma imagem esticada diferentemente em X e Y; não corrige rotação ou perspectiva.
   Cancelar mantém a escala anterior. Em **2. Escolher origem (0, 0)**, clique
   no local desejado da planta. x cresce à direita; marque **Eixo Y positivo para
   cima** se quiser a orientação cartesiana. Sem essa opção, y cresce para baixo.
   A cruz azul indica a origem; eixos e lista mostram as coordenadas relativas.
   Sem calibração, as coordenadas são pixels. Esc cancela a marcação em andamento.
7. Com três ou mais pontos medidos, não todos na mesma linha, clique em
   **Gerar mapa de calor**. Use pontos distribuídos pelo ambiente, não apenas três.
8. Troque para **Depois** para registrar uma segunda campanha na mesma malha.
   Os valores da primeira campanha permanecem preservados. A escala de cores é
   sempre -60 a -30 dBm: -60 dBm ou menos fica vermelho e -30 dBm ou mais fica
   verde. Valores fora dela saturam visualmente, mas ficam intactos.
9. **Salvar projeto** guarda planta, coordenadas, leituras, horários e observações
   num único JSON. **Abrir projeto** recupera tudo, mesmo se a PNG original mudou
   de pasta. Não há salvamento automático; ao fechar, o programa oferece salvar.
10. **Exportar PNG** salva a visualização atual em alta resolução (mapa ou malha).
    **Exportar CSV** salva as duas campanhas, amostras e estatísticas para planilha.
    O CSV usa ponto e vírgula entre colunas e vírgula decimal, para Excel em português.
    Coordenadas em metros, mediana e IQR saem com duas casas decimais; pixels, com
    três. As amostras originais permanecem com sua precisão e vírgula decimal.
    Esse arredondamento é apenas na exportação: os dados no JSON não mudam.
    Gere novamente CSVs antigos após atualizar o programa. Se importar manualmente,
    selecione UTF-8, delimitador `;` e localidade Português (Brasil).
11. Ajuste **Transparência** em tempo real: 0% mostra cores sólidas e 100% deixa
    somente a planta visível. O padrão é 75% para preservar os detalhes do fundo.
    A exportação PNG usa a mesma transparência. Origem, escala, direção do eixo Y
    e transparência ficam salvas no projeto. Projetos antigos continuam abrindo;
    neles, a origem inicial permanece no canto superior esquerdo.

Os controles abaixo do gráfico permitem zoom e deslocamento; desative essas
ferramentas para voltar a adicionar pontos. Excluir um ponto remove suas duas
campanhas e exige confirmação. Para conservar a comparabilidade, defina a malha
antes da coleta e evite excluí-la depois.

## Importar posições de outra planta

1. Salve o projeto de origem em JSON. Ele precisa ter escala em metros definida.
2. Abra a PNG de destino (ou seu projeto). Defina a **escala em metros** e escolha
   explicitamente a **origem (0,0)**. O botão **Importar posições (JSON)** permanece
   desabilitado até concluir as duas etapas.
3. Use o mesmo local físico como origem e a mesma orientação horizontal da planta;
   configure o sentido do eixo Y de acordo com a imagem. Não há correção de rotação.
4. Clique em **Importar posições (JSON)** e selecione o projeto de origem.
   O programa converte as coordenadas relativas em metros para os pixels da planta
   de destino, inclusive quando as imagens têm resoluções diferentes.
5. Confira os locais e salve o projeto de destino.

Somente posições e identificadores são trazidos; potências, observações e horários
não são copiados. Todos os novos pontos ficam **a medir** nas duas campanhas.
Os pontos existentes são mantidos. Identificadores conflitantes recebem novos
números. Se qualquer posição ficar fora da planta ou coincidir com outro ponto,
a importação inteira é cancelada e os dados anteriores permanecem intactos.
O arquivo de origem não é modificado.

A confirmação da origem fica salva nos novos projetos. Em projetos antigos usados
como destino, escolha novamente o (0,0) antes de importar, pois eles não registravam
se a origem havia sido escolhida explicitamente. A origem salva nos projetos antigos
continua sendo respeitada ao usá-los como fonte da importação.

## Zoom e nomes dos pontos

Acima da planta, use **Zoom + / Zoom −** ou role o mouse sobre o mapa para
aproximar/afastar em torno do cursor. **Restaurar visão** mostra a planta inteira.
O zoom é mantido ao editar pontos, gerar o mapa ou alternar nomes.
Para deslocar a área ampliada, use a ferramenta de deslocamento da barra inferior;
**Adicionar/editar pontos** desativa essa ferramenta para voltar à edição.

Desmarque **Mostrar nomes dos pontos** para ocultar P1, P2 etc. da planta,
mantendo os marcadores e valores em dBm. A lista lateral continua identificando
os pontos para edição. O PNG exporta a visualização atual, inclusive zoom e rótulos;
restaure a visão antes de exportar se quiser a planta inteira.

Zoom e visibilidade dos nomes valem para a sessão. Nenhum desses controles altera
coordenadas, leituras, origem ou calibração. Projetos JSON anteriores continuam
compatíveis: abra o projeto salvo para recuperar os pontos e a escala existentes.
O vermelho em -60 dBm é apenas a nova faixa visual, sem modificar as medições.

## Régua de distância

Depois de calibrar a escala, clique em **Régua: medir distância** e escolha dois
locais na planta, inclusive sobre pontos de medição existentes. Os marcadores R1
e R2 e uma linha mostram a distância em linha reta, em metros, além das separações
ΔX e ΔY. O cálculo usa as escalas independentes dos dois eixos:
`distância = sqrt((Δx_px * escala_x)² + (Δy_px * escala_y)²)`.
Não mede trajetos contornando paredes. A origem escolhida não altera a distância.

Um terceiro clique inicia outra medida. O botão **Adicionar/editar pontos** sai
da régua e volta à marcação de pontos; ele também encerra calibração, escolha de
origem, zoom ou deslocamento. **Esc** faz o mesmo. O indicador **Modo** mostra
a ferramenta ativa (pontos, régua, calibração ou origem).
A régua não adiciona leituras nem modifica a malha. É uma ferramenta
temporária: não fica salva no JSON, mas aparece no PNG se estiver visível ao exportar.
