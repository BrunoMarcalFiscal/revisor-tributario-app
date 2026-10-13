# -*- coding: utf-8 -*-
"""
BASE DE CONHECIMENTO DO REVISOR TRIBUTÁRIO
==========================================
Tudo que as regras consultam: alíquotas por UF, regras de crédito (o que permite e o que veda),
regimes por NCM (monofásico, alíquota zero), dicionários de CFOP/CST e a fundamentação legal.

Regra de conduta: nenhum dispositivo é inventado. Onde a referência exata não é segura,
o texto traz "(verificar dispositivo)" e descreve a regra.
Tabelas de alíquota são REFERÊNCIA (ano-base 2025) e devem ser conferidas na legislação da UF.
"""

# ---------------------------------------------------------------------------
# 1. ICMS: alíquotas de referência
# ---------------------------------------------------------------------------
# Alíquota interna "modal" (regra geral) por UF, ano-base 2025. Produtos específicos têm alíquotas próprias.
ALIQ_INTERNA_UF = {
 'AC':19.0,'AL':20.0,'AM':20.0,'AP':18.0,'BA':20.5,'CE':20.0,'DF':20.0,'ES':17.0,'GO':19.0,'MA':23.0,
 'MG':18.0,'MS':17.0,'MT':17.0,'PA':19.0,'PB':20.0,'PE':20.5,'PI':22.5,'PR':19.5,'RJ':20.0,'RN':20.0,
 'RO':19.5,'RR':20.0,'RS':17.0,'SC':17.0,'SE':20.0,'SP':18.0,'TO':20.0,
}
# Regiões para a alíquota interestadual (Resolução SF 22/1989): 7% de S/SE (exceto ES) para N/NE/CO/ES; 12% nos demais casos.
UF_SUL_SUDESTE = {'PR','SC','RS','SP','RJ','MG'}  # ES fica de fora de propósito (tratado como destino de 7%)
UF_REGIAO = {**{u:'N' for u in ['AC','AM','AP','PA','RO','RR','TO']}, **{u:'NE' for u in ['AL','BA','CE','MA','PB','PE','PI','RN','SE']},
             **{u:'CO' for u in ['DF','GO','MS','MT']}, **{u:'SE' for u in ['ES','MG','RJ','SP']}, **{u:'S' for u in ['PR','RS','SC']}}

def aliq_interestadual(uf_origem, uf_destino, importado=False):
    """Resolução SF 22/1989 (7% e 12%) e Resolução SF 13/2012 (4% para importados com conteúdo de importação > 40%)."""
    if importado:
        return 4.0
    if uf_origem in UF_SUL_SUDESTE and uf_destino not in UF_SUL_SUDESTE:
        return 7.0
    return 12.0

# UFs cujo FCP/FECOP adicional é comum (alíquota varia por produto e UF). Referência, verificar por NCM.
UF_COM_FCP = {'AL','AM','BA','CE','DF','ES','GO','MA','MG','MS','MT','PB','PE','PI','PR','RJ','RN','RO','RS','SE','SP','TO','AC','PA','RR','SC','AP'}

# ---------------------------------------------------------------------------
# 2. CFOP: natureza das operações (o que a regra usa pra decidir se há crédito)
# ---------------------------------------------------------------------------
def cfop_info(cfop):
    """Classifica o CFOP em grupos que interessam à revisão."""
    c = str(cfop or '').strip()
    if len(c) != 4 or not c.isdigit():
        return {'grupo': 'invalido', 'entrada': None, 'ambito': None}
    p = c[0]; sufixo = c[1:]
    entrada = p in '123'
    ambito = {'1':'interna','2':'interestadual','3':'exterior','5':'interna','6':'interestadual','7':'exterior'}[p]
    g = 'outros'
    if entrada:
        if sufixo in ('101','111','116','120','122','126'): g = 'industrializacao'
        elif sufixo in ('102','113','117','118','121'): g = 'revenda'
        elif sufixo == '401': g = 'industrializacao_st'
        elif sufixo == '403': g = 'revenda_st'
        elif sufixo in ('551','552','553','554','555'): g = 'ativo'
        elif sufixo in ('556','557','407'): g = 'uso_consumo'
        elif sufixo in ('252','253','254','255','256','257','258'): g = 'energia'
        elif sufixo in ('301','302','303','304','305','306','307'): g = 'comunicacao'
        elif sufixo in ('351','352','353','354','355','356','360'): g = 'frete'
        elif sufixo in ('201','202','203','204','208','209','410','411','660','661','662'): g = 'devolucao'
        elif sufixo in ('901','902','903','924','925','124','125'): g = 'industrializacao_terceiros'
        elif sufixo in ('910','911','912','913'): g = 'bonificacao_brinde_amostra'
        elif sufixo in ('908','909'): g = 'comodato'
        elif sufixo in ('151','152','153','155','156','408','409'): g = 'transferencia'
        elif sufixo in ('501','502','503','504','505','506'): g = 'exportacao_indireta'
    else:
        if p == '7': g = 'exportacao'
        elif sufixo in ('101','103','105','109','111','113','116','118','122','123','124','125','107'): g = 'venda_producao'
        elif sufixo in ('102','104','106','110','112','114','115','117','119','120','121','108'): g = 'venda_revenda'
        elif sufixo in ('401','402'): g = 'venda_st_producao'
        elif sufixo in ('403','404','405'): g = 'venda_st_revenda'
        elif sufixo in ('551','552','553','554','555'): g = 'ativo'
        elif sufixo in ('556','557'): g = 'uso_consumo'
        elif sufixo in ('201','202','203','204','208','209','210','410','411','412','413','660','661','662'): g = 'devolucao'
        elif sufixo in ('901','902','903','924','925'): g = 'industrializacao_terceiros'
        elif sufixo in ('910','911','912','913'): g = 'bonificacao_brinde_amostra'
        elif sufixo in ('908','909'): g = 'comodato'
        elif sufixo in ('151','152','153','155','156','408','409'): g = 'transferencia'
        elif sufixo in ('501','502'): g = 'exportacao_indireta'
        elif sufixo in ('915','916','917','918','919','920','921','922','923','926','927','928','929','931','932','933','934','949'): g = 'operacoes_diversas'
    return {'grupo': g, 'entrada': entrada, 'ambito': ambito}

CFOP_DESCR = {
 '1101':'Compra para industrialização','2101':'Compra para industrialização (outra UF)','3101':'Compra para industrialização (exterior)',
 '1102':'Compra para comercialização','2102':'Compra para comercialização (outra UF)','3102':'Compra para comercialização (exterior)',
 '1401':'Compra p/ industrialização com ST','2401':'Compra p/ industrialização com ST (outra UF)','1403':'Compra p/ comercialização com ST','2403':'Compra p/ comercialização com ST (outra UF)',
 '1551':'Compra de bem para o ativo imobilizado','2551':'Compra de bem para o ativo (outra UF)','3551':'Importação de bem para o ativo',
 '1556':'Compra de material para uso ou consumo','2556':'Compra de material para uso ou consumo (outra UF)','3556':'Importação de uso/consumo',
 '1252':'Energia elétrica para industrialização','1253':'Energia elétrica para comercialização','1254':'Energia elétrica por prestador de serviço de transporte','1256':'Energia elétrica por prestador de serviço de comunicação','1257':'Energia elétrica para consumo por demanda contratada',
 '1352':'Frete por estabelecimento industrial','2352':'Frete por estabelecimento industrial (outra UF)','1353':'Frete por estabelecimento comercial','2353':'Frete por estabelecimento comercial (outra UF)',
 '1201':'Devolução de venda de produção','1202':'Devolução de venda de mercadoria','1410':'Devolução de venda com ST (produção)','1411':'Devolução de venda com ST (mercadoria)',
 '5101':'Venda de produção do estabelecimento','6101':'Venda de produção (outra UF)','5102':'Venda de mercadoria adquirida','6102':'Venda de mercadoria adquirida (outra UF)',
 '6107':'Venda de produção a não contribuinte (outra UF)','6108':'Venda de mercadoria a não contribuinte (outra UF)',
 '5401':'Venda de produção com ST (substituto)','6401':'Venda de produção com ST (substituto, outra UF)','5403':'Venda de mercadoria com ST (substituto)','6403':'Venda de mercadoria com ST (substituto, outra UF)',
 '5405':'Venda de mercadoria com ST (substituído)','6404':'Venda de mercadoria com ST já retido (outra UF)',
 '5910':'Remessa em bonificação, doação ou brinde','6910':'Remessa em bonificação, doação ou brinde (outra UF)','5911':'Remessa de amostra grátis','6911':'Remessa de amostra grátis (outra UF)',
 '5551':'Venda de bem do ativo imobilizado','6551':'Venda de bem do ativo (outra UF)','5901':'Remessa para industrialização','5902':'Retorno de industrialização','5124':'Industrialização efetuada para outra empresa',
 '7101':'Exportação de produção','7102':'Exportação de mercadoria adquirida','5501':'Remessa com fim específico de exportação','6501':'Remessa com fim específico de exportação (outra UF)',
}

# ---------------------------------------------------------------------------
# 3. CST / CSOSN
# ---------------------------------------------------------------------------
CST_ICMS = {'00':'Tributada integralmente','10':'Tributada e com cobrança do ICMS por ST','20':'Com redução de base de cálculo','30':'Isenta/não tributada e com ST',
            '40':'Isenta','41':'Não tributada','50':'Suspensão','51':'Diferimento','60':'ICMS cobrado anteriormente por ST','70':'Com redução de BC e cobrança de ST','90':'Outras'}
CST_PIS_COFINS = {
 '01':'Operação tributável (alíquota básica)','02':'Tributável (alíquota diferenciada)','03':'Tributável (alíquota por unidade)','04':'Tributável monofásica (revenda a alíquota zero)',
 '05':'Tributável por ST','06':'Tributável a alíquota zero','07':'Isenta','08':'Sem incidência','09':'Com suspensão','49':'Outras operações de saída',
 '50':'Crédito vinculado a receita tributada no mercado interno','51':'Crédito vinculado a receita não tributada no MI','52':'Crédito vinculado a receita de exportação',
 '53':'Crédito vinculado a receitas tributadas e não tributadas no MI','54':'Crédito vinculado a receitas tributadas no MI e exportação','55':'Crédito vinculado a receitas não tributadas no MI e exportação','56':'Crédito vinculado a receitas tributadas e não tributadas no MI e exportação',
 '60':'Crédito presumido vinculado a receita tributada no MI','61':'Crédito presumido vinculado a receita não tributada no MI','62':'Crédito presumido vinculado a exportação','63':'Crédito presumido misto MI','64':'Crédito presumido MI + exportação','65':'Crédito presumido não tributada MI + exportação','66':'Crédito presumido misto total',
 '67':'Crédito presumido outras','70':'Aquisição sem direito a crédito','71':'Aquisição com isenção','72':'Aquisição com suspensão','73':'Aquisição a alíquota zero','74':'Aquisição sem incidência','75':'Aquisição por ST','98':'Outras entradas','99':'Outras',
}
CST_IPI = {'00':'Entrada com recuperação de crédito','01':'Entrada tributada a alíquota zero','02':'Entrada isenta','03':'Entrada não tributada','04':'Entrada imune','05':'Entrada com suspensão','49':'Outras entradas',
           '50':'Saída tributada','51':'Saída tributada a alíquota zero','52':'Saída isenta','53':'Saída não tributada','54':'Saída imune','55':'Saída com suspensão','99':'Outras saídas'}
CST_PIS_COM_CREDITO = {'50','51','52','53','54','55','56','60','61','62','63','64','65','66','67'}
CST_PIS_SEM_CREDITO = {'70','71','72','73','74','75','98','99'}

# ---------------------------------------------------------------------------
# 4. PIS/COFINS: regimes por NCM (monofásico, alíquota zero)
# ---------------------------------------------------------------------------
# Incidência monofásica (concentrada no fabricante/importador; revenda com CST 04, alíquota zero).
# Chave: prefixo de NCM. Valor: setor, base legal, alíquotas do fabricante (PIS, COFINS).
MONOFASICO = [
 (('3303','3304','3305','3307','34011190','34012010','96032100'), 'Perfumaria, toucador e higiene pessoal', 'Lei 10.147/2000, art. 1º, I, "b" (2,2% e 10,3%); art. 2º (alíquota zero na revenda)', (2.2, 10.3)),
 (('3001','3002','3003','3004','300630','300660','30063000','3005','3006'), 'Produtos farmacêuticos', 'Lei 10.147/2000, art. 1º, I, "a" (2,1% e 9,9%); art. 2º (alíquota zero na revenda)', (2.1, 9.9)),
 (('2201','2202','2203'), 'Bebidas frias (água, refrigerante, cerveja, energético)', 'Lei 13.097/2015, arts. 14 a 39 (regime especial; revenda no varejo/atacado com alíquota zero, art. 28)', (2.32, 10.68)),
 (('4011','4013'), 'Pneus e câmaras de ar', 'Lei 10.485/2002, art. 5º (2% e 9,5%); parágrafo único (alíquota zero na revenda)', (2.0, 9.5)),
 (('8701','8702','8703','8704','8705','8706'), 'Veículos (fabricante/importador)', 'Lei 10.485/2002, art. 1º (2% e 9,6%)', (2.0, 9.6)),
 (('8708','8707','8433','8432','8424','8430','8431','8429','8716'), 'Autopeças e máquinas (Anexos I e II da Lei 10.485/2002)', 'Lei 10.485/2002, art. 3º (verificar Anexos I e II por NCM; revenda com alíquota zero, art. 3º, §2º)', (1.65, 7.6)),
 (('2710','2711','2207','3826'), 'Combustíveis (gasolina, diesel, GLP, álcool, biodiesel)', 'Lei 9.718/1998, art. 4º; Lei 10.336/2001; Lei 11.116/2005 (verificar alíquotas específicas por produto)', (None, None)),
]
# Alíquota zero de PIS/COFINS nas saídas (mercado interno) por NCM - referência.
ALIQ_ZERO_PIS_COFINS = [
 (('0201','0202','0203','0206','0207','0210','0301','0302','0303','0304'), 'Carnes bovinas, suínas, aves e peixes', 'Lei 10.925/2004, art. 1º, XIX a XXII (redação da Lei 12.839/2013) (verificar posições)'),
 (('0401','0402','0403','0404','0405','0406'), 'Leite, laticínios, queijos e manteiga', 'Lei 10.925/2004, art. 1º, XI a XIII e XXVI (verificar)'),
 (('0407',), 'Ovos', 'Lei 10.865/2004, art. 28, III'),
 (('07','08'), 'Produtos hortícolas e frutas (Capítulos 7 e 8)', 'Lei 10.865/2004, art. 28, III'),
 (('1001','1101','1006','0713','1902','1905'), 'Trigo, farinha de trigo, arroz, feijão, massas e pão comum', 'Lei 10.925/2004, art. 1º, XIV a XVIII (verificar)'),
 (('0901','1701','15079011','15079090','15171000','04051000'), 'Café, açúcar, óleo de soja, margarina, manteiga', 'Lei 10.925/2004, art. 1º, incisos incluídos pela Lei 12.839/2013 (verificar)'),
 (('48181000','33061000'), 'Papel higiênico, creme dental (cesta básica)', 'Lei 10.925/2004, art. 1º, XXV a XXVIII (Lei 12.839/2013) (verificar)'),
 (('4901','4902','4903','4904'), 'Livros, jornais e periódicos', 'Lei 10.865/2004, art. 28, VI (livros); imunidade CF art. 150, VI, "d"'),
 (('3101','3102','3103','3104','3105','3808','1209','0102','0103','0105'), 'Adubos, fertilizantes, defensivos, sementes e animais vivos (insumos agropecuários)', 'Lei 10.925/2004, art. 1º, I a IV (verificar)'),
 (('2309','2304','2306'), 'Rações e farelos', 'Lei 10.925/2004, art. 1º, I e XX (verificar)'),
]

def regime_ncm(ncm):
    """Devolve (regime, setor, base_legal, aliquotas) para a NCM: 'monofasico', 'aliq_zero' ou None."""
    n = str(ncm or '').replace('.', '').strip()
    if not n:
        return None
    for prefixos, setor, base, aliq in MONOFASICO:
        if any(n.startswith(p) for p in prefixos):
            return {'regime': 'monofasico', 'setor': setor, 'base': base, 'aliq': aliq}
    for prefixos, setor, base in ALIQ_ZERO_PIS_COFINS:
        if any(n.startswith(p) for p in prefixos):
            return {'regime': 'aliq_zero', 'setor': setor, 'base': base, 'aliq': (0.0, 0.0)}
    return None

# NCMs com ST na maioria das UFs (Convênio ICMS 142/2018, Anexos). Referência por prefixo; a sujeição real é por UF/CEST.
SEGMENTOS_ST_CONV_142 = {
 '22':'Bebidas','24':'Cigarros','2710':'Combustíveis','3303':'Perfumaria','3304':'Cosméticos','3305':'Produtos capilares','3306':'Higiene bucal','3307':'Desodorantes/toucador','3401':'Sabões',
 '3003':'Medicamentos','3004':'Medicamentos','4011':'Pneus','8708':'Autopeças','8507':'Baterias','3208':'Tintas','3209':'Tintas','2523':'Cimento','8418':'Eletrodomésticos','8450':'Eletrodomésticos',
 '1905':'Produtos alimentícios','2106':'Produtos alimentícios','1704':'Chocolates/doces','1806':'Chocolates','0402':'Laticínios','1101':'Farinhas','4818':'Papel higiênico','9603':'Escovas',
 '3923':'Materiais de construção (plásticos)','7307':'Materiais de construção','6907':'Revestimentos','8481':'Torneiras/válvulas','8544':'Fios e cabos','9018':'Produtos médicos','8471':'Informática','8517':'Telefonia',
}

# ---------------------------------------------------------------------------
# 5. REGRAS DE CRÉDITO (o núcleo do conhecimento). Consultadas pelas regras de cruzamento.
# ---------------------------------------------------------------------------
REGRAS_CREDITO = {
 'ICMS': {
  'base': 'LC 87/1996, arts. 19 a 23 e 33',
  'permite': [
   {'item':'Mercadorias para revenda e insumos (matéria-prima, produto intermediário, embalagem)', 'quem':'indústria e comércio', 'base':'LC 87/96, art. 20, caput', 'cfop':['industrializacao','revenda'], 'obs':'Crédito integral do ICMS destacado na nota, limitado à alíquota e base corretas.'},
   {'item':'Energia elétrica consumida no processo de industrialização', 'quem':'indústria', 'base':'LC 87/96, art. 33, II, "b"', 'cfop':['energia'], 'obs':'Somente a parcela consumida na produção. Exige laudo técnico de rateio quando há consumo administrativo/comercial na mesma unidade consumidora.'},
   {'item':'Energia elétrica na proporção das exportações', 'quem':'qualquer contribuinte que exporte', 'base':'LC 87/96, art. 33, II, "c"', 'cfop':['energia'], 'obs':'Proporção = saídas para o exterior ÷ saídas totais do período.'},
   {'item':'Energia elétrica quando for objeto de operação de saída de energia', 'quem':'distribuidoras/comercializadoras', 'base':'LC 87/96, art. 33, II, "a"', 'cfop':['energia'], 'obs':''},
   {'item':'Serviço de transporte (frete) tomado, vinculado a operação com crédito', 'quem':'indústria e comércio', 'base':'LC 87/96, art. 20, caput (serviços de transporte interestadual e intermunicipal)', 'cfop':['frete'], 'obs':'Frete na compra de mercadoria/insumo com crédito (FOB) e frete na venda quando o vendedor é o tomador (CIF). Não há crédito quando a mercadoria transportada não gera crédito (uso/consumo, isenta sem manutenção).'},
   {'item':'Bens do ativo imobilizado (CIAP), 1/48 por mês', 'quem':'indústria, comércio e serviços tributados', 'base':'LC 87/96, art. 20, §5º; controle no CIAP (Ajuste SINIEF 08/1997) e registros G110/G125 da EFD', 'cfop':['ativo'], 'obs':'Fator = saídas tributadas (inclui exportação) ÷ saídas totais. Bens de uso administrativo não geram crédito.'},
   {'item':'Devoluções de venda', 'quem':'todos', 'base':'LC 87/96, art. 20 c/c RICMS de cada UF (verificar dispositivo)', 'cfop':['devolucao'], 'obs':'Crédito do imposto debitado na saída original, na proporção da mercadoria devolvida.'},
   {'item':'Comunicação (telefonia, dados) utilizada na execução de serviços de comunicação ou na proporção das exportações', 'quem':'prestadores de comunicação; exportadores', 'base':'LC 87/96, art. 33, IV', 'cfop':['comunicacao'], 'obs':'Para os demais contribuintes, só a partir de 1º/01/2033 (LC 171/2019).'},
   {'item':'Crédito de entradas de fornecedor do Simples Nacional', 'quem':'todos', 'base':'LC 123/2006, art. 23, §§1º a 4º', 'cfop':['industrializacao','revenda'], 'obs':'Limitado ao percentual informado na nota (pCredSN/vCredICMSSN). Não há crédito se a nota não traz a informação ou se o fornecedor está em situação vedada.'},
  ],
  'veda': [
   {'item':'Material de uso e consumo do estabelecimento', 'base':'LC 87/96, art. 33, I (crédito só a partir de 1º/01/2033, LC 171/2019)', 'cfop':['uso_consumo']},
   {'item':'Energia elétrica e comunicação fora das hipóteses do art. 33', 'base':'LC 87/96, art. 33, II e IV', 'cfop':['energia','comunicacao']},
   {'item':'Mercadorias com ST já retido na entrada (contribuinte substituído)', 'base':'Regime de ST: o imposto da cadeia foi recolhido pelo substituto; crédito só nos casos de ressarcimento/restituição (RICMS de cada UF)', 'cfop':['revenda_st','industrializacao_st']},
   {'item':'Entradas isentas ou não tributadas, salvo manutenção de crédito prevista em lei', 'base':'LC 87/96, art. 20, §1º', 'cfop':[]},
   {'item':'Entradas alheias à atividade do estabelecimento (presunção para veículos de transporte pessoal)', 'base':'LC 87/96, art. 20, §1º e §2º', 'cfop':[]},
   {'item':'Crédito extemporâneo depois de 5 anos da emissão do documento', 'base':'LC 87/96, art. 23, parágrafo único', 'cfop':[]},
  ],
 },
 'PIS_COFINS': {
  'base': 'Lei 10.637/2002, art. 3º (PIS) e Lei 10.833/2003, art. 3º (COFINS); IN RFB 2.121/2022, arts. 160 a 250 (verificar numeração)',
  'aliquotas_nao_cumulativo': (1.65, 7.6),
  'aliquotas_cumulativo': (0.65, 3.0),
  'permite': [
   {'item':'Bens adquiridos para revenda', 'base':'art. 3º, I', 'cfop':['revenda','revenda_st'], 'obs':'Exceto mercadorias sujeitas a incidência monofásica ou ST de PIS/COFINS (art. 3º, I, "a" e "b").'},
   {'item':'Bens e serviços utilizados como insumo na produção ou prestação de serviços', 'base':'art. 3º, II; REsp 1.221.170/PR (Tema 779 STJ: essencialidade ou relevância); Parecer Normativo COSIT 5/2018; IN RFB 2.121/2022, arts. 175 a 179', 'cfop':['industrializacao','industrializacao_st','industrializacao_terceiros'], 'obs':'Inclui EPI, uniformes obrigatórios, manutenção de máquinas, testes de qualidade, embalagens de transporte, tratamento de efluentes, combustíveis e lubrificantes da produção, materiais intermediários, serviços de industrialização por encomenda.'},
   {'item':'Energia elétrica e térmica consumida nos estabelecimentos', 'base':'art. 3º, IX (Lei 10.637) / art. 3º, III (Lei 10.833)', 'cfop':['energia'], 'obs':'Crédito INTEGRAL, para qualquer atividade no regime não cumulativo (indústria, comércio ou serviço), sem exigência de laudo.'},
   {'item':'Aluguéis de prédios, máquinas e equipamentos pagos a pessoa jurídica', 'base':'art. 3º, IV', 'cfop':[], 'obs':'Registro F100. Vedado quando o bem já integrou o patrimônio da PJ (§ 3º-A da Lei 10.865? verificar: Lei 10.865/2004, art. 31, §3º).'},
   {'item':'Contraprestação de arrendamento mercantil (leasing) de PJ', 'base':'art. 3º, V', 'cfop':[], 'obs':'Exceto de optante do Simples Nacional.'},
   {'item':'Máquinas, equipamentos e outros bens do ativo imobilizado para produção/locação (depreciação ou 1/48, ou imediato)', 'base':'art. 3º, VI e §1º, III; Lei 11.774/2008, art. 1º (crédito imediato para máquinas e equipamentos); Lei 10.865/2004, art. 31 (vedação para bens adquiridos até 30/04/2004)', 'cfop':['ativo'], 'obs':'Registros F120 (depreciação) ou F130 (valor de aquisição em 1/48 ou 1/12). Bens de uso administrativo não geram crédito.'},
   {'item':'Edificações e benfeitorias em imóveis próprios ou de terceiros usados na atividade', 'base':'art. 3º, VII', 'cfop':[], 'obs':'Pela depreciação; Lei 11.488/2007, art. 6º permite 1/24 para edificações novas destinadas à produção.'},
   {'item':'Bens recebidos em devolução cuja receita foi tributada', 'base':'art. 3º, VIII', 'cfop':['devolucao'], 'obs':''},
   {'item':'Vale-transporte, vale-refeição/alimentação, fardamento e uniformes fornecidos a empregados de limpeza, conservação e manutenção', 'base':'art. 3º, X (Lei 10.833)', 'cfop':[], 'obs':'Só para prestadoras desses serviços; para as demais, uniformes/EPI entram como insumo (art. 3º, II) quando exigidos.'},
   {'item':'Armazenagem de mercadoria e frete na operação de venda (ônus do vendedor)', 'base':'Lei 10.833/2003, art. 3º, IX', 'cfop':['frete'], 'obs':'Registros D100/D101/D105 e F100. Frete na compra integra o custo do bem (crédito como bem/insumo). Frete entre estabelecimentos da mesma empresa: controvertido (verificar Solução de Consulta COSIT e jurisprudência CARF).'},
   {'item':'Crédito de estoque de abertura (mudança do cumulativo para não cumulativo)', 'base':'Lei 10.637, art. 11; Lei 10.833, art. 12', 'cfop':[], 'obs':'Natureza 18 no M105/M505; 1/12 por mês; alíquotas 0,65% e 3%.'},
   {'item':'Crédito extemporâneo (não aproveitado no mês da aquisição)', 'base':'art. 3º, §4º; Solução de Consulta COSIT 355/2017 (verificar); prazo de 5 anos, CTN art. 168', 'cfop':[], 'obs':'Exige retificação da EFD Contribuições do período de origem ou lançamento em período posterior com identificação (verificar entendimento atual da RFB, que exige retificação).'},
  ],
  'veda': [
   {'item':'Mão de obra paga a pessoa física', 'base':'art. 3º, §2º, I', 'cfop':[]},
   {'item':'Aquisição de bens ou serviços não sujeitos ao pagamento da contribuição (isentos, alíquota zero, não incidência), inclusive de pessoa física', 'base':'art. 3º, §2º, II', 'cfop':[]},
   {'item':'ICMS destacado na nota de aquisição (desde 1º/05/2023)', 'base':'Lei 14.592/2023 (art. 3º, §2º, III das Leis 10.637 e 10.833); MP 1.159/2023', 'cfop':[], 'obs':'A base do crédito é o valor da aquisição SEM o ICMS destacado. Antes de maio/2023 o ICMS integrava a base do crédito.'},
   {'item':'IPI recuperável e ICMS-ST na aquisição', 'base':'IN RFB 2.121/2022, art. 170 (verificar): o IPI recuperável e o ICMS-ST não integram a base do crédito', 'cfop':[]},
   {'item':'Mercadorias monofásicas ou com ST de PIS/COFINS adquiridas para revenda', 'base':'art. 3º, I, "a" e "b"', 'cfop':['revenda']},
   {'item':'Bens do ativo de uso administrativo, veículos de passeio, prédios administrativos', 'base':'art. 3º, VI (só bens para produção/locação/prestação)', 'cfop':['ativo']},
   {'item':'Despesas com vendas, marketing, comissões, brindes (não são insumo)', 'base':'PN COSIT 5/2018 (insumo é da produção/prestação, não da venda)', 'cfop':['bonificacao_brinde_amostra']},
   {'item':'Crédito de fornecedor do Simples Nacional: PERMITIDO, não é vedação', 'base':'ADI SRF 15/2007; Solução de Consulta COSIT 4/2019 (verificar): aquisições de optante do Simples geram crédito normal no não cumulativo', 'cfop':[]},
  ],
  'exclusoes_base_saida': [
   {'item':'ICMS destacado na nota de saída não integra a base de PIS/COFINS', 'base':'RE 574.706/PR (Tema 69 STF), modulação: efeitos desde 15/03/2017; Lei 14.592/2023, art. 1º (art. 1º, §3º, XIV da Lei 10.637 e X da Lei 10.833)'},
   {'item':'ICMS-ST destacado pelo substituto não integra a receita do substituído', 'base':'REsp 1.896.678 e 1.958.265 (Tema 1.125 STJ), modulação: efeitos desde 15/03/2017'},
   {'item':'IPI destacado, vendas canceladas, descontos incondicionais e devoluções', 'base':'Lei 10.637, art. 1º, §3º, I e V-a; Lei 10.833, art. 1º, §3º'},
   {'item':'Receitas de exportação e vendas a comercial exportadora com fim específico', 'base':'Lei 10.637, art. 5º; Lei 10.833, art. 6º; créditos mantidos e ressarcíveis (Lei 11.033/2004, art. 17; Lei 11.116/2005, art. 16)'},
  ],
 },
 'IPI': {
  'base': 'Decreto 7.212/2010 (RIPI), arts. 225 a 258; TIPI (Decreto 11.158/2022 e alterações)',
  'permite': [
   {'item':'MP, PI e ME empregados na industrialização, inclusive os consumidos no processo (não incluídos no ativo)', 'quem':'industrial e equiparado', 'base':'RIPI, art. 226, I', 'cfop':['industrializacao','industrializacao_st'], 'obs':'Inclui produtos intermediários consumidos em contato direto com o produto (Parecer Normativo CST 65/1979).'},
   {'item':'Produtos adquiridos de comerciante atacadista não contribuinte (50% do valor × alíquota)', 'quem':'industrial', 'base':'RIPI, art. 227', 'cfop':['industrializacao'], 'obs':''},
   {'item':'Devoluções e retornos de produtos', 'quem':'industrial e equiparado', 'base':'RIPI, art. 229 e 231 (verificar)', 'cfop':['devolucao'], 'obs':'Exige escrituração da devolução e prova do retorno (art. 231).'},
   {'item':'Produtos importados (IPI vinculado à importação)', 'quem':'industrial e equiparado', 'base':'RIPI, art. 226, V', 'cfop':['industrializacao'], 'obs':''},
   {'item':'Crédito presumido de IPI como ressarcimento de PIS/COFINS na exportação', 'quem':'produtor-exportador', 'base':'Lei 9.363/1996; Lei 10.276/2001 (regime alternativo)', 'cfop':['exportacao'], 'obs':'Aplicável só a quem apura PIS/COFINS no cumulativo (verificar; no não cumulativo o benefício foi esvaziado).'},
   {'item':'Saldo credor de IPI trimestral: ressarcimento/compensação', 'quem':'todos', 'base':'Lei 9.779/1999, art. 11; IN RFB 2.055/2021 (PER/DCOMP)', 'cfop':[], 'obs':'Inclui crédito de insumos aplicados em produtos isentos ou alíquota zero (art. 11).'},
  ],
  'veda': [
   {'item':'Bens do ativo imobilizado e material de uso/consumo', 'base':'RIPI, art. 226, I, a contrario sensu (só MP/PI/ME)', 'cfop':['ativo','uso_consumo']},
   {'item':'Estabelecimento comercial não equiparado a industrial', 'base':'RIPI, arts. 8º a 11 (equiparação); sem equiparação não há crédito nem débito de IPI', 'cfop':[]},
   {'item':'Produtos NT (não tributados) na TIPI e insumos de produtos NT', 'base':'RIPI, art. 254 (verificar); Lei 9.779/99, art. 11 alcança isentos e alíquota zero, não NT', 'cfop':[]},
  ],
  'equiparacao': 'RIPI, art. 9º: são equiparados a industrial, entre outros, os importadores (I), as filiais de industriais que comercializem produtos da matriz (III), os atacadistas de produtos do Anexo III da Lei 7.798/1989 (perfumaria, cosméticos, bebidas) adquiridos de estabelecimento interdependente (VIII, verificar inciso) e, por opção, os atacadistas em geral (art. 11).',
 },
 'ICMS_ST': {
  'base': 'LC 87/96, arts. 6º a 10; Convênio ICMS 142/2018; RICMS de cada UF',
  'ressarcimento': [
   {'item':'Restituição do ST quando a base presumida foi maior que o preço efetivo de venda ao consumidor', 'base':'RE 593.849/MG (Tema 201 STF); LC 87/96, art. 10; regulamentação por UF (verificar)', 'obs':'Aplicável ao substituído. Algumas UFs cobram o complemento quando a base efetiva é maior.'},
   {'item':'Ressarcimento do ST retido na entrada quando a saída posterior é para outra UF (nova retenção) ou para não contribuinte de outra UF', 'base':'Convênio ICMS 142/2018, cláusula décima quinta a décima sétima (verificar); RICMS de cada UF', 'obs':'O contribuinte substituído recupera o ST pago na aquisição e o ICMS próprio do fornecedor. Mecanismos: crédito em conta gráfica, nota de ressarcimento ao fornecedor, pedido administrativo (SP: Portaria CAT 42/2018; PR: SISCRED/ressarcimento; verificar UF).'},
   {'item':'Ressarcimento por perda, roubo, perecimento ou saída isenta', 'base':'RICMS de cada UF (verificar)', 'obs':''},
  ],
 },
 'DIFAL': {
  'base': 'EC 87/2015; LC 190/2022; Convênio ICMS 236/2021 (não contribuinte); LC 87/96, art. 13, §1º (base única/dupla varia por UF)',
  'regras': [
   {'item':'Venda a não contribuinte de outra UF: DIFAL devido à UF de destino (base única, alíquota interna do destino menos interestadual, mais FCP)', 'base':'EC 87/2015; LC 190/2022; Convênio ICMS 236/2021', 'obs':'Recolhimento por GNRE ou inscrição de substituto. Exige o grupo ICMSUFDest no XML.'},
   {'item':'Compra interestadual de uso/consumo ou ativo por contribuinte: DIFAL devido à UF do adquirente', 'base':'LC 87/96, art. 12, XIV a XVI (redação LC 190/2022)', 'obs':'Base dupla ("por dentro") em várias UFs (ex.: MG, PR, GO, BA, PE, SE, TO, PB, PI, PA, AL, MS, RS: verificar por UF). Ajustes E111 (código por UF) ou E310.'},
   {'item':'DIFAL sobre ativo imobilizado gera crédito no CIAP (parcela de DIFAL)', 'base':'LC 87/96, art. 20, §5º; campo VL_IMOB_ICMS_DIF do G125', 'obs':''},
  ],
 },
 'SIMPLES': {
  'base': 'LC 123/2006, arts. 18 e 23; Resolução CGSN 140/2018',
  'regras': [
   {'item':'Segregação de receitas com ST, monofásico ou antecipação com encerramento (reduz PIS/COFINS/ICMS no DAS)', 'base':'LC 123/2006, art. 18, §4º-A; Res. CGSN 140/2018, art. 25', 'obs':'Sem segregação no PGDAS-D a empresa paga PIS/COFINS/ICMS em dobro sobre monofásicos e mercadorias com ST.'},
   {'item':'Crédito de ICMS ao adquirente (não optante) limitado ao percentual do DAS', 'base':'LC 123/2006, art. 23, §1º', 'obs':''},
   {'item':'Fator R e enquadramento por anexo', 'base':'LC 123/2006, art. 18, §5º-J a §5º-M', 'obs':''},
  ],
 },
 'REFORMA': {
  'base': 'EC 132/2023; LC 214/2025',
  'regras': [
   {'item':'2026: ano-teste com CBS 0,9% e IBS 0,1%, destaque obrigatório nos documentos fiscais; recolhimento dispensado a quem cumprir as obrigações acessórias', 'base':'LC 214/2025, art. 348 (verificar numeração) e ADCT art. 125', 'obs':'Grupo IBSCBS no XML (NT 2025.002 e seguintes). Falta do destaque = descumprimento de obrigação acessória e perda da dispensa.'},
   {'item':'2027: CBS integral e extinção de PIS/COFINS; IPI reduzido a zero, salvo ZFM', 'base':'ADCT art. 126', 'obs':''},
   {'item':'Créditos amplos (não cumulatividade plena) com condicionamento ao pagamento (split payment)', 'base':'LC 214/2025, arts. 47 a 57 (verificar)', 'obs':'Saldo de PIS/COFINS acumulado até 2026 continua compensável (LC 214, art. 378, verificar).'},
  ],
 },
}

# ---------------------------------------------------------------------------
# 6. Prazos e princípios
# ---------------------------------------------------------------------------
PRAZOS = {
 'decadencia_credito': 'CTN, arts. 150, §4º e 173 (lançamento); LC 87/96, art. 23, parágrafo único (crédito de ICMS: 5 anos da emissão do documento); CTN, art. 168 (restituição/compensação: 5 anos).',
 'per_dcomp': 'IN RFB 2.055/2021: pedido de ressarcimento de PIS/COFINS e IPI; compensação de débitos federais próprios.',
}

# ---------------------------------------------------------------------------
# 7. Códigos de ajuste E111 por UF: prefixos que identificam DIFAL / crédito presumido / estorno (referência).
# ---------------------------------------------------------------------------
# Estrutura do código de ajuste da apuração (Guia Prático, tabela 5.1.1): UF + tipo (0 débito, 1 crédito, 2 estorno, 3 dedução, 4 débito especial, 5 crédito especial) + ... 
def tipo_ajuste_e111(cod):
    c = str(cod or '')
    if len(c) < 4:
        return 'desconhecido'
    # Tabela 5.1.1 (Guia Prático): UF (2) + apuração (3º: 0 ICMS próprio, 1 ICMS-ST, 2 DIFAL/FCP...) + TIPO (4º) + sequencial.
    # 4º caractere: 0 outros débitos, 1 estorno de créditos, 2 outros créditos, 3 estorno de débitos, 4 deduções, 5 débitos especiais
    t = c[3]
    return {'0': 'débito', '1': 'estorno de crédito', '2': 'crédito', '3': 'estorno de débito', '4': 'dedução', '5': 'débito especial'}.get(t, 'outros')
