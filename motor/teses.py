# -*- coding: utf-8 -*-
"""Catálogo de teses de recuperação de créditos, versionado por vigência.

Cada tese junta as regras do motor que a evidenciam (F.., P.., X.., R..) e diz o que a regra não diz:
- vigência (de/até): só períodos dentro dela entram no cálculo;
- segurança jurídica: 'Consolidada' (lei expressa ou tese vinculante), 'Majoritária' (jurisprudência e RFB favoráveis,
  depende de prova do caso), 'Interpretativa' (controvertida, depende de medida judicial ou de risco assumido);
- comprovação padrão: 'Comprovado' (o valor sai do documento) ou 'Estimado' (depende de premissa ou análise técnica);
- via: como recupera (escrituração extemporânea, PER/DCOMP, ressarcimento, pedido à SEFAZ, judicial) e se exige habilitação;
- atualização: 'SELIC' (indébito, CTN art. 165 e Lei 9.250/95, art. 39, §4º) ou 'Sem atualização' (crédito escritural:
  Súmula 411 do STJ, só há correção se houver oposição ilegítima do Fisco);
- prazo: 5 anos (CTN, art. 168, I, para indébito; LC 87/96, art. 23, parágrafo único, e Lei 10.637/10.833 para crédito escritural);
- requisitos e documentos de prova (o que a equipe precisa confirmar e juntar ao dossiê).
O fundamento legal vem de base_legal.FUNDAMENTACAO (por regra) somado ao fundamento próprio da tese; nada é inventado:
onde o dispositivo exato não foi confirmado, o texto diz "verificar"."""

SELIC = 'SELIC'
SEM = 'Sem atualização (crédito escritural, Súmula 411 STJ)'

TESES = [
    {'id': 'T01', 'nome': 'Exclusão do ICMS da base do PIS/COFINS (Tema 69 STF)', 'tributo': 'PIS/COFINS',
     'regras': ['P06', 'X10', 'R01'], 'grupo': 'icms_base_pis', 'vigencia': ('2017-03', None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SELIC,
     'via': 'Administrativa: retificar a EFD Contribuições e transmitir PER/DCOMP de pagamento indevido (restituição ou compensação). Ação judicial só se houver período anterior a 15/03/2017 com ação ajuizada antes dessa data.',
     'habilitacao': 'Não exige habilitação prévia (é indébito apurado pelo próprio contribuinte).',
     'fundamento': 'STF, RE 574.706/PR (Tema 69): o ICMS não compõe a base do PIS/COFINS; embargos de 13/05/2021: ICMS destacado na nota, efeitos desde 15/03/2017. Lei 14.592/2023 positivou a exclusão.',
     'requisitos': ['Saídas tributadas pelo ICMS com o ICMS destacado incluído na base de PIS/COFINS', 'Período a partir de 03/2017 e dentro de 5 anos do pagamento', 'Pagamento efetivo das contribuições no período (DARF/DCTF)'],
     'documentos': ['EFD Contribuições (C170/C175, M210/M610)', 'EFD ICMS/IPI (C190) ou XML das saídas', 'DARF e DCTF do período', 'Memória da base recalculada por mês']},
    {'id': 'T02', 'nome': 'Exclusão do ICMS-ST da base do PIS/COFINS do substituído (Tema 1.125 STJ)', 'tributo': 'PIS/COFINS',
     'regras': ['T02'], 'grupo': 'icms_st_base_pis', 'vigencia': (None, None),
     'seguranca': 'Majoritária', 'comprovacao': 'Estimado', 'atualizacao': SELIC,
     'via': 'Judicial recomendada (a RFB não aplica administrativamente; tese repetitiva do STJ). Com decisão, PER/DCOMP após habilitação do crédito judicial.',
     'habilitacao': 'Crédito decorrente de decisão judicial: habilitação prévia na RFB antes da compensação (IN RFB 2.055/2021).',
     'fundamento': 'STJ, REsp 1.896.678 e 1.958.265 (Tema 1.125, 13/12/2023): o ICMS-ST não compõe a base do PIS/COFINS devidos pelo substituído (verificar modulação no acórdão).',
     'requisitos': ['Empresa substituída (compra com ICMS-ST retido e revende)', 'Regime não cumulativo ou cumulativo com receita tributada', 'Medida judicial própria'],
     'documentos': ['XML/EFD das entradas com ST (C170 VL_ICMS_ST)', 'EFD Contribuições das saídas', 'DARF/DCTF']},
    {'id': 'T03', 'nome': 'Créditos de PIS/COFINS sobre insumos (essencialidade e relevância)', 'tributo': 'PIS/COFINS',
     'regras': ['P04', 'P04b', 'X09'], 'grupo': 'insumos_pis', 'vigencia': (None, None),
     'seguranca': 'Majoritária', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: escrituração extemporânea por retificação da EFD Contribuições do mês de aquisição; o crédito abate débitos e o saldo segue as regras de ressarcimento/compensação (só para receitas de exportação, suspensão, isenção ou alíquota zero).',
     'habilitacao': 'Não exige habilitação. Exige laudo ou descrição técnica do processo para itens de essencialidade.',
     'fundamento': 'Lei 10.637/2002 e Lei 10.833/2003, art. 3º, II; STJ, REsp 1.221.170/PR (Temas 779/780); Parecer Normativo COSIT 5/2018.',
     'requisitos': ['Regime não cumulativo', 'Bem ou serviço essencial ou relevante à produção ou à prestação do serviço', 'Fornecedor pessoa jurídica domiciliada no país (ou importação com PIS/COFINS-Importação)', 'Não ser item com vedação expressa (art. 3º, §2º)'],
     'documentos': ['XML das entradas', 'EFD Contribuições (C170 CST 70/98/99)', 'Descrição do processo produtivo / laudo de essencialidade']},
    {'id': 'T04', 'nome': 'Crédito de PIS/COFINS sobre energia elétrica', 'tributo': 'PIS/COFINS',
     'regras': ['P07', 'F09b'], 'grupo': 'energia_pis', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Administrativa: escrituração extemporânea (retificação da EFD Contribuições, C501/C505).', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.637/2002, art. 3º, IX; Lei 10.833/2003, art. 3º, III.',
     'requisitos': ['Regime não cumulativo', 'Fatura de energia em nome do estabelecimento'], 'documentos': ['Faturas de energia (C500)', 'EFD Contribuições']},
    {'id': 'T05', 'nome': 'Crédito de PIS/COFINS sobre frete e armazenagem', 'tributo': 'PIS/COFINS',
     'regras': ['P08', 'F10b'], 'grupo': 'frete_pis', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Administrativa: escrituração extemporânea (D101/D105).', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.833/2003, art. 3º, IX (frete e armazenagem na venda) e art. 3º, I e II (frete na compra compõe o custo); IN RFB 2.121/2022.',
     'requisitos': ['Regime não cumulativo', 'CT-e tomado pela empresa', 'Frete de venda (ônus do vendedor) ou de compra de insumo/revenda'], 'documentos': ['XML dos CT-e', 'EFD Contribuições (D100/D101/D105)']},
    {'id': 'T06', 'nome': 'Crédito de PIS/COFINS sobre ativo imobilizado', 'tributo': 'PIS/COFINS',
     'regras': ['P11'], 'grupo': 'ativo_pis', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: F120 (depreciação) ou F130 (aquisição, crédito em 12/24/48 meses ou imediato para máquinas novas da produção).', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.637/2002 e Lei 10.833/2003, art. 3º, VI e §1º, III; Lei 11.774/2008, art. 1º.',
     'requisitos': ['Regime não cumulativo', 'Bem utilizado na produção, prestação de serviço ou locação', 'Controle patrimonial do bem'], 'documentos': ['XML de compra do ativo', 'Ficha do imobilizado', 'EFD Contribuições (F120/F130)']},
    {'id': 'T07', 'nome': 'Saldo credor de PIS/COFINS (exportação e vendas não tributadas) sem PER/DCOMP', 'tributo': 'PIS/COFINS',
     'regras': ['P09', 'F25b'], 'grupo': 'saldo_pis', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': 'SELIC só a partir do 361º dia do pedido (Tema 1.003 STJ)',
     'via': 'Administrativa: PER/DCOMP de ressarcimento trimestral ou compensação com outros tributos federais.', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.637/2002, art. 5º; Lei 10.833/2003, art. 6º; Lei 11.033/2004, art. 17; Lei 11.116/2005, art. 16; IN RFB 2.055/2021.',
     'requisitos': ['Crédito vinculado a exportação ou a vendas com suspensão, isenção, alíquota zero ou não incidência', 'Saldo nos registros 1100/1500 não utilizado'], 'documentos': ['EFD Contribuições (1100/1500)', 'Memória do rateio']},
    {'id': 'T08', 'nome': 'PIS/COFINS pago em produto monofásico ou de alíquota zero', 'tributo': 'PIS/COFINS',
     'regras': ['F20', 'P05'], 'grupo': 'monofasico', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SELIC,
     'via': 'Administrativa: retificar a EFD Contribuições (CST 04/06) e PER/DCOMP de pagamento indevido.', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.147/2000; Lei 10.485/2002; Lei 13.097/2015; Lei 10.925/2004; Lei 10.865/2004, art. 28; CTN, arts. 165 e 168.',
     'requisitos': ['NCM efetivamente no regime monofásico/alíquota zero (conferir a descrição do produto)', 'Empresa revendedora (não é a fabricante/importadora)', 'Pagamento efetivo no período'],
     'documentos': ['Cadastro de itens (0200) e XML de venda', 'EFD Contribuições (C170/C181/C185)', 'DARF/DCTF']},
    {'id': 'T09', 'nome': 'Crédito de ICMS de entradas não aproveitado', 'tributo': 'ICMS',
     'regras': ['F26', 'X02', 'F15', 'F14'], 'grupo': 'icms_entradas', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Administrativa: crédito extemporâneo conforme o RICMS da UF (alguns estados exigem comunicação ou autorização prévia).', 'habilitacao': 'Depende do RICMS da UF.',
     'fundamento': 'LC 87/96, arts. 19, 20 e 23, parágrafo único (5 anos da emissão).',
     'requisitos': ['Documento idôneo com ICMS destacado', 'Entrada vinculada a operação tributada', 'Dentro de 5 anos da emissão'], 'documentos': ['XML das entradas', 'EFD ICMS/IPI (C100/C170/C190)']},
    {'id': 'T10', 'nome': 'Crédito de ICMS de energia elétrica na industrialização ou exportação', 'tributo': 'ICMS',
     'regras': ['F09', 'F09c'], 'grupo': 'energia_icms', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: crédito extemporâneo com laudo técnico de consumo na produção (exigência da maioria das UFs).', 'habilitacao': 'Laudo técnico de rateio.',
     'fundamento': 'LC 87/96, art. 33, II, "b" e "c".',
     'requisitos': ['Estabelecimento industrial ou exportador', 'Laudo de consumo na produção'], 'documentos': ['Faturas de energia (C500)', 'Laudo técnico']},
    {'id': 'T11', 'nome': 'Crédito de ICMS sobre frete tomado (CT-e)', 'tributo': 'ICMS',
     'regras': ['F10', 'X05'], 'grupo': 'frete_icms', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Administrativa: crédito extemporâneo (D100/D190).', 'habilitacao': 'Depende do RICMS da UF.',
     'fundamento': 'LC 87/96, art. 20.', 'requisitos': ['Empresa tomadora do CT-e', 'Frete vinculado a operação tributada'], 'documentos': ['XML dos CT-e', 'EFD ICMS/IPI (D100)']},
    {'id': 'T12', 'nome': 'Crédito de ICMS do ativo imobilizado (CIAP)', 'tributo': 'ICMS',
     'regras': ['F11'], 'grupo': 'ciap', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: lançar no CIAP (G125) as parcelas de 1/48 dentro de 5 anos.', 'habilitacao': 'Não exige.',
     'fundamento': 'LC 87/96, art. 20, §5º; art. 23, parágrafo único.', 'requisitos': ['Bem do ativo ligado à atividade', 'Saídas tributadas (crédito proporcional)'], 'documentos': ['XML de compra do ativo', 'EFD (G110/G125)']},
    {'id': 'T13', 'nome': 'Ressarcimento de ICMS-ST (saída interestadual ou base menor)', 'tributo': 'ICMS-ST',
     'regras': ['F13'], 'grupo': 'st_ressarc', 'vigencia': (None, None),
     'seguranca': 'Majoritária', 'comprovacao': 'Estimado', 'atualizacao': 'Conforme lei da UF',
     'via': 'Pedido de ressarcimento à SEFAZ no rito do estado (ex.: SP, Portaria CAT 42/2018).', 'habilitacao': 'Em vários estados, credenciamento ou regime especial.',
     'fundamento': 'LC 87/96, art. 10; Convênio ICMS 142/2018 (verificar cláusula); STF, RE 593.849 (Tema 201).',
     'requisitos': ['Mercadoria adquirida com ST', 'Saída para outra UF ou base efetiva menor que a presumida'], 'documentos': ['XML de entrada e saída', 'EFD (C170, C176/C180-C186 conforme a UF)']},
    {'id': 'T14', 'nome': 'Crédito de IPI de insumos não aproveitado e saldo credor ressarcível', 'tributo': 'IPI',
     'regras': ['F12a', 'F12c'], 'grupo': 'ipi', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': 'SELIC só a partir do 361º dia do pedido (Tema 1.003 STJ)',
     'via': 'Administrativa: escrituração do crédito e PER/DCOMP de ressarcimento trimestral do saldo (Lei 9.779/99, art. 11).', 'habilitacao': 'Não exige.',
     'fundamento': 'RIPI (Decreto 7.212/2010), art. 226; Lei 9.779/1999, art. 11; IN RFB 2.055/2021.',
     'requisitos': ['Estabelecimento industrial ou equiparado', 'Insumo com IPI destacado'], 'documentos': ['XML das entradas', 'EFD (E500/E510/E520)']},
    {'id': 'T15', 'nome': 'ICMS pago a maior (alíquota interestadual ou DIFAL acima do devido)', 'tributo': 'ICMS',
     'regras': ['F18', 'X11', 'X13'], 'grupo': 'icms_maior', 'vigencia': (None, None),
     'seguranca': 'Interpretativa', 'comprovacao': 'Comprovado', 'atualizacao': 'Conforme lei da UF',
     'via': 'Pedido de restituição à SEFAZ; exige prova de que o encargo não foi repassado ao adquirente ou autorização dele (CTN, art. 166).', 'habilitacao': 'Prova do art. 166 do CTN.',
     'fundamento': 'Resoluções do Senado 22/1989 e 13/2012; EC 87/2015; LC 190/2022; CTN, art. 166.',
     'requisitos': ['Destaque/recolhimento acima da alíquota devida', 'Prova de não repasse ou autorização do adquirente'], 'documentos': ['XML de saída', 'EFD (C190, E300)', 'Guias pagas']},
    {'id': 'T16', 'nome': 'Retenções na fonte (CSRF/IRRF) não deduzidas', 'tributo': 'PIS/COFINS',
     'regras': ['R05', 'R06'], 'grupo': 'retencoes', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SELIC,
     'via': 'Administrativa: dedução na apuração (retificar EFD/DCTF) ou PER/DCOMP do saldo retido.', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.833/2003, arts. 30 a 36; Lei 9.430/1996, art. 64 (verificar); IN RFB 2.055/2021.',
     'requisitos': ['Retenção informada na NFS-e/EFD-Reinf pelo tomador', 'Valor não deduzido na apuração do mês'], 'documentos': ['NFS-e com retenção', 'EFD Contribuições (A100, M200/M600)', 'EFD-Reinf / DIRF do tomador']},
    {'id': 'T17', 'nome': 'Saldo credor de ICMS acumulado (exportação ou outros)', 'tributo': 'ICMS',
     'regras': ['F08'], 'grupo': 'saldo_icms', 'vigencia': (None, None),
     'seguranca': 'Majoritária', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Pedido de transferência/utilização do crédito acumulado no sistema da UF (ex.: SP e-CredAc; PR SISCRED).', 'habilitacao': 'Pedido e homologação pela SEFAZ.',
     'fundamento': 'LC 87/96, art. 25, §§1º e 2º.', 'requisitos': ['Saldo credor acumulado e origem identificada (exportação ou regra estadual)'], 'documentos': ['EFD (E110, 1200)', 'Memória da origem do saldo']},
    {'id': 'T20', 'nome': 'Crédito de PIS/COFINS de entradas fora da EFD Contribuições', 'tributo': 'PIS/COFINS',
     'regras': ['X15'], 'grupo': 'entradas_fora_efd', 'vigencia': (None, None),
     'seguranca': 'Majoritária', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: escriturar as notas na EFD Contribuições do mês (retificadora) com CST de crédito; crédito extemporâneo dentro de 5 anos.', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.637/2002 e Lei 10.833/2003, art. 3º, I e II e §4º.',
     'requisitos': ['Regime não cumulativo', 'Nota de insumo ou revenda escriturada no SPED Fiscal e ausente da EFD Contribuições', 'Natureza de insumo/revenda confirmada item a item'],
     'documentos': ['SPED Fiscal (C100/C170)', 'EFD Contribuições do mesmo mês', 'XML das notas']},
    {'id': 'T21', 'nome': 'Crédito de PIS/COFINS sobre devoluções de vendas', 'tributo': 'PIS/COFINS',
     'regras': ['T21'], 'grupo': 'devolucao_pis', 'vigencia': (None, None),
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Administrativa: retificar a EFD Contribuições do mês da devolução com o CST de crédito (C170 CST 50 a 56, natureza 12 no M105/M505).', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.637/2002, art. 3º, VIII, e Lei 10.833/2003, art. 3º, VIII: crédito sobre bens recebidos em devolução cuja receita de venda tenha integrado o faturamento do mês ou de mês anterior, tributada no regime não cumulativo.',
     'requisitos': ['Regime não cumulativo', 'Venda original tributada pelo PIS/COFINS não cumulativo', 'Devolução documentada (NF-e de devolução com referência à nota de venda)'],
     'documentos': ['XML da devolução e da venda original', 'EFD Contribuições (C170 da devolução)']},
    {'id': 'T27', 'nome': 'Crédito de PIS/COFINS sobre aluguéis, arrendamento e outros custos do F100', 'tributo': 'PIS/COFINS',
     'regras': ['T27'], 'grupo': 'f100', 'vigencia': (None, None), 'regimes': ['nao_cumulativo', 'misto'],
     'seguranca': 'Consolidada', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: retificar o F100 com a natureza do crédito (NAT_BC_CRED) e CST de crédito.', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.637/2002 e Lei 10.833/2003, art. 3º, IV (aluguéis de prédios, máquinas e equipamentos pagos a PJ, usados nas atividades), V (arrendamento mercantil de PJ, exceto optante do Simples) e IX (armazenagem).',
     'requisitos': ['Regime não cumulativo', 'Pagamento a pessoa jurídica domiciliada no país', 'Bem usado nas atividades da empresa', 'Contrato e comprovantes'],
     'documentos': ['EFD Contribuições (F100)', 'Contratos de aluguel/arrendamento', 'Notas ou recibos']},
    {'id': 'T28', 'nome': 'Crédito do PIS/COFINS-Importação', 'tributo': 'PIS/COFINS',
     'regras': ['T28'], 'grupo': 'importacao', 'vigencia': (None, None), 'regimes': ['nao_cumulativo', 'misto'],
     'seguranca': 'Consolidada', 'comprovacao': 'Estimado', 'atualizacao': SEM,
     'via': 'Administrativa: escriturar o crédito do PIS/COFINS-Importação pago (C120 e C170 com CST de crédito); crédito extemporâneo dentro de 5 anos.', 'habilitacao': 'Não exige.',
     'fundamento': 'Lei 10.865/2004, art. 15 (crédito do PIS/COFINS-Importação pago na importação de bens para revenda ou insumo, no regime não cumulativo).',
     'requisitos': ['Regime não cumulativo', 'Bem importado para revenda, insumo ou ativo', 'PIS/COFINS-Importação efetivamente pago (DI/DUIMP)'],
     'documentos': ['DI/DUIMP e comprovante de pagamento', 'XML da nota de entrada de importação', 'EFD Contribuições']},
    {'id': 'T29', 'nome': 'Exclusão do ISS da base do PIS/COFINS (Tema 118 STF)', 'tributo': 'PIS/COFINS',
     'regras': ['T29'], 'grupo': 'iss_base', 'vigencia': (None, None), 'regimes': ['nao_cumulativo', 'misto', 'cumulativo'],
     'seguranca': 'Interpretativa', 'comprovacao': 'Comprovado', 'atualizacao': SELIC,
     'via': 'Judicial: a RFB não aplica. Ação para excluir o ISS e restituir/compensar os últimos 5 anos; com decisão, habilitação prévia do crédito.', 'habilitacao': 'Crédito judicial: habilitação prévia (IN RFB 2.055/2021).',
     'fundamento': 'STF, RE 592.616 (Tema 118): inclusão do ISS na base do PIS/COFINS, mesma razão de decidir do Tema 69 (verificar a situação do julgamento e eventual modulação antes de propor).',
     'requisitos': ['Prestação de serviço com ISS destacado na NFS-e', 'ISS dentro da base do PIS/COFINS', 'Ação judicial'],
     'documentos': ['NFS-e emitidas', 'EFD Contribuições (A100)', 'DARF/DCTF']},
    {'id': 'T31', 'nome': 'Crédito de IPI nas devoluções de vendas', 'tributo': 'IPI',
     'regras': ['T31'], 'grupo': 'ipi_devolucao', 'vigencia': (None, None), 'regimes': ['nao_cumulativo', 'misto', 'cumulativo'],
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SEM,
     'via': 'Administrativa: escriturar o crédito de IPI da devolução (CST 00) e ressarcir o saldo (Lei 9.779/99, art. 11).', 'habilitacao': 'Não exige.',
     'fundamento': 'RIPI (Decreto 7.212/2010), art. 229 (crédito do imposto relativo a produtos devolvidos, verificar redação e condições do art. 231).',
     'requisitos': ['Estabelecimento contribuinte do IPI', 'IPI destacado na venda original', 'Devolução documentada com referência à nota de venda'], 'documentos': ['XML da venda e da devolução', 'EFD ICMS/IPI (C170, E520)']},
    {'id': 'T32', 'nome': 'Crédito presumido de ICMS fora da base do IRPJ/CSLL (até 2023)', 'tributo': 'IRPJ/CSLL',
     'regras': ['T32'], 'grupo': 'credpres_irpj', 'vigencia': (None, '2023-12'), 'regimes': ['nao_cumulativo', 'misto'],
     'seguranca': 'Majoritária', 'comprovacao': 'Estimado', 'atualizacao': SELIC,
     'via': 'Administrativa com risco (exclusão no LALUR/LACS e retificação da ECF) ou judicial; a RFB restringe. A partir de 2024 vale o regime da Lei 14.789/2023 (crédito fiscal de subvenção).', 'habilitacao': 'Judicial: habilitação prévia.',
     'fundamento': 'STJ, EREsp 1.517.492/PR (1ª Seção, 2017): o crédito presumido de ICMS não integra a base do IRPJ/CSLL (pacto federativo); LC 160/2017; Lei 12.973/2014, art. 30 (redação anterior à Lei 14.789/2023).',
     'requisitos': ['Lucro Real', 'Crédito presumido de ICMS concedido pelo estado', 'Valor tributado no IRPJ/CSLL (conferir ECF)'],
     'documentos': ['EFD ICMS/IPI (E111)', 'ECF (LALUR/LACS)', 'Ato concessivo do benefício']},
    # depende de documentos que o revisor ainda não recebe: entram no catálogo para não sumirem da análise
    {'id': 'T18', 'nome': 'Contribuições previdenciárias sobre verbas indenizatórias', 'tributo': 'INSS',
     'regras': [], 'grupo': 'previd', 'vigencia': (None, None), 'depende': 'Folha de pagamento ou eSocial (S-1200/S-1210) e GPS/DCTFWeb',
     'seguranca': 'Majoritária', 'comprovacao': 'Estimado', 'atualizacao': SELIC,
     'via': 'Administrativa (PER/DCOMP ou compensação na DCTFWeb) para verbas pacificadas; judicial para as controvertidas.', 'habilitacao': 'Judicial: habilitação prévia.',
     'fundamento': 'Lei 8.212/1991, art. 28, §9º; STJ, REsp 1.230.957 (Tema 478: aviso prévio indenizado e 15 dias de afastamento); STF, RE 1.072.485 (Tema 985: terço de férias INCIDE, contra o contribuinte, desde 15/09/2020).',
     'requisitos': ['Rubricas da folha com natureza indenizatória', 'Recolhimento sobre elas nos últimos 5 anos'], 'documentos': ['Folha/eSocial', 'DCTFWeb/GPS']},
    {'id': 'T26', 'nome': 'SELIC recebida na repetição de indébito fora do IRPJ/CSLL (Tema 962 STF)', 'tributo': 'IRPJ/CSLL',
     'regras': [], 'grupo': 'selic_irpj', 'vigencia': (None, None), 'depende': 'ECF/ECD (receitas financeiras de atualização de indébito)', 'regimes': ['nao_cumulativo', 'misto'],
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SELIC,
     'via': 'Administrativa: retificar a ECF excluindo a SELIC da repetição de indébito do lucro real e da base da CSLL; PER/DCOMP do saldo negativo ou do pagamento a maior.', 'habilitacao': 'Não exige.',
     'fundamento': 'STF, RE 1.063.187/SC (Tema 962): é inconstitucional a incidência de IRPJ e CSLL sobre a taxa SELIC recebida na repetição de indébito tributário (verificar alcance dos embargos).',
     'requisitos': ['Lucro Real', 'SELIC de restituição/compensação reconhecida como receita no período'], 'documentos': ['ECF (registros L e M)', 'ECD (receitas financeiras)', 'Decisões de PER/DCOMP com SELIC']},
    {'id': 'T19', 'nome': 'Pagamento indevido ou a maior (DARF × apuração)', 'tributo': 'Federais',
     'regras': [], 'grupo': 'pag_maior', 'vigencia': (None, None), 'depende': 'DCTF/DCTFWeb e comprovantes de arrecadação (DARF)',
     'seguranca': 'Consolidada', 'comprovacao': 'Comprovado', 'atualizacao': SELIC,
     'via': 'Administrativa: PER/DCOMP de pagamento indevido ou a maior.', 'habilitacao': 'Não exige.',
     'fundamento': 'CTN, arts. 165 e 168, I; Lei 9.430/1996, art. 74; IN RFB 2.055/2021.',
     'requisitos': ['DARF pago maior que o débito confessado após retificação'], 'documentos': ['DCTF/DCTFWeb', 'Comprovantes de arrecadação']},
]

# regimes de PIS/COFINS em que cada tese se aplica (Lucro Real = não cumulativo/misto)
NC = ['nao_cumulativo', 'misto']
for _t in TESES:
    if 'regimes' not in _t:
        _t['regimes'] = NC if _t['id'] in ('T03', 'T04', 'T05', 'T06', 'T07', 'T20', 'T21') else ['nao_cumulativo', 'misto', 'cumulativo']

POR_REGRA = {r: t for t in TESES for r in t['regras']}
POR_ID = {t['id']: t for t in TESES}

# grau da regra (base_legal: a, b, c) rebaixa a segurança da tese quando a evidência é mais fraca
GRAU_SEG = {'a': 0, 'b': 1, 'c': 2}
SEG_ORDEM = ['Consolidada', 'Majoritária', 'Interpretativa']


def tese_da_regra(regra):
    return POR_REGRA.get(regra)


def vigente(tese, periodo):
    """periodo 'AAAA-MM'. A tese só vale dentro da janela de vigência."""
    de, ate = tese.get('vigencia') or (None, None)
    if de and periodo < de:
        return False
    if ate and periodo > ate:
        return False
    return True


def seguranca(tese, grau_regra):
    i = max(SEG_ORDEM.index(tese['seguranca']), GRAU_SEG.get(grau_regra or 'a', 0))
    return SEG_ORDEM[min(i, 2)]
