# -*- coding: utf-8 -*-
"""Recuperação de créditos: transforma os achados do motor em oportunidades por tese, empresa e período.

Para cada oportunidade: tese e fundamento, requisitos, evidências, valor original, prazo (5 anos), atualização pela SELIC
quando é indébito, grau de segurança jurídica, comprovado × estimado, via de recuperação, habilitação, memória de cálculo
e status com trilha de auditoria (gravado em dados/recuperacao_status.json; nada é transmitido nem retificado daqui).

Duplicidade: regras diferentes podem apontar o mesmo crédito (ex.: ICMS na base do PIS/COFINS pelo XML e pela EFD).
Dentro do mesmo grupo de tese, empresa e período fica só o maior valor; as outras regras aparecem como "também apontado por"."""
import os, json, datetime, re
from collections import defaultdict
from . import teses as T, selic, base_legal
from .util import hash_curto, brl

STATUS = ['Identificada', 'Em validação', 'Validada', 'Em processamento', 'Recuperada', 'Descartada']
ARQ_STATUS = os.environ.get('REVISOR_STATUS_ARQ') or os.path.join(os.path.dirname(__file__), '..', 'dados', 'recuperacao_status.json')
CATEGORIAS = ('Recuperação', 'Pago a maior')
# regras que olham itens/documentos DIFERENTES dentro da mesma tese: somam (grupo próprio).
# As demais regras de uma tese apontam o mesmo crédito por caminhos diferentes: conta uma vez, pelo maior.
GRUPO_REGRA = {'P04b': 'insumos_uso_consumo', 'X09': 'insumos_servicos', 'F26': 'icms_entradas_sem_credito', 'F14': 'icms_cst_entrada',
               'F12c': 'ipi_saldo', 'F09c': 'energia_icms_titular', 'F25b': 'saldo_pis_exportacao'}
ANOS = 5


def _soma_mes(m, n):
    return selic._soma_mes(m, n)


def ler_status():
    if os.path.exists(ARQ_STATUS):
        try:
            return json.load(open(ARQ_STATUS, encoding='utf-8'))
        except Exception:
            return {}
    return {}


def gravar_status(op_id, status, obs='', valor_recuperado=None, usuario=''):
    """Muda o status de uma oportunidade e registra na trilha. Só grava o status: não transmite nada."""
    if status not in STATUS:
        raise ValueError('status inválido')
    if status == 'Descartada' and not (obs or '').strip():
        raise ValueError('informe o motivo do descarte')
    d = ler_status()
    r = d.setdefault(op_id, {'status': 'Identificada', 'historico': []})
    agora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    r['historico'].append({'em': agora, 'de': r.get('status'), 'para': status, 'obs': obs, 'usuario': usuario,
                           'valor_recuperado': valor_recuperado})
    r['status'] = status
    if valor_recuperado is not None:
        r['valor_recuperado'] = round(float(valor_recuperado), 2)
    os.makedirs(os.path.dirname(ARQ_STATUS), exist_ok=True)
    json.dump(d, open(ARQ_STATUS, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return r


def _periodos(a):
    """Um achado pode valer para vários meses (consolidado): devolve [(periodo, valor, evidencias)]."""
    if a.get('por_periodo'):
        out = []
        for p in a['por_periodo']:
            ev = [x.split(' | ', 1)[1] for x in a.get('evidencia', []) if x.startswith(p['periodo'] + ' | ')]
            out.append((p['periodo'], float(p.get('valor') or 0), ev))
        return out
    return [(a['periodo'], float(a.get('valor') or 0), list(a.get('evidencia', [])))]


def _limite(tese, periodo):
    """Último mês para pedir: 5 anos do marco (pagamento, para indébito; mês do documento, para crédito escritural)."""
    marco = selic.vencimento(tese['tributo'], periodo) if tese['atualizacao'] == T.SELIC else periodo
    return _soma_mes(marco, ANOS * 12)


def montar(ctx, achados, hoje=None):
    hoje = hoje or datetime.date.today().strftime('%Y-%m')
    taxas = selic.carregar()
    st = ler_status()
    regimes = {}
    for cnpj_, e_ in ((ctx or {}).get('empresas') or {}).items():
        r_ = e_.get('regime') or {}
        regimes[cnpj_] = {'pis_cofins': r_.get('pis_cofins', ''), 'tributario': r_.get('tributario', ''),
                          'lucro_real': r_.get('pis_cofins') in ('nao_cumulativo', 'misto') or str(r_.get('tributario', '')).startswith('Lucro Real')}
    brutas = []
    for a in achados:
        if a.get('categoria') not in CATEGORIAS:
            continue
        tese = T.tese_da_regra(a['regra'])
        if not tese:
            continue
        rg = regimes.get(a.get('empresa'), {})
        if rg.get('pis_cofins') and rg['pis_cofins'] not in tese.get('regimes', []):
            continue   # tese de outro regime (ex.: crédito não cumulativo em empresa do Presumido)
        grau = base_legal.FUNDAMENTACAO.get(a['regra'], ('', 'c'))[1]
        for periodo, valor, ev in _periodos(a):
            if not re.match(r'^\d{4}-\d{2}$', periodo or ''):
                continue
            brutas.append({'tese': tese, 'achado': a, 'periodo': periodo, 'valor': round(valor, 2), 'evidencia': ev, 'grau': grau,
                           'grupo': GRUPO_REGRA.get(a['regra'], tese['grupo'])})
    # dedupe: mesmo grupo de tese, empresa e período -> o maior
    grupos = defaultdict(list)
    for b in brutas:
        grupos[(b['grupo'], b['achado']['empresa'], b['periodo'])].append(b)
    ops = []
    for (grupo, cnpj, periodo), lista in grupos.items():
        lista.sort(key=lambda b: -b['valor'])
        b = lista[0]
        tese, a = b['tese'], b['achado']
        oid = hash_curto('REC', tese['id'], cnpj, periodo) if grupo == tese['grupo'] else hash_curto('REC', tese['id'], grupo, cnpj, periodo)
        estimado = bool(a.get('estimativa')) or tese['comprovacao'] == 'Estimado'
        limite = _limite(tese, periodo)
        prescrita = hoje > limite
        meses_rest = (int(limite[:4]) - int(hoje[:4])) * 12 + int(limite[5:7]) - int(hoje[5:7])
        vig = T.vigente(tese, periodo)
        pct, det = (None, '')
        valor_at = b['valor']
        if tese['atualizacao'] == T.SELIC and b['valor'] > 0:
            pct, det = selic.fator(selic.vencimento(tese['tributo'], periodo), taxas)
            if pct is not None:
                valor_at = round(b['valor'] * (1 + pct / 100), 2)
        s = st.get(oid, {})
        status = s.get('status', 'Identificada')
        if not vig:
            situacao = 'Fora da vigência da tese'
        elif prescrita:
            situacao = 'Prescrita'
        elif b['valor'] <= 0:
            situacao = 'A quantificar'
        else:
            situacao = 'Em prazo'
        fund = '%s %s' % (tese['fundamento'], a.get('fundamentacao') or '')
        ops.append({
            'id': oid, 'tese_id': tese['id'], 'tese': tese['nome'], 'tributo': tese['tributo'], 'grupo': grupo,
            'empresa': cnpj, 'nome': a.get('nome', ''), 'periodo': periodo, 'ano': periodo[:4],
            'regime': (regimes.get(cnpj) or {}).get('tributario', '') or 'não identificado', 'lucro_real': bool((regimes.get(cnpj) or {}).get('lucro_real')),
            'valor_original': b['valor'], 'valor_atualizado': valor_at, 'selic_pct': pct, 'selic_detalhe': det,
            'atualizacao': tese['atualizacao'], 'limite': limite, 'meses_para_prescrever': meses_rest, 'situacao': situacao,
            'comprovacao': 'Estimado' if estimado else 'Comprovado', 'seguranca': T.seguranca(tese, b['grau']),
            'via': tese['via'], 'habilitacao': tese['habilitacao'], 'fundamento': fund.strip(),
            'requisitos': [{'texto': r, 'situacao': 'A confirmar'} for r in tese['requisitos']], 'documentos': tese['documentos'],
            'evidencia': b['evidencia'][:80], 'memoria': a.get('memoria', ''), 'descricao': a.get('descricao', ''),
            'titulo': a.get('titulo', ''), 'regras': [x['achado']['regra'] for x in lista], 'achados': [x['achado'].get('id') for x in lista],
            'tambem': [{'regra': x['achado']['regra'], 'valor': x['valor'], 'titulo': x['achado'].get('titulo', '')} for x in lista[1:]],
            'status': status, 'valor_recuperado': s.get('valor_recuperado', 0), 'historico': s.get('historico', []),
        })
    ops.sort(key=lambda o: (o['situacao'] != 'Em prazo', T.SEG_ORDEM.index(o['seguranca']), -o['valor_atualizado']))
    return {'oportunidades': ops, 'painel': painel(ops, achados), 'catalogo': catalogo(ops), 'tem_lucro_real': any(r.get('lucro_real') for r in regimes.values()),
            'empresas_regime': [{'cnpj': k, 'regime': v.get('tributario', ''), 'lucro_real': v.get('lucro_real')} for k, v in regimes.items()], 'selic': {'meses': len(taxas), 'ate': max(taxas) if taxas else None},
            'gerado_em': datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}


def _ativa(o):
    return o['situacao'] == 'Em prazo' and o['status'] != 'Descartada'


def painel(ops, achados):
    at = [o for o in ops if _ativa(o)]
    soma = lambda xs, k='valor_atualizado': round(sum(o[k] for o in xs), 2)
    por = lambda campo: sorted(({'chave': k, 'valor': round(v, 2)} for k, v in _agrupa(at, campo).items()), key=lambda x: -x['valor'])
    hoje = datetime.date.today().strftime('%Y-%m')
    prazos = sorted([o for o in at if o['meses_para_prescrever'] <= 6], key=lambda o: o['meses_para_prescrever'])
    divergencias = [a for a in achados if a.get('regra', '').startswith('X') and a.get('categoria') in ('Risco', 'Integridade', 'Recuperação', 'Pago a maior')]
    return {
        'potencial': soma(at), 'potencial_original': soma(at, 'valor_original'),
        'consolidado': soma([o for o in at if o['seguranca'] == 'Consolidada' and o['comprovacao'] == 'Comprovado']),
        'pendente_validacao': soma([o for o in at if o['status'] in ('Identificada', 'Em validação')]),
        'validado': soma([o for o in at if o['status'] == 'Validada']),
        'em_processamento': soma([o for o in at if o['status'] == 'Em processamento']),
        'recuperado': round(sum(o.get('valor_recuperado') or 0 for o in ops if o['status'] == 'Recuperada'), 2),
        'descartado': soma([o for o in ops if o['status'] == 'Descartada']),
        'a_quantificar': len([o for o in ops if o['situacao'] == 'A quantificar' and o['status'] != 'Descartada']),
        'prescritas': soma([o for o in ops if o['situacao'] == 'Prescrita'], 'valor_original'),
        'qtd': len(at), 'por_tributo': por('tributo'), 'por_ano': sorted(por('ano'), key=lambda x: x['chave']), 'por_empresa': por('nome'),
        'por_seguranca': por('seguranca'), 'por_tese': por('tese'), 'por_regime': por('regime'),
        'lucro_real': soma([o for o in at if o.get('lucro_real')]), 'lucro_real_qtd': len([o for o in at if o.get('lucro_real')]),
        'divergencias': len(divergencias), 'divergencias_valor': round(sum(float(a.get('valor') or 0) for a in divergencias), 2),
        'prazos': [{'id': o['id'], 'tese': o['tese'], 'periodo': o['periodo'], 'limite': o['limite'], 'meses': o['meses_para_prescrever'], 'valor': o['valor_atualizado']} for o in prazos[:20]],
        'prioritarias': [o['id'] for o in sorted(at, key=lambda o: (T.SEG_ORDEM.index(o['seguranca']), o['comprovacao'] != 'Comprovado', -o['valor_atualizado']))[:10]],
    }


def _agrupa(xs, campo):
    d = defaultdict(float)
    for o in xs:
        d[o[campo]] += o['valor_atualizado']
    return d


def catalogo(ops):
    out = []
    for t in T.TESES:
        mine = [o for o in ops if o['tese_id'] == t['id']]
        at = [o for o in mine if _ativa(o)]
        out.append({'id': t['id'], 'nome': t['nome'], 'tributo': t['tributo'], 'seguranca': t['seguranca'], 'comprovacao': t['comprovacao'],
                    'atualizacao': t['atualizacao'], 'via': t['via'], 'habilitacao': t['habilitacao'], 'fundamento': t['fundamento'],
                    'vigencia': t['vigencia'], 'regras': t['regras'], 'requisitos': t['requisitos'], 'documentos': t['documentos'],
                    'avaliada': not t.get('depende'), 'depende': t.get('depende', ''), 'lucro_real': 'nao_cumulativo' in t.get('regimes', []), 'so_lucro_real': 'cumulativo' not in t.get('regimes', []),
                    'qtd': len(at), 'valor': round(sum(o['valor_atualizado'] for o in at), 2)})
    return out
