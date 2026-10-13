# -*- coding: utf-8 -*-
"""Funções utilitárias compartilhadas pelo motor."""
import re, hashlib, json, os

def num(v):
    """Converte campo numérico do SPED ('1234,56') ou do XML ('1234.56') em float."""
    if v is None:
        return 0.0
    s = str(v).strip()
    if not s:
        return 0.0
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def brl(v):
    s = '{:,.2f}'.format(abs(v)).replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if v < 0 else '') + 'R$ ' + s

def data_sped(d):
    """ddmmaaaa -> aaaa-mm-dd"""
    d = (d or '').strip()
    if len(d) == 8:
        return '%s-%s-%s' % (d[4:8], d[2:4], d[0:2])
    return d

def competencia(dt_ini):
    d = data_sped(dt_ini)
    return d[:7] if len(d) >= 7 else d

def ler_texto(caminho):
    """Lê o TXT do SPED tolerando UTF-8, Latin-1 e a assinatura binária ICP-Brasil colada no fim."""
    raw = open(caminho, 'rb').read()
    # corta tudo depois do registro 9999 (assinatura digital)
    m = re.search(rb'(?m)^\|9999\|\d+\|', raw)
    if m:
        raw = raw[:m.end()]
    for enc in ('utf-8', 'latin-1'):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode('latin-1', errors='replace'), 'latin-1?'

def cnpj_fmt(c):
    c = re.sub(r'\D', '', c or '')
    if len(c) == 14:
        return '%s.%s.%s/%s-%s' % (c[:2], c[2:5], c[5:8], c[8:12], c[12:])
    return c

def hash_curto(*partes):
    return hashlib.sha1('|'.join(str(p) for p in partes).encode('utf-8')).hexdigest()[:10]

def carregar_json(caminho, padrao=None):
    if os.path.exists(caminho):
        with open(caminho, encoding='utf-8') as f:
            return json.load(f)
    return padrao if padrao is not None else {}

def salvar_json(caminho, dados):
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

IBGE_UF = {'11':'RO','12':'AC','13':'AM','14':'RR','15':'PA','16':'AP','17':'TO','21':'MA','22':'PI','23':'CE','24':'RN','25':'PB','26':'PE','27':'AL','28':'SE','29':'BA','31':'MG','32':'ES','33':'RJ','35':'SP','41':'PR','42':'SC','43':'RS','50':'MS','51':'MT','52':'GO','53':'DF'}

def uf_do_municipio(cod_mun):
    c = str(cod_mun or '').strip()
    if len(c) == 7:
        return IBGE_UF.get(c[:2], '')
    return ''

def uf_participante(part):
    """UF do participante do 0150: pelo código do município; exterior quando COD_PAIS != 1058."""
    if not part:
        return ''
    if part.get('COD_PAIS') and part.get('COD_PAIS') not in ('1058', '01058', ''):
        return 'EX'
    return uf_do_municipio(part.get('COD_MUN'))
