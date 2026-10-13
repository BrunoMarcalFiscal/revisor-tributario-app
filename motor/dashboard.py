# -*- coding: utf-8 -*-
"""Gera o dashboard HTML (autocontido) e os anexos CSV."""
import os, json, csv, datetime
from . import conhecimento, base_legal, recuperacao, estrategia

def _anexos(ctx, achados, pasta):
    os.makedirs(os.path.join(pasta, 'anexos'), exist_ok=True)
    lista = []
    def csvw(nome, colunas, linhas, descricao):
        p = os.path.join(pasta, 'anexos', nome)
        with open(p, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.writer(f, delimiter=';'); w.writerow(colunas); w.writerows(linhas)
        lista.append({'arquivo': 'anexos/' + nome, 'descricao': descricao, 'linhas': len(linhas)})
    csvw('achados.csv', ['n', 'regra', 'categoria', 'tributo', 'empresa', 'cnpj', 'periodo', 'titulo', 'descricao', 'valor', 'estimativa', 'memoria', 'grau', 'tese', 'prioridade', 'acao', 'fundamentacao', 'evidencia'],
         [[a['n'], a['regra'], a['categoria'], a['tributo'], a['nome'], a['empresa'], a['periodo'], a['titulo'], a['descricao'], str(a['valor']).replace('.', ','), 'sim' if a.get('estimativa') else 'não', a.get('memoria', ''), a['grau'], a.get('tese', ''), a['prioridade'], a['acao'], a.get('fundamentacao', ''), ' || '.join(a.get('evidencia', []))] for a in achados],
         'Tabela completa de achados (uma linha por achado)')
    ev = []
    for a in achados:
        for x in a.get('evidencia', []):
            ev.append([a['n'], a['regra'], a['nome'], a['periodo'], a['titulo'], x])
    csvw('evidencias.csv', ['n', 'regra', 'empresa', 'periodo', 'achado', 'evidencia'], ev, 'Todas as linhas de evidência (documentos, chaves, registros) por achado')
    ncm = []
    for e in ctx['empresas'].values():
        for n in e.get('tabela_ncm', {}).values():
            ncm.append([e['nome'], n['cod'], n['descricao'], n['ncm'], n['cest'], n['tipo'], n['aliq_icms_cad'], n['regime_pis_cofins'], n['setor'], n['segmento_st_conv142']])
    csvw('cadastro_ncm.csv', ['empresa', 'codigo', 'descricao', 'ncm', 'cest', 'tipo_item', 'aliq_icms_cadastro', 'regime_pis_cofins', 'setor', 'segmento_st_conv142'], ncm, 'Cadastro de itens (0200) com o regime por NCM')
    # documentos escriturados (C100) para conciliação
    docs = []
    for e in ctx['empresas'].values():
        for comp, s in e['fiscal'].items():
            for c in s['regs'].get('C100', []):
                docs.append([e['nome'], comp, 'entrada' if c.get('IND_OPER') == '0' else 'saída', c.get('COD_MOD'), c.get('COD_SIT'), c.get('NUM_DOC'), c.get('CHV_NFE'), c.get('DT_DOC'), s['participantes'].get(c.get('COD_PART'), {}).get('NOME', ''), s['participantes'].get(c.get('COD_PART'), {}).get('CNPJ', ''), str(c.n('VL_DOC')).replace('.', ','), str(c.n('VL_ICMS')).replace('.', ','), str(c.n('VL_ICMS_ST')).replace('.', ','), str(c.n('VL_IPI')).replace('.', ',')])
    csvw('documentos_c100.csv', ['empresa', 'periodo', 'sentido', 'modelo', 'situacao', 'numero', 'chave', 'data', 'participante', 'cnpj_participante', 'vl_doc', 'vl_icms', 'vl_icms_st', 'vl_ipi'], docs, 'Todos os documentos do C100 (para conciliar com XML e com a outra escrituração)')
    return lista

def _faltam(ctx):
    f = []
    for e in ctx['empresas'].values():
        if not e['contrib']:
            f.append('%s: sem EFD Contribuições. Ficaram sem prova viva: CST/alíquota de PIS/COFINS nas saídas (monofásico, alíquota zero, ICMS na base), créditos de insumo/energia/frete/ativo, M100/M500, saldo 1100/1500.' % e['nome'])
        if not e['fiscal']:
            f.append('%s: sem EFD ICMS/IPI. Sem apuração de ICMS/IPI/ST, CIAP, energia e frete.' % e['nome'])
    if not ctx['xmls'].get('nfe'):
        f.append('Sem XML de NF-e: não foi possível cruzar item a item (NCM, CST, base, alíquota), detectar notas não escrituradas, cancelamentos, DIFAL de não contribuinte, crédito de fornecedor do Simples, nem o grupo IBS/CBS (2026).')
    if not ctx['xmls'].get('cte'):
        f.append('Sem XML de CT-e: a validação do frete ficou restrita ao D100/D190 (tomador, UF de origem/destino e NF-es vinculadas não conferidos).')
    if not ctx['xmls'].get('nfse'):
        f.append('Sem XML de NFS-e: serviços tomados com crédito (A100/A170) e receita de serviços não cruzados.')
    return f

def _anexo_recuperacao(rec, pasta, anexos):
    p = os.path.join(pasta, 'anexos', 'recuperacao_oportunidades.csv')
    cols = ['id', 'tese_id', 'tese', 'tributo', 'nome', 'empresa', 'periodo', 'seguranca', 'comprovacao', 'valor_original', 'selic_pct', 'valor_atualizado', 'limite', 'situacao', 'status', 'via', 'habilitacao', 'fundamento', 'memoria']
    with open(p, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';'); w.writerow(cols)
        for o in rec['oportunidades']:
            w.writerow([str(o.get(c, '')).replace('.', ',') if isinstance(o.get(c), float) else o.get(c, '') for c in cols])
    anexos.append({'arquivo': 'anexos/recuperacao_oportunidades.csv', 'descricao': 'Oportunidades de recuperação de créditos (tese, período, valor original e atualizado, prazo, status)', 'linhas': len(rec['oportunidades'])})


def gerar(ctx, achados, resumo, pasta_saida):
    os.makedirs(pasta_saida, exist_ok=True)
    anexos = _anexos(ctx, achados, pasta_saida)
    conhec = {
        'regras_credito': conhecimento.REGRAS_CREDITO,
        'monofasico': [{'ncm': list(p), 'setor': s, 'base': b, 'aliq': list(a)} for p, s, b, a in conhecimento.MONOFASICO],
        'aliq_zero': [{'ncm': list(p), 'setor': s, 'base': b} for p, s, b in conhecimento.ALIQ_ZERO_PIS_COFINS],
        'aliq_interna': conhecimento.ALIQ_INTERNA_UF,
        'fundamentacao': {k: [v[0], base_legal.GRAU_TEXTO[v[1]]] for k, v in base_legal.FUNDAMENTACAO.items()},
    }
    dados = {
        'gerado_em': datetime.datetime.now().strftime('%d/%m/%Y %H:%M'),
        'achados': [{k: v for k, v in a.items() if k not in ('_',)} for a in achados],
        'resumo': resumo, 'inventario': ctx['inventario'], 'faltam': _faltam(ctx), 'pendencias_perfil': ctx['pendencias_perfil'], 'perfil_arquivo': ctx['perfil_arquivo'],
        'anexos': anexos, 'pasta_saida': os.path.abspath(pasta_saida), 'conhecimento': conhec,
        'recuperacao': recuperacao.montar(ctx, achados),
    }
    dados['estrategia'] = estrategia.montar(ctx, achados, dados['recuperacao'])
    _anexo_recuperacao(dados['recuperacao'], pasta_saida, anexos)
    tpl = open(os.path.join(os.path.dirname(__file__), 'dashboard_template.html'), encoding='utf-8').read()
    js = json.dumps(dados, ensure_ascii=False, default=str).replace('</script', '<\\/script')
    html = tpl.replace('__DADOS__', js)
    p = os.path.join(pasta_saida, 'dashboard.html')
    open(p, 'w', encoding='utf-8').write(html)
    with open(os.path.join(pasta_saida, 'dados.json'), 'w', encoding='utf-8') as f:
        json.dump({k: v for k, v in dados.items() if k != 'conhecimento'}, f, ensure_ascii=False, indent=1, default=str)
    return p
