# -*- coding: utf-8 -*-
"""Regras sobre a EFD ICMS/IPI (SPED Fiscal). Cada regra consulta o contexto (atividade, UF, tipo de operação) antes de apontar."""
from collections import defaultdict, Counter
from .conhecimento import (cfop_info, ALIQ_INTERNA_UF, aliq_interestadual, regime_ncm, SEGMENTOS_ST_CONV_142, tipo_ajuste_e111, CFOP_DESCR, CST_ICMS)
from .util import brl, data_sped

TOL = 1.00  # tolerância em R$ para fechamentos

def _ev(*partes):
    return ' | '.join(str(p) for p in partes if p not in (None, ''))

def rodar(e, A):
    """e = empresa do contexto; A = Achados."""
    comps = sorted(e['fiscal'])
    for i, comp in enumerate(comps):
        s = e['fiscal'][comp]
        base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        integridade(s, A, base)
        apuracao_icms(s, A, base)
        c100_x_c190(s, A, base)
        c170_x_c190(s, A, base)
        cancelados(s, A, base)
        energia(e, s, A, base)
        frete(e, s, A, base)
        ciap(e, s, A, base)
        ipi(e, s, A, base)
        st(e, s, A, base)
        bonificacao(e, s, A, base)
        difal_entradas(e, s, A, base)
        aliquotas_saidas(e, s, A, base)
        uso_consumo_com_credito(e, s, A, base)
        cadastro_itens(e, s, A, base)
        monofasicos_aviso(e, s, A, base)
        obrigacoes_blocos(e, s, A, base)
        extemporaneos(e, s, A, base)
        exportacao(e, s, A, base)
        if i > 0:
            continuidade(e['fiscal'][comps[i - 1]], s, A, base)
            cst_oscilando(e['fiscal'][comps[i - 1]], s, A, base)
    saldo_credor_acumulado(e, A)

# ---------------------------------------------------------------- integridade
def integridade(s, A, base):
    if s['divergencias_9900']:
        A.add(regra='F01', categoria='Integridade', tributo='SPED', titulo='Contagem do 9900 não bate com os registros do arquivo',
              descricao='%d registro(s) com quantidade declarada diferente da real. O PVA rejeita ou o arquivo foi editado depois de assinado.' % len(s['divergencias_9900']),
              evidencia=[_ev(d['registro'], 'declarado', d['declarado'], 'real', d['real']) for d in s['divergencias_9900'][:20]], grau='Alto', acao='Regerar o arquivo no sistema de origem e retransmitir', prioridade='Alta', **base)
    if s['qtd_9999'] is not None and s['qtd_9999'] != s['linhas']:
        A.add(regra='F01', categoria='Integridade', tributo='SPED', titulo='Total de linhas do 9999 diverge', descricao='9999 declara %s linhas, o arquivo tem %s.' % (s['qtd_9999'], s['linhas']),
              grau='Alto', acao='Regerar o arquivo', prioridade='Alta', **base)
    if s['problemas']:
        A.add(regra='F01', categoria='Integridade', tributo='SPED', titulo='Linhas fora do padrão no arquivo', descricao='%d linha(s) ignoradas na leitura.' % len(s['problemas']), evidencia=s['problemas'][:10], grau='Médio', acao='Conferir o arquivo', **base)
    if s['encoding'] != 'utf-8' and s['empresa'].get('cod_ver', '') >= '017':
        A.add(regra='F01', categoria='Integridade', tributo='SPED', titulo='Arquivo não está em UTF-8', descricao='Leiaute %s exige codificação UTF-8 (lido como %s). Caracteres acentuados podem ter sido corrompidos na transmissão.' % (s['empresa'].get('cod_ver'), s['encoding']),
              grau='Baixo', acao='Ajustar a exportação do ERP para UTF-8', prioridade='Baixa', **base)

# ---------------------------------------------------------------- apuração
def _somas_icms(s):
    deb = cred = deb_st = cred_st = 0.0
    por_grupo = defaultdict(lambda: {'opr': 0.0, 'bc': 0.0, 'icms': 0.0, 'st': 0.0, 'ipi': 0.0, 'qtd': 0})
    for reg in ('C190', 'C590', 'D190', 'D590'):
        for r in s['regs'].get(reg, []):
            pai = r.get('pai')
            if pai is None:
                continue
            if pai.get('COD_SIT') not in ('00', '01', '06', '07', '08'):
                continue
            ci = cfop_info(r.get('CFOP'))
            v = r.n('VL_ICMS'); vst = r.n('VL_ICMS_ST')
            if ci['entrada']:
                cred += v; cred_st += vst
            else:
                deb += v; deb_st += vst
            g = por_grupo[(ci['entrada'], r.get('CFOP'), r.get('CST_ICMS'), r.get('ALIQ_ICMS'))]
            g['opr'] += r.n('VL_OPR'); g['bc'] += r.n('VL_BC_ICMS'); g['icms'] += v; g['st'] += vst; g['ipi'] += r.n('VL_IPI'); g['qtd'] += 1
    return deb, cred, deb_st, cred_st, por_grupo

def apuracao_icms(s, A, base):
    e110 = s['regs'].get('E110')
    if not e110:
        A.add(regra='F03', categoria='Integridade', tributo='ICMS', titulo='Sem registro E110 (apuração do ICMS)', descricao='O arquivo não traz a apuração do ICMS próprio.', grau='Alto', acao='Verificar', prioridade='Alta', **base)
        return
    r = e110[0]
    deb = r.n('VL_TOT_DEBITOS') + r.n('VL_AJ_DEBITOS') + r.n('VL_TOT_AJ_DEBITOS') + r.n('VL_ESTORNOS_CRED')
    cred = r.n('VL_TOT_CREDITOS') + r.n('VL_AJ_CREDITOS') + r.n('VL_TOT_AJ_CREDITOS') + r.n('VL_ESTORNOS_DEB') + r.n('VL_SLD_CREDOR_ANT')
    saldo = deb - cred
    apurado_esperado = max(saldo, 0.0); transportar_esperado = max(-saldo, 0.0)
    if abs(r.n('VL_SLD_APURADO') - apurado_esperado) > TOL or abs(r.n('VL_SLD_CREDOR_TRANSPORTAR') - transportar_esperado) > TOL:
        A.add(regra='F03', categoria='Risco', tributo='ICMS', titulo='E110 não fecha aritmeticamente',
              descricao='Débitos totais %s menos créditos totais (com saldo anterior) %s = %s; o arquivo declara saldo apurado %s e saldo credor a transportar %s.' % (brl(deb), brl(cred), brl(saldo), brl(r.n('VL_SLD_APURADO')), brl(r.n('VL_SLD_CREDOR_TRANSPORTAR'))),
              evidencia=[_ev('E110 linha', r['linha'])], valor=abs(r.n('VL_SLD_APURADO') - apurado_esperado) + abs(r.n('VL_SLD_CREDOR_TRANSPORTAR') - transportar_esperado),
              memoria='(%s) − (%s) = %s' % (brl(deb), brl(cred), brl(saldo)), grau='Alto', acao='Retificar a EFD (E110)', prioridade='Alta', **base)
    recolher_esperado = r.n('VL_SLD_APURADO') - r.n('VL_TOT_DED')
    if abs(r.n('VL_ICMS_RECOLHER') - recolher_esperado) > TOL:
        A.add(regra='F03', categoria='Risco', tributo='ICMS', titulo='ICMS a recolher (E110) diverge de saldo apurado menos deduções', descricao='Declarado %s, esperado %s.' % (brl(r.n('VL_ICMS_RECOLHER')), brl(recolher_esperado)), evidencia=[_ev('E110 linha', r['linha'])], valor=abs(r.n('VL_ICMS_RECOLHER') - recolher_esperado), grau='Alto', acao='Retificar a EFD', prioridade='Alta', **base)
    # E110 x blocos C e D
    deb_docs, cred_docs, _, _, _ = _somas_icms(s)
    if abs(deb_docs - r.n('VL_TOT_DEBITOS')) > TOL:
        A.add(regra='F04', categoria='Risco', tributo='ICMS', titulo='Débitos do E110 não batem com a soma dos documentos de saída',
              descricao='Soma do VL_ICMS das saídas (C190/C590/D190/D590, documentos regulares) = %s; E110 VL_TOT_DEBITOS = %s.' % (brl(deb_docs), brl(r.n('VL_TOT_DEBITOS'))),
              valor=abs(deb_docs - r.n('VL_TOT_DEBITOS')), memoria='Σ saídas %s vs E110 %s' % (brl(deb_docs), brl(r.n('VL_TOT_DEBITOS'))), grau='Alto', acao='Identificar os documentos fora da apuração (ou ajustes lançados sem C197/E111)', prioridade='Alta', **base)
    if abs(cred_docs - r.n('VL_TOT_CREDITOS')) > TOL:
        A.add(regra='F04', categoria='Risco' if cred_docs < r.n('VL_TOT_CREDITOS') else 'Recuperação', tributo='ICMS', titulo='Créditos do E110 não batem com a soma dos documentos de entrada',
              descricao='Soma do VL_ICMS das entradas (C190/C590/D190/D590) = %s; E110 VL_TOT_CREDITOS = %s. %s' % (brl(cred_docs), brl(r.n('VL_TOT_CREDITOS')), 'Crédito apropriado acima do documental (risco de glosa).' if cred_docs < r.n('VL_TOT_CREDITOS') else 'Há crédito documental que não entrou na apuração.'),
              valor=abs(cred_docs - r.n('VL_TOT_CREDITOS')), memoria='Σ entradas %s vs E110 %s' % (brl(cred_docs), brl(r.n('VL_TOT_CREDITOS'))), grau='Alto', acao='Conferir documento a documento; retificar', prioridade='Alta', **base)
    # ajustes E111 sem lastro
    for aj in r['filhos']:
        if aj['REG'] == 'E111':
            tipo = tipo_ajuste_e111(aj.get('COD_AJ_APUR'))
            tem_lastro = any(f['REG'] in ('E112', 'E113') for f in aj['filhos'])
            if aj.n('VL_AJ_APUR') > 0 and not tem_lastro and tipo in ('crédito', 'crédito especial', 'estorno de débito', 'dedução'):
                A.add(regra='F04', categoria='Risco', tributo='ICMS', titulo='Ajuste de crédito no E111 sem documento vinculado (E113)',
                      descricao='%s (%s) de %s sem E112/E113. A fiscalização pede o lastro do ajuste.' % (aj.get('COD_AJ_APUR'), aj.get('DESCR_COMPL_AJ', ''), brl(aj.n('VL_AJ_APUR'))),
                      evidencia=[_ev('E111 linha', aj['linha'])], valor=aj.n('VL_AJ_APUR'), grau='Médio', acao='Anexar E113 ou documentar o ajuste', **base)

def continuidade(ant, atu, A, base):
    a = ant['regs'].get('E110'); b = atu['regs'].get('E110')
    if a and b and abs(a[0].n('VL_SLD_CREDOR_TRANSPORTAR') - b[0].n('VL_SLD_CREDOR_ANT')) > TOL:
        A.add(regra='F02', categoria='Risco', tributo='ICMS', titulo='Saldo credor transportado não confere com o mês anterior',
              descricao='%s transportou %s; %s abriu com %s.' % (ant['periodo']['comp'], brl(a[0].n('VL_SLD_CREDOR_TRANSPORTAR')), atu['periodo']['comp'], brl(b[0].n('VL_SLD_CREDOR_ANT'))),
              valor=abs(a[0].n('VL_SLD_CREDOR_TRANSPORTAR') - b[0].n('VL_SLD_CREDOR_ANT')), grau='Alto', acao='Retificar o E110 do mês que quebrou a sequência', prioridade='Alta', **base)
    a = ant['regs'].get('E520'); b = atu['regs'].get('E520')
    if a and b and ant['regs']['E500'][0].get('IND_APUR') == '0' and abs(a[0].n('VL_SC_IPI') - b[0].n('VL_SD_ANT_IPI')) > TOL:
        A.add(regra='F02', categoria='Risco', tributo='IPI', titulo='Saldo credor de IPI transportado não confere com o mês anterior',
              descricao='%s fechou com saldo credor %s; %s abriu com %s.' % (ant['periodo']['comp'], brl(a[0].n('VL_SC_IPI')), atu['periodo']['comp'], brl(b[0].n('VL_SD_ANT_IPI'))),
              valor=abs(a[0].n('VL_SC_IPI') - b[0].n('VL_SD_ANT_IPI')), grau='Alto', acao='Retificar o E520', prioridade='Alta', **base)
    sa = {r['pai'].get('UF'): r for r in ant['regs'].get('E210', []) if r.get('pai')}
    sb = {r['pai'].get('UF'): r for r in atu['regs'].get('E210', []) if r.get('pai')}
    for uf, ra in sa.items():
        rb = sb.get(uf)
        if rb and abs(ra.n('VL_SLD_CRED_ST_TRANSPORTAR') - rb.n('VL_SLD_CRED_ANT_ST')) > TOL:
            A.add(regra='F02', categoria='Risco', tributo='ICMS-ST', titulo='Saldo credor de ST (%s) não confere entre meses' % uf, descricao='Transportado %s, aberto %s.' % (brl(ra.n('VL_SLD_CRED_ST_TRANSPORTAR')), brl(rb.n('VL_SLD_CRED_ANT_ST'))), valor=abs(ra.n('VL_SLD_CRED_ST_TRANSPORTAR') - rb.n('VL_SLD_CRED_ANT_ST')), grau='Alto', acao='Retificar o E210', **base)

def saldo_credor_acumulado(e, A):
    comps = sorted(e['fiscal'])
    if not comps:
        return
    ult = e['fiscal'][comps[-1]]
    r = ult['regs'].get('E110')
    if not r:
        return
    r = r[0]
    saldo = r.n('VL_SLD_CREDOR_TRANSPORTAR')
    if saldo <= 0:
        return
    debitos_medios = sum(e['fiscal'][c]['regs']['E110'][0].n('VL_TOT_DEBITOS') for c in comps if e['fiscal'][c]['regs'].get('E110')) / len(comps)
    meses = saldo / debitos_medios if debitos_medios else 999
    if meses < 3:
        return
    pi = e['perfil_inferido']
    causas = []
    if pi.get('exporta'): causas.append('exportações (crédito mantido, LC 87/96 art. 21 §2º e art. 25 §1º: transferível)')
    if pi.get('compra_com_st'): causas.append('compras com ST cujo ICMS próprio é creditado e a saída posterior sofre nova retenção ou é interestadual (ressarcimento de ST)')
    g = pi.get('grupos', {})
    if g.get('S:venda_revenda', 0) + g.get('S:venda_producao', 0) > 0:
        causas.append('saídas interestaduais a 7%/12% com entradas internas a alíquota cheia (acúmulo estrutural)')
    A.add(regra='F08', categoria='Recuperação', tributo='ICMS', titulo='Saldo credor de ICMS acumulado sem destinação: %s' % brl(saldo),
          descricao='O saldo credor equivale a %.0f meses de débitos (média mensal de débitos %s). Sem exportação ou regime de transferência, esse valor é caixa parado. Causas prováveis pelos CFOPs: %s.' % (meses, brl(debitos_medios), '; '.join(causas) or 'a apurar'),
          evidencia=[_ev('E110', comps[-1], 'VL_SLD_CREDOR_TRANSPORTAR', brl(saldo))] + [_ev('E110', c, 'transportar', brl(e['fiscal'][c]['regs']['E110'][0].n('VL_SLD_CREDOR_TRANSPORTAR'))) for c in comps if e['fiscal'][c]['regs'].get('E110')],
          valor=saldo, memoria='saldo %s ÷ débitos médios %s = %.1f meses' % (brl(saldo), brl(debitos_medios), meses), grau='Médio', estimativa=False,
          acao='Mapear a origem do saldo (exportação, ST, alíquota) e pedir a apropriação/transferência pelo regime da UF %s (ex.: SISCRED no PR, e-CredAc em SP, transferência de saldo credor no RS); avaliar pedido de regime especial' % e['uf'],
          prioridade='Alta', empresa=e['cnpj'], nome=e['nome'], periodo=comps[-1], uf=e['uf'])

# ---------------------------------------------------------------- documentos
def c100_x_c190(s, A, base):
    n = 0; total = 0.0; exemplos = []
    for c in s['regs'].get('C100', []):
        if c.get('COD_SIT') not in ('00', '01', '06', '07', '08'):
            continue
        c190 = [f for f in c['filhos'] if f['REG'] == 'C190']
        if not c190:
            n += 1; exemplos.append(_ev('C100 sem C190', 'nº', c.get('NUM_DOC'), 'linha', c['linha']))
            continue
        for campo, filho in (('VL_ICMS', 'VL_ICMS'), ('VL_ICMS_ST', 'VL_ICMS_ST'), ('VL_IPI', 'VL_IPI')):
            soma = sum(f.n(filho) for f in c190)
            if abs(soma - c.n(campo)) > TOL:
                n += 1; total += abs(soma - c.n(campo))
                if len(exemplos) < 15:
                    exemplos.append(_ev('NF', c.get('NUM_DOC'), 'chave', c.get('CHV_NFE'), campo, brl(c.n(campo)), 'Σ C190', brl(soma), 'linha', c['linha']))
    if n:
        A.add(regra='F05', categoria='Risco', tributo='ICMS', titulo='Cabeçalho (C100) diverge da consolidação (C190) em %d documento(s)' % n,
              descricao='ICMS, ST ou IPI do cabeçalho não fecham com a soma dos C190. A apuração usa o C190; o cabeçalho é o que a fiscalização cruza com o XML.', evidencia=exemplos, valor=total, grau='Alto', acao='Corrigir a escrituração dos documentos listados', **base)

def c170_x_c190(s, A, base):
    n = 0; total = 0.0; exemplos = []
    for c in s['regs'].get('C100', []):
        itens = [f for f in c['filhos'] if f['REG'] == 'C170']
        if not itens:
            continue
        c190 = [f for f in c['filhos'] if f['REG'] == 'C190']
        agrup = defaultdict(float)
        for it in itens:
            agrup[(it.get('CST_ICMS'), it.get('CFOP'), it.n('ALIQ_ICMS'))] += it.n('VL_ICMS')
        cons = defaultdict(float)
        for f in c190:
            cons[(f.get('CST_ICMS'), f.get('CFOP'), f.n('ALIQ_ICMS'))] += f.n('VL_ICMS')
        for k in set(agrup) | set(cons):
            if abs(agrup.get(k, 0) - cons.get(k, 0)) > TOL:
                n += 1; total += abs(agrup.get(k, 0) - cons.get(k, 0))
                if len(exemplos) < 15:
                    exemplos.append(_ev('NF', c.get('NUM_DOC'), 'CST/CFOP/aliq', '/'.join(str(x) for x in k), 'Σ C170', brl(agrup.get(k, 0)), 'C190', brl(cons.get(k, 0)), 'linha', c['linha']))
    if n:
        A.add(regra='F06', categoria='Risco', tributo='ICMS', titulo='Itens (C170) não fecham com a consolidação (C190) em %d combinação(ões)' % n, descricao='Soma do ICMS dos itens por CST/CFOP/alíquota difere do C190.', evidencia=exemplos, valor=total, grau='Alto', acao='Corrigir a escrituração', **base)

def cancelados(s, A, base):
    lista = [c for c in s['regs'].get('C100', []) if c.get('COD_SIT') in ('02', '03', '04', '05') and (c.n('VL_ICMS') > 0 or c.n('VL_DOC') > 0)]
    if lista:
        A.add(regra='F07', categoria='Risco', tributo='ICMS', titulo='%d documento(s) cancelado/denegado/inutilizado escriturado com valor' % len(lista),
              descricao='Documento com COD_SIT 02/03/04/05 deve ir sem valores. Se entrou com ICMS, distorce a apuração.',
              evidencia=[_ev('NF', c.get('NUM_DOC'), 'sit', c.get('COD_SIT'), 'VL_DOC', brl(c.n('VL_DOC')), 'ICMS', brl(c.n('VL_ICMS')), 'linha', c['linha']) for c in lista[:15]],
              valor=sum(c.n('VL_ICMS') for c in lista), grau='Alto', acao='Retificar (zerar valores dos cancelados)', **base)

# ---------------------------------------------------------------- energia
def energia(e, s, A, base):
    c500 = [r for r in s['regs'].get('C500', []) if r.get('IND_OPER') == '0']
    ativ = e['perfil']['atividade']; uf = e['uf']
    if not c500:
        if ativ == 'industria' and s['regs'].get('C100'):
            A.add(regra='F09', categoria='Recuperação', tributo='ICMS', titulo='Indústria sem fatura de energia elétrica escriturada (C500)',
                  descricao='Estabelecimento industrial sem C500 no período. Ou a fatura não foi escriturada (crédito perdido) ou a unidade consumidora está em nome de outro CNPJ (verificar coligadas no mesmo endereço).',
                  grau='Médio', acao='Localizar a fatura (NF3e) e escriturar com crédito proporcional ao consumo industrial (laudo)', prioridade='Alta', **base)
        return
    for r in c500:
        vdoc = r.n('VL_DOC'); icms = r.n('VL_ICMS'); bc = r.n('VL_BC_ICMS')
        c590 = [f for f in r['filhos'] if f['REG'] == 'C590']
        cred = sum(f.n('VL_ICMS') for f in c590 if cfop_info(f.get('CFOP'))['entrada'])
        cfops = ','.join(sorted(set(f.get('CFOP') for f in c590)))
        aliq_ref = ALIQ_INTERNA_UF.get(uf, 18.0)
        icms_embutido = icms if icms > 0 else vdoc * aliq_ref / 100.0
        ev = [_ev('C500', 'nº', r.get('NUM_DOC'), 'VL_DOC', brl(vdoc), 'VL_ICMS', brl(icms), 'crédito C590', brl(cred), 'CFOP', cfops, 'linha', r['linha'])]
        if ativ == 'industria' and cred <= 0:
            A.add(regra='F09', categoria='Recuperação', tributo='ICMS', titulo='Energia elétrica sem crédito de ICMS em estabelecimento industrial',
                  descricao='Fatura de %s escriturada sem crédito (CFOP %s). A indústria tem direito ao crédito do ICMS da energia consumida no processo produtivo. A parcela industrial precisa de laudo técnico; sem laudo, estimativa de 80%%.' % (brl(vdoc), cfops),
                  evidencia=ev, valor=icms_embutido * 0.8, estimativa=True, memoria='ICMS na fatura %s (%s) × 80%% (parcela industrial estimada, confirmar por laudo) = %s' % (brl(icms_embutido), 'destacado' if icms > 0 else 'estimado a %.1f%% de %s' % (aliq_ref, brl(vdoc)), brl(icms_embutido * 0.8)),
                  grau='Alto', acao='Laudo de rateio + escriturar CFOP 1252 com crédito; recuperar os últimos 60 meses por crédito extemporâneo', prioridade='Alta', **base)
        elif ativ != 'industria' and cred > 0 and not e['perfil_inferido'].get('exporta'):
            A.add(regra='F09', categoria='Risco', tributo='ICMS', titulo='Comércio/serviço creditando ICMS de energia elétrica',
                  descricao='Crédito de %s em estabelecimento não industrial e sem exportação. A LC 87/96 só permite a partir de 2033 fora das hipóteses do art. 33, II.' % brl(cred),
                  evidencia=ev, valor=cred, grau='Alto', acao='Estornar o crédito (E111 de estorno) e retificar', prioridade='Alta', **base)
        elif ativ != 'industria' and cred <= 0 and e['perfil_inferido'].get('exporta'):
            prop = e['perfil_inferido']['valor_exportacao'] / max(e['perfil_inferido']['total_saidas'], 1)
            A.add(regra='F09', categoria='Recuperação', tributo='ICMS', titulo='Energia elétrica: crédito proporcional às exportações não tomado',
                  descricao='Estabelecimento exporta (%.1f%% das saídas) e não creditou a energia na proporção.' % (prop * 100), evidencia=ev, valor=icms_embutido * prop, estimativa=True,
                  memoria='ICMS da fatura %s × %.1f%% = %s' % (brl(icms_embutido), prop * 100, brl(icms_embutido * prop)), grau='Alto', acao='Escriturar CFOP 1252/1253 com crédito proporcional', **base)
        # PIS/COFINS: só no regime não cumulativo
        if e.get('regime', {}).get('pis_cofins') in ('cumulativo', 'simples'):
            continue
        A.add(regra='F09b', categoria='Recuperação', tributo='PIS/COFINS', titulo='Energia elétrica: conferir crédito integral de PIS/COFINS na EFD Contribuições',
              descricao='Fatura de %s. No regime não cumulativo o crédito de PIS/COFINS sobre energia é integral para qualquer atividade (9,25%%). Confirmar no C501/C505 da EFD Contribuições do mesmo período.' % brl(vdoc),
              evidencia=ev, valor=vdoc * 0.0925, estimativa=True, memoria='%s × 9,25%% = %s (só vale no não cumulativo; ver EFD Contribuições)' % (brl(vdoc), brl(vdoc * 0.0925)), grau='Alto', acao='Cruzar com C501/C505; se ausente, retificar a EFD Contribuições', prioridade='Média', **base)

# ---------------------------------------------------------------- frete
def frete(e, s, A, base):
    tomados = [r for r in s['regs'].get('D100', []) if r.get('IND_OPER') == '0' and r.get('COD_SIT') in ('00', '01', '06', '07', '08')]
    if not tomados:
        return
    sem_credito = []; total_sem = 0.0; total_bc_sem = 0.0; total_cred = 0.0; total_frete = 0.0; isentos = 0.0
    por_cst = Counter()
    for r in tomados:
        total_frete += r.n('VL_DOC')
        d190 = [f for f in r['filhos'] if f['REG'] == 'D190']
        cred = sum(f.n('VL_ICMS') for f in d190)
        total_cred += cred
        for f in d190:
            por_cst[(f.get('CST_ICMS'), f.get('CFOP'), f.get('ALIQ_ICMS'))] += f.n('VL_OPR')
            if f.get('CST_ICMS') in ('000', '020', '090') and f.n('VL_ICMS') <= 0 and f.n('VL_OPR') > 0 and r.n('VL_ICMS') > 0:
                # o CT-e destacou ICMS (D100) mas o D190 não creditou
                sem_credito.append(_ev('CT-e', r.get('NUM_DOC'), 'chave', r.get('CHV_CTE'), 'ICMS no CT-e', brl(r.n('VL_ICMS')), 'CST', f.get('CST_ICMS'), 'CFOP', f.get('CFOP'), 'linha', r['linha']))
                total_sem += r.n('VL_ICMS'); total_bc_sem += f.n('VL_OPR')
            if f.get('CST_ICMS') in ('040', '041', '060'):
                isentos += f.n('VL_OPR')
    e.setdefault('tabela_frete', []).append({'periodo': base['periodo'], 'ctes': len(tomados), 'valor_frete': round(total_frete, 2), 'credito_tomado': round(total_cred, 2), 'icms_destacado_sem_credito': round(total_sem, 2), 'isento_ou_st': round(isentos, 2),
                                             'por_cst': [{'cst': k[0], 'cfop': k[1], 'aliq': k[2], 'valor': round(v, 2)} for k, v in sorted(por_cst.items())]})
    if sem_credito:
        A.add(regra='F10', categoria='Recuperação', tributo='ICMS', titulo='CT-e tomado com ICMS destacado e sem crédito: %d documento(s)' % len(sem_credito),
              descricao='O transportador destacou ICMS, o D100 registra o valor, mas o D190 não creditou. Se a mercadoria transportada dá direito a crédito (compra de insumo/revenda, ou venda CIF), o crédito do frete é devido.',
              evidencia=sem_credito[:20], valor=total_sem, memoria='Σ VL_ICMS dos D100 sem crédito no D190 = %s' % brl(total_sem), grau='Alto', acao='Retificar o D190 com o crédito; conferir a vinculação de cada CT-e à operação', prioridade='Alta', **base)
    if e.get('regime', {}).get('pis_cofins') in ('cumulativo', 'simples'):
        return
    A.add(regra='F10b', categoria='Recuperação', tributo='PIS/COFINS', titulo='Frete tomado: conferir crédito de PIS/COFINS (D101/D105) na EFD Contribuições',
          descricao='%d CT-e(s) tomados, %s de frete no período. Frete na venda (ônus do vendedor) e frete na compra de bens com crédito geram crédito de 9,25%% no não cumulativo.' % (len(tomados), brl(total_frete)),
          valor=total_frete * 0.0925, estimativa=True, memoria='%s × 9,25%% = %s (teto; depende do regime e da natureza de cada frete)' % (brl(total_frete), brl(total_frete * 0.0925)), grau='Médio', acao='Cruzar com D101/D105', prioridade='Média', **base)

# ---------------------------------------------------------------- CIAP
def ciap(e, s, A, base):
    entradas_ativo = []
    for r in s['regs'].get('C190', []):
        ci = cfop_info(r.get('CFOP'))
        if ci['entrada'] and ci['grupo'] == 'ativo' and r.n('VL_OPR') > 0:
            entradas_ativo.append(r)
    g125 = s['regs'].get('G125', [])
    if entradas_ativo and not g125:
        icms = sum(r.n('VL_ICMS') for r in entradas_ativo)
        opr = sum(r.n('VL_OPR') for r in entradas_ativo)
        uf = e['uf']
        if icms <= 0:
            icms_est = sum(r.n('VL_OPR') * (aliq_interestadual('XX', uf) if cfop_info(r.get('CFOP'))['ambito'] == 'interestadual' else ALIQ_INTERNA_UF.get(uf, 18)) / 100 for r in entradas_ativo)
        else:
            icms_est = icms
        A.add(regra='F11', categoria='Recuperação', tributo='ICMS', titulo='Bens do ativo imobilizado comprados sem controle no CIAP (G125)',
              descricao='Entradas com CFOP de ativo somam %s (ICMS destacado %s) e o bloco G está vazio. O crédito é de 1/48 por mês, proporcional às saídas tributadas. Sem CIAP não há crédito, e ele só pode ser tomado dentro de 5 anos.' % (brl(opr), brl(icms)),
              evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'CST', r.get('CST_ICMS'), 'VL_OPR', brl(r.n('VL_OPR')), 'ICMS', brl(r.n('VL_ICMS')), 'linha', r['linha']) for r in entradas_ativo[:15]],
              valor=icms_est, estimativa=icms <= 0, memoria='ICMS dos bens %s ÷ 48 = %s/mês, por 48 meses (fator de saídas tributadas a aplicar)' % (brl(icms_est), brl(icms_est / 48)), grau='Alto', acao='Abrir o CIAP (G110/G125), lançar os bens e apropriar 1/48 com o código de ajuste da UF', prioridade='Alta', **base)
    # DIFAL de ativo também compõe o CIAP
    if g125:
        parcelas = sum(r.n('VL_PARC_PASS') for r in g125 if r.get('TIPO_MOV') in ('SI', 'IM', 'IA'))
        e.setdefault('tabela_ciap', []).append({'periodo': base['periodo'], 'bens': len(g125), 'parcela_mes': round(parcelas, 2)})

# ---------------------------------------------------------------- IPI
def ipi(e, s, A, base):
    e520 = s['regs'].get('E520'); e510 = s['regs'].get('E510', [])
    ativ = e['perfil']['atividade']; ind_ativ = e['info'].get('ind_ativ')
    equip = e['perfil'].get('equiparado_industrial_ipi')
    if e520:
        r = e520[0]
        saldo = r.n('VL_SD_ANT_IPI') + r.n('VL_CRED_IPI') + r.n('VL_OC_IPI') - r.n('VL_DEB_IPI') - r.n('VL_OD_IPI')
        sc = max(saldo, 0); sd = max(-saldo, 0)
        if abs(sc - r.n('VL_SC_IPI')) > TOL or abs(sd - r.n('VL_SD_IPI')) > TOL:
            A.add(regra='F12', categoria='Risco', tributo='IPI', titulo='E520 (apuração do IPI) não fecha', descricao='Esperado saldo credor %s / devedor %s; declarado %s / %s.' % (brl(sc), brl(sd), brl(r.n('VL_SC_IPI')), brl(r.n('VL_SD_IPI'))), valor=abs(sc - r.n('VL_SC_IPI')) + abs(sd - r.n('VL_SD_IPI')), grau='Alto', acao='Retificar', **base)
        if r.n('VL_SC_IPI') > 0:
            A.add(regra='F12c', categoria='Recuperação', tributo='IPI', titulo='Saldo credor de IPI de %s ao fim do período' % brl(r.n('VL_SC_IPI')), descricao='Saldo credor de IPI acumulado ao fim de trimestre pode ser pedido em ressarcimento ou usado em compensação (PER/DCOMP).', valor=r.n('VL_SC_IPI'), grau='Alto', acao='Se persistir no fechamento do trimestre, PER/DCOMP (Lei 9.779/99, art. 11)', prioridade='Média', **base)
    # créditos por CFOP/CST (E510)
    cred_tomado = defaultdict(float); ipi_destacado_sem_cred = defaultdict(float)
    for r in e510:
        ci = cfop_info(r.get('CFOP'))
        if ci['entrada'] and r.get('CST_IPI') in ('00', '05') and r.n('VL_IPI') > 0:
            cred_tomado[(r.get('CFOP'), ci['grupo'])] += r.n('VL_IPI')
    # IPI destacado nos C100 de entrada de insumo mas C190 sem VL_IPI (sem crédito)
    for c in s['regs'].get('C100', []):
        if c.get('IND_OPER') != '0' or c.n('VL_IPI') <= 0:
            continue
        c190 = [f for f in c['filhos'] if f['REG'] == 'C190']
        for f in c190:
            ci = cfop_info(f.get('CFOP'))
            if ci['grupo'] in ('industrializacao', 'industrializacao_st') and f.n('VL_IPI') <= 0:
                ipi_destacado_sem_cred[f.get('CFOP')] += c.n('VL_IPI') * (f.n('VL_OPR') / max(c.n('VL_DOC'), 1))
    if ipi_destacado_sem_cred and (ativ == 'industria' or ind_ativ == '0'):
        total = sum(ipi_destacado_sem_cred.values())
        A.add(regra='F12a', categoria='Recuperação', tributo='IPI', titulo='IPI destacado em compras de insumo sem crédito na escrituração',
              descricao='Notas de entrada para industrialização trazem IPI no cabeçalho (C100) mas o C190 não registra VL_IPI (sem crédito). Indústria e equiparado creditam o IPI de MP/PI/ME.',
              evidencia=[_ev('CFOP', k, CFOP_DESCR.get(k, ''), 'IPI sem crédito', brl(v)) for k, v in ipi_destacado_sem_cred.items()], valor=total, estimativa=True, memoria='Σ VL_IPI (C100) rateado pelos C190 de insumo sem VL_IPI = %s' % brl(total), grau='Alto', acao='Retificar C190/E510 com o crédito (CST 00)', prioridade='Alta', **base)
    if cred_tomado and ativ != 'industria' and ind_ativ == '0' and equip is None:
        total = sum(cred_tomado.values())
        A.add(regra='F12b', categoria='Risco', tributo='IPI', titulo='Estabelecimento comercial creditando IPI: confirmar a equiparação a industrial',
              descricao='O arquivo se declara industrial/equiparado (IND_ATIV=0) mas os CFOPs são de revenda. O crédito de IPI (%s) só é válido se houver equiparação (importador, interdependência com fabricante de produtos do Anexo III da Lei 7.798/89, opção do art. 11 do RIPI). Sem isso, crédito indevido e débito indevido nas saídas.' % brl(total),
              evidencia=[_ev('E510 CFOP', k[0], k[1], 'crédito', brl(v)) for k, v in cred_tomado.items()], valor=total, grau='Médio', acao='Documentar a equiparação (informar em perfil.json: equiparado_industrial_ipi=true) ou estornar', prioridade='Média', **base)
    if ativ == 'industria' and not e520 and s['regs'].get('C100'):
        A.add(regra='F12', categoria='Risco', tributo='IPI', titulo='Indústria sem apuração de IPI (E500/E520)', descricao='Estabelecimento industrial sem bloco E de IPI. Se os produtos são tributados na TIPI, a apuração é obrigatória.', grau='Médio', acao='Verificar TIPI dos produtos (0200) e a obrigatoriedade', **base)

# ---------------------------------------------------------------- ST
def st(e, s, A, base):
    e210 = s['regs'].get('E210', [])
    pi = e['perfil_inferido']
    # entradas com ST retido (CST 60/10 em CFOP x403/x401) e saídas interestaduais da mesma mercadoria => ressarcimento
    entradas_st = 0.0; st_retido_entrada = 0.0
    for c in s['regs'].get('C100', []):
        if c.get('IND_OPER') != '0':
            continue
        for f in c['filhos']:
            if f['REG'] == 'C190' and cfop_info(f.get('CFOP'))['grupo'] in ('revenda_st', 'industrializacao_st'):
                entradas_st += f.n('VL_OPR'); st_retido_entrada += f.n('VL_ICMS_ST')
        if c.n('VL_ICMS_ST') > 0 and any(f['REG'] == 'C190' and cfop_info(f.get('CFOP'))['grupo'] in ('revenda_st', 'industrializacao_st') for f in c['filhos']):
            pass
    saidas_inter_st = 0.0; saidas_int_st = 0.0; saidas_substituido = 0.0
    for r in s['regs'].get('C190', []):
        ci = cfop_info(r.get('CFOP'))
        if ci['entrada']:
            continue
        if r.get('CFOP') in ('6404', '6403') or (ci['grupo'] == 'venda_st_revenda' and ci['ambito'] == 'interestadual'):
            saidas_inter_st += r.n('VL_OPR')
        if r.get('CFOP') in ('5405',):
            saidas_substituido += r.n('VL_OPR')
        if ci['grupo'] in ('venda_st_revenda',) and ci['ambito'] == 'interna':
            saidas_int_st += r.n('VL_OPR')
    ressarc = sum(r.n('VL_RESSARC_ST') for r in e210)
    if entradas_st > 0 and saidas_inter_st > 0 and ressarc <= 0:
        prop = saidas_inter_st / max(saidas_inter_st + saidas_substituido + saidas_int_st, 1)
        # o ST retido na entrada raramente vem no C190 de entrada (CST 60 não traz); estimar pelo VL_ICMS_ST do C100 ou por MVA média
        st_c100 = sum(c.n('VL_ICMS_ST') for c in s['regs'].get('C100', []) if c.get('IND_OPER') == '0')
        base_est = st_c100 if st_c100 > 0 else entradas_st * 0.06
        A.add(regra='F13', categoria='Recuperação', tributo='ICMS-ST', titulo='Mercadoria comprada com ST revendida para outra UF sem ressarcimento do ST',
              descricao='Entradas com ST (CFOP x401/x403) de %s no mês e saídas interestaduais com nova retenção (6404/6403) de %s (%.0f%% das saídas de mercadoria com ST). O E210 não registra ressarcimento (VL_RESSARC_ST = 0). O substituído tem direito a recuperar o ST retido na entrada e o ICMS próprio do fornecedor na proporção das saídas interestaduais.' % (brl(entradas_st), brl(saidas_inter_st), prop * 100),
              evidencia=[_ev('E210 VL_RESSARC_ST', brl(ressarc)), _ev('Σ C190 entradas x401/x403', brl(entradas_st)), _ev('Σ C190 saídas 6403/6404', brl(saidas_inter_st)), _ev('Σ VL_ICMS_ST nos C100 de entrada', brl(st_c100))],
              valor=base_est * prop, estimativa=True, memoria='ST retido nas entradas %s (%s) × %.0f%% de saídas interestaduais = %s' % (brl(base_est), 'C100' if st_c100 > 0 else 'estimado a 6% das entradas, confirmar pelas notas', prop * 100, brl(base_est * prop)),
              grau='Alto', acao='Levantar item a item (nota de entrada × nota de saída) e pedir o ressarcimento pelo rito da UF %s; retroagir 5 anos' % e['uf'], prioridade='Alta', **base)
    # ST recolhida por UF x E250 obrigações: retenção sem GNRE lançada
    for r in e210:
        uf = r['pai'].get('UF') if r.get('pai') else '?'
        recol = r.n('VL_ICMS_RECOL_ST')
        obrig = sum(f.n('VL_OR') for f in r['filhos'] if f['REG'] == 'E250')
        if recol > TOL and abs(recol - obrig) > TOL:
            A.add(regra='F13b', categoria='Risco', tributo='ICMS-ST', titulo='ST a recolher para %s (%s) sem obrigação equivalente no E250' % (uf, brl(recol)), descricao='E250 soma %s.' % brl(obrig), valor=abs(recol - obrig), grau='Médio', acao='Conferir as GNRE e o E250', **base)
    if e210:
        e.setdefault('tabela_st', []).append({'periodo': base['periodo'], 'ufs': [{'uf': r['pai'].get('UF') if r.get('pai') else '', 'retencao': round(r.n('VL_RETENCAO_ST'), 2), 'ressarcimento': round(r.n('VL_RESSARC_ST'), 2), 'recolher': round(r.n('VL_ICMS_RECOL_ST'), 2), 'saldo_credor': round(r.n('VL_SLD_CRED_ST_TRANSPORTAR'), 2)} for r in e210]})

# ---------------------------------------------------------------- bonificação
def bonificacao(e, s, A, base):
    lista = [r for r in s['regs'].get('C190', []) if cfop_info(r.get('CFOP'))['grupo'] == 'bonificacao_brinde_amostra' and not cfop_info(r.get('CFOP'))['entrada'] and r.get('CST_ICMS', '')[1:] in ('40', '41') and r.n('VL_OPR') > 0]
    if not lista:
        return
    total = sum(r.n('VL_OPR') for r in lista)
    aliq_media = 0.0
    trib = [r for r in s['regs'].get('C190', []) if not cfop_info(r.get('CFOP'))['entrada'] and r.n('VL_ICMS') > 0 and r.n('VL_BC_ICMS') > 0]
    if trib:
        aliq_media = sum(r.n('VL_ICMS') for r in trib) / sum(r.n('VL_BC_ICMS') for r in trib) * 100
    A.add(regra='F16', categoria='Risco', tributo='ICMS', titulo='Bonificação/brinde/amostra saindo como não tributada (CST 40/41): %s' % brl(total),
          descricao='Saídas 5910/6910/5911/6911 com CST isenta/não tributada. Na regra geral a bonificação é tributada como venda (base = valor da mercadoria, sem o desconto); amostra grátis só é isenta nas condições do Convênio ICMS 29/1990. Verificar se o RICMS/%s prevê isenção ou se houve estorno do crédito da entrada.' % e['uf'],
          evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'CST', r.get('CST_ICMS'), 'VL_OPR', brl(r.n('VL_OPR')), 'linha', r['linha']) for r in lista[:15]],
          valor=total * aliq_media / 100, estimativa=True, memoria='%s × alíquota média das saídas tributadas %.1f%% = %s' % (brl(total), aliq_media, brl(total * aliq_media / 100)), grau='Médio', acao='Confirmar o tratamento no RICMS da UF; se tributado, retificar e recolher com denúncia espontânea', prioridade='Alta', **base)

# ---------------------------------------------------------------- DIFAL entradas
def difal_entradas(e, s, A, base):
    uf = e['uf']
    entradas = [r for r in s['regs'].get('C190', []) if cfop_info(r.get('CFOP'))['entrada'] and cfop_info(r.get('CFOP'))['ambito'] == 'interestadual' and cfop_info(r.get('CFOP'))['grupo'] in ('uso_consumo', 'ativo') and r.n('VL_OPR') > 0]
    if not entradas:
        return
    total = sum(r.n('VL_OPR') for r in entradas)
    ajustes = [a for a in s['regs'].get('E111', []) if tipo_ajuste_e111(a.get('COD_AJ_APUR')) in ('débito', 'débito especial') and ('DIF' in (a.get('DESCR_COMPL_AJ') or '').upper() or 'DIFAL' in (a.get('DESCR_COMPL_AJ') or '').upper() or 'DIFERENCIAL' in (a.get('DESCR_COMPL_AJ') or '').upper())]
    e310 = s['regs'].get('E310', [])
    difal_lancado = sum(a.n('VL_AJ_APUR') for a in ajustes) + sum(r.n('VL_TOT_DEBITOS_DIFAL') for r in e310)
    interna = ALIQ_INTERNA_UF.get(uf, 18.0)
    esperado = 0.0
    for r in entradas:
        aliq = r.n('ALIQ_ICMS') or 12.0
        esperado += r.n('VL_OPR') * max(interna - aliq, 0) / 100
    if difal_lancado < esperado * 0.5:
        A.add(regra='F17', categoria='Risco', tributo='DIFAL', titulo='Compras interestaduais de uso/consumo e ativo sem DIFAL proporcional',
              descricao='Entradas 2556/2551 somam %s. DIFAL esperado (alíquota interna %s%% menos interestadual, base simples) ≈ %s; lançado nos ajustes %s. Várias UFs exigem base dupla, o que aumenta o valor.' % (brl(total), interna, brl(esperado), brl(difal_lancado)),
              evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'aliq', r.get('ALIQ_ICMS'), 'VL_OPR', brl(r.n('VL_OPR')), 'linha', r['linha']) for r in entradas[:12]] + [_ev('E111', a.get('COD_AJ_APUR'), a.get('DESCR_COMPL_AJ'), brl(a.n('VL_AJ_APUR'))) for a in ajustes],
              valor=esperado - difal_lancado, estimativa=True, memoria='Σ VL_OPR × (%.1f%% − alíquota interestadual) = %s − lançado %s' % (interna, brl(esperado), brl(difal_lancado)), grau='Médio', acao='Recalcular o DIFAL pelas regras da UF (base simples × dupla) e lançar o ajuste E111', prioridade='Alta', **base)

# ---------------------------------------------------------------- alíquotas
def aliquotas_saidas(e, s, A, base):
    uf = e['uf']; interna = ALIQ_INTERNA_UF.get(uf)
    if not interna:
        return
    maior = []; menor = []
    for r in s['regs'].get('C190', []):
        ci = cfop_info(r.get('CFOP'))
        if ci['entrada'] or r.n('VL_ICMS') <= 0 or r.get('CST_ICMS', '')[1:] not in ('00', '10', '20', '70'):
            continue
        aliq = r.n('ALIQ_ICMS')
        if ci['ambito'] == 'interestadual' and aliq >= interna - 0.01 and aliq > 12:
            maior.append(r)
        if ci['ambito'] == 'interna' and aliq in (4.0, 7.0, 12.0) and interna > 12.0:
            menor.append(r)
    if maior:
        # pode ser venda a não contribuinte com DIFAL? Não: desde EC 87/2015 se usa a interestadual + DIFAL. Alíquota interna em 6xxx é erro (ou operação com consumidor final antes de 2016).
        vbc = sum(r.n('VL_BC_ICMS') for r in maior); vicms = sum(r.n('VL_ICMS') for r in maior)
        excesso = sum(r.n('VL_ICMS') - r.n('VL_BC_ICMS') * 12 / 100 for r in maior)
        A.add(regra='F18', categoria='Pago a maior', tributo='ICMS', titulo='Saídas interestaduais tributadas com alíquota interna (%s%%)' % interna,
              descricao='%d consolidação(ões) 6xxx com alíquota igual à interna. A operação interestadual usa 4%%, 7%% ou 12%% (e o DIFAL vai para o destino em venda a não contribuinte).' % len(maior),
              evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'CST', r.get('CST_ICMS'), 'aliq', r.get('ALIQ_ICMS'), 'BC', brl(r.n('VL_BC_ICMS')), 'ICMS', brl(r.n('VL_ICMS')), 'linha', r['linha']) for r in maior[:15]],
              valor=max(excesso, 0), estimativa=True, memoria='ICMS pago %s − BC %s × 12%% (pior caso) = %s' % (brl(vicms), brl(vbc), brl(excesso)), grau='Médio', acao='Conferir o XML (idDest/indIEDest); se erro, retificar e pedir restituição/crédito', prioridade='Alta', **base)
    if menor:
        vbc = sum(r.n('VL_BC_ICMS') for r in menor); vicms = sum(r.n('VL_ICMS') for r in menor)
        bc_interna = sum(r.n('VL_BC_ICMS') for r in s['regs'].get('C190', []) if not cfop_info(r.get('CFOP'))['entrada'] and cfop_info(r.get('CFOP'))['ambito'] == 'interna' and r.n('VL_ICMS') > 0)
        sistematico = vbc > bc_interna * 0.5
        A.add(regra='F18', categoria='Risco', tributo='ICMS', titulo='Saídas internas tributadas com alíquota interestadual' + (' (aplicação sistemática: provável alíquota específica do produto, confirmar)' if sistematico else ''),
              descricao='%d consolidação(ões) 5xxx com 4%%/7%%/12%% em UF cuja alíquota interna é %s%%. Salvo produto com alíquota reduzida no RICMS, há ICMS a menor.' % (len(menor), interna),
              evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'aliq', r.get('ALIQ_ICMS'), 'BC', brl(r.n('VL_BC_ICMS')), 'linha', r['linha']) for r in menor[:15]],
              valor=vbc * interna / 100 - vicms, estimativa=True, memoria='BC %s × %s%% − pago %s' % (brl(vbc), interna, brl(vicms)), grau='Baixo' if sistematico else 'Médio', acao='Confirmar alíquota do produto no RICMS/%s (lei estadual de alíquotas e reduções de base)' % uf, prioridade='Média' if sistematico else 'Alta', **base)

def uso_consumo_com_credito(e, s, A, base):
    lista = [r for r in s['regs'].get('C190', []) if cfop_info(r.get('CFOP'))['entrada'] and cfop_info(r.get('CFOP'))['grupo'] == 'uso_consumo' and r.n('VL_ICMS') > 0]
    if lista:
        total = sum(r.n('VL_ICMS') for r in lista)
        A.add(regra='F22', categoria='Risco', tributo='ICMS', titulo='Crédito de ICMS sobre material de uso e consumo (CFOP x556)',
              descricao='%s de crédito em entradas de uso/consumo. Vedado até 2033. Exceção: se o item é na verdade insumo/intermediário (então o CFOP está errado, não o crédito).' % brl(total),
              evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'CST', r.get('CST_ICMS'), 'ICMS', brl(r.n('VL_ICMS')), 'linha', r['linha']) for r in lista[:15]], valor=total, grau='Alto', acao='Reclassificar o item (se insumo) ou estornar o crédito', prioridade='Alta', **base)

# ---------------------------------------------------------------- cadastro 0200
def cadastro_itens(e, s, A, base):
    itens = s['regs'].get('0200', [])
    if not itens:
        return
    sem_ncm = [i for i in itens if i.get('TIPO_ITEM') in ('00', '01', '02', '03', '04', '05', '06', '10') and len((i.get('COD_NCM') or '').strip()) != 8]
    if sem_ncm:
        A.add(regra='F19', categoria='NCM', tributo='Cadastro', titulo='%d item(ns) de mercadoria sem NCM válida no 0200' % len(sem_ncm), descricao='NCM ausente ou fora do padrão de 8 dígitos.', evidencia=[_ev(i.get('COD_ITEM'), i.get('DESCR_ITEM'), 'NCM', repr(i.get('COD_NCM'))) for i in sem_ncm[:15]], grau='Alto', acao='Corrigir cadastro', **base)
    # CEST: produto movimentado com ST e sem CEST
    itens_st = set()
    for it in s['regs'].get('C170', []):
        if it.n('VL_ICMS_ST') > 0 or it.get('CST_ICMS', '')[1:] in ('10', '30', '60', '70'):
            itens_st.add(it.get('COD_ITEM'))
    sem_cest = [i for i in itens if i.get('COD_ITEM') in itens_st and not (i.get('CEST') or '').strip()]
    if sem_cest:
        A.add(regra='F19', categoria='NCM', tributo='ICMS-ST', titulo='%d item(ns) com operação de ST e sem CEST no cadastro' % len(sem_cest), descricao='O CEST é obrigatório nas operações com mercadorias sujeitas a ST (Convênio ICMS 142/2018).', evidencia=[_ev(i.get('COD_ITEM'), i.get('DESCR_ITEM'), 'NCM', i.get('COD_NCM')) for i in sem_cest[:15]], grau='Alto', acao='Preencher CEST no cadastro e no XML', **base)
    # tipo do item incoerente com a atividade
    ativ = e['perfil']['atividade']
    if ativ == 'industria':
        # itens comprados com CFOP de industrialização mas cadastrados como 'mercadoria para revenda' (00) ou 'uso e consumo' (07)
        errados = Counter()
        for it in s['regs'].get('C170', []):
            ci = cfop_info(it.get('CFOP'))
            i = s['itens'].get(it.get('COD_ITEM'))
            if i and ci['entrada'] and ci['grupo'] == 'industrializacao' and i.get('TIPO_ITEM') in ('00', '07'):
                errados[(it.get('COD_ITEM'), i.get('DESCR_ITEM'), i.get('TIPO_ITEM'))] += it.n('VL_ITEM')
        if errados:
            A.add(regra='F19', categoria='NCM', tributo='Cadastro', titulo='%d item(ns) comprados para industrialização mas cadastrados como revenda/uso-consumo' % len(errados),
                  descricao='TIPO_ITEM no 0200 contradiz o CFOP de entrada. Isso confunde o bloco K, o CIAP e a análise de insumos para PIS/COFINS.', evidencia=[_ev(k[0], k[1], 'TIPO_ITEM', k[2], brl(v)) for k, v in errados.most_common(15)], grau='Médio', acao='Ajustar TIPO_ITEM (01 MP, 02 embalagem, 03 intermediário)', **base)
    # tabela NCM para o dashboard
    tab = e.setdefault('tabela_ncm', {})
    for i in itens:
        ncm = (i.get('COD_NCM') or '').strip()
        chave = (i.get('COD_ITEM'), ncm)
        if chave in tab:
            continue
        reg = regime_ncm(ncm)
        seg_st = next((v for k, v in SEGMENTOS_ST_CONV_142.items() if ncm.startswith(k)), '')
        tab[chave] = {'cod': i.get('COD_ITEM'), 'descricao': i.get('DESCR_ITEM'), 'ncm': ncm, 'cest': i.get('CEST', ''), 'tipo': i.get('TIPO_ITEM'), 'aliq_icms_cad': i.get('ALIQ_ICMS', ''),
                      'regime_pis_cofins': reg['regime'] if reg else '', 'setor': reg['setor'] if reg else '', 'base_pis_cofins': reg['base'] if reg else '', 'segmento_st_conv142': seg_st}

# ---------------------------------------------------------------- monofásicos
def monofasicos_aviso(e, s, A, base):
    por_regime = defaultdict(lambda: {'valor': 0.0, 'itens': set(), 'setor': set()})
    # sem C170 nas saídas (NF própria), o valor por item não existe; usar o 0200 × H010? Não. Usar C170 quando houver e avisar.
    for it in s['regs'].get('C170', []):
        ci = cfop_info(it.get('CFOP'))
        i = s['itens'].get(it.get('COD_ITEM'))
        if not i:
            continue
        reg = regime_ncm(i.get('COD_NCM'))
        if reg:
            por_regime[(reg['regime'], ci['entrada'])]['valor'] += it.n('VL_ITEM'); por_regime[(reg['regime'], ci['entrada'])]['itens'].add(it.get('COD_ITEM')); por_regime[(reg['regime'], ci['entrada'])]['setor'].add(reg['setor'])
    ncm_cad = Counter()
    for i in s['regs'].get('0200', []):
        reg = regime_ncm(i.get('COD_NCM'))
        if reg:
            ncm_cad[(reg['regime'], reg['setor'])] += 1
    if ncm_cad and not e.get('_aviso_mono'):
        e['_aviso_mono'] = True
        ativ = e['perfil']['atividade']
        desc = []
        for (regime, setor), q in ncm_cad.items():
            desc.append('%d item(ns) do setor "%s" (%s)' % (q, setor, 'monofásico: fabricante paga alíquota concentrada, revenda a alíquota zero com CST 04' if regime == 'monofasico' else 'alíquota zero de PIS/COFINS'))
        A.add(regra='F20', categoria='Pago a maior', tributo='PIS/COFINS', titulo='Cadastro tem NCM de regime monofásico ou alíquota zero: conferir CST de PIS/COFINS nas saídas',
              descricao='; '.join(desc) + '. %s Se a EFD Contribuições estiver com CST 01 nessas saídas, há PIS/COFINS pago a maior (9,25%% no não cumulativo, 3,65%% no cumulativo) e, no Simples, falta de segregação no PGDAS-D.' % ('Como a empresa é COMÉRCIO, a revenda de monofásicos é a alíquota zero.' if ativ == 'comercio' else 'Como a empresa é INDÚSTRIA, ela é a contribuinte da alíquota concentrada; a revenda de itens de terceiros é a alíquota zero.'),
              evidencia=[_ev(regime, setor, '%d itens' % q) for (regime, setor), q in ncm_cad.items()], grau='Alto', acao='Cruzar com a EFD Contribuições (regra P05); se ausente, fornecer o arquivo', prioridade='Alta', **base)

# ---------------------------------------------------------------- blocos obrigatórios
def obrigacoes_blocos(e, s, A, base):
    ativ = e['perfil']['atividade']; perfil = e['info'].get('perfil')
    tem_k = any(r for r in ('K200', 'K230', 'K220', 'K250') if s['regs'].get(r))
    if ativ == 'industria' and not tem_k and s['regs'].get('C100') and not e.get('_aviso_k'):
        e['_aviso_k'] = True
        A.add(regra='F21', categoria='Risco', tributo='SPED', titulo='Indústria com bloco K vazio', descricao='Estabelecimento industrial sem K200/K230 (controle de produção e estoque). A obrigatoriedade é escalonada por porte e CNAE (Ajuste SINIEF 02/2009, art. 3º; verificar faixa de faturamento e a exigência da UF %s). Perfil %s.' % (e['uf'], perfil), grau='Médio', acao='Confirmar enquadramento; se obrigado, escriturar (K200 mensal no mínimo)', prioridade='Média', **base)
    r1010 = s['regs'].get('1010')
    if r1010 and r1010[0].get('IND_CART') == 'N':
        nfce = any(c.get('COD_MOD') in ('65', '59', '2') for c in s['regs'].get('C100', []) + s['regs'].get('C400', []))
        if nfce:
            A.add(regra='F21', categoria='Risco', tributo='SPED', titulo='Vendas ao consumidor sem registro 1601 (cartão/PIX)', descricao='Há NFC-e/ECF e o 1010 declara IND_CART = N. O 1601 é obrigatório quando há recebimentos por cartão ou PIX no período; o fisco cruza com as administradoras.', grau='Médio', acao='Escriturar 1601', **base)
    comp = base['periodo']
    if comp.endswith('-02') and not s['regs'].get('H010'):
        A.add(regra='F21', categoria='Risco', tributo='SPED', titulo='Inventário (H005/H010) não entregue na competência de fevereiro', descricao='O inventário de 31/12 deve ser informado até a EFD de fevereiro (regra geral; verificar a UF).', grau='Médio', acao='Entregar o bloco H', **base)

# ---------------------------------------------------------------- extemporâneos
def extemporaneos(e, s, A, base):
    ini = s['periodo']['ini']
    velhas = []
    for c in s['regs'].get('C100', []):
        if c.get('IND_OPER') == '0' and c.get('COD_SIT') in ('00', '01') and c.n('VL_ICMS') > 0:
            d = data_sped(c.get('DT_DOC'))
            if d and d < ini[:7] + '-01':
                # emitida antes do mês: crédito extemporâneo (normal se entrada no mês). Só alertar se > 60 dias
                if d < ini[:4] + '-' + ('%02d' % max(int(ini[5:7]) - 2, 1)) + '-01':
                    velhas.append(c)
    if velhas:
        A.add(regra='F24', categoria='Risco', tributo='ICMS', titulo='%d nota(s) de entrada com mais de 60 dias escrituradas com crédito' % len(velhas),
              descricao='Crédito extemporâneo é permitido dentro de 5 anos, mas a UF pode exigir lançamento por ajuste (E111) com identificação do documento, e não como C100 comum. Confirmar o rito do RICMS/%s.' % e['uf'],
              evidencia=[_ev('NF', c.get('NUM_DOC'), 'emitida', data_sped(c.get('DT_DOC')), 'entrada', data_sped(c.get('DT_E_S')), 'ICMS', brl(c.n('VL_ICMS'))) for c in velhas[:15]], valor=sum(c.n('VL_ICMS') for c in velhas), grau='Baixo', acao='Conferir o rito da UF para crédito extemporâneo', prioridade='Baixa', **base)

# ---------------------------------------------------------------- exportação
def exportacao(e, s, A, base):
    exp = [r for r in s['regs'].get('C190', []) if cfop_info(r.get('CFOP'))['grupo'] in ('exportacao', 'exportacao_indireta') and r.n('VL_OPR') > 0]
    if not exp:
        return
    total = sum(r.n('VL_OPR') for r in exp)
    e110 = s['regs'].get('E110')
    saldo = e110[0].n('VL_SLD_CREDOR_TRANSPORTAR') if e110 else 0
    A.add(regra='F25', categoria='Planejamento', tributo='ICMS', titulo='Exportações de %s no mês: crédito mantido e transferível' % brl(total),
          descricao='Exportação é imune com manutenção do crédito das entradas. O saldo credor gerado por exportação é transferível a terceiros por força da LC 87/96 (art. 25, §1º), sem depender de lei estadual. %s' % ('Saldo credor atual: %s.' % brl(saldo) if saldo > 0 else ''),
          evidencia=[_ev('C190', 'CFOP', r.get('CFOP'), 'VL_OPR', brl(r.n('VL_OPR'))) for r in exp[:10]], valor=0, grau='Alto', acao='Apurar o crédito acumulado de exportação (proporção exportação ÷ saídas) e habilitar a transferência na UF', prioridade='Média', **base)
    if e.get('regime', {}).get('pis_cofins') in ('cumulativo', 'simples'):
        return
    A.add(regra='F25b', categoria='Recuperação', tributo='PIS/COFINS', titulo='Exportação: crédito de PIS/COFINS vinculado (CST 52/54/56) ressarcível em dinheiro',
          descricao='Créditos vinculados a receita de exportação podem ser ressarcidos ou compensados com qualquer tributo federal (Lei 11.033/2004, art. 17; Lei 10.637 art. 5º §§1º e 2º; Lei 10.833 art. 6º). Conferir o 1100/1500 da EFD Contribuições.',
          valor=0, grau='Alto', acao='PER/DCOMP trimestral dos créditos de exportação', prioridade='Média', **base)

# ---------------------------------------------------------------- CST oscilando
def cst_oscilando(ant, atu, A, base):
    def mapa(s):
        m = defaultdict(lambda: defaultdict(float))
        for c in s['regs'].get('C100', []):
            if c.get('IND_OPER') != '0':
                continue
            p = s['participantes'].get(c.get('COD_PART'), {})
            part = p.get('CNPJ') or p.get('CPF') or c.get('COD_PART')
            for f in c['filhos']:
                if f['REG'] == 'C190':
                    m[(part, f.get('CFOP'))][f.get('CST_ICMS')] += f.n('VL_OPR')
        return m
    ma = mapa(ant); mb = mapa(atu)
    achados = []
    for k in set(ma) & set(mb):
        da = max(ma[k].items(), key=lambda x: x[1])[0]; db = max(mb[k].items(), key=lambda x: x[1])[0]
        if da[1:] != db[1:] and (da[1:] in ('00', '10', '20') or db[1:] in ('00', '10', '20')):
            nome = next((p.get('NOME') for p in atu['participantes'].values() if (p.get('CNPJ') or p.get('CPF')) == k[0]), k[0])
            achados.append((k, da, db, sum(mb[k].values()), nome))
    if achados:
        total = sum(a[3] for a in achados)
        A.add(regra='F14', categoria='Risco', tributo='ICMS', titulo='CST das entradas mudou entre %s e %s para o mesmo fornecedor/CFOP (%d caso(s))' % (ant['periodo']['comp'], atu['periodo']['comp'], len(achados)),
              descricao='O mesmo fornecedor, no mesmo CFOP, passou de um CST com crédito para um sem crédito (ou vice-versa). Ou o fornecedor mudou o tratamento, ou a escrituração de um dos meses está errada: se o XML destaca ICMS (CST 10/00) e a entrada foi com CST 60, o crédito ficou de fora.',
              evidencia=[_ev(a[4], 'CFOP', a[0][1], 'de', a[1], 'para', a[2], 'valor no mês', brl(a[3])) for a in achados[:15]], valor=0, memoria='Operações afetadas no mês: %s (o crédito depende do XML)' % brl(total), grau='Médio', acao='Conferir o XML das notas do fornecedor (cruzamento X03) e retificar o mês errado', prioridade='Alta', **base)
