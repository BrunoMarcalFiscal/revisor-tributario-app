# -*- coding: utf-8 -*-
"""Taxa SELIC mensal (BCB/SGS, série 4390) e atualização de indébito tributário.

Regra (Lei 9.250/1995, art. 39, §4º; IN RFB 2.055/2021): o valor pago indevidamente é acrescido da SELIC acumulada
mensalmente, a partir do mês seguinte ao do pagamento até o mês anterior ao da restituição/compensação, mais 1% no mês
da restituição/compensação. A soma é simples (não composta). A tabela é baixada do Banco Central e guardada em cache;
sem internet, usa o cache; sem cache, a atualização fica marcada como "não calculada" (nunca é inventada)."""
import os, json, datetime, urllib.request

URL = 'https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json&dataInicial=01/01/%d&dataFinal=%s'
CACHE = os.environ.get('REVISOR_SELIC_CACHE') or os.path.join(os.path.dirname(__file__), '..', 'dados', 'selic_mensal.json')


def _mes(d):
    """'01/07/2024' -> '2024-07'."""
    p = d.split('/')
    return '%s-%s' % (p[2], p[1])


def carregar(forcar=False):
    """{ 'AAAA-MM': taxa_percentual }"""
    hoje = datetime.date.today()
    cache = {}
    if os.path.exists(CACHE):
        try:
            cache = json.load(open(CACHE, encoding='utf-8'))
        except Exception:
            cache = {}
    atualizado = cache.get('_baixado_em', '')
    if cache.get('taxas') and not forcar and atualizado[:7] == hoje.strftime('%Y-%m'):
        return cache['taxas']
    try:
        with urllib.request.urlopen(URL % (hoje.year - 7, hoje.strftime('%d/%m/%Y')), timeout=20) as r:
            serie = json.loads(r.read().decode('utf-8'))
        taxas = {_mes(x['data']): float(x['valor']) for x in serie}
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump({'_baixado_em': hoje.isoformat(), 'fonte': 'BCB/SGS série 4390', 'taxas': taxas}, open(CACHE, 'w', encoding='utf-8'), ensure_ascii=False)
        return taxas
    except Exception:
        return cache.get('taxas') or {}


def _soma_mes(m, n):
    a, b = int(m[:4]), int(m[5:7]) + n
    a += (b - 1) // 12
    b = (b - 1) % 12 + 1
    return '%04d-%02d' % (a, b)


def fator(mes_pagamento, taxas, mes_recuperacao=None):
    """Percentual acumulado (ex.: 38.5 = 38,5%) do mês seguinte ao pagamento até o mês anterior ao da recuperação, +1%.
    Devolve (percentual, detalhe) ou (None, motivo) se faltar taxa na tabela."""
    if not taxas:
        return None, 'tabela SELIC indisponível (sem internet e sem cache)'
    hoje = datetime.date.today().strftime('%Y-%m')
    fim = mes_recuperacao or hoje
    m = _soma_mes(mes_pagamento, 1)
    total, n, faltam = 0.0, 0, []
    while m < fim:
        if m in taxas:
            total += taxas[m]; n += 1
        else:
            faltam.append(m)
        m = _soma_mes(m, 1)
    if faltam and len(faltam) > 1:
        return None, 'faltam taxas SELIC de %s' % ', '.join(faltam[:6])
    total += 1.0
    return round(total, 4), 'SELIC de %s a %s (%d meses) + 1%% no mês da recuperação' % (_soma_mes(mes_pagamento, 1), _soma_mes(fim, -1), n)


def vencimento(tributo, periodo):
    """Mês de pagamento usado como marco da SELIC: PIS/COFINS e IRPJ/CSLL vencem no mês seguinte ao da apuração (dia 25/último
    dia útil), INSS no mês seguinte (dia 20); ICMS segue o RICMS (em geral mês seguinte)."""
    return _soma_mes(periodo, 1)
