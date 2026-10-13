# -*- coding: utf-8 -*-
"""
LEGISLAÇÃO POR NICHO
====================
Infere o setor da empresa (CNAE informado, NCM dos insumos e produtos, palavras do nome/descrição, CFOPs)
e entrega os pontos de atenção tributários daquele nicho: o que a fiscalização olha, benefícios usuais,
regimes especiais, riscos típicos. Cada ponto traz a base legal ou "verificar dispositivo".
Nada aqui é específico de uma empresa: são perfis de setor.
"""
from collections import Counter

# ponto = (tema, o_que_verificar, base_legal, regra_do_motor_relacionada)
SETORES = {
 'metal_mecanica': {
  'nome': 'Metalurgia, produtos de metal e componentes mecânicos (inclui climatização, ventilação, esquadrias, estruturas)',
  'cnae': ['24', '25', '28'], 'ncm_insumo': ['72', '73', '74', '76', '3214', '3208', '3209'], 'ncm_produto': ['73', '76', '8414', '8415', '8419', '8421', '8481', '8302', '8307'],
  'palavras': ['metal', 'metalur', 'alumin', 'aço', 'aco ', 'ar condicionado', 'difus', 'climat', 'ventila', 'esquadria', 'estrutura', 'usinagem', 'caldeiraria', 'grelha'],
  'resumo': 'Indústria de transformação com cadeia longa de insumos (metais, tintas, componentes), industrialização por encomenda em terceiros (anodização, pintura, corte), vendas a contribuintes (revendas/indústrias) e a não contribuintes (obras, construtoras, instaladoras, consumidor final). Tributos centrais: ICMS (crédito de insumos, energia, frete, ativo; DIFAL nas vendas a não contribuinte de outra UF), IPI (crédito de MP/PI/ME, alíquotas da TIPI por posição), PIS/COFINS (créditos amplos no não cumulativo) e ISS quando há instalação/montagem.',
  'pontos': [
   ('Energia elétrica', 'Indústria metal-mecânica é eletrointensiva (fornos, compressores, solda, usinagem). Crédito de ICMS sobre a parcela industrial da energia (laudo) e crédito integral de PIS/COFINS no não cumulativo. Fatura em nome de outro CNPJ ou locador = crédito perdido.', 'LC 87/96, art. 33, II, "b"; Leis 10.637/10.833, art. 3º', 'F09'),
   ('Industrialização por encomenda (5901/1902/1124)', 'Remessa com suspensão de IPI e diferimento/suspensão de ICMS conforme a UF; no retorno, o valor cobrado pelo industrializador (mão de obra + material aplicado) tem ICMS (diferido em várias UFs quando o produto segue para nova industrialização ou comercialização) e IPI. Prazo de retorno (180 dias, prorrogável) e escrituração do material remetido são pontos de autuação. Se a encomenda é de bem para uso do encomendante ou de item da lista de serviços, discussão ISS × ICMS.', 'RIPI, art. 43, VI e VII; Convênio AE 15/1974 e Convênio ICMS 34/90 (verificar vigência por UF); LC 116/2003, item 14.05; RICMS da UF (diferimento na industrialização por encomenda)', 'F26'),
   ('Vendas a não contribuinte em outra UF (6107/6108) e entrega futura (5922/6922 + 5116/6116)', 'DIFAL devido à UF de destino com base única e FCP, recolhido por GNRE ou inscrição de substituto; na venda para entrega futura, o ICMS e o DIFAL nascem na remessa efetiva (x116), o simples faturamento (x922) não tem imposto. Erro comum: usar alíquota interna na 6107 ou esquecer o DIFAL nas 6116.', 'EC 87/2015; LC 190/2022; Convênio ICMS 236/2021; Ajuste SINIEF 07/2005 (CFOP 5922/6922)', 'X13'),
   ('IPI e classificação fiscal', 'Alíquotas da TIPI variam por posição (partes de máquinas 84.14/84.15 versus obras de alumínio 76.16 versus estruturas 73.08): a NCM define o IPI, a ST e o DIFAL. Conferir a TIPI vigente (Decreto 11.158/2022 e alterações) e a coerência NCM × descrição; crédito de IPI sobre MP/PI/ME, inclusive os consumidos no processo (discos de corte, eletrodos, gases).', 'RIPI, art. 226, I; PN CST 65/1979; TIPI', 'F12a'),
   ('Convênio ICMS 52/91 (máquinas e equipamentos industriais)', 'Se o produto vendido consta dos Anexos I/II do Convênio 52/91 (pela NCM e descrição), há redução de base de cálculo do ICMS nas saídas internas e interestaduais (carga reduzida) com manutenção de crédito. Verificar item a item.', 'Convênio ICMS 52/1991 e prorrogações (verificar vigência); RICMS da UF', ''),
   ('Substituição tributária de materiais de construção e ferragens', 'Grelhas, difusores, tubos, conexões, perfis, ferragens e tintas podem estar nos segmentos de "materiais de construção" e "ferramentas" do Convênio 142/2018 conforme a UF de destino; a indústria pode ser substituta nas vendas a revendas. CEST obrigatório.', 'Convênio ICMS 142/2018, Anexos X, XI e XXIII (verificar); RICMS da UF de destino', 'F19'),
   ('Bloco K e inventário', 'Indústria com CNAE 24/25/28 está no cronograma do bloco K (K200/K280 no mínimo; K230/K235 conforme faturamento); inventário anual no bloco H. Falta de bloco K é multa e sinal para fiscalização de produção.', 'Ajuste SINIEF 02/2009, art. 3º; Guia Prático EFD', 'F21'),
   ('Sucata e resíduos (aparas, cavacos)', 'Venda de sucata gerada na produção tem diferimento de ICMS em muitas UFs e tributação normal de PIS/COFINS (receita); não escriturar a venda de sucata é omissão de receita.', 'RICMS da UF (diferimento de sucata, verificar); Leis 10.637/10.833, art. 1º', ''),
   ('Instalação e montagem', 'Quando a empresa também instala o que fabrica, o serviço de instalação (item 7.02/14.06 da LC 116) é ISS e, se o material for fornecido pelo prestador, a discussão de ISS × ICMS exige contrato e nota separados. No Lucro Presumido a receita de serviço tem presunção de 32%, não 8%.', 'LC 116/2003, itens 7.02 e 14.06; Lei 9.249/95, art. 15, §1º, III', 'R04'),
  ],
 },
 'maquinas_equipamentos': {
  'nome': 'Máquinas, equipamentos e eletroeletrônicos', 'cnae': ['26', '27', '28', '29', '30'], 'ncm_insumo': ['84', '85', '73', '74', '39'], 'ncm_produto': ['84', '85', '90'],
  'palavras': ['maquin', 'equipamento', 'eletr', 'automa', 'motor', 'bomba', 'compressor'],
  'resumo': 'Bens de capital e eletroeletrônicos: IPI por posição da TIPI, redução de base do Convênio 52/91 (máquinas industriais e agrícolas), crédito de ICMS/PIS-COFINS sobre insumos, DIFAL para não contribuinte, garantia e assistência técnica (ISS × ICMS), exportação com drawback.',
  'pontos': [
   ('Convênio ICMS 52/91', 'Redução de base para máquinas industriais (Anexo I) e agrícolas (Anexo II) listadas por NCM: carga reduzida nas saídas internas e interestaduais, com manutenção do crédito. Verificar cada NCM vendida contra o anexo.', 'Convênio ICMS 52/1991 (verificar vigência); RICMS da UF', ''),
   ('Ex-tarifário e importação', 'Bens de capital sem similar nacional: II reduzido (ex-tarifário) e IPI/ICMS na importação; crédito de PIS/COFINS-Importação e de ICMS na entrada (CIAP quando ativo).', 'Resoluções GECEX (ex-tarifário); Lei 10.865/2004, art. 15', ''),
   ('Garantia, assistência técnica e peças', 'Remessas em garantia (5949/6949 ou CFOP específico), peças aplicadas em garantia (IPI/ICMS) e serviços de conserto (ISS, item 14.01) exigem CFOP e documentos próprios.', 'LC 116/2003, item 14.01; RICMS', ''),
   ('Drawback e exportação', 'Drawback suspensão/isenção nos insumos de produtos exportados; crédito de ICMS mantido e transferível; PIS/COFINS-exportação ressarcível.', 'Lei 11.945/2009 (drawback integrado); LC 87/96, art. 25, §1º', 'F25'),
   ('Bloco K', 'Obrigatório para CNAE 26 a 30 conforme cronograma.', 'Ajuste SINIEF 02/2009', 'F21'),
  ],
 },
 'cosmeticos_perfumaria': {
  'nome': 'Cosméticos, perfumaria e higiene pessoal', 'cnae': ['2063'], 'ncm_insumo': ['3302', '3823', '2905', '3402', '3923', '7010'], 'ncm_produto': ['3303', '3304', '3305', '3307', '3401'],
  'palavras': ['cosmet', 'perfum', 'beleza', 'higiene', 'toucador'],
  'resumo': 'PIS/COFINS monofásico (fabricante/importador paga alíquota concentrada, revenda a alíquota zero), ICMS-ST na maioria das UFs com MVA elevada, IPI com alíquotas relevantes e equiparação a industrial dos atacadistas interdependentes, ANVISA.',
  'pontos': [
   ('PIS/COFINS monofásico', 'Fabricante/importador: CST 02 com 2,2%/10,3% (NCM 3303 a 3307, 3401.11.90, 3401.20.10, 9603.21.00); revenda: CST 04 alíquota zero. Crédito nas aquisições para revenda é vedado; crédito de insumos do fabricante é permitido.', 'Lei 10.147/2000, arts. 1º e 2º; Lei 10.637/10.833, art. 3º, I, "b"', 'P05'),
   ('Equiparação a industrial (IPI) do atacadista interdependente', 'Atacadista que revende produtos de perfumaria/cosméticos adquiridos de fabricante interdependente é equiparado a industrial: debita e credita IPI. Sem interdependência, não há IPI na revenda.', 'Lei 7.798/1989, art. 7º e Anexo III; RIPI, art. 9º (verificar inciso)', 'F12b'),
   ('ICMS-ST', 'Substituição tributária com MVA por UF e protocolos/convênios; ressarcimento nas vendas interestaduais do substituído; CEST obrigatório.', 'Convênio ICMS 142/2018, Anexo XIX (verificar); protocolos por UF', 'F13'),
   ('Brindes, amostras e bonificações', 'Amostra grátis de cosmético tem regras próprias de isenção (embalagem, quantidade); bonificação é tributada na regra geral.', 'Convênio ICMS 29/1990; RICMS da UF', 'F16'),
  ],
 },
 'farmaceutico': {
  'nome': 'Farmacêutico e produtos para saúde', 'cnae': ['2110', '2121', '2123', '4644', '4771'], 'ncm_insumo': ['29', '30'], 'ncm_produto': ['3001', '3002', '3003', '3004', '3005', '3006'],
  'palavras': ['farma', 'medicament', 'drogaria', 'hospitalar'],
  'resumo': 'Monofásico de PIS/COFINS (2,1%/9,9% no fabricante, alíquota zero na revenda), crédito presumido para medicamentos de lista (Decreto 3.803/2001), ICMS-ST com PMC/PMPF, Convênio 87/02 (isenção em vendas a órgãos públicos), Lei do Bem.',
  'pontos': [
   ('PIS/COFINS monofásico e crédito presumido', 'CST 02 no fabricante, CST 04 na revenda; crédito presumido do art. 3º da Lei 10.147 para medicamentos listados (Decreto 3.803/2001).', 'Lei 10.147/2000, arts. 1º a 3º', 'P05'),
   ('ICMS-ST com base PMC/PMPF', 'Base de cálculo da ST pelo preço máximo ao consumidor ou PMPF; restituição quando a venda efetiva é menor (Tema 201).', 'Convênio ICMS 142/2018; RE 593.849', 'F13'),
   ('Isenção em vendas a órgãos públicos', 'Convênio ICMS 87/02: isenção de ICMS nas vendas de medicamentos listados a órgãos da administração pública.', 'Convênio ICMS 87/2002 (verificar vigência)', ''),
  ],
 },
 'alimentos_bebidas': {
  'nome': 'Alimentos e bebidas', 'cnae': ['10', '11'], 'ncm_insumo': ['01', '02', '04', '07', '08', '10', '11', '12', '15', '17'], 'ncm_produto': ['02', '04', '15', '16', '17', '18', '19', '20', '21', '22'],
  'palavras': ['aliment', 'bebida', 'laticin', 'frigor', 'panific', 'massa', 'cerveja', 'refriger'],
  'resumo': 'Alíquota zero de PIS/COFINS em cesta básica e insumos agropecuários, crédito presumido agroindustrial (Lei 10.925, art. 8º), ICMS reduzido/isento em cesta básica estadual, ST em bebidas e alimentos industrializados, regime especial de bebidas frias (Lei 13.097).',
  'pontos': [
   ('Alíquota zero e crédito presumido agroindustrial', 'Saídas de cesta básica com CST 06; insumos de pessoa física/cooperativa geram crédito presumido (35%/50%/60% conforme o produto).', 'Lei 10.925/2004, arts. 1º e 8º; Lei 12.839/2013', 'P05'),
   ('Bebidas frias', 'Regime especial com alíquotas específicas no fabricante e alíquota zero no varejo; ST de ICMS com PMPF.', 'Lei 13.097/2015, arts. 14 a 39', 'P05'),
   ('Cesta básica estadual', 'Redução de base/isenção de ICMS por UF (lista própria), com ou sem manutenção de crédito.', 'RICMS da UF (verificar lista)', ''),
   ('Perdas, quebras e vencidos', 'Estorno de crédito de ICMS e de PIS/COFINS sobre mercadorias perecidas/vencidas; documento de baixa.', 'LC 87/96, art. 21, IV; Leis 10.637/10.833, art. 3º, §13 (verificar)', ''),
  ],
 },
 'autopecas_veiculos': {
  'nome': 'Autopeças, pneus e veículos', 'cnae': ['29', '4530', '4541'], 'ncm_insumo': ['72', '73', '40', '84', '85'], 'ncm_produto': ['8708', '8707', '4011', '8409', '8511', '8512', '8536', '8544'],
  'palavras': ['autope', 'auto pe', 'pneu', 'veicul', 'automotiv'],
  'resumo': 'PIS/COFINS monofásico (Lei 10.485: fabricante 2%/9,6% ou 1,65%/7,6% + regime dos Anexos, revenda alíquota zero), ICMS-ST de autopeças (Protocolo 41/08 e 97/10) com MVA por origem, IPI com alíquotas por posição.',
  'pontos': [
   ('Monofásico de autopeças', 'Fabricante/importador de itens dos Anexos I e II da Lei 10.485: CST 02; revenda: CST 04. Itens fora dos anexos: tributação normal.', 'Lei 10.485/2002, art. 3º e Anexos', 'P05'),
   ('ST de autopeças', 'Protocolos ICMS 41/2008 e 97/2010: MVA ajustada por origem e destino; índice de fidelidade; ressarcimento nas vendas interestaduais.', 'Protocolos ICMS 41/2008 e 97/2010; Convênio 142/2018', 'F13'),
  ],
 },
 'construcao_materiais': {
  'nome': 'Materiais de construção e acabamento', 'cnae': ['23', '4744', '4679'], 'ncm_insumo': ['25', '68', '69', '72', '73'], 'ncm_produto': ['2523', '6810', '6907', '7308', '7314', '7318', '3917', '3922', '3925', '7607', '8481'],
  'palavras': ['constru', 'cimento', 'ceram', 'revestimento', 'tijolo', 'argamassa'],
  'resumo': 'ICMS-ST ampla (segmento materiais de construção do Convênio 142/2018), vendas a não contribuinte (obras) com DIFAL, construtora não é contribuinte do ICMS, ISS na execução da obra.',
  'pontos': [
   ('ST de materiais de construção', 'Segmento com muitos itens no Convênio 142/2018; a indústria/importador é substituta; CEST obrigatório; MVA por UF.', 'Convênio ICMS 142/2018, Anexo XI (verificar)', 'F19'),
   ('Vendas a construtoras e obras', 'Construtora é não contribuinte na regra geral: venda interestadual com alíquota interestadual + DIFAL ao destino (não usar alíquota interna).', 'EC 87/2015; LC 190/2022; STJ, Súmula 432', 'X13'),
  ],
 },
 'textil_confeccao_calcados': {
  'nome': 'Têxtil, confecção e calçados', 'cnae': ['13', '14', '15'], 'ncm_insumo': ['50', '51', '52', '53', '54', '55', '56', '58', '59', '60', '41', '42'], 'ncm_produto': ['61', '62', '63', '64', '42'],
  'palavras': ['textil', 'confec', 'malha', 'calçad', 'calcad', 'vestu', 'tecido'],
  'resumo': 'Industrialização por encomenda (facção) com ISS × ICMS, desoneração/reoneração da folha (CPRB), crédito presumido de ICMS por UF (têxtil e calçadista), Simples com Fator R nas facções.',
  'pontos': [
   ('Facção e industrialização por encomenda', 'Serviço de facção sobre material do encomendante para industrialização posterior: ICMS/IPI (não ISS) na regra geral; suspensão de IPI na remessa e retorno.', 'RIPI, art. 43; LC 116, item 14.05; RICMS', 'F26'),
   ('CPRB (desoneração da folha)', 'Setores de confecção e calçados tiveram CPRB até 2024 com reoneração gradual a partir de 2025 (verificar alíquotas do ano).', 'Lei 12.546/2011; Lei 14.973/2024', ''),
   ('Créditos presumidos estaduais', 'Vários estados concedem crédito presumido para indústria têxtil/calçadista (ex.: SC TTD, RS, MG, CE); verificar adesão.', 'RICMS da UF (verificar)', ''),
  ],
 },
 'moveis_madeira': {
  'nome': 'Móveis e madeira', 'cnae': ['16', '31'], 'ncm_insumo': ['44', '4410', '4411', '4412', '7318', '8302', '3921'], 'ncm_produto': ['9401', '9403', '9404', '44'],
  'palavras': ['movei', 'móvei', 'madeira', 'marcen'],
  'resumo': 'IPI por posição (móveis 94.03), crédito de IPI sobre MDF/MDP/ferragens, vendas a consumidor final com DIFAL, móveis sob medida (ISS × ICMS), crédito presumido estadual no polo moveleiro.',
  'pontos': [
   ('Móveis sob medida', 'Móvel planejado com instalação: discussão ISS (item 7.02/14.13) × ICMS; predominância de mercadoria = ICMS.', 'LC 116/2003; STJ REsp 1.092.206 (verificar)', ''),
   ('Crédito de IPI sobre insumos', 'MDF/MDP, ferragens, tintas e vernizes com IPI destacado geram crédito.', 'RIPI, art. 226, I', 'F12a'),
  ],
 },
 'plasticos_embalagens': {
  'nome': 'Plásticos, borracha e embalagens', 'cnae': ['22', '17'], 'ncm_insumo': ['3901', '3902', '3903', '3904', '3907', '4002', '48'], 'ncm_produto': ['39', '40', '4819', '4821'],
  'palavras': ['plastic', 'plástic', 'embalag', 'borracha', 'papel'],
  'resumo': 'Crédito de IPI/ICMS sobre resinas, embalagens como insumo do cliente (crédito de PIS/COFINS pelo adquirente), ST de descartáveis e materiais de construção plásticos, logística reversa.',
  'pontos': [
   ('Embalagem de transporte × apresentação', 'Para o cliente, embalagem de apresentação é insumo com crédito; embalagem de transporte também gera crédito (STJ). Para o fabricante, resinas e aditivos são MP.', 'REsp 1.221.170; PN COSIT 5/2018', 'P04'),
   ('ST de descartáveis e plásticos de construção', 'Copos, pratos, sacolas, tubos e conexões podem estar em ST conforme a UF.', 'Convênio ICMS 142/2018 (verificar anexos)', 'F19'),
  ],
 },
 'quimico': {
  'nome': 'Químicos, tintas e produtos de limpeza', 'cnae': ['20'], 'ncm_insumo': ['28', '29', '32', '34', '38'], 'ncm_produto': ['3208', '3209', '3214', '3402', '3808', '3814', '2828'],
  'palavras': ['quimic', 'químic', 'tinta', 'limpeza', 'solvente'],
  'resumo': 'ST de tintas e vernizes (Convênio 74/94 e 142/18), controle de produtos controlados (Exército/PF), IPI por posição, crédito de insumos, defensivos com alíquota zero/isenção.',
  'pontos': [
   ('ST de tintas, vernizes e solventes', 'Convênio ICMS 74/94 (tintas) incorporado ao 142/2018: ST nacional, MVA por UF.', 'Convênio ICMS 74/1994; Convênio 142/2018, Anexo XXIII (verificar)', 'F19'),
   ('Defensivos e fertilizantes', 'Alíquota zero de PIS/COFINS e redução de base/isenção de ICMS (Convênio 100/97) para insumos agropecuários listados.', 'Lei 10.925/2004, art. 1º, I e II; Convênio ICMS 100/1997', 'P05'),
  ],
 },
 'agro': {
  'nome': 'Agropecuária e agroindústria', 'cnae': ['01', '02', '03', '1041', '1061', '1071'], 'ncm_insumo': ['31', '3808', '1209', '2309', '84'], 'ncm_produto': ['01', '02', '04', '07', '08', '09', '10', '12', '15', '17', '23', '24'],
  'palavras': ['agro', 'rural', 'grão', 'grao', 'soja', 'milho', 'frigor', 'usina', 'açúcar', 'acucar', 'cooperativa'],
  'resumo': 'Diferimento de ICMS nas saídas de produtor rural, Convênio 100/97 (insumos), crédito presumido de PIS/COFINS agroindustrial, suspensão nas vendas de produtos in natura (Lei 10.925, art. 9º), Funrural, exportação.',
  'pontos': [
   ('Suspensão e crédito presumido de PIS/COFINS', 'Venda de produtos agropecuários in natura por cerealista/produtor com suspensão; agroindústria com crédito presumido sobre insumos de PF.', 'Lei 10.925/2004, arts. 8º e 9º; IN RFB 2.121/2022', 'P05'),
   ('Convênio 100/97', 'Redução de base/isenção de ICMS para insumos agropecuários (rações, sementes, fertilizantes, defensivos).', 'Convênio ICMS 100/1997', ''),
   ('Diferimento nas saídas de produtor', 'ICMS diferido para a etapa seguinte; agroindústria recolhe como responsável.', 'RICMS da UF', ''),
  ],
 },
 'comercio_atacado_varejo': {
  'nome': 'Comércio atacadista e varejista', 'cnae': ['46', '47'], 'ncm_insumo': [], 'ncm_produto': [],
  'palavras': ['comerc', 'distribui', 'atacad', 'varej', 'loja', 'mercado', 'supermercado'],
  'resumo': 'Sem industrialização: sem crédito de IPI (salvo equiparação), sem crédito de ICMS sobre energia (até 2033), crédito de ICMS sobre mercadorias e frete, ST na entrada (substituído) com ressarcimento nas vendas interestaduais, monofásicos na revenda (alíquota zero), NFC-e e registro 1601, regimes especiais de atacadista por UF (crédito presumido/outorgado).',
  'pontos': [
   ('Ressarcimento de ST', 'Mercadoria comprada com ST e revendida para outra UF ou com base efetiva menor: ressarcimento/restituição.', 'Convênio 142/2018; RE 593.849', 'F13'),
   ('Monofásicos e alíquota zero na revenda', 'Cosméticos, farmacêuticos, autopeças, pneus, bebidas frias, cesta básica: CST 04/06 nas saídas; no Simples, segregação no PGDAS-D.', 'Leis 10.147, 10.485, 13.097, 10.925; LC 123, art. 18, §4º-A', 'P05'),
   ('Regimes de atacadista', 'Vários estados concedem crédito presumido/outorgado ao atacadista com regime especial (ex.: SC TTD 409/410/411, GO, ES Compete, MG, PR Paraná Competitivo, verificar). Avaliar adesão e condições (contrapartidas, fundos).', 'Legislação estadual (verificar)', 'F08'),
   ('Cartões e PIX (1601)', 'Registro obrigatório quando há recebimentos por cartão/PIX; cruzado com administradoras.', 'Guia Prático EFD', 'F21'),
  ],
 },
 'servicos': {
  'nome': 'Prestação de serviços', 'cnae': ['33', '41', '42', '43', '49', '52', '55', '56', '58', '59', '60', '61', '62', '63', '69', '70', '71', '72', '73', '74', '77', '78', '80', '81', '82', '85', '86', '87', '88', '90', '93', '95', '96'], 'ncm_insumo': [], 'ncm_produto': [],
  'palavras': ['servi', 'consult', 'engenharia', 'software', 'tecnologia', 'clinica', 'transport', 'logist'],
  'resumo': 'ISS (fora do escopo fiscal do SPED, mas cruzado com a EFD Contribuições), presunção de 32% no Lucro Presumido (16% para transporte), PIS/COFINS cumulativo na maioria; no não cumulativo, insumos pela essencialidade (subcontratação, EPI, combustível no transporte).',
  'pontos': [
   ('Presunção de IRPJ/CSLL', 'Serviços em geral: 32% (IRPJ e CSLL); transporte de cargas: 8%/12%; serviços hospitalares: 8%/12% quando organizados como sociedade empresária com estrutura (verificar requisitos).', 'Lei 9.249/1995, art. 15 e 20; IN RFB 1.700/2017', 'R04'),
   ('Retenções na fonte', 'PIS/COFINS/CSLL (4,65%) e IRRF (1,5%/1%) retidos pelos tomadores PJ: compensar na apuração (M200/M600, campo retenções) e na DCTF.', 'Lei 10.833/2003, art. 30; Lei 9.430/96, art. 64', 'P10'),
   ('Transporte: créditos', 'Combustível, pneus, manutenção, pedágio e subcontratação são insumos no não cumulativo; crédito presumido de 75% para subcontratação de transportador PF/Simples (verificar).', 'Lei 10.833/2003, art. 3º, II e §19', 'P04'),
  ],
 },
}

REGIME_PONTOS = {
 'Lucro Presumido': [
  ('Base de cálculo do PIS/COFINS cumulativo (0,65% e 3%)', 'Receita bruta SEM o ICMS destacado (Tema 69 vale para o cumulativo), sem IPI, sem vendas canceladas, descontos incondicionais e devoluções; receitas financeiras e outras receitas fora da atividade não entram (Lei 9.718 com a redação pós-Lei 11.941).', 'Lei 9.718/1998, arts. 2º e 3º; RE 574.706; RE 585.235 (Tema 110)', 'R01'),
  ('Presunção de IRPJ e CSLL', 'Indústria e comércio: 8% (IRPJ) e 12% (CSLL); serviços: 32%; transporte de cargas: 8%/12%; receita de industrialização por encomenda é "venda de produção" (8%), não serviço (verificar tratamento adotado). Adicional de 10% do IRPJ acima de R$ 60 mil/trimestre. Ganhos de capital e receitas financeiras tributados integralmente.', 'Lei 9.249/1995, arts. 15 e 20; Lei 9.430/1996, arts. 1º e 25; IN RFB 1.700/2017', 'R04'),
  ('Sem créditos de PIS/COFINS', 'No cumulativo não há crédito sobre insumos, energia, frete ou ativo: toda análise de crédito de PIS/COFINS fica sem efeito; o que existe é a comparação com o Lucro Real (simulação).', 'Lei 10.637/2002, art. 8º; Lei 10.833/2003, art. 10', 'R03'),
  ('Limite de receita', 'Até R$ 78 milhões de receita bruta no ano anterior; acima, Lucro Real obrigatório.', 'Lei 9.718/1998, art. 13', ''),
  ('Simulação Lucro Real × Presumido', 'Comparar: (a) PIS/COFINS 3,65% sobre receita versus 9,25% sobre receita menos 9,25% dos créditos reais (insumos, energia, frete, depreciação, aluguéis); (b) IRPJ/CSLL sobre 8%/12% da receita versus 34% do lucro real. A margem de equilíbrio sai dos próprios dados.', 'Leis 9.249, 9.430, 9.718, 10.637, 10.833', 'R03'),
 ],
 'Lucro Real': [
  ('PIS/COFINS não cumulativo (1,65% e 7,6%)', 'Créditos amplos (insumos pela essencialidade, energia, frete, aluguéis PJ, depreciação, devoluções); base de saída sem ICMS; base de crédito sem ICMS desde 05/2023; créditos de exportação ressarcíveis.', 'Leis 10.637/2002 e 10.833/2003, art. 3º; Lei 14.592/2023', 'P04'),
  ('IRPJ/CSLL pelo lucro contábil ajustado', 'Adições/exclusões (LALUR/e-LALUR), prejuízo fiscal com trava de 30%, JCP dedutível, incentivos (PAT, Lei do Bem, Rouanet), subvenções para investimento (Lei 14.789/2023: crédito fiscal em vez de exclusão).', 'Decreto 9.580/2018 (RIR); Lei 9.430/96; Lei 14.789/2023', ''),
  ('Estimativas mensais × trimestral', 'Apuração anual com estimativas mensais permite suspensão/redução por balancete; trimestral limita a compensação de prejuízo.', 'Lei 9.430/1996, arts. 1º, 2º e 35', ''),
 ],
 'Simples Nacional': [
  ('Segregação de receitas no PGDAS-D', 'Receitas de produtos com ST, monofásicos de PIS/COFINS e antecipação com encerramento devem ser segregadas para não pagar ICMS/PIS/COFINS em dobro no DAS.', 'LC 123/2006, art. 18, §4º-A; Res. CGSN 140/2018, art. 25', 'P05'),
  ('Sem crédito de ICMS/IPI/PIS/COFINS', 'Optante não se apropria de créditos; transfere crédito de ICMS limitado ao adquirente (art. 23).', 'LC 123/2006, arts. 23 e 24', ''),
  ('Sublimite de ICMS/ISS e DIFAL', 'Acima do sublimite estadual (R$ 3,6 milhões), ICMS/ISS fora do DAS; compras interestaduais de uso/consumo e ativo com DIFAL/antecipação em várias UFs.', 'LC 123/2006, arts. 13, §1º, XIII, "g" e "h", e 19', 'F17'),
  ('Fator R e anexos', 'Serviços dos anexos III/V conforme folha ÷ receita (28%).', 'LC 123/2006, art. 18, §5º-J a §5º-M', ''),
 ],
}

def inferir(e):
    """Pontua os setores com CNAE, NCM de insumos/produtos, palavras e CFOPs. Devolve (chave, pontuação, motivos)."""
    from .conhecimento import cfop_info
    pontos = Counter(); motivos = {}
    p = e['perfil']; texto = (e['nome'] + ' ' + (p.get('descricao_negocio') or '')).lower()
    cnaes = [str(p.get('cnae_principal') or '').replace('-', '').replace('/', '').replace('.', '')] + [str(c).replace('-', '').replace('/', '').replace('.', '') for c in (p.get('cnaes_secundarios') or [])]
    ncm_ent = Counter(); ncm_sai = Counter(); ncm_cad = Counter()
    for s in e['fiscal'].values():
        for it in s['regs'].get('C170', []):
            i = s['itens'].get(it.get('COD_ITEM'), {}); n = (i.get('COD_NCM') or '')
            if not n:
                continue
            (ncm_ent if cfop_info(it.get('CFOP'))['entrada'] else ncm_sai)[n] += it.n('VL_ITEM')
        for i in s['regs'].get('0200', []):
            if i.get('COD_NCM'):
                ncm_cad[i['COD_NCM']] += 1
    for s in e['contrib'].values():
        for it in s['regs'].get('C170', []):
            i = s['itens'].get(it.get('COD_ITEM'), {}); n = (i.get('COD_NCM') or '')
            if n:
                (ncm_ent if cfop_info(it.get('CFOP'))['entrada'] else ncm_sai)[n] += it.n('VL_ITEM')
        for c180 in s['regs'].get('C180', []):
            if c180.get('COD_NCM'):
                ncm_sai[c180['COD_NCM']] += c180.n('VL_TOT_ITEM')
    tot_ent = sum(ncm_ent.values()) or 1; tot_sai = sum(ncm_sai.values()) or 1
    ativ = p.get('atividade')
    for chave, st in SETORES.items():
        m = []
        for c in cnaes:
            if c and any(c.startswith(x) for x in st['cnae']):
                pontos[chave] += 6; m.append('CNAE %s' % c)
        for n, v in ncm_ent.items():
            if any(n.startswith(x) for x in st['ncm_insumo']):
                pontos[chave] += 3 * v / tot_ent; 
        for n, v in ncm_sai.items():
            if any(n.startswith(x) for x in st['ncm_produto']):
                pontos[chave] += 4 * v / tot_sai
        for n, q in ncm_cad.items():
            if any(n.startswith(x) for x in st['ncm_insumo'] + st['ncm_produto']):
                pontos[chave] += 0.02 * q
        for w in st['palavras']:
            if w in texto:
                pontos[chave] += 2; m.append('nome/descrição contém "%s"' % w.strip())
        if ativ == 'comercio' and chave == 'comercio_atacado_varejo':
            pontos[chave] += 3; m.append('atividade inferida: comércio')
        if ativ == 'servico' and chave == 'servicos':
            pontos[chave] += 3; m.append('atividade inferida: serviços')
        if ativ == 'industria' and chave in ('comercio_atacado_varejo', 'servicos'):
            pontos[chave] -= 3
        motivos[chave] = m
    if not pontos:
        return None
    chave, score = pontos.most_common(1)[0]
    ins = [n for n, _ in ncm_ent.most_common(6)]; prods = [n for n, _ in ncm_sai.most_common(6)]
    m = motivos[chave] + (['insumos NCM ' + ', '.join(ins)] if ins else []) + (['produtos NCM ' + ', '.join(prods)] if prods else [])
    alternativos = [(k, round(v, 1)) for k, v in pontos.most_common(3)[1:] if v > 0]
    return {'chave': chave, 'nome': SETORES[chave]['nome'], 'pontuacao': round(score, 1), 'motivos': m, 'alternativos': alternativos, 'resumo': SETORES[chave]['resumo'],
            'pontos': [{'tema': t, 'verificar': v, 'base': b, 'regra': r} for t, v, b, r in SETORES[chave]['pontos']]}

def pontos_regime(regime_tributario):
    return [{'tema': t, 'verificar': v, 'base': b, 'regra': r} for t, v, b, r in REGIME_PONTOS.get(regime_tributario, [])]
