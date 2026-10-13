# -*- coding: utf-8 -*-
"""Análise estratégica por empresa: onde está a carga tributária, quem a gera (operações, produtos, fornecedores, UFs),
o que muda com a Reforma Tributária e o plano de ação. Tudo sai dos arquivos (SPED Fiscal, EFD Contribuições, XML);
o que depende de premissa (centro de distribuição, alíquotas da reforma) é calculado na tela com premissas editáveis.
Nada aqui é recomendação automática de planejamento: é a base técnica para a decisão do especialista."""
from collections import defaultdict
from .conhecimento import cfop_info, regime_ncm, ALIQ_INTERNA_UF, aliq_interestadual, CFOP_DESCR
from .util import uf_participante

# legislação considerada pelo revisor (data de corte da base: 13/10/2026). Onde o status pede confirmação, está escrito.
LEGISLACAO = [
    {'norma': 'EC 132/2023 e LC 214/2025', 'tema': 'Reforma Tributária do consumo (CBS, IBS e Imposto Seletivo)', 'vigencia': '2026 (teste) a 2033',
     'impacto': '2026: CBS 0,9% e IBS 0,1% em caráter de teste. 2027: CBS plena e fim do PIS/COFINS; IPI zerado (exceto ZFM). 2029 a 2032: IBS sobe e ICMS/ISS caem 10 pontos por ano. 2033: só CBS/IBS.',
     'na_ferramenta': 'Simulador da Reforma; regra X08 (NF-e de 2026 sem grupo IBS/CBS).', 'status': 'Vigente; alíquotas de referência dependem de resolução do Senado (os valores do simulador são editáveis).'},
    {'norma': 'Lei 14.592/2023 (MP 1.159/2023)', 'tema': 'ICMS fora da base do crédito de PIS/COFINS', 'vigencia': 'desde 05/2023',
     'impacto': 'O ICMS destacado na aquisição deixa de integrar a base do crédito; reduz o crédito das entradas.', 'na_ferramenta': 'Base do crédito (antes de 05/2023 com ICMS, depois sem); P06b.', 'status': 'Vigente.'},
    {'norma': 'STF, RE 574.706 (Tema 69)', 'tema': 'ICMS fora da base do PIS/COFINS', 'vigencia': 'desde 15/03/2017',
     'impacto': 'Exclusão do ICMS destacado da receita tributável.', 'na_ferramenta': 'T01 (P06, X10, R01).', 'status': 'Pacificado.'},
    {'norma': 'STJ, Tema 1.125', 'tema': 'ICMS-ST fora da base do PIS/COFINS do substituído', 'vigencia': 'acórdão de 13/12/2023',
     'impacto': 'Revendedor substituído exclui o ICMS-ST da base.', 'na_ferramenta': 'T02.', 'status': 'Repetitivo do STJ; RFB não aplica: via judicial. Verificar modulação.'},
    {'norma': 'STF, RE 592.616 (Tema 118)', 'tema': 'ISS na base do PIS/COFINS', 'vigencia': '-',
     'impacto': 'Possível exclusão do ISS, por analogia ao Tema 69.', 'na_ferramenta': 'T29.', 'status': 'Confirmar a situação do julgamento antes de propor.'},
    {'norma': 'STJ, REsp 1.221.170 (Temas 779/780) e PN COSIT 5/2018', 'tema': 'Conceito de insumo para PIS/COFINS', 'vigencia': 'desde 2018',
     'impacto': 'Crédito sobre bens e serviços essenciais ou relevantes.', 'na_ferramenta': 'T03 (P04, P04b, X09).', 'status': 'Pacificado; depende da prova por item.'},
    {'norma': 'LC 190/2022 e STF, Tema 1.093', 'tema': 'DIFAL nas vendas a consumidor final não contribuinte', 'vigencia': 'desde 2022 (anterioridade discutida)',
     'impacto': 'DIFAL exigível por lei complementar; recolhimento ao estado de destino.', 'na_ferramenta': 'X07, X13, F17.', 'status': 'Vigente.'},
    {'norma': 'LC 194/2022 e STF, Tema 745', 'tema': 'Essencialidade: alíquota de ICMS de energia, comunicação e combustíveis limitada à modal', 'vigencia': 'desde 06/2022',
     'impacto': 'Alíquota interna de energia e telecom não pode passar da modal; restituição do passado só para ações ajuizadas até 05/02/2021 (modulação).', 'na_ferramenta': 'Conferir faturas de energia/telecom (C500/D500).', 'status': 'Vigente.'},
    {'norma': 'LC 160/2017 e Lei 14.789/2023', 'tema': 'Benefícios fiscais de ICMS e IRPJ/CSLL', 'vigencia': 'até 12/2023 regra anterior; desde 01/2024 crédito fiscal de subvenção',
     'impacto': 'Até 2023, crédito presumido de ICMS fora do IRPJ/CSLL (STJ, EREsp 1.517.492); desde 2024, subvenção tributada com crédito fiscal de 25% (requisitos da lei).', 'na_ferramenta': 'T32 (até 2023).', 'status': 'Vigente; habilitação do crédito fiscal na RFB.'},
    {'norma': 'Convênio ICMS 142/2018 e STF, Tema 201', 'tema': 'ICMS-ST: segmentos, CEST e restituição', 'vigencia': 'vigente',
     'impacto': 'Ressarcimento de ST na saída interestadual e quando a base efetiva é menor que a presumida.', 'na_ferramenta': 'F13, F19, T13.', 'status': 'Rito por UF (verificar RICMS).'},
    {'norma': 'LC 123/2006, art. 23', 'tema': 'Crédito de ICMS de fornecedor do Simples Nacional', 'vigencia': 'vigente',
     'impacto': 'Crédito limitado ao informado na NF-e (vCredICMSSN); PIS/COFINS de fornecedor do Simples dá crédito integral no não cumulativo.', 'na_ferramenta': 'X06; análise de fornecedores.', 'status': 'Vigente.'},
    {'norma': 'Lei 10.865/2004, art. 15', 'tema': 'Crédito de PIS/COFINS-Importação', 'vigencia': 'vigente', 'impacto': 'Crédito do pago na importação.', 'na_ferramenta': 'T28.', 'status': 'Vigente.'},
]


def _soma(lista, campo):
    return sum(r.n(campo) for r in lista)


def montar(ctx, achados, rec):
    ops = (rec or {}).get('oportunidades', [])
    out = []
    xml_crt = {}
    for d in (ctx.get('xmls') or {}).get('nfe', []):
        em = d.get('emit') or {}
        if em.get('cnpj'):
            xml_crt[em['cnpj']] = em.get('crt', '')
    for cnpj, e in ctx['empresas'].items():
        out.append(_empresa(e, achados, ops, xml_crt))
    return {'empresas': out, 'legislacao': LEGISLACAO, 'base_ate': '13/10/2026'}


def _empresa(e, achados, ops, xml_crt):
    d = e.get('diagnostico') or {}
    ind = d.get('indicadores') or {}
    meses = max(len(d.get('mensal') or []), 1)
    rec_total = ind.get('receita_total') or 0
    # mesmo período em tudo: os meses do SPED Fiscal (base da receita e da carga); sem SPED Fiscal, os da EFD Contribuições
    periodo = {m['periodo'] for m in d.get('mensal', [])} or set(e['contrib'])
    contribs = [s for c, s in e['contrib'].items() if c in periodo]
    # ---- tributos (soma do período)
    iss = ret_pc = 0.0
    pis_deb = cof_deb = pis_cred = cof_cred = 0.0
    for s in contribs:
        a100 = [r for r in s['regs'].get('A100', []) if r.get('IND_OPER') == '1' and r.get('COD_SIT') not in ('02', '03', '04', '05')]
        iss += _soma(a100, 'VL_ISS')
        ret_pc += _soma(a100, 'VL_PIS_RET') + _soma(a100, 'VL_COFINS_RET')
        ret_pc += sum(r.n('VL_RET_PIS') + r.n('VL_RET_COFINS') for r in s['regs'].get('F600', []))
        pis_deb += sum(r.n('VL_TOT_CONT_NC_PER') + r.n('VL_TOT_CONT_CUM_PER') for r in s['regs'].get('M200', []))
        cof_deb += sum(r.n('VL_TOT_CONT_NC_PER') + r.n('VL_TOT_CONT_CUM_PER') for r in s['regs'].get('M600', []))
        pis_cred += sum(r.n('VL_TOT_CRED_DESC') for r in s['regs'].get('M200', []))
        cof_cred += sum(r.n('VL_TOT_CRED_DESC') for r in s['regs'].get('M600', []))
    icms_deb = sum(m.get('icms_debitos') or 0 for m in d.get('mensal', []))
    icms_cred = sum(m.get('icms_creditos') or 0 for m in d.get('mensal', []))
    ipi_deb = sum(m.get('ipi_debitos') or 0 for m in d.get('mensal', []))
    ipi_cred = sum(m.get('ipi_creditos') or 0 for m in d.get('mensal', []))
    trib = [
        {'tributo': 'ICMS', 'recolhido': ind.get('icms_recolhido') or 0, 'debitos': icms_deb, 'creditos': icms_cred},
        {'tributo': 'ICMS-ST', 'recolhido': ind.get('st_total') or 0, 'debitos': ind.get('st_total') or 0, 'creditos': 0},
        {'tributo': 'DIFAL/FCP', 'recolhido': ind.get('difal_total') or 0, 'debitos': ind.get('difal_total') or 0, 'creditos': 0},
        {'tributo': 'IPI', 'recolhido': ind.get('ipi_total') or 0, 'debitos': ipi_deb, 'creditos': ipi_cred},
        {'tributo': 'PIS/COFINS', 'recolhido': ind.get('pis_cofins_total') or 0, 'debitos': pis_deb + cof_deb, 'creditos': pis_cred + cof_cred, 'retencoes': ret_pc},
        {'tributo': 'ISS', 'recolhido': iss, 'debitos': iss, 'creditos': 0},
    ]
    tot_trib = sum(t['recolhido'] for t in trib)
    for t in trib:
        t['pct_receita'] = round(t['recolhido'] / rec_total * 100, 2) if rec_total else 0
        t['pct_carga'] = round(t['recolhido'] / tot_trib * 100, 1) if tot_trib else 0
        chaves = {'ICMS': ('ICMS',), 'ICMS-ST': ('ICMS-ST',), 'DIFAL/FCP': ('DIFAL',), 'IPI': ('IPI',), 'PIS/COFINS': ('PIS/COFINS', 'PIS', 'COFINS'), 'ISS': ('ISS',)}[t['tributo']]
        t['achados'] = len([a for a in achados if a.get('empresa') == e['cnpj'] and a.get('tributo') in chaves])
        t['riscos'] = round(sum(float(a.get('valor') or 0) for a in achados if a.get('empresa') == e['cnpj'] and a.get('tributo') in chaves and a.get('categoria') == 'Risco'), 2)
        t['oportunidade'] = round(sum(o['valor_atualizado'] for o in ops if o['empresa'] == e['cnpj'] and o['tributo'] in chaves and o['situacao'] == 'Em prazo' and o['status'] != 'Descartada'), 2)
        for k in ('recolhido', 'debitos', 'creditos'):
            t[k] = round(t[k], 2)
    # ---- produtos vendidos (EFD Contribuições, item a item) e operações (CFOP)
    prod = defaultdict(lambda: {'receita': 0.0, 'icms': 0.0, 'ipi': 0.0, 'pis': 0.0, 'cofins': 0.0})
    itens = {}
    for s in contribs:
        itens.update(s.get('itens') or {})
        for r in s['regs'].get('C170', []):
            p = r.get('pai')
            if not p or p.get('IND_OPER') != '1' or p.get('COD_SIT') in ('02', '03', '04', '05'):
                continue
            g = prod[r.get('COD_ITEM')]
            g['receita'] += r.n('VL_ITEM') - r.n('VL_DESC'); g['icms'] += r.n('VL_ICMS'); g['ipi'] += r.n('VL_IPI'); g['pis'] += r.n('VL_PIS'); g['cofins'] += r.n('VL_COFINS')
    for s in e['fiscal'].values():
        for k, v in (s.get('itens') or {}).items():
            itens.setdefault(k, v)
    produtos = []
    for cod, g in prod.items():
        it = itens.get(cod) or {}
        ncm = it.get('COD_NCM', '')
        carga = g['icms'] + g['ipi'] + g['pis'] + g['cofins']
        rn = regime_ncm(ncm)
        produtos.append({'cod': cod, 'descr': (it.get('DESCR_ITEM') or '')[:70], 'ncm': ncm, 'receita': round(g['receita'], 2), 'icms': round(g['icms'], 2), 'ipi': round(g['ipi'], 2),
                         'pis_cofins': round(g['pis'] + g['cofins'], 2), 'carga': round(carga, 2), 'carga_pct': round(carga / g['receita'] * 100, 2) if g['receita'] else 0,
                         'regime_pis_cofins': (rn or {}).get('regime', 'regra geral'), 'alerta': ('NCM de %s: PIS/COFINS deveria ser zero na revenda' % rn['setor']) if rn and (g['pis'] + g['cofins']) > 0 else ''})
    produtos.sort(key=lambda x: -x['carga'])
    cfops = defaultdict(lambda: {'valor': 0.0, 'icms': 0.0, 'st': 0.0, 'ipi': 0.0})
    for s in e['fiscal'].values():
        for r in s['regs'].get('C190', []):
            if cfop_info(r.get('CFOP'))['entrada']:
                continue
            g = cfops[r.get('CFOP')]
            g['valor'] += r.n('VL_OPR'); g['icms'] += r.n('VL_ICMS'); g['st'] += r.n('VL_ICMS_ST'); g['ipi'] += r.n('VL_IPI')
    operacoes = sorted([{'cfop': c, 'descr': CFOP_DESCR.get(c, cfop_info(c)['grupo']), 'valor': round(g['valor'], 2), 'icms': round(g['icms'], 2), 'st': round(g['st'], 2), 'ipi': round(g['ipi'], 2),
                         'carga_pct': round((g['icms'] + g['st'] + g['ipi']) / g['valor'] * 100, 2) if g['valor'] else 0} for c, g in cfops.items()], key=lambda x: -x['icms'] - x['st'] - x['ipi'])
    # ---- fornecedores: quanto crédito cada um gera
    pc_doc = {}
    for s in e['contrib'].values():   # todas as EFD: a nota de entrada pode ter sido escriturada em outro mês
        for c in s['regs'].get('C100', []):
            if c.get('IND_OPER') == '0' and c.get('CHV_NFE'):
                pc_doc[c['CHV_NFE']] = sum(x.n('VL_PIS') + x.n('VL_COFINS') for x in c.get('filhos', []) if x.get('REG') == 'C170')
    forn = defaultdict(lambda: {'nome': '', 'uf': '', 'valor': 0.0, 'icms': 0.0, 'ipi': 0.0, 'pis_cofins': 0.0, 'docs': 0, 'na_efd': 0})
    for s in e['fiscal'].values():
        for c in s['regs'].get('C100', []):
            if c.get('IND_OPER') != '0' or c.get('COD_SIT') in ('02', '03', '04', '05'):
                continue
            part = s['participantes'].get(c.get('COD_PART'), {})
            cn = part.get('CNPJ') or c.get('COD_PART') or '?'
            g = forn[cn]
            g['nome'] = part.get('NOME', g['nome']); g['uf'] = uf_participante(part) or g['uf']
            g['valor'] += c.n('VL_DOC'); g['icms'] += c.n('VL_ICMS'); g['ipi'] += c.n('VL_IPI'); g['docs'] += 1
            if c.get('CHV_NFE') in pc_doc:
                g['pis_cofins'] += pc_doc[c['CHV_NFE']]; g['na_efd'] += 1
    lr = (e.get('regime') or {}).get('pis_cofins') in ('nao_cumulativo', 'misto')
    fornecedores = []
    for cn, g in forn.items():
        cred = g['icms'] + g['ipi'] + g['pis_cofins']
        crt = xml_crt.get(cn, '')
        fornecedores.append({'cnpj': cn, 'nome': g['nome'][:50], 'uf': g['uf'], 'valor': round(g['valor'], 2), 'docs': g['docs'], 'icms': round(g['icms'], 2), 'ipi': round(g['ipi'], 2),
                             'pis_cofins': round(g['pis_cofins'], 2), 'credito': round(cred, 2), 'credito_pct': round(cred / g['valor'] * 100, 2) if g['valor'] else 0,
                             'simples': {'1': True, '2': True, '4': True}.get(crt, False) if crt else None})
    fornecedores.sort(key=lambda x: -x['valor'])
    normais = [f for f in fornecedores if f['simples'] is False and f['valor'] > 0]
    ref_cred = round(sum(f['credito'] for f in normais) / sum(f['valor'] for f in normais) * 100, 2) if normais else None
    # ---- vendas por UF (operações interestaduais)
    uf_emp = (e.get('uf') or '').upper()
    por_uf = defaultdict(lambda: {'valor': 0.0, 'icms': 0.0, 'st': 0.0, 'docs': 0})
    for s in e['fiscal'].values():
        for c in s['regs'].get('C100', []):
            if c.get('IND_OPER') != '1' or c.get('COD_SIT') in ('02', '03', '04', '05'):
                continue
            uf = uf_participante(s['participantes'].get(c.get('COD_PART'), {})) or '?'
            g = por_uf[uf]; g['valor'] += c.n('VL_DOC'); g['icms'] += c.n('VL_ICMS'); g['st'] += c.n('VL_ICMS_ST'); g['docs'] += 1
    difal_uf = defaultdict(float)
    for s in e['fiscal'].values():
        for r in s['regs'].get('E300', []):
            for f in r.get('filhos', []):
                if f.get('REG') == 'E310':
                    difal_uf[r.get('UF')] += f.n('VL_RECOL_DIFAL') + f.n('VL_RECOL_FCP')
    tot_v = sum(g['valor'] for g in por_uf.values()) or 1
    ufs = []
    for uf, g in por_uf.items():
        ufs.append({'uf': uf, 'valor': round(g['valor'], 2), 'pct': round(g['valor'] / tot_v * 100, 1), 'icms': round(g['icms'], 2), 'st': round(g['st'], 2), 'difal': round(difal_uf.get(uf, 0), 2), 'docs': g['docs'],
                    'aliq_inter': aliq_interestadual(uf_emp, uf) if uf not in (uf_emp, '?', 'EX') and uf_emp else None, 'aliq_interna': ALIQ_INTERNA_UF.get(uf)})
    ufs.sort(key=lambda x: -x['valor'])
    # ---- base anual para o simulador da reforma
    fator_ano = 12 / meses
    compras = sum((m.get('entradas_insumo_revenda') or 0) for m in d.get('mensal', []))
    reforma = {'meses': meses, 'receita_ano': round(rec_total * fator_ano, 2), 'compras_credito_ano': round(compras * fator_ano, 2),
               'pis_cofins_ano': round((ind.get('pis_cofins_total') or 0) * fator_ano, 2), 'icms_ano': round(((ind.get('icms_recolhido') or 0) + (ind.get('st_total') or 0) + (ind.get('difal_total') or 0)) * fator_ano, 2),
               'iss_ano': round(iss * fator_ano, 2), 'ipi_ano': round((ind.get('ipi_total') or 0) * fator_ano, 2)}
    # ---- plano estratégico: oportunidades em prazo + pontos de planejamento + riscos a corrigir
    plano = []
    for o in ops:
        if o['empresa'] != e['cnpj'] or o['situacao'] != 'Em prazo' or o['status'] == 'Descartada':
            continue
        plano.append({'tipo': 'Recuperação', 'titulo': o['tese'], 'periodo': o['periodo'], 'tributo': o['tributo'], 'impacto': o['valor_atualizado'], 'risco': o['seguranca'],
                      'comprovacao': o['comprovacao'], 'fundamento': o['fundamento'][:400], 'acao': o['via'], 'prazo': 'prescreve em %d meses' % o['meses_para_prescrever'], 'id': o['id']})
    for a in achados:
        if a.get('empresa') == e['cnpj'] and a.get('categoria') == 'Planejamento':
            plano.append({'tipo': 'Planejamento', 'titulo': a['titulo'], 'periodo': a['periodo'], 'tributo': a['tributo'], 'impacto': float(a.get('valor') or 0), 'risco': {'a': 'Consolidada', 'b': 'Majoritária'}.get((a.get('tese') or 'c')[:1].lower(), 'Interpretativa'),
                          'comprovacao': 'Estimado' if a.get('estimativa') else 'Comprovado', 'fundamento': (a.get('fundamentacao') or '')[:400], 'acao': a.get('acao', ''), 'prazo': 'contínuo'})
        if a.get('empresa') == e['cnpj'] and a.get('categoria') == 'Risco' and float(a.get('valor') or 0) > 0:
            plano.append({'tipo': 'Correção de risco', 'titulo': a['titulo'], 'periodo': a['periodo'], 'tributo': a['tributo'], 'impacto': float(a.get('valor') or 0), 'risco': 'Exposição',
                          'comprovacao': 'Estimado' if a.get('estimativa') else 'Comprovado', 'fundamento': (a.get('fundamentacao') or '')[:400], 'acao': a.get('acao', ''), 'prazo': 'antes de fiscalização (denúncia espontânea, CTN art. 138)'})
    ordem = {'Recuperação': 0, 'Correção de risco': 1, 'Planejamento': 2}
    plano.sort(key=lambda x: (ordem[x['tipo']], -x['impacto']))
    return {'periodo_analise': '%s a %s' % (min(periodo), max(periodo)) if periodo else '', 'cnpj': e['cnpj'], 'nome': e['nome'], 'uf': uf_emp,
            'regime': (e.get('regime') or {}).get('tributario', ''), 'lucro_real': lr,
            'receita': round(rec_total, 2), 'carga_total': round(tot_trib, 2), 'carga_pct': round(tot_trib / rec_total * 100, 2) if rec_total else 0, 'meses': meses,
            'indicadores': ind, 'mensal': d.get('mensal', []), 'tributos': trib, 'produtos': produtos[:60], 'qtd_produtos': len(produtos), 'operacoes': operacoes[:30],
            'fornecedores': fornecedores[:60], 'qtd_fornecedores': len(fornecedores), 'simples_identificados': len([f for f in fornecedores if f['simples']]), 'sem_xml_regime': len([f for f in fornecedores if f['simples'] is None]),
            'credito_ref_pct': ref_cred, 'ufs': ufs, 'contribuinte_x_nao': d.get('contribuinte_x_nao', []), 'reforma': reforma, 'plano': plano[:120], 'narrativa': d.get('narrativa', '')}
