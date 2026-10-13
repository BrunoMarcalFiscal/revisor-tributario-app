# -*- coding: utf-8 -*-
"""Diagnóstico da empresa: lê os arquivos e monta o retrato do negócio (produtos, clientes, fornecedores, operações,
carga tributária mês a mês, indicadores) e uma narrativa em português. Genérico: tudo sai dos CFOP/CST/NCM/registros."""
from collections import Counter, defaultdict
from .conhecimento import cfop_info, CFOP_DESCR
from .util import brl, uf_participante
from .regras_regime import CFOP_RECEITA, CFOP_FAT_FUTURO, CFOP_ENTREGA_FUTURA, _icms_ipi_receita_fiscal

GRUPO_NOME = {'venda_producao': 'venda de produção própria', 'venda_revenda': 'revenda de mercadorias', 'venda_st_producao': 'venda de produção com ST', 'venda_st_revenda': 'revenda com ST',
              'exportacao': 'exportação', 'exportacao_indireta': 'exportação indireta', 'industrializacao_terceiros': 'industrialização (remessa/retorno/encomenda)', 'devolucao': 'devoluções',
              'bonificacao_brinde_amostra': 'bonificação, brinde e amostra', 'transferencia': 'transferências', 'comodato': 'comodato', 'ativo': 'ativo imobilizado', 'uso_consumo': 'uso e consumo',
              'operacoes_diversas': 'remessas e operações diversas (entrega futura, conserto, demonstração)', 'industrializacao': 'insumos para industrialização', 'revenda': 'mercadorias para revenda',
              'industrializacao_st': 'insumos com ST', 'revenda_st': 'mercadorias para revenda com ST', 'energia': 'energia elétrica', 'frete': 'frete (CT-e)', 'comunicacao': 'comunicação', 'outros': 'outros'}

def montar(e):
    d = {'meses_fiscal': sorted(e['fiscal']), 'meses_contrib': sorted(e['contrib']), 'retificadoras': [s['periodo']['comp'] for s in list(e['fiscal'].values()) + list(e['contrib'].values()) if s.get('retificadora')]}
    mensal = []; saidas_grupo = Counter(); entradas_grupo = Counter(); uf_dest = Counter(); uf_orig = Counter(); ambito_ent = Counter()
    contrib_nc = Counter(); forn = defaultdict(lambda: {'valor': 0.0, 'uf': '', 'cst': Counter(), 'docs': 0}); cli = defaultdict(lambda: {'valor': 0.0, 'uf': '', 'docs': 0, 'nao_contrib': 0.0})
    ncm_ent = defaultdict(lambda: {'valor': 0.0, 'descr': '', 'tipo': ''}); ncm_sai = defaultdict(lambda: {'valor': 0.0, 'descr': ''})
    cap_cad = Counter(); tipo_item = Counter()
    for comp in d['meses_fiscal']:
        s = e['fiscal'][comp]
        rec, icms_rec, ipi_rec, dev, exp = _icms_ipi_receita_fiscal(s)
        e110 = s['regs'].get('E110', [None])[0]; e520 = s['regs'].get('E520', [None])[0]
        st = sum(r.n('VL_ICMS_RECOL_ST') for r in s['regs'].get('E210', [])); difal = sum(r.n('VL_RECOL_DIFAL') + r.n('VL_RECOL_FCP') for r in s['regs'].get('E310', []))
        fut = sum(r.n('VL_OPR') for r in s['regs'].get('C190', []) if r.get('CFOP') in CFOP_FAT_FUTURO)
        c = e['contrib'].get(comp)
        pc = (sum(r.n('VL_TOT_CONT_REC') for r in c['regs'].get('M200', [])) + sum(r.n('VL_TOT_CONT_REC') for r in c['regs'].get('M600', []))) if c else None
        ent_trib = sum(r.n('VL_OPR') for r in s['regs'].get('C190', []) if cfop_info(r.get('CFOP'))['entrada'] and cfop_info(r.get('CFOP'))['grupo'] in ('industrializacao', 'revenda', 'industrializacao_st', 'revenda_st'))
        linha = {'periodo': comp, 'receita': round(rec, 2), 'exportacao': round(exp, 2), 'simples_faturamento': round(fut, 2), 'devolucoes': round(dev, 2), 'entradas_insumo_revenda': round(ent_trib, 2),
                 'icms_debitos': round(e110.n('VL_TOT_DEBITOS'), 2) if e110 else None, 'icms_creditos': round(e110.n('VL_TOT_CREDITOS'), 2) if e110 else None, 'icms_recolher': round(e110.n('VL_ICMS_RECOLHER'), 2) if e110 else None, 'icms_saldo_credor': round(e110.n('VL_SLD_CREDOR_TRANSPORTAR'), 2) if e110 else None,
                 'icms_st': round(st, 2), 'difal_fcp': round(difal, 2), 'ipi_debitos': round(e520.n('VL_DEB_IPI'), 2) if e520 else None, 'ipi_creditos': round(e520.n('VL_CRED_IPI'), 2) if e520 else None, 'ipi_recolher': round(e520.n('VL_SD_IPI'), 2) if e520 else None,
                 'pis_cofins': round(pc, 2) if pc is not None else None}
        total_trib = (linha['icms_recolher'] or 0) + st + difal + (linha['ipi_recolher'] or 0) + (pc or 0)
        linha['carga_pct'] = round(total_trib / rec * 100, 2) if rec else None
        linha['total_tributos'] = round(total_trib, 2)
        mensal.append(linha)
        for r in s['regs'].get('C190', []):
            ci = cfop_info(r.get('CFOP'))
            (entradas_grupo if ci['entrada'] else saidas_grupo)[ci['grupo']] += r.n('VL_OPR')
            if ci['entrada']:
                ambito_ent[ci['ambito']] += r.n('VL_OPR')
        for c100 in s['regs'].get('C100', []):
            if c100.get('COD_SIT') not in ('00', '01'):
                continue
            p = s['participantes'].get(c100.get('COD_PART'), {}); uf = uf_participante(p) or '?'
            cnpj = p.get('CNPJ') or p.get('CPF') or c100.get('COD_PART')
            if c100.get('IND_OPER') == '1':
                uf_dest[uf] += c100.n('VL_DOC'); k = cli[cnpj]; k['valor'] += c100.n('VL_DOC'); k['uf'] = uf; k['docs'] += 1; k['nome'] = p.get('NOME', '')
                for f in c100['filhos']:
                    if f['REG'] == 'C190' and f.get('CFOP') in ('6107', '6108', '5101', '5102', '6101', '6102', '6116', '5116'):
                        contrib_nc['não contribuinte (x107/x108)' if f.get('CFOP') in ('6107', '6108') else 'contribuinte / regra geral'] += f.n('VL_OPR')
                        if f.get('CFOP') in ('6107', '6108'):
                            k['nao_contrib'] += f.n('VL_OPR')
            else:
                uf_orig[uf] += c100.n('VL_DOC'); k = forn[cnpj]; k['valor'] += c100.n('VL_DOC'); k['uf'] = uf; k['docs'] += 1; k['nome'] = p.get('NOME', '')
                for f in c100['filhos']:
                    if f['REG'] == 'C190':
                        k['cst'][f.get('CST_ICMS')] += f.n('VL_OPR')
        for it in s['regs'].get('C170', []):
            i = s['itens'].get(it.get('COD_ITEM'), {}); n = i.get('COD_NCM') or '(sem NCM)'
            if cfop_info(it.get('CFOP'))['entrada']:
                g = ncm_ent[n]; g['valor'] += it.n('VL_ITEM'); g['descr'] = g['descr'] or (i.get('DESCR_ITEM') or it.get('DESCR_COMPL') or '')[:50]; g['tipo'] = i.get('TIPO_ITEM', '')
            else:
                g = ncm_sai[n]; g['valor'] += it.n('VL_ITEM'); g['descr'] = g['descr'] or (i.get('DESCR_ITEM') or '')[:50]
        for i in s['regs'].get('0200', []):
            cap_cad[(i.get('COD_NCM') or '')[:4]] += 1; tipo_item[i.get('TIPO_ITEM')] += 1
    # produtos vendidos: C170 de saída (raro) > XML > C180 da EFD Contribuições
    for comp in d['meses_contrib']:
        c = e['contrib'][comp]
        for c180 in c['regs'].get('C180', []):
            n = c180.get('COD_NCM') or '(sem NCM)'; g = ncm_sai[n]; g['valor'] += c180.n('VL_TOT_ITEM'); g['descr'] = g['descr'] or c['itens'].get(c180.get('COD_ITEM'), {}).get('DESCR_ITEM', '')[:50]
        for it in c['regs'].get('C170', []):
            if it.get('pai') and it['pai'].get('IND_OPER') == '1':
                i = c['itens'].get(it.get('COD_ITEM'), {}); n = i.get('COD_NCM') or '(sem NCM)'; g = ncm_sai[n]; g['valor'] += it.n('VL_ITEM'); g['descr'] = g['descr'] or (i.get('DESCR_ITEM') or '')[:50]
    tot_s = sum(saidas_grupo.values()) or 1; tot_e = sum(entradas_grupo.values()) or 1
    d['mensal'] = mensal
    d['saidas_por_grupo'] = [{'grupo': GRUPO_NOME.get(g, g), 'valor': round(v, 2), 'pct': round(v / tot_s * 100, 1)} for g, v in saidas_grupo.most_common()]
    d['entradas_por_grupo'] = [{'grupo': GRUPO_NOME.get(g, g), 'valor': round(v, 2), 'pct': round(v / tot_e * 100, 1)} for g, v in entradas_grupo.most_common()]
    d['uf_destino'] = [{'uf': u, 'valor': round(v, 2), 'pct': round(v / max(sum(uf_dest.values()), 1) * 100, 1)} for u, v in uf_dest.most_common(12)]
    d['uf_origem'] = [{'uf': u, 'valor': round(v, 2), 'pct': round(v / max(sum(uf_orig.values()), 1) * 100, 1)} for u, v in uf_orig.most_common(12)]
    d['ambito_entradas'] = [{'ambito': a, 'valor': round(v, 2), 'pct': round(v / tot_e * 100, 1)} for a, v in ambito_ent.most_common()]
    d['contribuinte_x_nao'] = [{'tipo': k, 'valor': round(v, 2)} for k, v in contrib_nc.most_common()]
    d['fornecedores'] = [{'nome': (k['nome'] or c)[:40], 'cnpj': c, 'uf': k['uf'], 'valor': round(k['valor'], 2), 'docs': k['docs'], 'cst': ', '.join('%s (%d%%)' % (cst, v / k['valor'] * 100) for cst, v in k['cst'].most_common(2)) if k['valor'] else ''} for c, k in sorted(forn.items(), key=lambda x: -x[1]['valor'])[:12]]
    d['clientes'] = [{'nome': (k['nome'] or c)[:40], 'cnpj': c, 'uf': k['uf'], 'valor': round(k['valor'], 2), 'docs': k['docs'], 'nao_contrib_pct': round(k['nao_contrib'] / k['valor'] * 100) if k['valor'] else 0} for c, k in sorted(cli.items(), key=lambda x: -x[1]['valor'])[:12]]
    d['ncm_insumos'] = [{'ncm': n, 'descr': g['descr'], 'tipo_item': g['tipo'], 'valor': round(g['valor'], 2)} for n, g in sorted(ncm_ent.items(), key=lambda x: -x[1]['valor'])[:15]]
    d['ncm_produtos'] = [{'ncm': n, 'descr': g['descr'], 'valor': round(g['valor'], 2)} for n, g in sorted(ncm_sai.items(), key=lambda x: -x[1]['valor'])[:15]]
    d['capitulos_cadastro'] = [{'ncm4': k, 'itens': v} for k, v in cap_cad.most_common(12)]
    d['tipo_item_cadastro'] = dict(tipo_item)
    # indicadores agregados
    rec_t = sum(m['receita'] for m in mensal); trib_t = sum(m['total_tributos'] for m in mensal); ent_t = sum(m['entradas_insumo_revenda'] for m in mensal)
    cred_t = sum(m['icms_creditos'] or 0 for m in mensal); deb_t = sum(m['icms_debitos'] or 0 for m in mensal)
    d['indicadores'] = {'receita_total': round(rec_t, 2), 'tributos_total': round(trib_t, 2), 'carga_pct': round(trib_t / rec_t * 100, 2) if rec_t else None,
                        'icms_recolhido': round(sum(m['icms_recolher'] or 0 for m in mensal), 2), 'icms_efetivo_pct': round(sum(m['icms_recolher'] or 0 for m in mensal) / rec_t * 100, 2) if rec_t else None,
                        'credito_sobre_entradas_pct': round(cred_t / ent_t * 100, 2) if ent_t else None, 'creditos_sobre_debitos_pct': round(cred_t / deb_t * 100, 1) if deb_t else None,
                        'difal_total': round(sum(m['difal_fcp'] for m in mensal), 2), 'ipi_total': round(sum(m['ipi_recolher'] or 0 for m in mensal), 2), 'st_total': round(sum(m['icms_st'] for m in mensal), 2),
                        'pis_cofins_total': round(sum(m['pis_cofins'] or 0 for m in mensal), 2), 'devolucoes_pct': round(sum(m['devolucoes'] for m in mensal) / rec_t * 100, 2) if rec_t else None,
                        'exportacao_pct': round(sum(m['exportacao'] for m in mensal) / rec_t * 100, 2) if rec_t else None, 'nao_contribuinte_pct': round(contrib_nc.get('não contribuinte (x107/x108)', 0) / max(sum(contrib_nc.values()), 1) * 100, 1)}
    d['narrativa'] = narrativa(e, d)
    return d

def narrativa(e, d):
    p = e['perfil']; pi = e['perfil_inferido']; r = e.get('regime', {}); ind = d['indicadores']; m = d['mensal']
    frases = []
    ativ = {'industria': 'indústria', 'comercio': 'comércio', 'servico': 'prestadora de serviços', 'misto': 'atividade mista'}.get(p.get('atividade'), 'atividade não identificada')
    frases.append('%s é %s%s, estabelecida em %s, %s.' % (e['nome'], ativ, ' (inferido pelos CFOPs)' if p.get('atividade_inferida') else '', e['uf'], ('regime %s, PIS/COFINS %s (%s)' % (r.get('tributario') or 'não informado', (r.get('pis_cofins') or '?').replace('_', ' '), r.get('fonte'))) if r else ''))
    if d['meses_fiscal'] or d['meses_contrib']:
        frases.append('Arquivos: EFD ICMS/IPI de %s; EFD Contribuições de %s%s.' % (('%s a %s (%d meses)' % (d['meses_fiscal'][0], d['meses_fiscal'][-1], len(d['meses_fiscal']))) if d['meses_fiscal'] else 'nenhum', ('%s a %s (%d meses)' % (d['meses_contrib'][0], d['meses_contrib'][-1], len(d['meses_contrib']))) if d['meses_contrib'] else 'nenhum', ('; retificadoras em %s' % ', '.join(sorted(set(d['retificadoras'])))) if d['retificadoras'] else ''))
    if d['ncm_insumos']:
        frases.append('Compra principalmente %s.' % '; '.join('%s (NCM %s, %s)' % (x['descr'] or 'item', x['ncm'], brl(x['valor'])) for x in d['ncm_insumos'][:4]))
    if d['ncm_produtos']:
        frases.append('Vende principalmente %s.' % '; '.join('%s (NCM %s, %s)' % (x['descr'] or 'item', x['ncm'], brl(x['valor'])) for x in d['ncm_produtos'][:4]))
    elif d['capitulos_cadastro']:
        frases.append('As NF-e próprias não trazem itens no SPED (C170 só nas entradas); o cadastro 0200 concentra as posições NCM %s. Para o retrato dos produtos vendidos, forneça os XML de saída.' % ', '.join(x['ncm4'] for x in d['capitulos_cadastro'][:6]))
    if d['saidas_por_grupo']:
        frases.append('Saídas: %s.' % '; '.join('%s %s (%.0f%%)' % (x['grupo'], brl(x['valor']), x['pct']) for x in d['saidas_por_grupo'][:5]))
    if d['uf_destino']:
        frases.append('Destinos: %s.' % ', '.join('%s %.0f%%' % (x['uf'], x['pct']) for x in d['uf_destino'][:7]) + (' Vendas a não contribuintes de outra UF (DIFAL) representam %.0f%% das vendas de mercadorias.' % ind['nao_contribuinte_pct'] if ind['nao_contribuinte_pct'] else ''))
    if d['entradas_por_grupo']:
        frases.append('Entradas: %s; origem %s.' % ('; '.join('%s %s (%.0f%%)' % (x['grupo'], brl(x['valor']), x['pct']) for x in d['entradas_por_grupo'][:4]), ', '.join('%s %.0f%%' % (x['ambito'], x['pct']) for x in d['ambito_entradas'])))
    if m:
        frases.append('Carga tributária apurada no SPED: %s de tributos sobre %s de receita (%.1f%%): ICMS recolhido %s (%.1f%% da receita; créditos cobrem %.0f%% dos débitos), DIFAL/FCP %s, ICMS-ST %s, IPI %s, PIS/COFINS %s.' % (brl(ind['tributos_total']), brl(ind['receita_total']), ind['carga_pct'] or 0, brl(ind['icms_recolhido']), ind['icms_efetivo_pct'] or 0, ind['creditos_sobre_debitos_pct'] or 0, brl(ind['difal_total']), brl(ind['st_total']), brl(ind['ipi_total']), brl(ind['pis_cofins_total'])))
        if ind['credito_sobre_entradas_pct'] is not None:
            frases.append('O crédito de ICMS equivale a %.1f%% das entradas de insumo/revenda (a alíquota nominal interna em %s é %s%%): a diferença vem de diferimento, isenção, fornecedores do Simples e entradas interestaduais a 4/7/12%%, detalhado no quadro de crédito efetivo.' % (ind['credito_sobre_entradas_pct'], e['uf'], __import__('motor.conhecimento', fromlist=['ALIQ_INTERNA_UF']).ALIQ_INTERNA_UF.get(e['uf'], '?')))
        if ind['devolucoes_pct']:
            frases.append('Devoluções de venda somam %.1f%% da receita.' % ind['devolucoes_pct'])
    sinais = []
    if not pi.get('tem_energia') and p.get('atividade') == 'industria': sinais.append('nenhuma fatura de energia elétrica escriturada')
    if not any(e['fiscal'][c]['regs'].get('K200') for c in d['meses_fiscal']) and p.get('atividade') == 'industria': sinais.append('bloco K vazio')
    if pi.get('exporta'): sinais.append('exporta (%s)' % brl(pi.get('valor_exportacao', 0)))
    if pi.get('substituto_tributario'): sinais.append('atua como substituto tributário')
    if pi.get('compra_com_st'): sinais.append('compra mercadorias com ST')
    if sinais:
        frases.append('Sinais relevantes: %s.' % '; '.join(sinais))
    return ' '.join(frases)
