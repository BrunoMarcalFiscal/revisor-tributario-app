# -*- coding: utf-8 -*-
"""Regras que dependem do regime tributário (Presumido/Real/Simples, cumulativo/não cumulativo) e cruzamentos de apuração
que exigem entender a empresa: base do PIS/COFINS, conciliação de receita, simulação de regime, DIFAL por UF,
crédito efetivo das entradas, industrialização por encomenda, retificadoras."""
from collections import defaultdict, Counter
from .conhecimento import cfop_info, ALIQ_INTERNA_UF, aliq_interestadual
from .util import brl, uf_participante

TOL = 1.00
CFOP_RECEITA = {'5101', '5102', '5103', '5104', '5105', '5106', '5109', '5110', '5111', '5112', '5113', '5114', '5115', '5116', '5117', '5118', '5119', '5120', '5122', '5123', '5124', '5125',
                '6101', '6102', '6103', '6104', '6105', '6106', '6107', '6108', '6109', '6110', '6111', '6112', '6113', '6114', '6115', '6116', '6117', '6118', '6119', '6120', '6122', '6123', '6124', '6125',
                '7101', '7102', '7105', '7106', '7127', '5401', '5402', '5403', '5405', '6401', '6402', '6403', '6404', '5501', '5502', '6501', '6502', '5551', '6551', '5933', '6933'}
CFOP_FAT_FUTURO = {'5922', '6922'}
CFOP_ENTREGA_FUTURA = {'5116', '5117', '6116', '6117'}

def _ev(*p):
    return ' | '.join(str(x) for x in p if x not in (None, ''))

def regime(e):
    """Consolida o regime: perfil informado > 0110 da EFD Contribuições > inferência."""
    p = e['perfil']; inf = e['info']
    trib = p.get('regime_tributario') or ''
    cod = inf.get('cod_inc_trib', '')
    pc = {'1': 'nao_cumulativo', '2': 'cumulativo', '3': 'misto'}.get(cod, '')
    if p.get('regime_pis_cofins_informado'):
        pc = p['regime_pis_cofins_informado']
    if not pc:
        pc = {'Lucro Presumido': 'cumulativo', 'Lucro Real': 'nao_cumulativo', 'Simples Nacional': 'simples'}.get(trib, '')
    if not trib:
        trib = {'cumulativo': 'Lucro Presumido (inferido pelo 0110)', 'nao_cumulativo': 'Lucro Real (inferido pelo 0110)'}.get(pc, '')
    fonte = 'perfil informado' if p.get('regime_tributario') else ('registro 0110 da EFD Contribuições' if cod else 'não informado')
    return {'tributario': trib, 'pis_cofins': pc, 'fonte': fonte, 'cod_inc_trib': cod}

def rodar(e, A):
    r = e['regime']
    comps = sorted(set(e['fiscal']) | set(e['contrib']))
    if not comps:
        return
    for comp in sorted(e['fiscal']):
        s = e['fiscal'][comp]; base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        difal_por_uf(e, s, A, base)
        credito_efetivo(e, s, A, base)
        industrializacao_encomenda(e, s, A, base)
    for comp in sorted(e['contrib']):
        c = e['contrib'][comp]; base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        if r['pis_cofins'] in ('cumulativo', 'misto'):
            base_cumulativa(e, c, A, base)
        conciliacao_receita(e, c, A, base)
        retencoes(e, c, A, base)
    retificadoras(e, A)
    if r['tributario'].startswith('Lucro Presumido'):
        simulacao_real_x_presumido(e, A)
        presuncao(e, A)
    if r['tributario'].startswith('Simples'):
        simples(e, A)

# ---------------------------------------------------------------- PIS/COFINS cumulativo
def _icms_ipi_receita_fiscal(s):
    icms = ipi = rec = dev = exp = 0.0
    for r in s['regs'].get('C190', []):
        ci = cfop_info(r.get('CFOP'))
        if ci['entrada']:
            if ci['grupo'] == 'devolucao':
                dev += r.n('VL_OPR')
            continue
        if r.get('CFOP') in CFOP_RECEITA:
            rec += r.n('VL_OPR'); icms += r.n('VL_ICMS'); ipi += r.n('VL_IPI')
            if ci['grupo'] in ('exportacao', 'exportacao_indireta'):
                exp += r.n('VL_OPR')
    return rec, icms, ipi, dev, exp

def base_cumulativa(e, c, A, base):
    comp = base['periodo']
    m210 = [r for r in c['regs'].get('M210', [])]; m610 = c['regs'].get('M610', [])
    if not m210:
        return
    rec_brt = sum(r.n('VL_REC_BRT') for r in m210); bc = sum(r.n('VL_BC_CONT_AJUS') or r.n('VL_BC_CONT') for r in m210)
    exclusao = rec_brt - bc
    f = e['fiscal'].get(comp)
    if not f:
        # sem SPED Fiscal do mês: só registra a exclusão praticada
        e.setdefault('tabela_base_cumulativa', []).append({'periodo': comp, 'receita_bruta': round(rec_brt, 2), 'base': round(bc, 2), 'exclusao': round(exclusao, 2), 'exclusao_pct': round(exclusao / rec_brt * 100, 2) if rec_brt else 0, 'icms_fiscal': None, 'ipi_fiscal': None})
        return
    rec_f, icms, ipi, dev, exp = _icms_ipi_receita_fiscal(f)
    esperado_min = icms  # o mínimo que deveria sair da base é o ICMS destacado (Tema 69)
    esperado_max = icms + ipi + dev + exp
    e.setdefault('tabela_base_cumulativa', []).append({'periodo': comp, 'receita_bruta': round(rec_brt, 2), 'base': round(bc, 2), 'exclusao': round(exclusao, 2), 'exclusao_pct': round(exclusao / rec_brt * 100, 2) if rec_brt else 0, 'icms_fiscal': round(icms, 2), 'ipi_fiscal': round(ipi, 2), 'devolucoes': round(dev, 2), 'exportacao': round(exp, 2)})
    aliq = 0.0365
    if exclusao < esperado_min * 0.9 and icms > 0:
        A.add(regra='R01', categoria='Pago a maior', tributo='PIS/COFINS', titulo='Base do PIS/COFINS cumulativo não exclui o ICMS destacado (Tema 69)',
              descricao='Receita bruta no M210/M610 %s, base de cálculo %s: exclusão de %s (%.1f%%). Só o ICMS destacado nas saídas do mês foi %s (SPED Fiscal); IPI %s; devoluções %s. A exclusão do ICMS vale também para o regime cumulativo.' % (brl(rec_brt), brl(bc), brl(exclusao), exclusao / rec_brt * 100 if rec_brt else 0, brl(icms), brl(ipi), brl(dev)),
              evidencia=[_ev('M210 VL_REC_BRT', brl(rec_brt), 'VL_BC_CONT', brl(bc)), _ev('SPED Fiscal Σ VL_ICMS saídas de receita', brl(icms)), _ev('Σ VL_IPI', brl(ipi)), _ev('devoluções (entradas 1201/2201)', brl(dev))],
              valor=(esperado_min - exclusao) * aliq, memoria='(ICMS %s − exclusão praticada %s) × 3,65%% = %s' % (brl(icms), brl(exclusao), brl((esperado_min - exclusao) * aliq)), grau='Alto', acao='Retificar EFD Contribuições e DCTF; PER/DCOMP dos últimos 5 anos', prioridade='Alta', **base)
    elif exclusao > esperado_max * 1.15 + 100:
        A.add(regra='R01', categoria='Risco', tributo='PIS/COFINS', titulo='Exclusões da base do PIS/COFINS acima do que ICMS + IPI + devoluções + exportação justificam',
              descricao='Exclusão praticada %s; ICMS %s + IPI %s + devoluções %s + exportação %s = %s. O excedente precisa de justificativa (vendas canceladas, descontos incondicionais, receitas fora da atividade).' % (brl(exclusao), brl(icms), brl(ipi), brl(dev), brl(exp), brl(esperado_max)),
              evidencia=[_ev('M210', brl(rec_brt), brl(bc))], valor=(exclusao - esperado_max) * aliq, memoria='(exclusão %s − justificado %s) × 3,65%%' % (brl(exclusao), brl(esperado_max)), grau='Médio', acao='Documentar as exclusões (M400/M410 e conta contábil)', prioridade='Média', **base)

def conciliacao_receita(e, c, A, base):
    comp = base['periodo']; f = e['fiscal'].get(comp)
    if not f:
        return
    m210 = c['regs'].get('M210', []); m610 = c['regs'].get('M610', [])
    rec_c = sum(r.n('VL_REC_BRT') for r in m210) or sum(r.n('VL_REC_BRT') for r in m610)
    if not rec_c:
        return
    rec_f, icms, ipi, dev, exp = _icms_ipi_receita_fiscal(f)
    fut = sum(r.n('VL_OPR') for r in f['regs'].get('C190', []) if r.get('CFOP') in CFOP_FAT_FUTURO)
    ent_fut = sum(r.n('VL_OPR') for r in f['regs'].get('C190', []) if r.get('CFOP') in CFOP_ENTREGA_FUTURA)
    # duas leituras: receita na remessa (x116) ou receita no faturamento (x922)
    v1 = rec_f; v2 = rec_f - ent_fut + fut
    melhor = min((abs(rec_c - v1), 'remessa (x116)', v1), (abs(rec_c - v2), 'faturamento (x922)', v2))
    e.setdefault('tabela_receita', []).append({'periodo': comp, 'receita_contrib': round(rec_c, 2), 'receita_fiscal_remessa': round(v1, 2), 'receita_fiscal_faturamento': round(v2, 2), 'entrega_futura_remessa': round(ent_fut, 2), 'simples_faturamento': round(fut, 2), 'criterio': melhor[1], 'diferenca': round(rec_c - melhor[2], 2)})
    if melhor[0] > max(rec_c, melhor[2]) * 0.02 + 100:
        A.add(regra='R02', categoria='Risco', tributo='PIS/COFINS', titulo='Receita bruta da EFD Contribuições não concilia com as saídas do SPED Fiscal',
              descricao='M210 receita bruta %s; SPED Fiscal: receita pelas remessas %s, pelo faturamento (entrega futura) %s. Diferença mínima %s (%.1f%%). Se a receita do PIS/COFINS é menor, há omissão; se maior, pagamento a maior ou receita fora do SPED Fiscal (serviços, financeiras).' % (brl(rec_c), brl(v1), brl(v2), brl(melhor[0]), melhor[0] / max(rec_c, 1) * 100),
              evidencia=[_ev('M210 Σ VL_REC_BRT', brl(rec_c)), _ev('SPED Fiscal Σ VL_OPR CFOPs de receita', brl(rec_f)), _ev('x922 simples faturamento', brl(fut)), _ev('x116 remessa entrega futura', brl(ent_fut))],
              valor=melhor[0] * (0.0365 if e['regime']['pis_cofins'] == 'cumulativo' else 0.0925), estimativa=True, memoria='diferença %s × alíquota do regime' % brl(melhor[0]), grau='Médio', acao='Conciliar receita contábil × fiscal × contribuições (razão da conta de receita)', prioridade='Alta', **base)

def retencoes(e, c, A, base):
    for reg, trib in (('M200', 'PIS'), ('M600', 'COFINS')):
        for r in c['regs'].get(reg, []):
            ret = r.n('VL_RET_NC') + r.n('VL_RET_CUM')
            a100 = sum(x.n('VL_PIS_RET' if trib == 'PIS' else 'VL_COFINS_RET') for x in c['regs'].get('A100', []) if x.get('IND_OPER') == '1')
            if a100 > ret + TOL:
                A.add(regra='R05', categoria='Recuperação', tributo=trib, titulo='%s retido na fonte nas NFS-e (A100) maior que o deduzido na apuração (%s)' % (trib, reg), descricao='Retido pelos tomadores %s; deduzido %s.' % (brl(a100), brl(ret)), valor=a100 - ret, grau='Alto', acao='Deduzir as retenções no %s e na DCTF; PER/DCOMP do excedente' % reg, prioridade='Alta', **base)

# ---------------------------------------------------------------- DIFAL por UF (X13)
def difal_por_uf(e, s, A, base):
    e310 = {r['pai'].get('UF'): r for r in s['regs'].get('E310', []) if r.get('pai')}
    vendas = defaultdict(float)
    for c in s['regs'].get('C100', []):
        if c.get('IND_OPER') != '1' or c.get('COD_SIT') not in ('00', '01'):
            continue
        uf = uf_participante(s['participantes'].get(c.get('COD_PART')))
        if not uf or uf in ('EX', e['uf']):
            continue
        for f in c['filhos']:
            if f['REG'] == 'C190' and f.get('CFOP') in ('6107', '6108') + tuple(CFOP_ENTREGA_FUTURA & {'6116', '6117'}) and f.get('CST_ICMS', '')[1:] in ('00', '10', '20', '70'):
                vendas[uf] += f.n('VL_BC_ICMS') or f.n('VL_OPR')
    if not vendas and not e310:
        return
    linhas = []; total_esp = total_dec = 0.0; faltando = []
    for uf in sorted(set(vendas) | set(e310)):
        basev = vendas.get(uf, 0.0)
        interna = ALIQ_INTERNA_UF.get(uf)
        esperado = basev * (interna - aliq_interestadual(e['uf'], uf)) / 100 if interna else 0.0
        r = e310.get(uf)
        declarado = r.n('VL_TOT_DEBITOS_DIFAL') if r else 0.0
        fcp = r.n('VL_TOT_DEB_FCP') if r else 0.0
        linhas.append({'uf': uf, 'base': round(basev, 2), 'aliq_interna_ref': interna, 'esperado': round(esperado, 2), 'declarado': round(declarado, 2), 'fcp': round(fcp, 2), 'recolhido': round(r.n('VL_RECOL_DIFAL'), 2) if r else 0})
        total_esp += esperado; total_dec += declarado
        if basev > 0 and declarado < esperado * 0.85 - 50:
            faltando.append(_ev(uf, 'base 6107/6108/6116', brl(basev), 'esperado', brl(esperado), 'declarado E310', brl(declarado)))
    e.setdefault('tabela_difal', []).append({'periodo': base['periodo'], 'ufs': linhas, 'esperado': round(total_esp, 2), 'declarado': round(total_dec, 2)})
    if faltando:
        A.add(regra='X13', categoria='Risco', tributo='DIFAL', titulo='DIFAL de vendas a não contribuinte abaixo do esperado em %d UF(s)' % len(faltando),
              descricao='Vendas 6107/6108/6116 a não contribuintes de outra UF: DIFAL esperado %s (alíquota interna de referência do destino menos interestadual, base única), declarado no E310 %s. Diferenças pequenas vêm de alíquotas específicas de produto e FCP; diferenças grandes indicam UF sem apuração ou base errada.' % (brl(total_esp), brl(total_dec)),
              evidencia=faltando, valor=max(total_esp - total_dec, 0), estimativa=True, memoria='Σ por UF: base × (interna − interestadual) − declarado', grau='Médio', acao='Conferir a apuração por UF (E300/E310) e as GNRE; corrigir alíquotas internas por produto', prioridade='Alta', **base)
    elif vendas and total_dec > total_esp * 1.15 + 100:
        A.add(regra='X13', categoria='Pago a maior', tributo='DIFAL', titulo='DIFAL declarado acima do esperado pelas vendas a não contribuinte',
              descricao='Esperado %s, declarado %s. Verificar se há DIFAL calculado com base dupla (indevida para não contribuinte) ou alíquota interna maior que a do produto.' % (brl(total_esp), brl(total_dec)),
              evidencia=[_ev(l['uf'], 'esperado', brl(l['esperado']), 'declarado', brl(l['declarado'])) for l in linhas if l['declarado'] > l['esperado'] * 1.15], valor=total_dec - total_esp, estimativa=True, grau='Médio', acao='Recalcular por UF; pedir restituição na UF de destino se confirmado', prioridade='Média', **base)

# ---------------------------------------------------------------- crédito efetivo das entradas (F26)
def credito_efetivo(e, s, A, base):
    por = defaultdict(lambda: {'opr': 0.0, 'bc': 0.0, 'icms': 0.0, 'qtd': 0})
    sem_credito = []; perdido = 0.0
    for c in s['regs'].get('C100', []):
        if c.get('IND_OPER') != '0' or c.get('COD_SIT') not in ('00', '01'):
            continue
        for f in c['filhos']:
            if f['REG'] != 'C190':
                continue
            ci = cfop_info(f.get('CFOP'))
            if ci['grupo'] not in ('industrializacao', 'revenda', 'industrializacao_st', 'revenda_st', 'industrializacao_terceiros', 'devolucao', 'ativo', 'frete', 'energia', 'uso_consumo'):
                continue
            k = (ci['grupo'], f.get('CFOP'), f.get('CST_ICMS'), f.get('ALIQ_ICMS'))
            g = por[k]; g['opr'] += f.n('VL_OPR'); g['bc'] += f.n('VL_BC_ICMS'); g['icms'] += f.n('VL_ICMS'); g['qtd'] += 1
            # tributada na origem (CST x00/x10/x20/x70), operação com direito a crédito, mas crédito zero
            if ci['grupo'] in ('industrializacao', 'revenda', 'industrializacao_st', 'revenda_st', 'devolucao') and f.get('CST_ICMS', '')[1:] in ('00', '10', '20', '70') and f.n('VL_ICMS') <= 0 and c.n('VL_ICMS') > 0:
                sem_credito.append(_ev('NF', c.get('NUM_DOC'), s['participantes'].get(c.get('COD_PART'), {}).get('NOME', '')[:28], 'CFOP', f.get('CFOP'), 'CST', f.get('CST_ICMS'), 'ICMS no cabeçalho', brl(c.n('VL_ICMS')), 'linha', f['linha']))
                perdido += c.n('VL_ICMS') * (f.n('VL_OPR') / max(c.n('VL_DOC'), 1))
    tab = [{'grupo': k[0], 'cfop': k[1], 'cst': k[2], 'aliq': k[3], 'valor': round(g['opr'], 2), 'base': round(g['bc'], 2), 'credito': round(g['icms'], 2), 'efetivo_pct': round(g['icms'] / g['opr'] * 100, 2) if g['opr'] else 0, 'docs': g['qtd']} for k, g in sorted(por.items(), key=lambda x: -x[1]['opr'])]
    e.setdefault('tabela_credito', []).append({'periodo': base['periodo'], 'linhas': tab})
    if sem_credito:
        A.add(regra='F26', categoria='Recuperação', tributo='ICMS', titulo='Entradas tributadas (CST 00/10/20/70) com direito a crédito escrituradas sem crédito: %d linha(s)' % len(sem_credito),
              descricao='O fornecedor destacou ICMS (cabeçalho C100) e a operação é de insumo/revenda/devolução, mas o C190 está com VL_ICMS zero.', evidencia=sem_credito[:20], valor=perdido, memoria='Σ ICMS do cabeçalho rateado pelas consolidações sem crédito = %s' % brl(perdido), grau='Alto', acao='Retificar o C190 com o crédito (ou justificar a vedação)', prioridade='Alta', **base)

# ---------------------------------------------------------------- industrialização por encomenda (F27)
def industrializacao_encomenda(e, s, A, base):
    rem = sum(r.n('VL_OPR') for r in s['regs'].get('C190', []) if r.get('CFOP') in ('5901', '6901'))
    ret = sum(r.n('VL_OPR') for r in s['regs'].get('C190', []) if r.get('CFOP') in ('1902', '2902'))
    serv = [r for r in s['regs'].get('C190', []) if r.get('CFOP') in ('1124', '2124', '1125', '2125')]
    if not serv and not rem:
        return
    vserv = sum(r.n('VL_OPR') for r in serv); icms_serv = sum(r.n('VL_ICMS') for r in serv); ipi_serv = sum(r.n('VL_IPI') for r in serv)
    csts = Counter(r.get('CST_ICMS') for r in serv)
    e.setdefault('tabela_encomenda', []).append({'periodo': base['periodo'], 'remessa_5901': round(rem, 2), 'retorno_1902': round(ret, 2), 'valor_cobrado_1124': round(vserv, 2), 'icms_credito': round(icms_serv, 2), 'ipi_credito': round(ipi_serv, 2), 'csts': dict(csts)})
    if vserv > 0 and icms_serv <= 0 and any(k[1:] in ('00', '10', '20') for k in csts):
        A.add(regra='F27', categoria='Recuperação', tributo='ICMS', titulo='Industrialização por encomenda (1124/1125) com ICMS destacado pelo industrializador e sem crédito', descricao='Valor cobrado %s; CSTs %s; crédito zero.' % (brl(vserv), dict(csts)), valor=0, grau='Médio', acao='Conferir as notas do industrializador (valor agregado tributado ou diferido) e o crédito', prioridade='Média', **base)
    # só informação sobre o regime (diferimento) quando tudo veio com CST 51/50
    if vserv > 0 and all(k[1:] in ('50', '51') for k in csts):
        A.add(regra='F27', categoria='Planejamento', tributo='ICMS', titulo='Industrialização por encomenda em terceiros: %s no mês com diferimento/suspensão' % brl(vserv),
              descricao='Remessas 5901 %s, retornos 1902 %s, valor cobrado pelo industrializador (1124/1125) %s com CST %s. O diferimento transfere o ICMS do valor agregado para a saída do produto final: conferir o prazo de retorno (180 dias, RIPI art. 43), o estorno quando o produto sai sem tributação e o tratamento de ISS × ICMS se o industrializador for optante do Simples.' % (brl(rem), brl(ret), brl(vserv), ', '.join(sorted(csts))),
              evidencia=[_ev('CFOP', r.get('CFOP'), 'CST', r.get('CST_ICMS'), brl(r.n('VL_OPR'))) for r in serv[:8]], valor=0, grau='Alto', acao='Controle de remessas em aberto (prazo) e conciliação 5901 × 1902 por item', prioridade='Baixa', **base)

# ---------------------------------------------------------------- retificadoras (P13)
def retificadoras(e, A):
    subs = e.get('substituidos', [])
    if not subs:
        return
    for antigo in subs:
        comp = antigo['periodo']['comp']; tipo = antigo['tipo']; novo = e[tipo].get(comp)
        if not novo or novo is antigo:
            continue
        base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        if tipo == 'contrib':
            def tot(s):
                return (sum(r.n('VL_TOT_CONT_REC') for r in s['regs'].get('M200', [])), sum(r.n('VL_TOT_CONT_REC') for r in s['regs'].get('M600', [])), sum(r.n('VL_REC_BRT') for r in s['regs'].get('M210', [])), len(s['regs'].get('C100', [])))
            a = tot(antigo); b = tot(novo)
            A.add(regra='P13', categoria='Integridade', tributo='PIS/COFINS', titulo='Competência %s tem original e retificadora: a retificadora foi usada' % comp,
                  descricao='PIS a recolher %s → %s; COFINS %s → %s; receita bruta %s → %s; documentos C100 %d → %d. Se a retificadora reduziu o valor, confirmar a DCTF retificadora e o pedido de restituição do que já foi pago.' % (brl(a[0]), brl(b[0]), brl(a[1]), brl(b[1]), brl(a[2]), brl(b[2]), a[3], b[3]),
                  evidencia=[_ev('original', antigo['arquivo']), _ev('retificadora', novo['arquivo'])], valor=abs((a[0] + a[1]) - (b[0] + b[1])), grau='Alto', acao='Conferir DCTF/DARF do período', prioridade='Baixa', **base)
        else:
            def tot(s):
                r = s['regs'].get('E110', [None])[0]
                return (r.n('VL_ICMS_RECOLHER') if r else 0, len(s['regs'].get('C100', [])))
            a = tot(antigo); b = tot(novo)
            A.add(regra='P13', categoria='Integridade', tributo='ICMS', titulo='Competência %s tem original e retificadora da EFD ICMS/IPI' % comp, descricao='ICMS a recolher %s → %s; documentos %d → %d.' % (brl(a[0]), brl(b[0]), a[1], b[1]), valor=abs(a[0] - b[0]), grau='Alto', acao='Conferir GIA/guia do período', prioridade='Baixa', **base)

# ---------------------------------------------------------------- simulação Lucro Real × Presumido (R03)
def simulacao_real_x_presumido(e, A):
    comps = sorted(e['fiscal'])
    if not comps:
        return
    rec = exp = ins = ind = energia = frete = ativo = dev = 0.0
    for comp in comps:
        s = e['fiscal'][comp]
        r, icms, ipi, d, x = _icms_ipi_receita_fiscal(s)
        rec += r - icms; exp += x; dev += d
        for f in s['regs'].get('C190', []):
            ci = cfop_info(f.get('CFOP'))
            if not ci['entrada']:
                continue
            liq = f.n('VL_OPR') - f.n('VL_ICMS')  # base do crédito sem ICMS (Lei 14.592/2023)
            if ci['grupo'] in ('industrializacao', 'industrializacao_st', 'revenda', 'revenda_st'):
                ins += liq
            elif ci['grupo'] == 'industrializacao_terceiros' and f.get('CFOP') in ('1124', '2124', '1125', '2125'):
                ind += liq
            elif ci['grupo'] == 'ativo':
                ativo += liq
            elif ci['grupo'] == 'frete':
                frete += liq
        for r5 in s['regs'].get('C500', []):
            energia += r5.n('VL_DOC')
        for d1 in s['regs'].get('D100', []):
            if d1.get('IND_OPER') == '0':
                frete += d1.n('VL_DOC') - d1.n('VL_ICMS')
    n = len(comps)
    if rec <= 0:
        return
    rec_trib = rec - exp
    cum = rec_trib * 0.0365
    creditos = (ins + ind + energia + frete + dev) * 0.0925 + ativo * 0.0925 / 48 * n  # ativo: 1/48 por mês (conservador; máquinas novas podem ser imediato)
    ncum = max(rec_trib * 0.0925 - creditos, 0)
    delta_pc = cum - ncum  # positivo = Lucro Real gastaria menos com PIS/COFINS
    # IRPJ/CSLL presumido (indústria/comércio 8%/12%; serviços 32%)
    ativ = e['perfil'].get('atividade')
    p_irpj, p_csll = (0.32, 0.32) if ativ == 'servico' else (0.08, 0.12)
    rec_bruta = rec  # presunção incide sobre a receita bruta sem ICMS? Não: a receita bruta da presunção inclui o ICMS (Lei 9.249 art. 15 c/c art. 12 do DL 1.598); usar receita com ICMS
    rec_com_icms = 0.0
    for comp in comps:
        rec_com_icms += _icms_ipi_receita_fiscal(e['fiscal'][comp])[0]
    base_irpj = rec_com_icms * p_irpj; base_csll = rec_com_icms * p_csll
    irpj_pres = base_irpj * 0.15 + max(base_irpj - 60000 * (n / 3), 0) * 0.10
    csll_pres = base_csll * 0.09
    pres_total = cum + irpj_pres + csll_pres
    # margem de equilíbrio: lucro real L tal que 0,34·L (com adicional aprox.) + ncum = pres_total
    margem_eq = ((pres_total - ncum) / 0.34) / rec_com_icms * 100 if rec_com_icms else 0
    margem_inf = e['perfil'].get('margem_liquida_estimada')
    texto_margem = ''
    real_total = None
    if margem_inf not in (None, ''):
        try:
            m = float(str(margem_inf).replace('%', '').replace(',', '.')) / 100
            lucro = rec_com_icms * m
            real_total = ncum + lucro * 0.15 + max(lucro - 20000 * n, 0) * 0.10 + lucro * 0.09
            texto_margem = ' Com a margem informada de %.1f%%, o Lucro Real custaria %s no período (Presumido: %s): %s.' % (m * 100, brl(real_total), brl(pres_total), 'Lucro Real mais barato em ' + brl(pres_total - real_total) if real_total < pres_total else 'Presumido mais barato em ' + brl(real_total - pres_total))
        except ValueError:
            pass
    e['simulacao_regime'] = {'meses': n, 'receita_sem_icms': round(rec, 2), 'receita_com_icms': round(rec_com_icms, 2), 'exportacao': round(exp, 2), 'pis_cofins_cumulativo': round(cum, 2), 'pis_cofins_nao_cumulativo': round(ncum, 2), 'creditos_potenciais': round(creditos, 2),
                             'bases_credito': {'insumos_revenda': round(ins, 2), 'industrializacao_terceiros': round(ind, 2), 'energia': round(energia, 2), 'frete': round(frete, 2), 'devolucoes': round(dev, 2), 'ativo': round(ativo, 2)},
                             'irpj_csll_presumido': round(irpj_pres + csll_pres, 2), 'presumido_total': round(pres_total, 2), 'margem_equilibrio_pct': round(margem_eq, 2), 'real_total_com_margem_informada': round(real_total, 2) if real_total is not None else None, 'presuncao': '%d%% / %d%%' % (p_irpj * 100, p_csll * 100)}
    A.add(regra='R03', categoria='Planejamento', tributo='PIS/COFINS + IRPJ/CSLL', titulo='Simulação Lucro Real × Lucro Presumido com os dados de %d mês(es): margem de equilíbrio %.1f%%' % (n, margem_eq),
          descricao='PIS/COFINS: cumulativo %s (3,65%% sobre %s) contra não cumulativo %s (9,25%% sobre a receita menos %s de créditos sobre insumos %s, industrialização em terceiros %s, energia %s, frete %s, devoluções %s e ativo %s). %s IRPJ/CSLL no Presumido (presunção %s): %s. O Lucro Real fica mais barato se a margem de lucro tributável for menor que %.1f%% da receita.%s' % (
              brl(cum), brl(rec_trib), brl(ncum), brl(creditos), brl(ins), brl(ind), brl(energia), brl(frete), brl(dev), brl(ativo), 'PIS/COFINS favorece o Lucro Real em %s.' % brl(delta_pc) if delta_pc > 0 else 'PIS/COFINS favorece o Presumido em %s.' % brl(-delta_pc), '%d%%/%d%%' % (p_irpj * 100, p_csll * 100), brl(irpj_pres + csll_pres), margem_eq, texto_margem),
          evidencia=[_ev('receita (CFOPs de receita) sem ICMS', brl(rec)), _ev('exportação', brl(exp)), _ev('créditos potenciais no não cumulativo', brl(creditos))], valor=max(delta_pc, 0) / n * 12, estimativa=True,
          memoria='anualizado: (%s − %s) ÷ %d × 12. Premissas: créditos só sobre o que está no SPED Fiscal (sem aluguéis, serviços PJ e depreciação contábil, que aumentariam o crédito); ativo a 1/48; adicional de IRPJ pelo limite trimestral.' % (brl(cum), brl(ncum), n), grau='Médio', acao='Levar a simulação para a contabilidade com a DRE real (margem) antes da opção anual', prioridade='Média', empresa=e['cnpj'], nome=e['nome'], periodo='%s a %s' % (comps[0], comps[-1]), uf=e['uf'])

def presuncao(e, A):
    comps = sorted(e['contrib'])
    serv = 0.0; enc = 0.0
    for comp in comps:
        c = e['contrib'][comp]
        serv += sum(r.n('VL_DOC') for r in c['regs'].get('A100', []) if r.get('IND_OPER') == '1')
    for comp in sorted(e['fiscal']):
        s = e['fiscal'][comp]
        enc += sum(r.n('VL_OPR') for r in s['regs'].get('C190', []) if r.get('CFOP') in ('5124', '5125', '6124', '6125'))
    base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comps[-1] if comps else sorted(e['fiscal'])[-1], uf=e['uf'])
    if serv > 0 and e['perfil'].get('atividade') != 'servico':
        A.add(regra='R04', categoria='Risco', tributo='IRPJ/CSLL', titulo='Receita de serviços (NFS-e no A100) de %s em empresa industrial/comercial: presunção de 32%%' % brl(serv), descricao='No Lucro Presumido a receita de serviços tem base de 32% (IRPJ e CSLL), enquanto a de venda tem 8%/12%. Conferir se a apuração trimestral segregou.', valor=serv * (0.32 - 0.08) * 0.15 + serv * (0.32 - 0.12) * 0.09, estimativa=True, memoria='receita de serviços × diferença de presunção × alíquotas', grau='Alto', acao='Segregar por atividade na apuração trimestral e na ECF', prioridade='Alta', **base)
    if enc > 0:
        A.add(regra='R04', categoria='Planejamento', tributo='IRPJ/CSLL', titulo='Industrialização por encomenda para terceiros (5124/5125) de %s: presunção de 8%%, não 32%%' % brl(enc), descricao='Receita de industrialização efetuada para terceiros é receita de venda de produção (8%/12%) e não de serviço (32%), desde que a operação seja industrialização (RIPI art. 4º) e não serviço da lista do ISS. Verificar o tratamento adotado na ECF.', valor=0, grau='Médio', acao='Confirmar na ECF a base usada para essa receita', prioridade='Média', **base)

def simples(e, A):
    comps = sorted(e['fiscal'])
    if comps:
        base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comps[-1], uf=e['uf'])
        A.add(regra='R06', categoria='Planejamento', tributo='Simples', titulo='Optante do Simples Nacional: a revisão de créditos de ICMS/IPI/PIS/COFINS não se aplica', descricao='Os pontos que valem: segregação de receitas com ST/monofásico no PGDAS-D, sublimite de ICMS, DIFAL/antecipação nas compras interestaduais, Fator R. Fornecer os PGDAS-D e o extrato do Simples para a revisão específica.', valor=0, grau='Alto', acao='Fornecer PGDAS-D', prioridade='Média', **base)
