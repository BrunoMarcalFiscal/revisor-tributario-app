# -*- coding: utf-8 -*-
"""Regras que alimentam a Recuperação de Créditos e o confronto SPED Fiscal × EFD Contribuições item a item.

X14  confronto item a item (mesma chave e mesmo NUM_ITEM nos dois arquivos): CFOP, valor do item, código do item,
     ICMS e IPI divergentes entre as escriturações; impacto na base do PIS/COFINS.
X15  entradas com direito a crédito de PIS/COFINS (insumo/revenda) escrituradas no SPED Fiscal e ausentes da
     EFD Contribuições: crédito não considerado na apuração (estimado pela base sem ICMS/IPI).
X16  saídas: ICMS informado na EFD Contribuições diferente do SPED Fiscal (afeta a exclusão do Tema 69 e a
     conferência da base).
T02  ICMS-ST pago nas compras para revenda (empresa substituída): base do PIS/COFINS sem o ICMS-ST (Tema 1.125 STJ),
     estimativa pelo ICMS-ST das entradas do mês.
Nenhuma regra supõe o que o arquivo não diz: sem os dois arquivos do mesmo mês, o confronto não roda e isso é informado."""
from collections import defaultdict
from . import conhecimento as K
from .regras_contrib import base_credito
from .util import brl

CRED_PIS = {'industrializacao', 'revenda', 'industrializacao_st', 'revenda_st', 'devolucao'}
SEM_CRED = {'70', '71', '72', '73', '74', '75', '98', '99'}
TOL = 0.05


def _chave(r):
    p = r.get('pai')
    return (p.get('CHV_NFE') or '') if p else ''


def _itens(s, sentido):
    """{(chave, NUM_ITEM): C170} das NF-e (modelo 55/65) do sentido pedido ('0' entrada, '1' saída)."""
    out = {}
    for c in s['regs'].get('C100', []):
        if c.get('IND_OPER') != sentido or c.get('COD_SIT') in ('02', '03', '04', '05') or not c.get('CHV_NFE'):
            continue
        for it in c.get('filhos', []):
            if it.get('REG') == 'C170':
                out[(c['CHV_NFE'], (it.get('NUM_ITEM') or '').lstrip('0'))] = it
    return out


def _docs(s, sentido):
    return {c['CHV_NFE']: c for c in s['regs'].get('C100', []) if c.get('IND_OPER') == sentido and c.get('CHV_NFE') and c.get('COD_SIT') not in ('02', '03', '04', '05')}


def rodar(e, A):
    reg = (e.get('regime') or {}).get('pis_cofins', '')
    for comp in sorted(set(e['fiscal']) & set(e['contrib'])):
        f, c = e['fiscal'][comp], e['contrib'][comp]
        base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        confronto_itens(f, c, A, base)
        entradas_fora_da_efd(f, c, A, base, reg, comp)
        icms_saidas(f, c, A, base)
    for comp in sorted(e['contrib']):
        c = e['contrib'][comp]
        bc = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        if reg in ('nao_cumulativo', 'misto'):
            devolucoes_sem_credito(c, A, bc, comp)
            f100_sem_credito(c, A, bc)
            importacao_sem_credito(c, A, bc)
        iss_na_base(c, A, bc, reg)
        retencoes_f600(c, A, bc)
    ipi_contribuinte = any(s_['regs'].get('E520') for s_ in e['fiscal'].values())
    for comp in sorted(e['fiscal']):
        bf = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        if ipi_contribuinte:
            ipi_devolucoes(e['fiscal'][comp], A, bf)
        if reg in ('nao_cumulativo', 'misto') and comp <= '2023-12':
            credito_presumido_icms_irpj(e['fiscal'][comp], A, bf)
    for comp in sorted(e['fiscal']):
        icms_st_base(e, e['fiscal'][comp], A, dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf']), reg)


def confronto_itens(f, c, A, base):
    div = []
    impacto = 0.0
    for sentido in ('0', '1'):
        fi, ci = _itens(f, sentido), _itens(c, sentido)
        for k, a in fi.items():
            b = ci.get(k)
            if not b:
                continue
            dif = []
            for campo, rot in (('CFOP', 'CFOP'), ('COD_ITEM', 'código do item')):
                if (a.get(campo) or '').strip() != (b.get(campo) or '').strip():
                    dif.append('%s %s × %s' % (rot, a.get(campo), b.get(campo)))
            for campo, rot in (('VL_ITEM', 'valor'), ('VL_ICMS', 'ICMS'), ('VL_IPI', 'IPI'), ('VL_DESC', 'desconto')):
                va, vb = a.n(campo), b.n(campo)
                if abs(va - vb) > TOL:
                    dif.append('%s %s × %s' % (rot, brl(va), brl(vb)))
                    if campo in ('VL_ITEM', 'VL_DESC'):
                        impacto += abs(va - vb) * 0.0925
            if dif:
                div.append('%s | chave %s item %s | %s | SPED Fiscal × EFD Contribuições: %s' % ('entrada' if sentido == '0' else 'saída', k[0], k[1], a.get('COD_ITEM'), '; '.join(dif)))
    # saídas próprias: o SPED Fiscal não tem C170 (só C190); confronta os totais da nota com a soma dos itens da EFD Contribuições
    fd, cd = _docs(f, '1'), _docs(c, '1')
    for chave, d in fd.items():
        b = cd.get(chave)
        if not b:
            continue
        itens_c = [x for x in b.get('filhos', []) if x.get('REG') == 'C170']
        if not itens_c or any(x.get('REG') == 'C170' for x in d.get('filhos', [])):
            continue
        dif = []
        merc_c = sum(x.n('VL_ITEM') for x in itens_c)
        if abs(d.n('VL_MERC') - merc_c) > TOL and d.n('VL_MERC'):
            dif.append('mercadorias %s × soma dos itens %s' % (brl(d.n('VL_MERC')), brl(merc_c)))
            impacto += abs(d.n('VL_MERC') - merc_c) * 0.0925
        for campo, rot in (('VL_ICMS', 'ICMS'), ('VL_IPI', 'IPI')):
            vc = sum(x.n(campo) for x in itens_c)
            if abs(d.n(campo) - vc) > TOL:
                dif.append('%s %s × %s' % (rot, brl(d.n(campo)), brl(vc)))
        cf_f = sorted({x.get('CFOP') for x in d.get('filhos', []) if x.get('REG') == 'C190'})
        cf_c = sorted({x.get('CFOP') for x in itens_c})
        if cf_f and cf_f != cf_c:
            dif.append('CFOP %s × %s' % ('/'.join(cf_f), '/'.join(cf_c)))
        if dif:
            div.append('saída | chave %s (NF-e %s) | totais SPED Fiscal × itens EFD Contribuições: %s' % (chave, d.get('NUM_DOC'), '; '.join(dif)))
    if div:
        A.add(regra='X14', grau='Médio', categoria='Risco', tributo='SPED', titulo='%d item(ns) divergente(s) entre SPED Fiscal e EFD Contribuições (mesma chave e item)' % len(div),
              descricao='O mesmo item da mesma NF-e foi escriturado com CFOP, código, valor, ICMS ou IPI diferentes nos dois arquivos. A RFB e a SEFAZ cruzam as duas escriturações; a divergência de valor afeta a base do PIS/COFINS.',
              valor=round(impacto, 2), estimativa=True, evidencia=div[:200],
              memoria='Impacto estimado: diferença de valor/desconto × 9,25%% (alíquota não cumulativa de referência) = %s.' % brl(impacto),
              acao='Retificar a escrituração que diverge do XML (conferir o XML de cada chave) e reavaliar a base do PIS/COFINS do mês.', prioridade='Média', **base)


def entradas_fora_da_efd(f, c, A, base, reg, comp):
    if reg not in ('nao_cumulativo', 'misto'):
        return
    na_efd = set(_docs(c, '0'))
    faltam, total_base = [], 0.0
    for chave, d in _docs(f, '0').items():
        if chave in na_efd:
            continue
        b = 0.0
        for it in d.get('filhos', []):
            if it.get('REG') != 'C170':
                continue
            if K.cfop_info(it.get('CFOP')).get('grupo') not in CRED_PIS:
                continue
            b += base_credito(it, comp)
        if b > 0:
            total_base += b
            part = f['participantes'].get(d.get('COD_PART'), {})
            faltam.append('NF-e %s | %s | %s | base de crédito %s' % (d.get('NUM_DOC'), chave, part.get('NOME', d.get('COD_PART', '')), brl(b)))
    if faltam:
        cred = total_base * 0.0925
        A.add(regra='X15', grau='Médio', categoria='Recuperação', tributo='PIS/COFINS', titulo='%d NF-e de entrada com direito a crédito no SPED Fiscal e fora da EFD Contribuições' % len(faltam),
              descricao='Entradas de insumo ou revenda escrituradas no SPED Fiscal não aparecem na EFD Contribuições do mesmo mês: o crédito de PIS/COFINS não foi considerado.',
              valor=round(cred, 2), estimativa=True, evidencia=faltam[:200],
              memoria='Base %s (valor do item − desconto%s) × 9,25%% = %s. Confirmar a natureza de insumo/revenda de cada item.' % (brl(total_base), ' − ICMS, desde 05/2023' if comp >= '2023-05' else '', brl(cred)),
              acao='Escriturar as notas na EFD Contribuições (retificadora do mês) com o CST de crédito correto.', prioridade='Alta', **base)


def icms_saidas(f, c, A, base):
    fd, cd = _docs(f, '1'), _docs(c, '1')
    div = []
    for chave, a in fd.items():
        b = cd.get(chave)
        if b and abs(a.n('VL_ICMS') - b.n('VL_ICMS')) > TOL:
            div.append('NF-e %s | %s | ICMS SPED Fiscal %s × EFD Contribuições %s' % (a.get('NUM_DOC'), chave, brl(a.n('VL_ICMS')), brl(b.n('VL_ICMS'))))
    if div:
        A.add(regra='X16', grau='Médio', categoria='Risco', tributo='PIS/COFINS', titulo='%d NF-e de saída com ICMS diferente entre SPED Fiscal e EFD Contribuições' % len(div),
              descricao='A exclusão do ICMS da base do PIS/COFINS (Tema 69) usa o ICMS destacado; se a EFD Contribuições informa outro valor, a base e a recuperação ficam distorcidas.',
              valor=0.0, evidencia=div[:200], acao='Conferir o ICMS destacado no XML e corrigir a escrituração divergente.', prioridade='Média', **base)


def icms_st_base(e, f, A, base, reg):
    """Empresa substituída: comprou com ST (CFOP x403/x401 com VL_ICMS_ST ou CST 10/60) e revende com CST 60."""
    st_ent, revende = 0.0, False
    for d in f['regs'].get('C100', []):
        if d.get('COD_SIT') in ('02', '03', '04', '05'):
            continue
        for it in d.get('filhos', []):
            if it.get('REG') != 'C170':
                continue
            g = K.cfop_info(it.get('CFOP')).get('grupo')
            if d.get('IND_OPER') == '0' and g in ('revenda_st', 'industrializacao_st'):
                st_ent += it.n('VL_ICMS_ST')
            if d.get('IND_OPER') == '1' and (it.get('CST_ICMS') or '')[-2:] == '60':
                revende = True
    if st_ent <= 0 or not revende:
        return
    aliq = 0.0925 if reg in ('nao_cumulativo', 'misto') else 0.0365
    v = st_ent * aliq
    A.add(regra='T02', grau='Médio', categoria='Pago a maior', tributo='PIS/COFINS', titulo='ICMS-ST das compras para revenda dentro da base do PIS/COFINS (Tema 1.125 STJ)',
          descricao='A empresa compra com ICMS-ST e revende (CST 60): o ICMS-ST embutido no preço de venda integrou a receita tributada pelo PIS/COFINS. O STJ (Tema 1.125) afastou essa inclusão para o substituído.',
          valor=round(v, 2), estimativa=True, evidencia=['ICMS-ST das entradas para revenda no mês: %s' % brl(st_ent)],
          memoria='ICMS-ST das entradas para revenda %s × %s%% = %s (proxy do ICMS-ST embutido nas vendas do mês; refinar com o custo das mercadorias vendidas).' % (brl(st_ent), str(round(aliq * 100, 2)).replace('.', ','), brl(v)),
          acao='Avaliar ação judicial; com decisão, recalcular por nota e habilitar o crédito.', prioridade='Média', **base)


def devolucoes_sem_credito(c, A, base, comp):
    """T21: devolução de venda (entrada x201/x202/x410/x411...) escriturada na EFD Contribuições sem crédito."""
    lin, total = [], 0.0
    for d in c['regs'].get('C100', []):
        if d.get('IND_OPER') != '0' or d.get('COD_SIT') in ('02', '03', '04', '05'):
            continue
        for it in d.get('filhos', []):
            if it.get('REG') != 'C170' or K.cfop_info(it.get('CFOP')).get('grupo') != 'devolucao':
                continue
            if (it.get('CST_PIS') or '') not in SEM_CRED:
                continue
            b = base_credito(it, comp)
            if b <= 0:
                continue
            total += b
            lin.append('NF-e %s | %s | item %s %s | CFOP %s | CST PIS %s | base %s' % (d.get('NUM_DOC'), d.get('CHV_NFE'), it.get('NUM_ITEM'), it.get('COD_ITEM'), it.get('CFOP'), it.get('CST_PIS'), brl(b)))
    if lin:
        v = total * 0.0925
        A.add(regra='T21', grau='Médio', categoria='Recuperação', tributo='PIS/COFINS', titulo='Devolução de venda escriturada sem crédito de PIS/COFINS (%d item(ns))' % len(lin),
              descricao='Entradas de devolução de venda com CST sem crédito na EFD Contribuições. No regime não cumulativo, a devolução de venda tributada dá crédito (Lei 10.833/2003, art. 3º, VIII).',
              valor=round(v, 2), estimativa=False, evidencia=lin[:200],
              memoria='Base %s (valor − desconto%s) × 9,25%% = %s.' % (brl(total), ' − ICMS, desde 05/2023' if comp >= '2023-05' else '', brl(v)),
              acao='Retificar a EFD Contribuições do mês com CST de crédito (natureza 12).', prioridade='Alta', **base)


def f100_sem_credito(c, A, base):
    """T27: F100 de aquisição (IND_OPER 0: aluguel de PJ, arrendamento, armazenagem, outros custos com direito a crédito) sem PIS apurado."""
    lin, tot = [], 0.0
    for r in c['regs'].get('F100', []):
        if r.get('IND_OPER') != '0' or r.n('VL_OPER') <= 0:
            continue
        if r.n('VL_PIS') > 0 or r.n('VL_COFINS') > 0:
            continue
        tot += r.n('VL_OPER')
        lin.append('F100 linha %s | %s | %s | CST %s | natureza %s | %s' % (r['linha'], r.get('DT_OPER'), (r.get('DESC_DOC_OPER') or r.get('COD_ITEM') or '')[:60], r.get('CST_PIS'), r.get('NAT_BC_CRED') or '-', brl(r.n('VL_OPER'))))
    if lin:
        v = tot * 0.0925
        A.add(regra='T27', grau='Médio', categoria='Recuperação', tributo='PIS/COFINS', titulo='%d operação(ões) de aquisição no F100 sem crédito de PIS/COFINS' % len(lin),
              descricao='Custos e despesas informados no F100 como operação com direito a crédito (IND_OPER 0), mas sem PIS/COFINS apurado: aluguel de prédio, máquina e equipamento pago a PJ, arrendamento mercantil, armazenagem e outros do art. 3º.',
              valor=round(v, 2), estimativa=True, evidencia=lin[:200], memoria='Valor das operações %s × 9,25%% = %s (confirmar a natureza de cada uma).' % (brl(tot), brl(v)),
              acao='Classificar a natureza (NAT_BC_CRED) e retificar o F100 com CST de crédito.', prioridade='Média', **base)


def importacao_sem_credito(c, A, base):
    """T28: entradas de importação (CFOP 3xxx) sem crédito na EFD Contribuições (Lei 10.865/2004, art. 15)."""
    lin, tot = [], 0.0
    for d in c['regs'].get('C100', []):
        if d.get('IND_OPER') != '0' or d.get('COD_SIT') in ('02', '03', '04', '05'):
            continue
        for it in d.get('filhos', []):
            if it.get('REG') != 'C170' or not (it.get('CFOP') or '').startswith('3'):
                continue
            if (it.get('CST_PIS') or '') not in SEM_CRED:
                continue
            g = K.cfop_info(it.get('CFOP')).get('grupo')
            if g in ('uso_consumo',):
                continue
            b = it.n('VL_ITEM') - it.n('VL_DESC') + it.n('VL_IPI')
            tot += b
            lin.append('NF-e %s | %s | item %s %s | CFOP %s | CST %s | %s' % (d.get('NUM_DOC'), d.get('CHV_NFE'), it.get('NUM_ITEM'), it.get('COD_ITEM'), it.get('CFOP'), it.get('CST_PIS'), brl(b)))
    if lin:
        v = tot * 0.1175
        A.add(regra='T28', grau='Alto', categoria='Recuperação', tributo='PIS/COFINS', titulo='Importação sem crédito do PIS/COFINS-Importação (%d item(ns))' % len(lin),
              descricao='Bens importados para revenda ou como insumo escriturados sem crédito. No não cumulativo, o PIS/COFINS-Importação pago dá direito a crédito (Lei 10.865/2004, art. 15).',
              valor=round(v, 2), estimativa=True, evidencia=lin[:200],
              memoria='Base %s × 11,75%% (2,1%% + 9,65%%, alíquotas gerais) = %s. O valor exato é o PIS/COFINS-Importação pago na DI/DUIMP (conferir alíquota do NCM).' % (brl(tot), brl(v)),
              acao='Escriturar o crédito com base na DI/DUIMP (C120/C170 com CST 50 a 56).', prioridade='Alta', **base)


def iss_na_base(c, A, base, reg):
    """T29: ISS dentro da base do PIS/COFINS nas NFS-e emitidas (Tema 118 STF, julgamento a confirmar)."""
    iss, n = 0.0, 0
    for r in c['regs'].get('A100', []):
        if r.get('IND_OPER') != '1' or r.get('COD_SIT') in ('02', '03', '04', '05'):
            continue
        if r.n('VL_ISS') > 0 and r.n('VL_BC_PIS') >= r.n('VL_DOC') - r.n('VL_DESC') - 0.05:
            iss += r.n('VL_ISS'); n += 1
    if n:
        aliq = 0.0925 if reg in ('nao_cumulativo', 'misto') else 0.0365
        v = iss * aliq
        A.add(regra='T29', grau='Médio', categoria='Pago a maior', tributo='PIS/COFINS', titulo='ISS dentro da base do PIS/COFINS em %d NFS-e emitida(s) (Tema 118 STF)' % n,
              descricao='A base de PIS/COFINS das NFS-e inclui o ISS. A exclusão do ISS (por analogia ao Tema 69) está no Tema 118 do STF; não é aplicada pela RFB: depende de ação judicial.',
              valor=round(v, 2), estimativa=True, evidencia=['ISS das NFS-e emitidas no mês: %s em %d nota(s)' % (brl(iss), n)],
              memoria='ISS %s × %s%% = %s.' % (brl(iss), str(round(aliq * 100, 2)).replace('.', ','), brl(v)), acao='Avaliar ação judicial (tese controvertida).', prioridade='Baixa', **base)


def retencoes_f600(c, A, base):
    """R06: PIS/COFINS retidos na fonte (F600) maiores que a dedução na apuração (M200/M600)."""
    f6 = c['regs'].get('F600', [])
    if not f6:
        return
    ret_p = sum(r.n('VL_RET_PIS') for r in f6); ret_c = sum(r.n('VL_RET_COFINS') for r in f6)
    ded_p = sum(r.n('VL_RET_NC') + r.n('VL_RET_CUM') for r in c['regs'].get('M200', []))
    ded_c = sum(r.n('VL_RET_NC') + r.n('VL_RET_CUM') for r in c['regs'].get('M600', []))
    sobra = max(ret_p - ded_p, 0) + max(ret_c - ded_c, 0)
    if sobra > TOL:
        A.add(regra='R06', grau='Alto', categoria='Recuperação', tributo='PIS/COFINS', titulo='Retenções de PIS/COFINS na fonte (F600) não deduzidas na apuração: %s' % brl(sobra),
              descricao='Retido (F600): PIS %s, COFINS %s; deduzido (M200/M600): PIS %s, COFINS %s. O retido e não deduzido pode ser deduzido nos meses seguintes ou pedido em PER/DCOMP.' % (brl(ret_p), brl(ret_c), brl(ded_p), brl(ded_c)),
              valor=round(sobra, 2), evidencia=['F600 linha %s | %s | CNPJ fonte %s | PIS %s | COFINS %s' % (r['linha'], r.get('DT_RET'), r.get('CNPJ'), brl(r.n('VL_RET_PIS')), brl(r.n('VL_RET_COFINS'))) for r in f6[:100]],
              memoria='(retido − deduzido) de PIS e de COFINS = %s.' % brl(sobra), acao='Deduzir no mês seguinte ou PER/DCOMP do saldo retido (5 anos).', prioridade='Alta', **base)


def ipi_devolucoes(f, A, base):
    """T31: devolução de venda (entrada) com IPI destacado e sem crédito de IPI (RIPI, art. 229)."""
    lin, tot = [], 0.0
    for d in f['regs'].get('C100', []):
        if d.get('IND_OPER') != '0' or d.get('COD_SIT') in ('02', '03', '04', '05'):
            continue
        for it in d.get('filhos', []):
            if it.get('REG') != 'C170' or K.cfop_info(it.get('CFOP')).get('grupo') != 'devolucao':
                continue
            if it.n('VL_IPI') > 0 and (it.get('CST_IPI') or '') != '00':
                tot += it.n('VL_IPI')
                lin.append('NF-e %s | %s | item %s | CFOP %s | CST IPI %s | IPI %s' % (d.get('NUM_DOC'), d.get('CHV_NFE'), it.get('NUM_ITEM'), it.get('CFOP'), it.get('CST_IPI'), brl(it.n('VL_IPI'))))
    if lin:
        A.add(regra='T31', grau='Alto', categoria='Recuperação', tributo='IPI', titulo='Devolução de venda com IPI destacado sem crédito de IPI (%d item(ns))' % len(lin),
              descricao='O IPI destacado na venda e devolvido pelo cliente pode ser creditado (RIPI, art. 229). A entrada da devolução foi escriturada sem o crédito.',
              valor=round(tot, 2), evidencia=lin[:200], memoria='Soma do IPI das devoluções sem crédito = %s.' % brl(tot),
              acao='Escriturar o crédito de IPI (CST 00) e rever o saldo do E520.', prioridade='Média', **base)


def credito_presumido_icms_irpj(f, A, base):
    """T32: crédito presumido de ICMS lançado no E111 (até 12/2023) fora da base do IRPJ/CSLL do Lucro Real."""
    tot, lin = 0.0, []
    for r in f['regs'].get('E111', []):
        if K.tipo_ajuste_e111(r.get('COD_AJ_APUR')) != 'crédito':
            continue
        if 'PRESUMID' not in (r.get('DESCR_COMPL_AJ') or '').upper():
            continue
        tot += r.n('VL_AJ_APUR'); lin.append('E111 %s | %s | %s' % (r.get('COD_AJ_APUR'), (r.get('DESCR_COMPL_AJ') or '')[:80], brl(r.n('VL_AJ_APUR'))))
    if tot > 0:
        v = tot * 0.34
        A.add(regra='T32', grau='Médio', categoria='Pago a maior', tributo='IRPJ/CSLL', titulo='Crédito presumido de ICMS de %s: verificar exclusão do IRPJ/CSLL' % brl(tot),
              descricao='O crédito presumido de ICMS não é receita tributável pelo IRPJ/CSLL (STJ, EREsp 1.517.492/PR) até 12/2023; a partir de 2024 vale a Lei 14.789/2023. Se foi tributado no Lucro Real, há IRPJ/CSLL a recuperar.',
              valor=round(v, 2), estimativa=True, evidencia=lin[:100], memoria='Crédito presumido %s × 34%% (IRPJ 25%% + CSLL 9%%, alíquota máxima) = %s. Confirmar na ECF se foi excluído no LALUR/LACS.' % (brl(tot), brl(v)),
              acao='Conferir a ECF; se tributado, retificar a ECF e pedir PER/DCOMP do saldo negativo/pagamento a maior.', prioridade='Média', **base)
