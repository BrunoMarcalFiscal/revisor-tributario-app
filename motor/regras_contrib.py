# -*- coding: utf-8 -*-
"""Regras sobre a EFD Contribuições (PIS/COFINS)."""
from collections import defaultdict, Counter
from .conhecimento import cfop_info, regime_ncm, CST_PIS_COM_CREDITO, CST_PIS_SEM_CREDITO, REGRAS_CREDITO
from .util import brl, data_sped

TOL = 1.00
ALIQ_NC = (1.65, 7.6); ALIQ_CUM = (0.65, 3.0)

def _ev(*p):
    return ' | '.join(str(x) for x in p if x not in (None, ''))

def rodar(e, A):
    for comp in sorted(e['contrib']):
        s = e['contrib'][comp]
        base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        regime = s['empresa'].get('cod_inc_trib', '')
        e['perfil']['regime_pis_cofins'] = {'1': 'não cumulativo', '2': 'cumulativo', '3': 'misto'}.get(regime, '?')
        integridade(s, A, base)
        creditos_x_apuracao(s, A, base, regime)
        cst_aliquota(s, A, base, regime)
        insumos_sem_credito(e, s, A, base, regime)
        saidas_monofasicas(e, s, A, base, regime)
        icms_na_base(e, s, A, base, regime)
        energia_frete(s, A, base, regime)
        saldo_credor(s, A, base)
        apuracao(s, A, base, regime)
        ativo(e, s, A, base, regime)

def integridade(s, A, base):
    if s['divergencias_9900'] or (s['qtd_9999'] is not None and s['qtd_9999'] != s['linhas']):
        A.add(regra='P01', categoria='Integridade', tributo='SPED', titulo='EFD Contribuições com contagem 9900/9999 inconsistente', descricao='%d divergência(s) no 9900; 9999=%s, linhas=%s.' % (len(s['divergencias_9900']), s['qtd_9999'], s['linhas']), evidencia=[_ev(d['registro'], d['declarado'], d['real']) for d in s['divergencias_9900'][:10]], grau='Alto', acao='Regerar', prioridade='Alta', **base)
    if not s['regs'].get('0110'):
        A.add(regra='P01', categoria='Integridade', tributo='SPED', titulo='Sem registro 0110 (regime de apuração)', descricao='', grau='Alto', acao='Verificar', **base)

def _somas_credito_docs(s):
    """Soma o crédito documental por natureza (bloco A, C, D, F) para PIS e COFINS."""
    pis = defaultdict(float); cof = defaultdict(float)
    for reg, cpis, ccof in (('A170', 'VL_PIS', 'VL_COFINS'), ('C170', 'VL_PIS', 'VL_COFINS'), ('C501', 'VL_PIS', None), ('C505', None, 'VL_COFINS'), ('D101', 'VL_PIS', None), ('D105', None, 'VL_COFINS'), ('F100', 'VL_PIS', 'VL_COFINS'), ('F120', 'VL_PIS', 'VL_COFINS'), ('F130', 'VL_PIS', 'VL_COFINS'), ('C191', 'VL_PIS', None), ('C195', None, 'VL_COFINS'), ('C181', 'VL_PIS', None), ('C185', None, 'VL_COFINS')):
        for r in s['regs'].get(reg, []):
            cst = r.get('CST_PIS') or r.get('CST_COFINS') or ''
            if reg == 'C170':
                if r.get('pai') and r['pai'].get('IND_OPER') != '0':
                    continue
            if reg in ('A170',) and r.get('pai') and r['pai'].get('IND_OPER') != '0':
                continue
            if cst not in CST_PIS_COM_CREDITO:
                continue
            nat = r.get('NAT_BC_CRED', '') or ('01' if reg in ('C170', 'C191', 'C181') else '')
            if cpis and r.get('CST_PIS', cst) in CST_PIS_COM_CREDITO:
                pis[nat] += r.n(cpis)
            if ccof and r.get('CST_COFINS', cst) in CST_PIS_COM_CREDITO:
                cof[nat] += r.n(ccof)
    return pis, cof

def creditos_x_apuracao(s, A, base, regime):
    m100 = s['regs'].get('M100', []); m500 = s['regs'].get('M500', [])
    pis_docs, cof_docs = _somas_credito_docs(s)
    tp = sum(pis_docs.values()); tc = sum(cof_docs.values())
    mp = sum(r.n('VL_CRED') for r in m100); mc = sum(r.n('VL_CRED') for r in m500)
    if regime in ('1', '3'):
        if abs(tp - mp) > TOL:
            A.add(regra='P02', categoria='Risco' if mp > tp else 'Recuperação', tributo='PIS', titulo='Crédito de PIS apurado (M100) diverge do crédito documental',
                  descricao='Documentos (A/C/D/F com CST 50 a 66) somam %s; M100 soma %s. %s' % (brl(tp), brl(mp), 'Crédito acima do lastro (glosa).' if mp > tp else 'Crédito documental não apurado.'), valor=abs(tp - mp), memoria='Σ docs %s vs M100 %s' % (brl(tp), brl(mp)), grau='Alto', acao='Conferir M105 por natureza e retificar', prioridade='Alta', **base)
        if abs(tc - mc) > TOL:
            A.add(regra='P02', categoria='Risco' if mc > tc else 'Recuperação', tributo='COFINS', titulo='Crédito de COFINS apurado (M500) diverge do crédito documental',
                  descricao='Documentos somam %s; M500 soma %s.' % (brl(tc), brl(mc)), valor=abs(tc - mc), memoria='Σ docs %s vs M500 %s' % (brl(tc), brl(mc)), grau='Alto', acao='Conferir M505 e retificar', prioridade='Alta', **base)
    if regime == '2' and (mp > 0 or mc > 0):
        A.add(regra='P12', categoria='Risco', tributo='PIS/COFINS', titulo='Regime cumulativo com créditos apurados (M100/M500)', descricao='No cumulativo não há crédito. PIS %s, COFINS %s.' % (brl(mp), brl(mc)), valor=mp + mc, grau='Alto', acao='Retificar', prioridade='Alta', **base)

def cst_aliquota(s, A, base, regime):
    erros = []; total = 0.0
    esperado = ALIQ_NC if regime in ('1', '3') else ALIQ_CUM
    for reg in ('C170', 'A170', 'C501', 'C505', 'D101', 'D105', 'F100'):
        for r in s['regs'].get(reg, []):
            for cst_campo, aliq_campo, bc_campo, vl_campo, idx in (('CST_PIS', 'ALIQ_PIS', 'VL_BC_PIS', 'VL_PIS', 0), ('CST_COFINS', 'ALIQ_COFINS', 'VL_BC_COFINS', 'VL_COFINS', 1)):
                cst = r.get(cst_campo, '')
                if cst not in CST_PIS_COM_CREDITO or cst in ('60', '61', '62', '63', '64', '65', '66', '67'):
                    continue
                if not r.get(aliq_campo):
                    continue
                aliq = r.n(aliq_campo); bc = r.n(bc_campo); vl = r.n(vl_campo)
                if aliq > 0 and abs(aliq - esperado[idx]) > 0.005 and r.n('QUANT_BC_PIS' if idx == 0 else 'QUANT_BC_COFINS') == 0:
                    erros.append(_ev(reg, 'linha', r['linha'], cst_campo, cst, 'alíquota', aliq, 'esperada', esperado[idx], 'BC', brl(bc)))
                    total += bc * (esperado[idx] - aliq) / 100
                elif bc > 0 and abs(bc * aliq / 100 - vl) > 0.05:
                    erros.append(_ev(reg, 'linha', r['linha'], cst_campo, cst, 'BC × aliq', brl(bc * aliq / 100), 'valor', brl(vl)))
                    total += bc * aliq / 100 - vl
    if erros:
        A.add(regra='P03', categoria='Recuperação' if total > 0 else 'Risco', tributo='PIS/COFINS', titulo='%d linha(s) de crédito com alíquota fora do padrão ou base × alíquota ≠ valor' % len(erros),
              descricao='Crédito básico no não cumulativo é 1,65%% (PIS) e 7,6%% (COFINS). Diferença líquida: %s (%s).' % (brl(abs(total)), 'crédito a menor' if total > 0 else 'crédito a maior'), evidencia=erros[:20], valor=abs(total), grau='Alto', acao='Retificar', prioridade='Alta', **base)

def base_credito(r, comp):
    """Base do crédito de PIS/COFINS de um item de entrada (Lei 10.637/10.833, art. 3º, §1º): valor da aquisição.
    Valor do item − desconto; o IPI não recuperável integra o custo (CST IPI ≠ 00) e o recuperável não;
    desde 05/2023 o ICMS destacado sai da base (Lei 14.592/2023; antes integrava)."""
    b = r.n('VL_ITEM') - r.n('VL_DESC')
    if (r.get('CST_IPI') or '') != '00':
        b += r.n('VL_IPI')
    if comp >= '2023-05':
        b -= r.n('VL_ICMS')
    return max(b, 0.0)


def insumos_sem_credito(e, s, A, base, regime):
    if regime not in ('1', '3'):
        return
    ativ = e['perfil']['atividade']
    grupos_credito = {'industrializacao', 'industrializacao_st', 'revenda', 'energia', 'frete', 'industrializacao_terceiros', 'ativo'}
    por = defaultdict(lambda: {'valor': 0.0, 'qtd': 0, 'ex': []})
    for r in s['regs'].get('C170', []):
        pai = r.get('pai')
        if not pai or pai.get('IND_OPER') != '0' or pai.get('COD_SIT') not in ('00', '01'):
            continue
        ci = cfop_info(r.get('CFOP'))
        if not ci['entrada'] or ci['grupo'] not in grupos_credito:
            continue
        if ci['grupo'] == 'ativo':
            continue  # ativo vai pelo F120/F130
        cst = r.get('CST_PIS', '')
        if cst in CST_PIS_SEM_CREDITO and cst not in ('71', '72', '73', '74', '75'):  # 70/98/99: sem crédito por decisão do contribuinte
            i = s['itens'].get(r.get('COD_ITEM'), {})
            reg = regime_ncm(i.get('COD_NCM')) if i else None
            if ci['grupo'] in ('revenda', 'revenda_st') and reg and reg['regime'] == 'monofasico':
                continue  # revenda de monofásico não gera crédito, está certo
            g = por[(r.get('CFOP'), cst)]
            g['valor'] += base_credito(r, base['periodo']); g['qtd'] += 1
            if len(g['ex']) < 5:
                g['ex'].append(_ev('NF', pai.get('NUM_DOC'), 'item', r.get('COD_ITEM'), (r.get('DESCR_COMPL') or i.get('DESCR_ITEM', ''))[:40], 'VL_ITEM', brl(r.n('VL_ITEM')), 'linha', r['linha']))
    if por:
        total = sum(g['valor'] for g in por.values())
        A.add(regra='P04', categoria='Recuperação', tributo='PIS/COFINS', titulo='Entradas com CFOP de insumo/revenda/frete/energia escrituradas SEM crédito (CST 70/98/99)',
              descricao='%d item(ns), base de crédito de %s (valor do item − desconto + IPI não recuperável; desde 05/2023 sem o ICMS, Lei 14.592/2023). Bens para revenda (art. 3º, I) e insumos pelo critério da essencialidade (art. 3º, II) geram crédito de 9,25%%. Cada CFOP/CST abaixo precisa de justificativa; sem ela, o crédito ficou na mesa.' % (sum(g['qtd'] for g in por.values()), brl(total)),
              evidencia=[_ev('CFOP', k[0], 'CST', k[1], '%d itens' % g['qtd'], brl(g['valor'])) for k, g in sorted(por.items(), key=lambda x: -x[1]['valor'])[:12]] + [x for g in list(por.values())[:3] for x in g['ex']],
              valor=total * 0.0925, memoria='%s × 9,25%% = %s (retirar itens que sejam de fornecedor sem incidência ou monofásicos)' % (brl(total), brl(total * 0.0925)), grau='Médio', acao='Revisar item a item; retificar com CST 50/53/56 conforme a receita vinculada', prioridade='Alta', **base)
    # uso e consumo que pode ser insumo (indústria): só aviso
    if ativ == 'industria':
        uc = [r for r in s['regs'].get('C170', []) if r.get('pai') and r['pai'].get('IND_OPER') == '0' and cfop_info(r.get('CFOP'))['grupo'] == 'uso_consumo' and r.get('CST_PIS', '') in CST_PIS_SEM_CREDITO]
        if uc:
            total = sum(base_credito(r, base['periodo']) for r in uc)
            A.add(regra='P04b', categoria='Recuperação', tributo='PIS/COFINS', titulo='Indústria: %d item(ns) de "uso e consumo" sem crédito que podem ser insumo pela essencialidade' % len(uc),
                  descricao='Base de %s. EPI, uniformes, manutenção, materiais de limpeza da produção, testes, tratamento de efluentes, combustíveis e lubrificantes de máquinas são insumo (REsp 1.221.170; PN COSIT 5/2018). O CFOP de uso/consumo não impede o crédito de PIS/COFINS.' % brl(total),
                  evidencia=[_ev('NF', r['pai'].get('NUM_DOC'), (r.get('DESCR_COMPL') or s['itens'].get(r.get('COD_ITEM'), {}).get('DESCR_ITEM', ''))[:50], brl(r.n('VL_ITEM'))) for r in sorted(uc, key=lambda x: -x.n('VL_ITEM'))[:20]],
                  valor=total * 0.0925 * 0.5, estimativa=True, memoria='%s × 9,25%% × 50%% (parcela estimada que passa no teste de essencialidade) = %s' % (brl(total), brl(total * 0.0925 * 0.5)), grau='Médio', acao='Classificar item a item com a produção; documentar; retificar', prioridade='Média', **base)

def saidas_monofasicas(e, s, A, base, regime):
    ativ = e['perfil']['atividade']
    achados = defaultdict(lambda: {'bc': 0.0, 'pis': 0.0, 'cof': 0.0, 'qtd': 0, 'ex': []})
    # C170 (NF-e detalhada) e C180/C181/C185 (consolidado por item) e C175 (NFC-e)
    def considerar(cfop, cod_item, ncm, cst_pis, bc_pis, vl_pis, cst_cof, bc_cof, vl_cof, ref):
        ci = cfop_info(cfop)
        if ci['entrada'] or ci['grupo'] not in ('venda_producao', 'venda_revenda', 'venda_st_producao', 'venda_st_revenda', 'exportacao'):
            return
        reg = regime_ncm(ncm)
        if not reg:
            return
        if reg['regime'] == 'monofasico':
            revenda = ci['grupo'] in ('venda_revenda', 'venda_st_revenda') or ativ == 'comercio'
            if revenda and cst_pis in ('01', '02'):
                g = achados[(reg['setor'], 'revenda de monofásico tributada (deveria ser CST 04)')]
            elif not revenda and cst_pis == '01':
                g = achados[(reg['setor'], 'fabricante de monofásico com alíquota básica (deveria ser CST 02 com alíquota concentrada: RISCO de pagamento a menor)')]
            else:
                return
        else:
            if cst_pis == '01':
                g = achados[(reg['setor'], 'alíquota zero tributada (deveria ser CST 06)')]
            else:
                return
        g['bc'] += bc_pis; g['pis'] += vl_pis; g['cof'] += vl_cof; g['qtd'] += 1
        if len(g['ex']) < 6:
            g['ex'].append(ref)
    for r in s['regs'].get('C170', []):
        pai = r.get('pai')
        if not pai or pai.get('IND_OPER') != '1':
            continue
        i = s['itens'].get(r.get('COD_ITEM'), {})
        considerar(r.get('CFOP'), r.get('COD_ITEM'), i.get('COD_NCM'), r.get('CST_PIS'), r.n('VL_BC_PIS'), r.n('VL_PIS'), r.get('CST_COFINS'), r.n('VL_BC_COFINS'), r.n('VL_COFINS'), _ev('NF', pai.get('NUM_DOC'), r.get('COD_ITEM'), i.get('DESCR_ITEM', '')[:35], 'NCM', i.get('COD_NCM'), 'CST', r.get('CST_PIS'), brl(r.n('VL_PIS') + r.n('VL_COFINS'))))
    for c180 in s['regs'].get('C180', []):
        pis_f = [f for f in c180['filhos'] if f['REG'] == 'C181']; cof_f = {(f.get('CST_COFINS'), f.get('CFOP')): f for f in c180['filhos'] if f['REG'] == 'C185'}
        for f in pis_f:
            cf = cof_f.get((f.get('CST_PIS'), f.get('CFOP')))
            considerar(f.get('CFOP'), c180.get('COD_ITEM'), c180.get('COD_NCM'), f.get('CST_PIS'), f.n('VL_BC_PIS'), f.n('VL_PIS'), cf.get('CST_COFINS') if cf else '', cf.n('VL_BC_COFINS') if cf else 0, cf.n('VL_COFINS') if cf else 0, _ev('C180', c180.get('COD_ITEM'), 'NCM', c180.get('COD_NCM'), 'CFOP', f.get('CFOP'), 'CST', f.get('CST_PIS'), brl(f.n('VL_PIS'))))
    for (setor, problema), g in achados.items():
        risco = 'RISCO' in problema
        A.add(regra='P05', categoria='Risco' if risco else 'Pago a maior', tributo='PIS/COFINS', titulo='%s: %s' % (setor, problema.split(' (')[0]),
              descricao='%d linha(s) de saída, base %s, PIS+COFINS pagos %s. %s' % (g['qtd'], brl(g['bc']), brl(g['pis'] + g['cof']), problema), evidencia=g['ex'],
              valor=g['pis'] + g['cof'] if not risco else g['bc'] * 0.0325, estimativa=risco, memoria=('PIS %s + COFINS %s pagos indevidamente' % (brl(g['pis']), brl(g['cof']))) if not risco else 'base %s × diferença de alíquota estimada' % brl(g['bc']),
              grau='Alto', acao='Retificar a EFD Contribuições (CST 04/06) e a DCTF; PER/DCOMP do indébito (5 anos); corrigir o cadastro para estancar' if not risco else 'Revisar enquadramento (fabricante/importador × revendedor) e alíquotas da lei específica', prioridade='Alta', **base)

def icms_na_base(e, s, A, base, regime):
    """Saídas: ICMS dentro da base de PIS/COFINS (Tema 69). Entradas após 05/2023: ICMS dentro da base do crédito (Lei 14.592)."""
    comp = base['periodo']
    sai_bc = sai_icms = 0.0; n_sai = 0; ex_s = []
    ent_bc = ent_icms = 0.0; n_ent = 0; ex_e = []
    for r in s['regs'].get('C170', []):
        pai = r.get('pai')
        if not pai or pai.get('COD_SIT') not in ('00', '01'):
            continue
        icms = r.n('VL_ICMS'); item = r.n('VL_ITEM') - r.n('VL_DESC')
        if icms <= 0 or item <= 0:
            continue
        if pai.get('IND_OPER') == '1' and r.get('CST_PIS') in ('01', '02'):
            bc = r.n('VL_BC_PIS')
            if bc >= item - 0.05:  # base não excluiu o ICMS
                sai_bc += bc; sai_icms += icms; n_sai += 1
                if len(ex_s) < 10: ex_s.append(_ev('NF', pai.get('NUM_DOC'), 'item', r.get('NUM_ITEM'), 'VL_ITEM', brl(item), 'BC PIS', brl(bc), 'ICMS', brl(icms)))
        if pai.get('IND_OPER') == '0' and r.get('CST_PIS') in CST_PIS_COM_CREDITO and comp >= '2023-05':
            bc = r.n('VL_BC_PIS')
            if bc >= item - 0.05:
                ent_bc += bc; ent_icms += icms; n_ent += 1
                if len(ex_e) < 10: ex_e.append(_ev('NF', pai.get('NUM_DOC'), 'item', r.get('NUM_ITEM'), 'VL_ITEM', brl(item), 'BC crédito', brl(bc), 'ICMS', brl(icms)))
    aliq = 0.0925 if regime in ('1', '3') else 0.0365
    if n_sai:
        A.add(regra='P06', categoria='Pago a maior', tributo='PIS/COFINS', titulo='ICMS dentro da base de PIS/COFINS nas saídas (Tema 69 do STF) em %d item(ns)' % n_sai,
              descricao='Base de PIS/COFINS igual ao valor do item, sem excluir o ICMS destacado (%s). O ICMS destacado não compõe a receita bruta desde 15/03/2017.' % brl(sai_icms), evidencia=ex_s,
              valor=sai_icms * aliq, memoria='ICMS destacado %s × %.2f%% = %s' % (brl(sai_icms), aliq * 100, brl(sai_icms * aliq)), grau='Alto', acao='Retificar EFD Contribuições e DCTF; PER/DCOMP; ajustar o ERP', prioridade='Alta', **base)
    if n_ent:
        A.add(regra='P06b', categoria='Risco', tributo='PIS/COFINS', titulo='ICMS dentro da base do CRÉDITO de PIS/COFINS após maio/2023 em %d item(ns)' % n_ent,
              descricao='Desde 1º/05/2023 (Lei 14.592/2023) o ICMS destacado na aquisição não integra a base do crédito. Crédito a maior de %s.' % brl(ent_icms * 0.0925), evidencia=ex_e, valor=ent_icms * 0.0925, memoria='ICMS nas entradas %s × 9,25%%' % brl(ent_icms), grau='Alto', acao='Retificar e recolher a diferença com denúncia espontânea', prioridade='Alta', **base)

def energia_frete(s, A, base, regime):
    if regime not in ('1', '3'):
        return
    for r in s['regs'].get('C500', []):
        if r.get('IND_OPER') != '0':
            continue
        c501 = [f for f in r['filhos'] if f['REG'] == 'C501']; c505 = [f for f in r['filhos'] if f['REG'] == 'C505']
        vdoc = r.n('VL_DOC')
        bdoc = vdoc - (r.n('VL_ICMS') if base['periodo'] >= '2023-05' else 0)
        if not c501 or sum(f.n('VL_PIS') for f in c501) <= 0:
            A.add(regra='P07', categoria='Recuperação', tributo='PIS/COFINS', titulo='Energia elétrica escriturada sem crédito de PIS/COFINS (C501/C505)', descricao='Fatura de %s no C500 sem crédito. Crédito integral no não cumulativo, qualquer atividade.' % brl(vdoc), evidencia=[_ev('C500 nº', r.get('NUM_DOC'), brl(vdoc), 'linha', r['linha'])], valor=bdoc * 0.0925, memoria='%s%s × 9,25%%' % (brl(bdoc), ' (fatura − ICMS, desde 05/2023)' if bdoc != vdoc else ''), grau='Alto', acao='Retificar com C501 (CST 50, natureza 04) e C505', prioridade='Alta', **base)
    for r in s['regs'].get('D100', []):
        if r.get('IND_OPER') != '0':
            continue
        d101 = [f for f in r['filhos'] if f['REG'] == 'D101']
        bfr = r.n('VL_DOC') - (r.n('VL_ICMS') if base['periodo'] >= '2023-05' else 0)
        if not d101 or sum(f.n('VL_PIS') for f in d101) <= 0:
            A.add(regra='P08', categoria='Recuperação', tributo='PIS/COFINS', titulo='CT-e tomado sem crédito de PIS/COFINS (D101/D105)', descricao='Frete de %s (CT-e %s). Frete na venda e frete na compra de bens com crédito geram crédito; frete de transferência de produto acabado entre estabelecimentos não (STJ).' % (brl(r.n('VL_DOC')), r.get('NUM_DOC')), evidencia=[_ev('D100', r.get('CHV_CTE'), 'linha', r['linha'])], valor=bfr * 0.0925, memoria='%s%s × 9,25%%' % (brl(bfr), ' (frete − ICMS, desde 05/2023)' if bfr != r.n('VL_DOC') else ''), grau='Médio', acao='Classificar o frete (venda/compra/transferência) e retificar', prioridade='Média', **base)

def saldo_credor(s, A, base):
    for reg, trib in (('1100', 'PIS'), ('1500', 'COFINS')):
        for r in s['regs'].get(reg, []):
            fim = r.n('SLD_CRED_FIM')
            if fim > 0 and r.n('VL_CRED_PER_EFD') + r.n('VL_CRED_DCOMP_EFD') + r.n('VL_CRED_PER_PA_ANT') + r.n('VL_CRED_DCOMP_PA_ANT') <= 0:
                A.add(regra='P09', categoria='Recuperação', tributo=trib, titulo='Saldo de crédito de %s de %s (origem %s, código %s) sem PER/DCOMP' % (trib, brl(fim), r.get('PER_APU_CRED'), r.get('COD_CRED')),
                      descricao='Crédito controlado no %s sem pedido de ressarcimento nem compensação. Créditos de exportação, alíquota zero e suspensão (códigos 2xx/3xx) são ressarcíveis em dinheiro; os de mercado interno tributado só compensam PIS/COFINS.' % reg, evidencia=[_ev(reg, 'linha', r['linha'], 'apurado', brl(r.n('VL_TOT_CRED_APU')), 'saldo fim', brl(fim))], valor=fim, grau='Alto', acao='PER/DCOMP (IN RFB 2.055/2021) dentro de 5 anos do período de apuração', prioridade='Alta', **base)

def apuracao(s, A, base, regime):
    for reg, trib, sub in (('M200', 'PIS', 'M210'), ('M600', 'COFINS', 'M610')):
        for r in s['regs'].get(reg, []):
            cont = sum(f.n('VL_CONT_PER') for f in r['filhos'] if f['REG'] == sub)
            if abs(cont - r.n('VL_TOT_CONT_NC_PER') - r.n('VL_TOT_CONT_CUM_PER')) > TOL:
                A.add(regra='P10', categoria='Risco', tributo=trib, titulo='%s: contribuição do período não fecha com os %s' % (reg, sub), descricao='Σ %s = %s; %s declara %s (NC) + %s (cum).' % (sub, brl(cont), reg, brl(r.n('VL_TOT_CONT_NC_PER')), brl(r.n('VL_TOT_CONT_CUM_PER'))), valor=abs(cont - r.n('VL_TOT_CONT_NC_PER') - r.n('VL_TOT_CONT_CUM_PER')), grau='Alto', acao='Retificar', **base)
    # rateio proporcional (0111) x receitas
    r0111 = s['regs'].get('0111')
    r0110 = s['regs'].get('0110')
    if r0110 and r0110[0].get('IND_APRO_CRED') == '2' and not r0111:
        A.add(regra='P10', categoria='Risco', tributo='PIS/COFINS', titulo='Rateio proporcional declarado (0110) sem o 0111', descricao='', grau='Médio', acao='Informar as receitas do 0111', **base)
    # receitas não tributadas sem natureza (M400/M410)
    for reg, sub, trib in (('M400', 'M410', 'PIS'), ('M800', 'M810', 'COFINS')):
        for r in s['regs'].get(reg, []):
            if r.n('VL_TOT_REC') > 0 and not [f for f in r['filhos'] if f['REG'] == sub]:
                A.add(regra='P10', categoria='Risco', tributo=trib, titulo='%s com receita não tributada (%s) sem detalhamento por natureza (%s)' % (reg, brl(r.n('VL_TOT_REC')), sub), descricao='CST %s.' % r.get('CST_PIS') or r.get('CST_COFINS'), grau='Médio', acao='Informar o %s' % sub, **base)

def ativo(e, s, A, base, regime):
    if regime not in ('1', '3'):
        return
    f120 = s['regs'].get('F120', []); f130 = s['regs'].get('F130', [])
    entradas_ativo = [r for r in s['regs'].get('C170', []) if r.get('pai') and r['pai'].get('IND_OPER') == '0' and cfop_info(r.get('CFOP'))['grupo'] == 'ativo']
    if entradas_ativo and not f120 and not f130:
        total = sum(base_credito(r, base['periodo']) for r in entradas_ativo)
        A.add(regra='P11', categoria='Recuperação', tributo='PIS/COFINS', titulo='Aquisição de ativo imobilizado (%s) sem crédito no F120/F130' % brl(total),
              descricao='Máquinas e equipamentos para produção/locação/prestação geram crédito (depreciação, 1/48 ou imediato para máquinas novas, Lei 11.774/2008 art. 1º). Bens administrativos não.',
              evidencia=[_ev('NF', r['pai'].get('NUM_DOC'), (r.get('DESCR_COMPL') or s['itens'].get(r.get('COD_ITEM'), {}).get('DESCR_ITEM', ''))[:40], brl(r.n('VL_ITEM'))) for r in entradas_ativo[:10]],
              valor=total * 0.0925, estimativa=True, memoria='%s × 9,25%% (se bem de produção; crédito imediato para máquinas novas)' % brl(total), grau='Médio', acao='Identificar o uso do bem; escriturar F130 (imediato/1-48) ou F120', prioridade='Média', **base)
