# -*- coding: utf-8 -*-
"""Monta o contexto da revisão: lê a pasta de entrada, agrupa por empresa e período, aplica o perfil informado."""
import os, zipfile, glob, re, tempfile, shutil
from collections import defaultdict
from . import sped, xml_docs
from .util import carregar_json, salvar_json

ATIV = {'0': 'industrial ou equiparado', '1': 'outros (comércio/serviços)'}
REGIME_CONTRIB = {'1': 'não cumulativo', '2': 'cumulativo', '3': 'misto (cumulativo e não cumulativo)'}

class Achados(list):
    def add(self, **a):
        a.setdefault('valor', 0.0)
        a.setdefault('evidencia', [])
        a.setdefault('memoria', '')
        a.setdefault('estimativa', False)
        a.setdefault('prioridade', 'Média')
        self.append(a)
        return a

def _extrair_zips(pasta, destino):
    for z in glob.glob(os.path.join(pasta, '**', '*.zip'), recursive=True):
        try:
            with zipfile.ZipFile(z) as zf:
                zf.extractall(destino)
        except zipfile.BadZipFile:
            pass

def carregar(pasta_entrada, log=print):
    tmp = tempfile.mkdtemp(prefix='revisor-')
    _extrair_zips(pasta_entrada, tmp)
    arquivos = []
    for base in (pasta_entrada, tmp):
        for f in glob.glob(os.path.join(base, '**', '*'), recursive=True):
            if os.path.isfile(f) and not os.path.basename(f).startswith('.') and not f.lower().endswith(('.zip', '.json', '.md', '.pdf', '.xlsx')):
                arquivos.append(f)
    inventario = []
    empresas = {}
    xmls = {'nfe': [], 'cte': [], 'nfse': [], 'evento': [], 'erro': [], 'desconhecido': []}
    for f in sorted(arquivos):
        ext = f.lower().rsplit('.', 1)[-1]
        try:
            if ext == 'txt':
                s = sped.parsear(f)
                cnpj = s['empresa']['cnpj']
                nome = s['empresa']['nome'] + ('' if cnpj[8:12] == '0001' else ' (filial %s)' % cnpj[8:12])
                e = empresas.setdefault(cnpj, {'cnpj': cnpj, 'nome': nome, 'uf': s['empresa']['uf'], 'fiscal': {}, 'contrib': {}, 'info': dict(s['empresa'])})
                if s['tipo'] == 'fiscal':
                    e['info'].update({k: v for k, v in s['empresa'].items() if v})
                else:
                    e['info'].update({k: v for k, v in s['empresa'].items() if v and (k not in e['info'] or k in ('cod_inc_trib', 'ind_apro_cred', 'cod_tipo_cont', 'ind_reg_cum'))})
                    e['info']['ind_ativ_contrib'] = s['empresa'].get('ind_ativ', '')
                s['retificadora'] = str(s['empresa'].get('cod_fin', '')) == '1'
                # arquivo enviado em "Atualizar arquivos" (entrada/atualizados/AAAAMMDDHHMMSS__nome) sempre vence o do mesmo mês
                s['atualizado'] = (os.sep + 'atualizados' + os.sep) in f
                s['enviado_em'] = os.path.basename(f).split('__')[0] if s['atualizado'] else ''
                comp = s['periodo']['comp']
                ja = e[s['tipo']].get(comp)
                if ja is not None and (s['atualizado'] or ja.get('atualizado')):
                    vence = s['atualizado'] and (not ja.get('atualizado') or s['enviado_em'] > ja.get('enviado_em', ''))
                else:
                    vence = ja is None or (s['retificadora'] and not ja.get('retificadora')) or (s['retificadora'] == ja.get('retificadora') and s['arquivo'] > ja['arquivo'])
                if vence:
                    if ja is not None:
                        e.setdefault('substituidos', []).append(ja)
                    e[s['tipo']][comp] = s
                else:
                    e.setdefault('substituidos', []).append(s)
                inventario.append({'arquivo': s['arquivo'], 'tipo': ('EFD ICMS/IPI' if s['tipo'] == 'fiscal' else 'EFD Contribuições') + (' (retificadora)' if s['retificadora'] else '') + (' (atualizado %s/%s/%s)' % (s['enviado_em'][6:8], s['enviado_em'][4:6], s['enviado_em'][:4]) if s['atualizado'] and len(s['enviado_em']) >= 8 else ''), 'empresa': s['empresa']['nome'], 'cnpj': cnpj,
                                   'periodo': s['periodo']['comp'], 'linhas': s['linhas'], 'qtd_9999': s['qtd_9999'], 'encoding': s['encoding'],
                                   'divergencias_9900': s['divergencias_9900'], 'problemas': s['problemas'], 'ok': not s['divergencias_9900'] and s['qtd_9999'] == s['linhas']})
            elif ext == 'xml':
                d = xml_docs.ler(f)
                xmls.setdefault(d['tipo'], []).append(d)
                if d['tipo'] in ('erro', 'desconhecido'):
                    inventario.append({'arquivo': os.path.basename(f), 'tipo': 'XML ' + d['tipo'], 'empresa': '', 'cnpj': '', 'periodo': '', 'ok': False, 'problemas': [d.get('erro', d.get('raiz', ''))]})
            else:
                inventario.append({'arquivo': os.path.basename(f), 'tipo': 'ignorado (%s)' % ext, 'empresa': '', 'cnpj': '', 'periodo': '', 'ok': False, 'problemas': ['extensão não tratada']})
        except Exception as ex:  # arquivo ruim não derruba a revisão
            inventario.append({'arquivo': os.path.basename(f), 'tipo': 'erro de leitura', 'empresa': '', 'cnpj': '', 'periodo': '', 'ok': False, 'problemas': [str(ex)]})
            log('  ! %s: %s' % (os.path.basename(f), ex))
    shutil.rmtree(tmp, ignore_errors=True)

    # resumo dos XMLs por tipo
    for t, lista in xmls.items():
        if lista and t not in ('erro', 'desconhecido'):
            inventario.append({'arquivo': '%d arquivo(s) XML' % len(lista), 'tipo': {'nfe': 'NF-e/NFC-e', 'cte': 'CT-e', 'nfse': 'NFS-e', 'evento': 'Eventos'}[t], 'empresa': '', 'cnpj': '', 'periodo': '', 'ok': True, 'problemas': []})

    # perfil informado pelo usuário (perfil.json na pasta de entrada), um bloco por CNPJ
    caminho_perfil = os.path.join(pasta_entrada, 'perfil.json')
    perfil = carregar_json(caminho_perfil, {})
    pendencias = []
    modelo_perfil = {}
    for cnpj, e in empresas.items():
        p = perfil.get(cnpj, {})
        inf = e['info']
        e['perfil'] = {
            'regime_tributario': p.get('regime_tributario', ''),            # Lucro Real / Lucro Presumido / Simples Nacional
            'atividade': p.get('atividade', ''),   # industria / comercio / servico / misto (vazio = usa a inferida)
            'cnae_principal': p.get('cnae_principal', ''),
            'cnaes_secundarios': p.get('cnaes_secundarios', []),
            'beneficios': p.get('beneficios', []),
            'regimes_especiais': p.get('regimes_especiais', []),
            'equiparado_industrial_ipi': p.get('equiparado_industrial_ipi', None),
            'exporta': p.get('exporta', None),
            'observacoes': p.get('observacoes', ''),
            'regime_pis_cofins_informado': p.get('regime_pis_cofins_informado', ''),
            'ufs_st': p.get('ufs_st', ''),
            'descricao_negocio': p.get('descricao_negocio', ''),
            'margem_liquida_estimada': p.get('margem_liquida_estimada', None),
            'faturamento_anual': p.get('faturamento_anual', None),
        }
        if p.get('uf') and len(p['uf'].strip()) == 2:
            e['uf'] = p['uf'].strip().upper()
        e['perfil_inferido'] = inferir_perfil(e)
        if not e['perfil']['atividade']:
            e['perfil']['atividade'] = e['perfil_inferido']['atividade']
            e['perfil']['atividade_inferida'] = True
        faltando = [k for k in ('regime_tributario', 'cnae_principal') if not e['perfil'].get(k)]
        if e['perfil'].get('atividade_inferida'): faltando.append('atividade (inferida: %s, confirmar)' % e['perfil']['atividade'])
        if faltando:
            pendencias.append({'cnpj': cnpj, 'empresa': e['nome'], 'faltando': faltando, 'inferido': e['perfil_inferido']})
        modelo_perfil[cnpj] = {'_empresa': e['nome'], 'regime_tributario': e['perfil']['regime_tributario'] or 'Lucro Real | Lucro Presumido | Simples Nacional',
                               'atividade': e['perfil']['atividade'] or e['perfil_inferido']['atividade'], 'cnae_principal': e['perfil']['cnae_principal'],
                               'cnaes_secundarios': e['perfil']['cnaes_secundarios'], 'beneficios': e['perfil']['beneficios'], 'regimes_especiais': e['perfil']['regimes_especiais'],
                               'equiparado_industrial_ipi': e['perfil']['equiparado_industrial_ipi'], 'exporta': e['perfil']['exporta'], 'observacoes': e['perfil']['observacoes']}
    if not os.path.exists(caminho_perfil) and modelo_perfil:
        salvar_json(caminho_perfil, modelo_perfil)
    return {'empresas': empresas, 'xmls': xmls, 'inventario': inventario, 'pendencias_perfil': pendencias, 'perfil_arquivo': caminho_perfil}

def inferir_perfil(e):
    """Deduz a atividade e o tipo de operação pelos CFOP/registros do próprio arquivo (é só um palpite, o perfil.json manda)."""
    from .conhecimento import cfop_info
    from collections import Counter
    grupos = Counter(); ufs_dest = Counter(); st_saida = 0.0; export = 0.0; total_saida = 0.0; total_entrada = 0.0
    for comp, s in e['fiscal'].items():
        for r in s['regs'].get('C190', []) + s['regs'].get('D190', []) + s['regs'].get('C590', []):
            ci = cfop_info(r.get('CFOP'))
            v = r.n('VL_OPR')
            grupos[('E' if ci['entrada'] else 'S', ci['grupo'])] += v
            if not ci['entrada']:
                total_saida += v
                if ci['grupo'] == 'exportacao' or ci['grupo'] == 'exportacao_indireta': export += v
                if ci['grupo'] in ('venda_st_producao','venda_st_revenda'): st_saida += v
            else:
                total_entrada += v
        for r in s['regs'].get('E200', []):
            ufs_dest[r.get('UF')] += 1
    vp = grupos[('S', 'venda_producao')] + grupos[('S', 'venda_st_producao')]; vr = grupos[('S', 'venda_revenda')] + grupos[('S', 'venda_st_revenda')]
    ind_ativ = e['info'].get('ind_ativ')
    if ind_ativ == '0' and vp >= vr * 0.5:
        atividade = 'industria'
    elif vp > vr:
        atividade = 'industria'
    elif vr > 0:
        atividade = 'comercio'
    elif e['contrib'] and not e['fiscal']:
        atividade = 'servico'
    else:
        atividade = 'indefinida'
    return {
        'atividade': atividade, 'ind_ativ_sped': ind_ativ,
        'vende_producao': round(vp, 2), 'vende_revenda': round(vr, 2), 'exporta': export > 0, 'valor_exportacao': round(export, 2),
        'substituto_tributario': grupos[('S', 'venda_st_producao')] + grupos[('S', 'venda_st_revenda')] > 0, 'ufs_com_st': sorted(u for u in ufs_dest if u),
        'compra_com_st': grupos[('E', 'revenda_st')] + grupos[('E', 'industrializacao_st')] > 0,
        'tem_energia': grupos[('E', 'energia')] > 0, 'tem_frete': grupos[('E', 'frete')] > 0, 'tem_ativo': grupos[('E', 'ativo')] > 0,
        'total_saidas': round(total_saida, 2), 'total_entradas': round(total_entrada, 2),
        'grupos': {('%s:%s' % k): round(v, 2) for k, v in grupos.items() if v},
    }
