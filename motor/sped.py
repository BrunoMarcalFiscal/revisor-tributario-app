# -*- coding: utf-8 -*-
"""Parser genérico dos arquivos SPED (EFD ICMS/IPI e EFD Contribuições)."""
import os, re
from collections import defaultdict, Counter
from . import layouts
from .util import ler_texto, num, data_sped, competencia

PAIS_FISCAL = {
 'C170':'C100','C190':'C100','C195':'C100','C197':'C100',
 'C501':'C500','C505':'C500','C590':'C500',
 'D190':'D100','D197':'D100',
 'E111':'E110','E112':'E111','E113':'E111','E115':'E110','E116':'E110',
 'E210':'E200','E220':'E210','E250':'E210','E310':'E300','E311':'E310',
 'E510':'E500','E520':'E500','E530':'E520','G125':'G110','H010':'H005',
}
PAIS_CONTRIB = {
 'A170':'A100','C170':'C100','C175':'C100','C181':'C180','C185':'C180',
 'C191':'C190','C195':'C190','C501':'C500','C505':'C500',
 'D101':'D100','D105':'D100',
 'M105':'M100','M110':'M100','M210':'M200','M220':'M210','M410':'M400',
 'M505':'M500','M510':'M500','M610':'M600','M620':'M610','M810':'M800',
}

def detectar_tipo(primeira_linha):
    """Fiscal: |0000|COD_VER|COD_FIN|DT_INI|DT_FIN|... (datas nos campos 3 e 4).
    Contribuições: |0000|COD_VER|TIPO_ESCRIT|IND_SIT_ESP|NUM_REC_ANTERIOR|DT_INI|DT_FIN|... (datas nos campos 5 e 6).
    Tolera um campo a mais/a menos: procura o primeiro par de datas consecutivas."""
    c = primeira_linha.strip().strip('|').split('|')
    if not c or c[0] != '0000':
        return None
    def data(i):
        return i < len(c) and re.fullmatch(r'\d{8}', c[i] or '') is not None
    if data(3) and data(4):
        return 'fiscal'
    for i in (5, 6, 4):
        if data(i) and data(i + 1):
            return 'contrib'
    return None

class Registro(dict):
    """dict com os campos nomeados + 'REG', 'linha', 'campos' (lista posicional) e 'filhos'."""
    def n(self, k):
        return num(self.get(k))

def parsear(caminho):
    texto, enc = ler_texto(caminho)
    linhas = texto.splitlines()
    if not linhas:
        raise ValueError('arquivo vazio')
    tipo = detectar_tipo(linhas[0])
    if tipo is None:
        raise ValueError('não parece um SPED (registro 0000 não reconhecido)')
    lay = layouts.FISCAL if tipo == 'fiscal' else layouts.CONTRIB
    pais = PAIS_FISCAL if tipo == 'fiscal' else PAIS_CONTRIB

    regs = defaultdict(list)
    contagem = Counter()
    ultimo = {}
    problemas = []
    n_linhas = 0
    for i, ln in enumerate(linhas, 1):
        ln = ln.rstrip('\r')
        if not ln.startswith('|'):
            if ln.strip():
                problemas.append('linha %d não começa com | (ignorada)' % i)
            continue
        campos = ln.strip('|').split('|')
        reg = campos[0]
        if not re.fullmatch(r'[0-9A-Z]\d{3}', reg):
            problemas.append('linha %d com registro inválido "%s"' % (i, reg[:10]))
            continue
        n_linhas += 1
        r = Registro()
        r['REG'] = reg
        r['linha'] = i
        r['campos'] = campos[1:]
        r['filhos'] = []
        nomes = lay.get(reg)
        if nomes:
            for j, nome in enumerate(nomes):
                r[nome] = campos[j + 1] if j + 1 < len(campos) else ''
        regs[reg].append(r)
        contagem[reg] += 1
        ultimo[reg] = r
        pai = pais.get(reg)
        if pai and pai in ultimo:
            ultimo[pai]['filhos'].append(r)
            r['pai'] = ultimo[pai]

    h = regs['0000'][0]
    empresa = {
        'cnpj': re.sub(r'\D', '', h.get('CNPJ', '')),
        'nome': h.get('NOME', '').strip(),
        'uf': h.get('UF', '').strip(),
        'ie': h.get('IE', '').strip() if tipo == 'fiscal' else '',
        'cod_mun': h.get('COD_MUN', '').strip(),
        'perfil': h.get('IND_PERFIL', '') if tipo == 'fiscal' else '',
        'ind_ativ': h.get('IND_ATIV', '').strip(),
        'cod_fin': h.get('COD_FIN', '') if tipo == 'fiscal' else h.get('TIPO_ESCRIT', ''),
        'cod_ver': h.get('COD_VER', ''),
    }
    if regs.get('0005'):
        e = regs['0005'][0]
        empresa['endereco'] = ' '.join(x for x in [e.get('END',''), e.get('NUM',''), e.get('COMPL',''), e.get('BAIRRO',''), e.get('CEP','')] if x).strip()
    if tipo == 'contrib' and regs.get('0110'):
        r = regs['0110'][0]
        empresa['cod_inc_trib'] = r.get('COD_INC_TRIB', '')
        empresa['ind_apro_cred'] = r.get('IND_APRO_CRED', '')
        empresa['cod_tipo_cont'] = r.get('COD_TIPO_CONT', '')
        empresa['ind_reg_cum'] = r.get('IND_REG_CUM', '')

    # validação estrutural 9900 / 9999
    declarado = {r['REG_BLC']: int(num(r['QTD_REG_BLC'])) for r in regs.get('9900', [])}
    divergencias_9900 = []
    for reg, qtd in declarado.items():
        real = contagem.get(reg, 0)
        if real != qtd:
            divergencias_9900.append({'registro': reg, 'declarado': qtd, 'real': real})
    for reg, qtd in contagem.items():
        if reg not in declarado:
            divergencias_9900.append({'registro': reg, 'declarado': 0, 'real': qtd})
    qtd_9999 = int(num(regs['9999'][0]['QTD_LIN'])) if regs.get('9999') else None

    participantes = {r['COD_PART']: r for r in regs.get('0150', [])}
    itens = {r['COD_ITEM']: r for r in regs.get('0200', [])}

    return {
        'arquivo': os.path.basename(caminho),
        'tipo': tipo,
        'encoding': enc,
        'empresa': empresa,
        'periodo': {'ini': data_sped(h.get('DT_INI')), 'fim': data_sped(h.get('DT_FIN')), 'comp': competencia(h.get('DT_INI'))},
        'regs': regs,
        'contagem': dict(contagem),
        'linhas': n_linhas,
        'qtd_9999': qtd_9999,
        'divergencias_9900': divergencias_9900,
        'problemas': problemas,
        'participantes': participantes,
        'itens': itens,
    }
