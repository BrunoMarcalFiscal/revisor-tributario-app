# -*- coding: utf-8 -*-
"""Integridade das obrigações mês a mês, regime por ano e confronto SPED Fiscal × EFD Contribuições.

Regime por ano: perfil informado para o ano > registro 0110 da EFD Contribuições daquele ano > perfil geral.
  COD_INC_TRIB 1 = não cumulativo (Lucro Real), 2 = cumulativo (Lucro Presumido), 3 = misto (Lucro Real).
  Ano sem EFD Contribuições não vira "Simples" por palpite: fica "não identificado" com o motivo.
Integridade: da abertura (perfil `data_abertura`; sem ela, o 1º arquivo enviado) até o último mês com prazo vencido,
  cada mês de cada obrigação exigida no regime do ano tem um estado (ok, retificadora, problema de estrutura,
  sem arquivo, não exigida). "Sem arquivo" quer dizer que o arquivo não veio para a revisão, não que não foi entregue.
Confronto: nota a nota pela chave (NF-e/NFC-e no C100, CT-e no D100), por estabelecimento (C010 da EFD × CNPJ do
  SPED Fiscal), com o campo e os dois valores de cada divergência. EFD escriturada de forma consolidada (sem C100)
  é confrontada pela receita do mês."""
import datetime, re
from collections import Counter, defaultdict
from .util import brl

TOL = 0.05
CANCELADAS = {'02', '03', '04', '05'}
NOME_COD = {'1': 'Lucro Real', '2': 'Lucro Presumido', '3': 'Lucro Real'}
PC_COD = {'1': 'nao_cumulativo', '2': 'cumulativo', '3': 'misto'}
PC_REGIME = {'Lucro Real': 'nao_cumulativo', 'Lucro Presumido': 'cumulativo', 'Simples Nacional': 'simples'}
MAX_DET = 400


def _soma_mes(m, n):
    a, b = int(m[:4]), int(m[5:7]) + n
    a += (b - 1) // 12
    b = (b - 1) % 12 + 1
    return '%04d-%02d' % (a, b)


def _meses(ini, fim):
    out, m = [], ini
    while m <= fim:
        out.append(m)
        m = _soma_mes(m, 1)
    return out


def _abertura(e):
    d = str((e.get('perfil') or {}).get('data_abertura') or '').strip()
    m = re.match(r'^(\d{4})-(\d{2})', d) or re.match(r'^\d{2}/(\d{2})/(\d{4})', d)
    if not m:
        return None
    return '%s-%s' % ((m.group(1), m.group(2)) if '-' in d[:5] else (m.group(2), m.group(1)))


def _irmas(e, ctx):
    """Empresas do mesmo CNPJ raiz (matriz e filiais): a EFD Contribuições é entregue pela matriz para todas."""
    raiz = e['cnpj'][:8]
    return [x for c, x in ctx['empresas'].items() if c[:8] == raiz]


# ── regime por ano ──────────────────────────────────────────────────────────

def regime_por_ano(e, ctx):
    perfil = e.get('perfil') or {}
    por_ano_inf = {str(k): v for k, v in (perfil.get('regimes_por_ano') or {}).items() if v}
    geral = perfil.get('regime_tributario') or ''
    codigos = defaultdict(Counter)
    for x in _irmas(e, ctx):
        for comp, s in x['contrib'].items():
            cod = str(s['empresa'].get('cod_inc_trib') or '')
            if cod:
                codigos[comp[:4]][cod] += 1
    anos_arquivos = {c[:4] for x in _irmas(e, ctx) for c in list(x['fiscal']) + list(x['contrib'])}
    ab = _abertura(e)
    candidatos = ([ab[:4]] if ab else []) + sorted(anos_arquivos)[:1]
    if not candidatos:
        return {}
    ini = min(candidatos)
    fim = max(sorted(anos_arquivos)[-1:] + [ultimo_mes_exigivel()[:4]])
    out = {}
    for ano in [str(a) for a in range(int(ini), int(fim) + 1)]:
        c = codigos.get(ano, Counter())
        alertas = []
        detectado = ''
        if c:
            cod = c.most_common(1)[0][0]
            detectado = NOME_COD.get(cod, '')
            if len(c) > 1:
                alertas.append('Regime de PIS/COFINS muda dentro do ano (%s). A opção é irretratável no ano-calendário: conferir as EFD do ano.'
                               % ', '.join('%s em %d mês(es)' % ({'1': 'não cumulativo', '2': 'cumulativo', '3': 'misto'}.get(k, k), n) for k, n in c.items()))
        if ano in por_ano_inf:
            reg, fonte = por_ano_inf[ano], 'informado no perfil para %s' % ano
            if detectado and detectado != reg:
                alertas.append('Informado %s, mas a EFD Contribuições de %s está escriturada como %s.' % (reg, ano, detectado))
        elif detectado:
            reg, fonte = detectado, 'registro 0110 da EFD Contribuições'
            if geral and geral != detectado:
                alertas.append('O perfil geral diz %s, mas a EFD Contribuições de %s está como %s. Para as teses vale o da EFD; corrija o perfil se a EFD estiver errada.' % (geral, ano, detectado))
        elif ano in anos_arquivos and geral:
            reg, fonte = geral, 'perfil geral (sem EFD Contribuições no ano)'
        else:
            reg = 'Não identificado'
            fonte = ('sem EFD Contribuições no ano: pode ser Simples Nacional ou arquivo não enviado' if ano in anos_arquivos
                     else 'nenhum arquivo do ano foi enviado')
        cod_dom = c.most_common(1)[0][0] if c else ''
        pc = PC_COD.get(cod_dom, '') if fonte.startswith('registro') else PC_REGIME.get(reg, '')
        out[ano] = {'ano': ano, 'regime': reg, 'pis_cofins': pc, 'fonte': fonte, 'meses_efd': sum(c.values()), 'alertas': alertas,
                    'lucro_real': reg == 'Lucro Real'}
    return out


def regime_do_periodo(e, periodo):
    ra = (e.get('regime_anos') or {}).get(str(periodo or '')[:4])
    return ra if ra and ra['regime'] != 'Não identificado' else None


# ── integridade mês a mês ───────────────────────────────────────────────────

def ultimo_mes_exigivel(hoje=None):
    """EFD Contribuições vence no 10º dia útil do 2º mês seguinte; SPED Fiscal, em regra, até o dia 25 do mês seguinte
    (varia por UF). Para não acusar falta de arquivo ainda no prazo, a régua é o mês retrasado."""
    hoje = hoje or datetime.date.today()
    return _soma_mes(hoje.strftime('%Y-%m'), -2)


def _estado_arquivo(s):
    probl = []
    if s.get('divergencias_9900'):
        probl.append('9900 não fecha com o arquivo (%d registro(s))' % len(s['divergencias_9900']))
    if s.get('qtd_9999') != s.get('linhas'):
        probl.append('9999 declara %s linhas; o arquivo tem %s' % (s.get('qtd_9999'), s.get('linhas')))
    probl += [p for p in (s.get('problemas') or []) if p]
    if probl:
        return 'estrutura', probl
    return ('retificadora' if s.get('retificadora') else 'ok'), []


def integridade(e, ctx, hoje=None):
    ra = e.get('regime_anos') or {}
    meses_arq = sorted(set(e['fiscal']) | set(e['contrib']))
    ab = _abertura(e)
    ini = ab or (meses_arq[0] if meses_arq else None)
    if not ini:
        return None
    fim = max(ultimo_mes_exigivel(hoje), meses_arq[-1] if meses_arq else ini)
    matriz = e['cnpj'][8:12] == '0001'
    tem_ie = bool((e.get('info') or {}).get('ie')) or bool(e['fiscal'])
    linhas = []
    cont = Counter()
    for m in _meses(ini, fim):
        reg = (ra.get(m[:4]) or {}).get('regime', 'Não identificado')
        simples = reg == 'Simples Nacional'
        dentro_prazo = m > ultimo_mes_exigivel(hoje)
        cel = {'mes': m, 'regime': reg}
        for chave, arquivos, exigida in (('fiscal', e['fiscal'], tem_ie and not simples), ('contrib', e['contrib'], matriz and not simples)):
            s = arquivos.get(m)
            if s:
                est, probl = _estado_arquivo(s)
                cel[chave] = {'estado': est, 'problemas': probl, 'arquivo': s.get('arquivo'), 'retificadora': bool(s.get('retificadora')),
                              'versoes': 1 + sum(1 for x in e.get('substituidos', []) if x.get('tipo') == chave and x['periodo']['comp'] == m)}
            elif not exigida:
                motivo = 'Simples Nacional' if simples else ('EFD Contribuições é entregue pela matriz' if chave == 'contrib' and not matriz else 'sem inscrição estadual nos arquivos')
                cel[chave] = {'estado': 'nao_exigida', 'problemas': [motivo]}
            elif dentro_prazo:
                cel[chave] = {'estado': 'no_prazo', 'problemas': ['ainda dentro do prazo de entrega']}
            else:
                cel[chave] = {'estado': 'sem_arquivo', 'problemas': ['arquivo do mês não foi enviado para a revisão']}
            cont[(chave, cel[chave]['estado'])] += 1
        linhas.append(cel)
    resumo = {}
    for chave in ('fiscal', 'contrib'):
        r = {k: cont[(chave, k)] for k in ('ok', 'retificadora', 'estrutura', 'sem_arquivo', 'nao_exigida', 'no_prazo')}
        r['exigidos'] = sum(v for k, v in r.items() if k not in ('nao_exigida', 'no_prazo'))
        r['integros'] = r['ok'] + r['retificadora']
        resumo[chave] = r
    return {'inicio': ini, 'fim': fim, 'abertura': ab, 'abertura_informada': bool(ab), 'meses': linhas, 'resumo': resumo,
            'integra': all(resumo[k]['sem_arquivo'] == 0 and resumo[k]['estrutura'] == 0 for k in resumo)}


# ── confronto SPED Fiscal × EFD Contribuições ───────────────────────────────

def _estabelecimentos(s, bloco):
    """[(linha, cnpj)] dos C010/D010 da EFD Contribuições: o documento pertence ao último estabelecimento aberto antes dele."""
    import bisect
    lst = sorted((r['linha'], re.sub(r'\D', '', r.get('CNPJ') or ((r.get('campos') or [''])[0])))
                 for r in s['regs'].get(bloco, []))
    linhas = [x[0] for x in lst]
    return lambda ln: lst[bisect.bisect_right(linhas, ln) - 1][1] if lst and bisect.bisect_right(linhas, ln) else ''


def _docs(s, reg, campo_chave, cnpj=None):
    out = {}
    estab = _estabelecimentos(s, reg[0] + '010') if cnpj else None
    for d in s['regs'].get(reg, []):
        ch = (d.get(campo_chave) or '').strip()
        if not ch:
            continue
        if estab and estab(d['linha']) not in ('', cnpj):
            continue
        out[ch] = d
    return out


def _itens(d):
    return [x for x in d.get('filhos', []) if x.get('REG') == 'C170']


def _brl(v):
    return brl(v)


def _comparar_doc(df, dc, tipo):
    """Diferenças campo a campo entre o mesmo documento nos dois arquivos."""
    dif = []
    campos = [('IND_OPER', 'sentido'), ('COD_SIT', 'situação'), ('DT_DOC', 'data de emissão'), ('NUM_DOC', 'número')]
    for k, rot in campos:
        a, b = (df.get(k) or '').strip(), (dc.get(k) or '').strip()
        if a != b and not (k == 'COD_SIT' and {a, b} <= {'00', '01', '06', '07', '08'}):
            dif.append({'campo': rot, 'fiscal': a, 'contrib': b})
    vals = [('VL_DOC', 'valor do documento'), ('VL_DESC', 'desconto'), ('VL_ICMS', 'ICMS'), ('VL_ICMS_ST', 'ICMS-ST'), ('VL_IPI', 'IPI')]
    if tipo == 'nfe':
        vals.insert(1, ('VL_MERC', 'valor das mercadorias'))
    else:
        vals = [('VL_DOC', 'valor do documento'), ('VL_SERV', 'valor do serviço'), ('VL_ICMS', 'ICMS')]
    for k, rot in vals:
        a, b = df.n(k), dc.n(k)
        if abs(a - b) > TOL:
            dif.append({'campo': rot, 'fiscal': _brl(a), 'contrib': _brl(b), 'diferenca': round(b - a, 2)})
    if tipo == 'nfe':
        itf, itc = _itens(df), _itens(dc)
        if itf and itc:
            if len(itf) != len(itc):
                dif.append({'campo': 'quantidade de itens', 'fiscal': str(len(itf)), 'contrib': str(len(itc))})
            porn = {(x.get('NUM_ITEM') or '').strip(): x for x in itc}
            for x in itf:
                y = porn.get((x.get('NUM_ITEM') or '').strip())
                if y is None:
                    continue
                for k, rot in (('COD_ITEM', 'código do item'), ('CFOP', 'CFOP')):
                    if (x.get(k) or '').strip() != (y.get(k) or '').strip():
                        dif.append({'campo': '%s (item %s)' % (rot, x.get('NUM_ITEM')), 'fiscal': x.get(k) or '', 'contrib': y.get(k) or ''})
                for k, rot in (('VL_ITEM', 'valor'), ('VL_DESC', 'desconto'), ('VL_ICMS', 'ICMS'), ('VL_IPI', 'IPI')):
                    if abs(x.n(k) - y.n(k)) > TOL:
                        dif.append({'campo': '%s do item %s' % (rot, x.get('NUM_ITEM')), 'fiscal': _brl(x.n(k)), 'contrib': _brl(y.n(k)), 'diferenca': round(y.n(k) - x.n(k), 2)})
    return dif


ENTREGA_FUTURA = {'5116', '5117', '6116', '6117'}
VENDA_ATIVO = {'5551', '6551', '7551'}


def _classificar_so_fiscal(d, saida, cfops, cumulativo):
    """Documento que está no SPED Fiscal e não na EFD Contribuições: nem toda ausência é erro."""
    from .regras_regime import CFOP_RECEITA
    if d.get('COD_SIT') in CANCELADAS:
        return 'info', 'documento cancelado/denegado (informativo)'
    if saida:
        receita = [c for c in cfops if c in CFOP_RECEITA and c not in ENTREGA_FUTURA and c not in VENDA_ATIVO]
        if receita:
            return 'alta', 'venda com receita (CFOP %s) fora da EFD Contribuições: receita fora da base do PIS/COFINS' % '/'.join(receita)
        if set(cfops) & VENDA_ATIVO:
            return 'info', 'venda de bem do ativo imobilizado: fora da receita bruta do PIS/COFINS (Lei 9.718/1998, art. 3º, § 2º, IV; Lei 10.637/2002 e 10.833/2003, art. 1º, § 3º); conferir o ganho de capital no IRPJ/CSLL'
        if set(cfops) & ENTREGA_FUTURA:
            return 'media', 'venda para entrega futura: a receita costuma ser reconhecida no faturamento antecipado (5922/6922); conferir se o faturamento está na EFD'
        return 'info', 'saída sem receita (remessa, retorno, devolução, transferência): escrituração na EFD Contribuições facultativa'
    if cumulativo:
        return 'info', 'entrada no regime cumulativo: não gera crédito e não precisa constar da EFD Contribuições'
    return 'media', 'entrada fora da EFD no regime não cumulativo: se for insumo, frete ou ativo com direito a crédito, é crédito não tomado'


def _resumo_lado(docs):
    r = {'saida': [0, 0.0], 'entrada': [0, 0.0]}
    for d in docs.values():
        if d.get('COD_SIT') in CANCELADAS:
            continue
        lado = 'saida' if d.get('IND_OPER') == '1' else 'entrada'
        r[lado][0] += 1
        r[lado][1] += d.n('VL_DOC')
    return {k: {'qtd': v[0], 'valor': round(v[1], 2)} for k, v in r.items()}


def _receita_fiscal(s):
    from .regras_regime import CFOP_RECEITA
    return round(sum(r.n('VL_OPR') for r in s['regs'].get('C190', []) if (r.get('CFOP') or '') in CFOP_RECEITA), 2)


def _receita_contrib(c):
    m = sum(r.n('VL_REC_BRT') for r in c['regs'].get('M210', []))
    if not m:
        o = c['regs'].get('0111', [])
        m = o[0].n('REC_BRU_TOTAL') if o else 0.0
    return round(m, 2)


def confronto(e, ctx):
    """Mês a mês, para o estabelecimento `e`. A EFD Contribuições é a da matriz (mesmo CNPJ raiz)."""
    contribs = {}
    for x in _irmas(e, ctx):
        for comp, c in x['contrib'].items():
            contribs[comp] = c
    meses = sorted(set(e['fiscal']) | set(contribs))
    out = []
    for m in meses:
        f, c = e['fiscal'].get(m), contribs.get(m)
        linha = {'mes': m, 'fiscal': bool(f), 'contrib': bool(c)}
        if not f or not c:
            linha.update(estado='sem_par', resumo='só %s no mês' % ('o SPED Fiscal' if f else 'a EFD Contribuições'))
            out.append(linha)
            continue
        divs = []
        for reg, campo, tipo, rot in (('C100', 'CHV_NFE', 'nfe', 'NF-e'), ('D100', 'CHV_CTE', 'cte', 'CT-e')):
            df_ = _docs(f, reg, campo)
            dc_ = _docs(c, reg, campo, e['cnpj'])
            if reg == 'C100':
                linha['lados'] = {'fiscal': _resumo_lado(df_), 'contrib': _resumo_lado(dc_)}
                linha['consolidada'] = not c['regs'].get('C100')
            if reg == 'C100' and linha['consolidada']:
                continue
            cumulativo = str(c['empresa'].get('cod_inc_trib') or '') == '2'
            for ch, d in df_.items():
                if ch in dc_:
                    continue
                saida = d.get('IND_OPER') == '1'
                cfops = sorted({x.get('CFOP') for x in d.get('filhos', []) if x.get('REG') in ('C190', 'D190')} - {None, ''})
                gravidade, motivo = _classificar_so_fiscal(d, saida, cfops, cumulativo)
                divs.append({'tipo': 'so_fiscal', 'gravidade': gravidade, 'doc': rot, 'chave': ch, 'cfop': '/'.join(cfops),
                             'numero': d.get('NUM_DOC'), 'data': d.get('DT_DOC'), 'sentido': 'saída' if saida else 'entrada', 'valor': d.n('VL_DOC'),
                             'onde': '%s %s %s (CFOP %s) só no SPED Fiscal, linha %s: %s' % (rot, 'de saída' if saida else 'de entrada', d.get('NUM_DOC'), '/'.join(cfops) or '-', d.get('linha'), motivo)})
            for ch, d in dc_.items():
                if ch in df_:
                    continue
                saida = d.get('IND_OPER') == '1'
                divs.append({'tipo': 'so_contrib', 'gravidade': 'alta', 'doc': rot, 'chave': ch, 'numero': d.get('NUM_DOC'), 'data': d.get('DT_DOC'),
                             'sentido': 'saída' if saida else 'entrada', 'valor': d.n('VL_DOC'),
                             'onde': '%s %s %s só na EFD Contribuições (linha %s)%s' % (rot, 'de saída' if saida else 'de entrada', d.get('NUM_DOC'), d.get('linha'),
                                     ': receita sem registro no SPED Fiscal' if saida else ': crédito sem lastro no SPED Fiscal')})
            for ch, d in df_.items():
                dc = dc_.get(ch)
                if dc is None:
                    continue
                dif = _comparar_doc(d, dc, tipo)
                if dif:
                    divs.append({'tipo': 'valores', 'gravidade': 'alta' if any('diferenca' in x for x in dif) else 'media', 'doc': rot, 'chave': ch,
                                 'numero': d.get('NUM_DOC'), 'data': d.get('DT_DOC'), 'sentido': 'saída' if d.get('IND_OPER') == '1' else 'entrada',
                                 'valor': d.n('VL_DOC'), 'diferencas': dif,
                                 'onde': '%s %s: SPED Fiscal linha %s × EFD Contribuições linha %s' % (rot, d.get('NUM_DOC'), d.get('linha'), dc.get('linha'))})
        if linha.get('consolidada'):
            rf, rc = _receita_fiscal(f), _receita_contrib(c)
            linha['receita'] = {'fiscal': rf, 'contrib': rc, 'diferenca': round(rc - rf, 2)}
            if abs(rc - rf) > max(1.0, rf * 0.005):
                divs.append({'tipo': 'receita', 'gravidade': 'alta', 'doc': 'Receita', 'valor': abs(rc - rf),
                             'onde': 'EFD Contribuições escriturada de forma consolidada (sem C100): receita das saídas no SPED Fiscal (C190, CFOP de receita) %s × receita bruta na EFD (M210) %s'
                             % (_brl(rf), _brl(rc))})
        cont = Counter(d['tipo'] for d in divs if d['gravidade'] != 'info')
        linha['qtd'] = dict(cont)
        linha['total'] = sum(cont.values())
        linha['informativos'] = sum(1 for d in divs if d['gravidade'] == 'info')
        linha['estado'] = 'divergente' if linha['total'] else 'ok'
        linha['divergencias'] = sorted(divs, key=lambda d: ({'alta': 0, 'media': 1, 'info': 2}[d['gravidade']], -d.get('valor', 0)))[:MAX_DET]
        linha['cortadas'] = max(0, len(divs) - MAX_DET)
        partes = []
        for k, rot in (('so_fiscal', 'só no SPED Fiscal'), ('so_contrib', 'só na EFD'), ('valores', 'com valor/campo diferente'), ('receita', 'receita diferente')):
            if cont.get(k):
                partes.append('%d %s' % (cont[k], rot))
        linha['resumo'] = '; '.join(partes) if partes else 'sem divergência'
        out.append(linha)
    return out


# ── orquestração ────────────────────────────────────────────────────────────

def preparar(ctx):
    """Antes das regras: regime de cada ano em cada empresa (as teses usam o regime do período)."""
    for e in ctx['empresas'].values():
        e['regime_anos'] = regime_por_ano(e, ctx)


def rodar(ctx, A, hoje=None):
    for cnpj, e in ctx['empresas'].items():
        e['integridade'] = integridade(e, ctx, hoje)
        e['confronto'] = confronto(e, ctx)
        base = dict(empresa=cnpj, nome=e['nome'], uf=e['uf'])
        it = e['integridade']
        if it:
            for chave, rot in (('contrib', 'EFD Contribuições'), ('fiscal', 'SPED Fiscal (EFD ICMS/IPI)')):
                faltam = [l['mes'] for l in it['meses'] if l[chave]['estado'] == 'sem_arquivo']
                ruins = [l for l in it['meses'] if l[chave]['estado'] == 'estrutura']
                if faltam:
                    A.add(regra='I01', grau='Alto', categoria='Integridade', tributo='SPED', periodo=faltam[0],
                          titulo='%s: %d mês(es) sem arquivo desde %s' % (rot, len(faltam), it['inicio']),
                          descricao='Meses exigidos no regime do ano sem arquivo na revisão: %s. Confirmar a entrega no ReceitaNet/SPED e enviar o arquivo; se não foi entregue, entregar em atraso (multa menor com denúncia espontânea).' % ', '.join('%s/%s' % (x[5:], x[:4]) for x in faltam),
                          evidencia=['%s sem arquivo' % x for x in faltam], acao='Localizar o recibo de entrega ou entregar o arquivo do mês', prioridade='Alta', **base)
                if ruins:
                    A.add(regra='I02', grau='Alto', categoria='Integridade', tributo='SPED', periodo=ruins[0]['mes'],
                          titulo='%s: %d mês(es) com problema de estrutura' % (rot, len(ruins)),
                          descricao='Arquivos com contagem de registros (9900/9999) que não fecha: a escrituração pode estar incompleta ou corrompida.',
                          evidencia=['%s: %s' % (l['mes'], '; '.join(l[chave]['problemas'])) for l in ruins], acao='Regerar o arquivo e retificar', prioridade='Alta', **base)
        for ano, r in (e.get('regime_anos') or {}).items():
            for al in r.get('alertas', []):
                A.add(regra='I03', grau='Médio', categoria='Integridade', tributo='PIS/COFINS', periodo='%s-01' % ano,
                      titulo='Regime de %s a conferir' % ano, descricao=al, acao='Conferir a opção do ano (DCTF/ECF) e corrigir a EFD ou o perfil', prioridade='Média', **base)
        divergentes = [l for l in e['confronto'] if l.get('estado') == 'divergente']
        if divergentes:
            tot = sum(l['total'] for l in divergentes)
            A.add(regra='I04', grau='Alto', categoria='Risco', tributo='SPED', periodo=divergentes[0]['mes'],
                  titulo='SPED Fiscal × EFD Contribuições: %d divergência(s) em %d mês(es)' % (tot, len(divergentes)),
                  descricao='Documentos presentes em só um dos arquivos ou com valores diferentes. O detalhe nota a nota está em "Integridade e confronto".',
                  evidencia=['%s: %s' % (l['mes'], l['resumo']) for l in divergentes], acao='Corrigir a escrituração que diverge do XML e retificar', prioridade='Alta', **base)
