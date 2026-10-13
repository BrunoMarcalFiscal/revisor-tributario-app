# -*- coding: utf-8 -*-
"""Orquestra a revisão: contexto -> regime -> regras -> consolidação -> achados fundamentados -> diagnóstico e resumo."""
import re
from collections import defaultdict, Counter
from . import contexto, regras_fiscal, regras_contrib, regras_cruz, regras_regime, regras_recup, base_legal, diagnostico, setores, integridade
from .util import brl, hash_curto

ORDEM_PRIORIDADE = {'Alta': 0, 'Média': 1, 'Baixa': 2}

def executar(pasta_entrada, log=print):
    ctx = contexto.carregar(pasta_entrada, log=log)
    A = contexto.Achados()
    integridade.preparar(ctx)   # regime de cada ano (as teses usam o regime do período)
    for cnpj, e in ctx['empresas'].items():
        e['regime'] = regras_regime.regime(e)
        e['setor'] = setores.inferir(e)
        regras_fiscal.rodar(e, A)
        regras_contrib.rodar(e, A)
        regras_regime.rodar(e, A)
        regras_recup.rodar(e, A)
    regras_cruz.rodar(ctx, A)
    integridade.rodar(ctx, A)   # obrigações mês a mês e confronto SPED Fiscal × EFD Contribuições
    for cnpj, e in ctx['empresas'].items():
        e['diagnostico'] = diagnostico.montar(e)
    achados = consolidar(list(A))
    for i, a in enumerate(achados, 1):
        base_legal.fundamentar(a)
        a['id'] = hash_curto(a['regra'], a['empresa'], a['periodo'], a['titulo'])
        a['valor'] = round(float(a.get('valor') or 0), 2)
    achados.sort(key=lambda a: (ORDEM_PRIORIDADE.get(a['prioridade'], 1), -a['valor']))
    for i, a in enumerate(achados, 1):
        a['n'] = i
    return ctx, achados

def _chave_consolidacao(a):
    t = re.sub(r'\d+([.,]\d+)?', '#', a['titulo'])
    t = re.sub(r'R\$ [#.,]+', 'R$ #', t)
    return (a['regra'], a['empresa'], a['categoria'], a['tributo'], t)

def consolidar(achados):
    """Mesmo achado repetido em vários períodos vira um só, com quadro por período."""
    grupos = defaultdict(list)
    for a in achados:
        grupos[_chave_consolidacao(a)].append(a)
    saida = []
    for k, lista in grupos.items():
        if len(lista) == 1:
            saida.append(lista[0]); continue
        lista.sort(key=lambda a: a['periodo'])
        base = dict(lista[0])
        periodos = [a['periodo'] for a in lista]
        base['periodo'] = '%s a %s' % (periodos[0], periodos[-1])
        base['periodos'] = periodos
        base['por_periodo'] = [{'periodo': a['periodo'], 'valor': round(a['valor'], 2), 'titulo': a['titulo']} for a in lista]
        base['valor'] = round(sum(a['valor'] for a in lista), 2)
        base['titulo'] = lista[-1]['titulo'] if lista[-1]['valor'] >= lista[0]['valor'] else lista[0]['titulo']
        base['titulo'] = '[%d meses] ' % len(lista) + re.sub(r'^\d+ ', '', base['titulo']) if base['titulo'][0].isdigit() else '[%d meses] ' % len(lista) + base['titulo']
        base['descricao'] = lista[0]['descricao'] + ' Repete em %d competências (%s); o valor é a soma do período.' % (len(lista), ', '.join(periodos))
        ev = []
        for a in lista:
            for x in a.get('evidencia', [])[:8]:
                ev.append('%s | %s' % (a['periodo'], x))
        base['evidencia'] = ev[:60]
        base['memoria'] = '; '.join('%s: %s' % (a['periodo'], a.get('memoria')) for a in lista if a.get('memoria'))[:1500]
        base['estimativa'] = any(a.get('estimativa') for a in lista)
        saida.append(base)
    return saida

def resumo(ctx, achados):
    por_cat = defaultdict(float); por_trib = defaultdict(float); por_emp = defaultdict(lambda: defaultdict(float))
    for a in achados:
        por_cat[a['categoria']] += a['valor']; por_trib[a['tributo']] += a['valor']; por_emp[a['empresa']][a['categoria']] += a['valor']
    recuperacao = por_cat.get('Recuperação', 0) + por_cat.get('Pago a maior', 0)
    riscos = por_cat.get('Risco', 0)
    fut = defaultdict(float)
    for a in achados:
        if a['categoria'] in ('Recuperação', 'Pago a maior', 'Planejamento') and a['regra'] in ('F09', 'F09b', 'F09c', 'F10', 'F10b', 'F11', 'F12a', 'F13', 'F26', 'P04', 'P04b', 'P05', 'P06', 'P07', 'P08', 'X10', 'F18', 'R01', 'X13'):
            n = len(a.get('periodos', [a['periodo']]))
            fut[(a['regra'], a['empresa'])] = max(fut[(a['regra'], a['empresa'])], a['valor'] / n * 12)
        if a['regra'] == 'R03':
            fut[('R03', a['empresa'])] = a['valor']
    futura_ano = sum(fut.values())
    top5 = sorted([a for a in achados if a['valor'] > 0], key=lambda a: -a['valor'])[:5]
    empresas = []
    for cnpj, e in ctx['empresas'].items():
        comps = sorted(set(e['fiscal']) | set(e['contrib']))
        empresas.append({'cnpj': cnpj, 'nome': e['nome'], 'uf': e['uf'], 'periodos': comps, 'perfil': e['perfil'], 'perfil_inferido': e['perfil_inferido'], 'regime': e.get('regime'), 'setor': e.get('setor'),
                         'pontos_regime': setores.pontos_regime((e.get('regime') or {}).get('tributario', '').split(' (')[0]),
                         'diagnostico': e.get('diagnostico'), 'simulacao_regime': e.get('simulacao_regime'),
                         'info': dict(e['info']), 'arquivos': {'fiscal': sorted(e['fiscal']), 'contrib': sorted(e['contrib'])},
                         'totais': {c: round(v, 2) for c, v in por_emp[cnpj].items()},
                         'tabela_frete': e.get('tabela_frete', []), 'tabela_st': e.get('tabela_st', []), 'tabela_ciap': e.get('tabela_ciap', []), 'tabela_nfse': e.get('tabela_nfse', []),
                         'tabela_ncm': list(e.get('tabela_ncm', {}).values()), 'tabela_difal': e.get('tabela_difal', []), 'tabela_credito': e.get('tabela_credito', []),
                         'tabela_base_cumulativa': e.get('tabela_base_cumulativa', []), 'tabela_receita': e.get('tabela_receita', []), 'tabela_encomenda': e.get('tabela_encomenda', [])})
    return {'recuperacao': round(recuperacao, 2), 'riscos': round(riscos, 2), 'economia_futura_ano': round(futura_ano, 2), 'por_categoria': {k: round(v, 2) for k, v in por_cat.items()},
            'por_tributo': {k: round(v, 2) for k, v in por_trib.items()}, 'top5': [a['id'] for a in top5], 'qtd': len(achados), 'qtd_por_categoria': dict(Counter(a['categoria'] for a in achados)),
            'empresas': empresas}
