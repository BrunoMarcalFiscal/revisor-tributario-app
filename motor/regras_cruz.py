# -*- coding: utf-8 -*-
"""Cruzamentos: XML × SPED, SPED Fiscal × EFD Contribuições, empresas do mesmo lote (espelho), NFS-e × EFD Contribuições."""
from collections import defaultdict, Counter
from .conhecimento import cfop_info, regime_ncm, aliq_interestadual, ALIQ_INTERNA_UF
from .regras_regime import CFOP_RECEITA, CFOP_FAT_FUTURO, CFOP_ENTREGA_FUTURA
from .util import brl, data_sped

TOL = 0.05

def _ev(*p):
    return ' | '.join(str(x) for x in p if x not in (None, ''))

def rodar(ctx, A):
    empresas = ctx['empresas']; xmls = ctx['xmls']
    idx_nfe = {d['chave']: d for d in xmls.get('nfe', []) if d.get('chave')}
    idx_cte = {d['chave']: d for d in xmls.get('cte', []) if d.get('chave')}
    eventos = defaultdict(list)
    for ev in xmls.get('evento', []):
        eventos[ev['chave']].append(ev)
    for cnpj, e in empresas.items():
        fiscal_x_contrib(e, A)
        for comp, s in e['fiscal'].items():
            base = dict(empresa=cnpj, nome=e['nome'], periodo=comp, uf=e['uf'])
            xml_x_c100(e, s, idx_nfe, eventos, A, base)
            xml_item_x_c170(e, s, idx_nfe, A, base, 'fiscal')
            cte_x_d100(e, s, idx_cte, A, base)
            xml_saidas_regras(e, s, idx_nfe, A, base)
        for comp, s in e['contrib'].items():
            base = dict(empresa=cnpj, nome=e['nome'], periodo=comp, uf=e['uf'])
            xml_item_x_c170(e, s, idx_nfe, A, base, 'contrib')
            nfse_x_a100(e, s, xmls.get('nfse', []), A, base)
    espelho_entre_empresas(empresas, A)
    ncm_xml_x_cadastro(empresas, idx_nfe, A)

# ---------------------------------------------------------------- XML x C100
def _chaves_xml_da_empresa(cnpj, idx_nfe, comp):
    emitidas = {}; recebidas = {}
    for ch, d in idx_nfe.items():
        if d['emissao'][:7] != comp and d['emissao']:
            # NF-e de outro mês pode ter entrado neste mês; deixamos o cruzamento de entradas mais tolerante
            pass
        if d['emit']['cnpj'] == cnpj:
            emitidas[ch] = d
        elif d['dest']['cnpj'] == cnpj:
            recebidas[ch] = d
    return emitidas, recebidas

def xml_x_c100(e, s, idx_nfe, eventos, A, base):
    if not idx_nfe:
        return
    comp = base['periodo']
    emitidas, recebidas = _chaves_xml_da_empresa(e['cnpj'], idx_nfe, comp)
    c100 = {c.get('CHV_NFE'): c for c in s['regs'].get('C100', []) if c.get('CHV_NFE')}
    # emitidas no mês sem C100
    canceladas = {ch for ch, evs in eventos.items() if any(ev['tpEvento'] == '110111' and ev.get('cStat') in ('135', '155', '') for ev in evs)}
    faltam_saida = [d for ch, d in emitidas.items() if d['emissao'][:7] == comp and ch not in c100 and ch not in canceladas and d.get('protocolo', '100') in ('100', '')]
    if faltam_saida:
        tot = sum(d['totais']['vNF'] for d in faltam_saida); icms = sum(d['totais']['vICMS'] for d in faltam_saida)
        A.add(regra='X02', categoria='Risco', tributo='ICMS', titulo='%d NF-e emitida(s) no mês sem escrituração no C100 (omissão de saída)' % len(faltam_saida),
              descricao='Notas autorizadas contra o CNPJ da empresa que não aparecem no SPED. Valor %s, ICMS %s. O fisco tem o XML.' % (brl(tot), brl(icms)),
              evidencia=[_ev('NF', d['numero'], d['chave'], d['emissao'], brl(d['totais']['vNF'])) for d in faltam_saida[:20]], valor=icms, grau='Alto', acao='Retificar a EFD incluindo as notas; recolher a diferença', prioridade='Alta', **base)
    # recebidas (a empresa é destinatária) sem C100: crédito perdido ou omissão de entrada
    faltam_entrada = [d for ch, d in recebidas.items() if ch not in c100 and ch not in canceladas and d['emissao'][:7] <= comp and d.get('protocolo', '100') in ('100', '')]
    # só as do mês (ou anteriores que não estão em nenhum mês da empresa)
    todas_c100 = set()
    for s2 in e['fiscal'].values():
        todas_c100 |= {c.get('CHV_NFE') for c in s2['regs'].get('C100', [])}
    faltam_entrada = [d for d in faltam_entrada if d['chave'] not in todas_c100 and d['emissao'][:7] == comp]
    if faltam_entrada:
        icms = sum(d['totais']['vICMS'] for d in faltam_entrada); ipi = sum(d['totais']['vIPI'] for d in faltam_entrada); tot = sum(d['totais']['vNF'] for d in faltam_entrada)
        A.add(regra='X02', categoria='Recuperação', tributo='ICMS', titulo='%d NF-e recebida(s) (empresa como destinatária) sem escrituração de entrada' % len(faltam_entrada),
              descricao='Valor %s; ICMS destacado %s; IPI %s. Se são compras de insumo/revenda, o crédito não foi tomado; se são notas indevidas, cabe manifestação "operação não realizada". Sem manifestação, o fisco presume a entrada (omissão).' % (brl(tot), brl(icms), brl(ipi)),
              evidencia=[_ev('NF', d['numero'], 'emit', d['emit']['nome'][:30], d['emit']['uf'], d['chave'], brl(d['totais']['vNF']), 'ICMS', brl(d['totais']['vICMS'])) for d in faltam_entrada[:20]], valor=icms, grau='Alto', acao='Escriturar as entradas (crédito) ou manifestar desconhecimento; crédito extemporâneo em até 5 anos', prioridade='Alta', **base)
    # C100 com chave sem XML fornecido (só informativo, o lote pode ser parcial)
    sem_xml = [c for ch, c in c100.items() if ch not in idx_nfe and c.get('COD_MOD') in ('55', '65')]
    if sem_xml and len(sem_xml) < len(c100):
        A.add(regra='X02b', categoria='Integridade', tributo='SPED', titulo='%d documento(s) do C100 sem XML no lote' % len(sem_xml), descricao='Cruzamento item a item ficou prejudicado para esses documentos.', evidencia=[_ev('NF', c.get('NUM_DOC'), c.get('CHV_NFE')) for c in sem_xml[:10]], grau='Baixo', acao='Fornecer os XMLs', prioridade='Baixa', **base)
    # cancelamentos: C100 normal com evento de cancelamento
    canc_escrit = [c for ch, c in c100.items() if ch in canceladas and c.get('COD_SIT') in ('00', '01') and c.n('VL_DOC') > 0]
    if canc_escrit:
        A.add(regra='X04', categoria='Risco', tributo='ICMS', titulo='%d NF-e cancelada(s) escriturada(s) como regular' % len(canc_escrit), descricao='Evento de cancelamento autorizado, mas o C100 está com COD_SIT 00 e valores.', evidencia=[_ev('NF', c.get('NUM_DOC'), c.get('CHV_NFE'), brl(c.n('VL_DOC'))) for c in canc_escrit[:15]], valor=sum(c.n('VL_ICMS') for c in canc_escrit), grau='Alto', acao='Retificar (COD_SIT 02, sem valores)', prioridade='Alta', **base)
    # cartas de correção: informar
    cce = [(ch, ev) for ch, evs in eventos.items() for ev in evs if ev['tpEvento'] == '110110' and ch in c100]
    if cce:
        A.add(regra='X04', categoria='Integridade', tributo='SPED', titulo='%d NF-e escriturada(s) com carta de correção' % len(cce), descricao='Conferir se a escrituração reflete o conteúdo da CC-e (CFOP, dados do destinatário, etc.).', evidencia=[_ev('NF', c100[ch].get('NUM_DOC'), ev['xCorrecao'][:80]) for ch, ev in cce[:10]], grau='Baixo', acao='Conferir', prioridade='Baixa', **base)

# ---------------------------------------------------------------- XML item x C170
def xml_item_x_c170(e, s, idx_nfe, A, base, tipo):
    if not idx_nfe:
        return
    div = []; total = 0.0; n_docs = 0
    for c in s['regs'].get('C100', []):
        d = idx_nfe.get(c.get('CHV_NFE'))
        itens = [f for f in c['filhos'] if f['REG'] == 'C170']
        if not d or not itens:
            continue
        n_docs += 1
        xml_itens = {it['nItem']: it for it in d['itens']}
        for it in itens:
            x = xml_itens.get(it.get('NUM_ITEM'))
            if not x:
                div.append(_ev('NF', c.get('NUM_DOC'), 'item', it.get('NUM_ITEM'), 'não existe no XML')); continue
            if tipo == 'fiscal':
                pares = [('CFOP', it.get('CFOP'), x['CFOP'], False), ('CST ICMS', (it.get('CST_ICMS') or '')[1:], x['icms'].get('CST', ''), False),
                         ('BC ICMS', it.n('VL_BC_ICMS'), x['icms'].get('vBC', 0), True), ('ICMS', it.n('VL_ICMS'), x['icms'].get('vICMS', 0), True),
                         ('ICMS-ST', it.n('VL_ICMS_ST'), x['icms'].get('vICMSST', 0), True), ('IPI', it.n('VL_IPI'), x['ipi'].get('vIPI', 0), True), ('VL_ITEM', it.n('VL_ITEM'), x['vProd'], True)]
            else:
                pares = [('CST PIS', it.get('CST_PIS'), x['pis'].get('CST', ''), False), ('BC PIS', it.n('VL_BC_PIS'), x['pis'].get('vBC', 0), True), ('PIS', it.n('VL_PIS'), x['pis'].get('vPIS', 0), True),
                         ('COFINS', it.n('VL_COFINS'), x['cofins'].get('vCOFINS', 0), True)]
            for nome, vs, vx, numerico in pares:
                if numerico:
                    if abs(float(vs) - float(vx)) > TOL:
                        # CFOP muda de saída (XML do fornecedor) para entrada (SPED): esperado. ICMS pode diferir legitimamente (crédito limitado). Reportar mesmo assim.
                        div.append(_ev('NF', c.get('NUM_DOC'), 'item', it.get('NUM_ITEM'), nome, 'SPED', brl(float(vs)), 'XML', brl(float(vx)), 'linha', it['linha'])); total += abs(float(vs) - float(vx))
                else:
                    if nome == 'CFOP':
                        # entrada: espelho do CFOP de saída (5102 -> 1102); compara só o sufixo
                        if c.get('IND_OPER') == '0' and (vs or '')[1:] != (vx or '')[1:] and not ((vx or '')[1:] in ('101', '102') and (vs or '')[1:] in ('101', '102', '556', '551', '403', '401', '407')):
                            div.append(_ev('NF', c.get('NUM_DOC'), 'item', it.get('NUM_ITEM'), 'CFOP', 'SPED', vs, 'XML', vx))
                        elif c.get('IND_OPER') == '1' and vs != vx:
                            div.append(_ev('NF', c.get('NUM_DOC'), 'item', it.get('NUM_ITEM'), 'CFOP', 'SPED', vs, 'XML', vx))
                    elif (vs or '') != (vx or '') and c.get('IND_OPER') == '1':
                        div.append(_ev('NF', c.get('NUM_DOC'), 'item', it.get('NUM_ITEM'), nome, 'SPED', vs, 'XML', vx))
    if div:
        A.add(regra='X03', categoria='Risco', tributo='ICMS/IPI' if tipo == 'fiscal' else 'PIS/COFINS', titulo='XML × %s: %d divergência(s) item a item em %d documento(s) cruzados' % ('SPED Fiscal' if tipo == 'fiscal' else 'EFD Contribuições', len(div), n_docs),
              descricao='Campos do C170 diferentes do XML. Em entradas, ICMS menor no SPED pode ser crédito limitado de propósito (uso/consumo, Simples); ICMS maior no SPED é crédito sem lastro. Em saídas, qualquer diferença é erro.',
              evidencia=div[:40], valor=total, grau='Alto', acao='Conferir cada linha; retificar o SPED ou emitir CC-e/nota complementar', prioridade='Alta', **base)
    # Simples Nacional: crédito acima do permitido
    exc = []; total_exc = 0.0
    for c in s['regs'].get('C100', []):
        d = idx_nfe.get(c.get('CHV_NFE'))
        if not d or c.get('IND_OPER') != '0' or d['emit'].get('crt') != '1':
            continue
        permitido = sum(it['icms'].get('vCredICMSSN', 0) for it in d['itens'])
        cred = sum(f.n('VL_ICMS') for f in c['filhos'] if f['REG'] == 'C190')
        if cred > permitido + TOL and tipo == 'fiscal':
            exc.append(_ev('NF', c.get('NUM_DOC'), d['emit']['nome'][:30], 'crédito SPED', brl(cred), 'permitido (vCredICMSSN)', brl(permitido))); total_exc += cred - permitido
    if exc:
        A.add(regra='X06', categoria='Risco', tributo='ICMS', titulo='Crédito de ICMS acima do permitido em compras de fornecedor do Simples Nacional (%d nota(s))' % len(exc), descricao='O crédito é limitado ao valor informado na nota (LC 123/2006, art. 23).', evidencia=exc[:15], valor=total_exc, grau='Alto', acao='Estornar o excesso', prioridade='Alta', **base)

# ---------------------------------------------------------------- saídas: regras só possíveis com o XML
def xml_saidas_regras(e, s, idx_nfe, A, base):
    if not idx_nfe:
        return
    comp = base['periodo']; uf = e['uf']
    emitidas = [d for d in idx_nfe.values() if d['emit']['cnpj'] == e['cnpj'] and d['emissao'][:7] == comp and d['tpNF'] == '1']
    if not emitidas:
        return
    # DIFAL não contribuinte
    sem_difal = []; base_difal = 0.0
    for d in emitidas:
        if d['idDest'] == '2' and d['indFinal'] == '1' and d['dest'].get('indIEDest') == '9':
            if d['totais'].get('vICMSUFDest', 0) <= 0 and not any(it['ufdest'] for it in d['itens']) and d['emit'].get('crt') != '1':
                sem_difal.append(_ev('NF', d['numero'], 'dest', d['dest']['uf'], brl(d['totais']['vNF']))); base_difal += d['totais']['vProd']
    if sem_difal:
        A.add(regra='X07', categoria='Risco', tributo='DIFAL', titulo='%d venda(s) interestadual(is) a consumidor final não contribuinte sem DIFAL (ICMSUFDest)' % len(sem_difal), descricao='Base %s. DIFAL devido à UF de destino (EC 87/2015, LC 190/2022).' % brl(base_difal), evidencia=sem_difal[:15], valor=base_difal * 0.07, estimativa=True, memoria='base × ~7%% (diferença típica; calcular por UF de destino)' % (), grau='Alto', acao='Apurar por UF e recolher (GNRE); corrigir a emissão', prioridade='Alta', **base)
    # ICMS na base do PIS/COFINS pelo XML
    n = 0; icms_dentro = 0.0
    for d in emitidas:
        for it in d['itens']:
            if it['pis'].get('CST') in ('01', '02') and it['icms'].get('vICMS', 0) > 0 and it['pis'].get('vBC', 0) >= it['vProd'] - it['vDesc'] - TOL:
                n += 1; icms_dentro += it['icms']['vICMS']
    if n:
        A.add(regra='X10', categoria='Pago a maior', tributo='PIS/COFINS', titulo='XML: ICMS dentro da base de PIS/COFINS em %d item(ns) de saída' % n, descricao='A base de PIS/COFINS no XML é igual ao valor do produto, sem excluir o ICMS (%s).' % brl(icms_dentro), valor=icms_dentro * 0.0925, estimativa=True, memoria='ICMS %s × 9,25%% (não cumulativo)' % brl(icms_dentro), grau='Alto', acao='Ajustar o ERP e retificar EFD Contribuições/DCTF', prioridade='Alta', **base)
    # 2026+: IBS/CBS
    if comp >= '2026-01':
        sem = [d for d in emitidas if not d['ibscbs']]
        if sem:
            A.add(regra='X08', categoria='Risco', tributo='IBS/CBS', titulo='%d NF-e de 2026 sem o grupo IBSCBS' % len(sem), descricao='Em 2026 o destaque de CBS (0,9%%) e IBS (0,1%%) é obrigatório; a dispensa de recolhimento depende de cumprir a obrigação acessória.', evidencia=[_ev('NF', d['numero'], d['emissao']) for d in sem[:10]], valor=sum(d['totais']['vProd'] for d in sem) * 0.01, estimativa=True, grau='Alto', acao='Atualizar o emissor (NT 2025.002) e reemitir/complementar', prioridade='Alta', **base)
    # alíquota interestadual por UF de destino (XML permite checar exatamente)
    err = []; excesso = 0.0
    for d in emitidas:
        if d['idDest'] != '2' or d['emit'].get('crt') == '1':
            continue
        for it in d['itens']:
            ic = it['icms']
            if ic.get('CST') in ('00', '10', '20', '70') and ic.get('pICMS', 0) > 0:
                esperada = aliq_interestadual(uf, d['dest']['uf'], importado=ic.get('orig') in ('1', '2', '3', '6', '7', '8'))
                if abs(ic['pICMS'] - esperada) > 0.01:
                    err.append(_ev('NF', d['numero'], 'dest', d['dest']['uf'], 'item', it['nItem'], 'orig', ic.get('orig'), 'aliq', ic['pICMS'], 'esperada', esperada)); excesso += ic['vBC'] * (ic['pICMS'] - esperada) / 100
    if err:
        A.add(regra='X11', categoria='Pago a maior' if excesso > 0 else 'Risco', tributo='ICMS', titulo='Alíquota interestadual diferente da esperada por origem/destino em %d item(ns)' % len(err), descricao='Diferença líquida %s (%s).' % (brl(abs(excesso)), 'a maior' if excesso > 0 else 'a menor'), evidencia=err[:20], valor=abs(excesso), grau='Alto', acao='Conferir origem (FCI/importado) e destino; corrigir emissão', prioridade='Alta', **base)

# ---------------------------------------------------------------- CT-e
def cte_x_d100(e, s, idx_cte, A, base):
    if not idx_cte:
        return
    comp = base['periodo']
    tomados = {ch: d for ch, d in idx_cte.items() if d['tomador_cnpj'] == e['cnpj'] and d['emissao'][:7] == comp}
    d100 = {r.get('CHV_CTE'): r for r in s['regs'].get('D100', []) if r.get('CHV_CTE')}
    faltam = [d for ch, d in tomados.items() if ch not in d100]
    if faltam:
        icms = sum(d['icms'].get('vICMS', 0) for d in faltam)
        A.add(regra='X05', categoria='Recuperação', tributo='ICMS', titulo='%d CT-e tomado(s) sem escrituração no D100' % len(faltam), descricao='Frete de %s com ICMS de %s não escriturado (crédito perdido quando vinculado a operação com crédito).' % (brl(sum(d['vTPrest'] for d in faltam)), brl(icms)), evidencia=[_ev('CT-e', d['numero'], d['chave'], d['UFIni'] + '>' + d['UFFim'], brl(d['vTPrest'])) for d in faltam[:15]], valor=icms, grau='Alto', acao='Escriturar D100/D190 com crédito', prioridade='Alta', **base)
    # CT-e onde a empresa NÃO é tomadora mas foi escriturado com crédito
    indevidos = [r for ch, r in d100.items() if ch in idx_cte and idx_cte[ch]['tomador_cnpj'] and idx_cte[ch]['tomador_cnpj'] != e['cnpj'] and sum(f.n('VL_ICMS') for f in r['filhos']) > 0]
    if indevidos:
        A.add(regra='X05', categoria='Risco', tributo='ICMS', titulo='%d CT-e escriturado(s) com crédito sem a empresa ser a tomadora' % len(indevidos), descricao='Só o tomador (quem paga o frete) credita o ICMS do transporte.', evidencia=[_ev('CT-e', r.get('NUM_DOC'), r.get('CHV_CTE'), 'tomador no XML', idx_cte[r.get('CHV_CTE')]['tomador_cnpj']) for r in indevidos[:15]], valor=sum(sum(f.n('VL_ICMS') for f in r['filhos']) for r in indevidos), grau='Alto', acao='Estornar', prioridade='Alta', **base)

# ---------------------------------------------------------------- NFS-e x A100
def nfse_x_a100(e, s, nfses, A, base):
    if not nfses:
        return
    comp = base['periodo']
    tomadas = [d for d in nfses if d['tomador']['cnpj'] == e['cnpj'] and (d.get('competencia') or d['emissao'])[:7] == comp]
    prestadas = [d for d in nfses if d['prestador']['cnpj'] == e['cnpj'] and (d.get('competencia') or d['emissao'])[:7] == comp]
    a100_ent = [r for r in s['regs'].get('A100', []) if r.get('IND_OPER') == '0']
    a100_sai = [r for r in s['regs'].get('A100', []) if r.get('IND_OPER') == '1']
    regime = s['empresa'].get('cod_inc_trib', '')
    if tomadas and regime in ('1', '3'):
        chaves = {r.get('CHV_NFSE') for r in a100_ent} | {r.get('NUM_DOC') for r in a100_ent}
        faltam = [d for d in tomadas if d['chave'] not in chaves and d['numero'] not in chaves]
        if faltam:
            tot = sum(d['vServ'] for d in faltam)
            A.add(regra='X09', categoria='Recuperação', tributo='PIS/COFINS', titulo='%d NFS-e tomada(s) sem escrituração no A100 (crédito possível)' % len(faltam), descricao='Serviços de %s. Serviços que são insumo (essencialidade), industrialização por encomenda, manutenção, armazenagem e frete geram crédito; administrativos não.' % brl(tot), evidencia=[_ev('NFS-e', d['numero'], d['prestador']['nome'][:30], d.get('cTribNac'), (d.get('xDescServ') or '')[:40], brl(d['vServ'])) for d in faltam[:15]], valor=tot * 0.0925 * 0.5, estimativa=True, memoria='%s × 9,25%% × 50%% (parcela estimada de serviços-insumo)' % brl(tot), grau='Médio', acao='Classificar cada serviço; escriturar A100/A170 com CST 50', prioridade='Média', **base)
    if prestadas:
        receita_nfse = sum(d['vServ'] for d in prestadas)
        receita_a100 = sum(r.n('VL_DOC') for r in a100_sai)
        if receita_a100 < receita_nfse - 1:
            A.add(regra='X09', categoria='Risco', tributo='PIS/COFINS', titulo='Receita de serviços nas NFS-e (%s) maior que a escriturada no A100 (%s)' % (brl(receita_nfse), brl(receita_a100)), descricao='Omissão de receita de serviços na EFD Contribuições (%s).' % brl(receita_nfse - receita_a100), valor=(receita_nfse - receita_a100) * (0.0925 if regime in ('1', '3') else 0.0365), grau='Alto', acao='Retificar', prioridade='Alta', **base)
        # ISS fora do escopo, mas inconsistência óbvia: serviço com ICMS?
        e.setdefault('tabela_nfse', []).append({'periodo': comp, 'prestadas': len(prestadas), 'receita': round(receita_nfse, 2), 'iss': round(sum(d['vISS'] for d in prestadas), 2), 'tomadas': len(tomadas), 'valor_tomado': round(sum(d['vServ'] for d in tomadas), 2)})

# ---------------------------------------------------------------- Fiscal x Contrib
def fiscal_x_contrib(e, A):
    for comp in sorted(set(e['fiscal']) & set(e['contrib'])):
        f = e['fiscal'][comp]; c = e['contrib'][comp]
        base = dict(empresa=e['cnpj'], nome=e['nome'], periodo=comp, uf=e['uf'])
        cf = {r.get('CHV_NFE'): r for r in f['regs'].get('C100', []) if r.get('CHV_NFE') and r.get('COD_SIT') in ('00', '01')}
        cc = {r.get('CHV_NFE'): r for r in c['regs'].get('C100', []) if r.get('CHV_NFE') and r.get('COD_SIT') in ('00', '01')}
        def cfops(r):
            return {x.get('CFOP') for x in r['filhos'] if x['REG'] == 'C190'}
        usa_faturamento = any(x.get('CFOP') in CFOP_FAT_FUTURO for r in c['regs'].get('C100', []) for x in r['filhos'] if x['REG'] == 'C190')
        def gera_receita(r):
            cs = cfops(r)
            if usa_faturamento and cs & CFOP_ENTREGA_FUTURA and not cs - CFOP_ENTREGA_FUTURA:
                return False  # receita já reconhecida no x922
            return bool(cs & (CFOP_RECEITA | (CFOP_FAT_FUTURO if usa_faturamento else set())))
        so_f = [cf[k] for k in set(cf) - set(cc) if cf[k].get('IND_OPER') == '1' and gera_receita(cf[k])]
        so_c = [cc[k] for k in set(cc) - set(cf)]
        # a EFD Contribuições pode consolidar saídas (C180/C190) sem C100; só alertar se ela tem C100 de saída
        tem_c100_saida_contrib = any(r.get('IND_OPER') == '1' for r in c['regs'].get('C100', []))
        if so_f and tem_c100_saida_contrib:
            A.add(regra='X01', categoria='Risco', tributo='PIS/COFINS', titulo='%d NF-e de saída no SPED Fiscal que não estão na EFD Contribuições' % len(so_f), descricao='Receita possivelmente omitida na apuração de PIS/COFINS: %s.' % brl(sum(r.n('VL_DOC') for r in so_f)), evidencia=[_ev('NF', r.get('NUM_DOC'), r.get('CHV_NFE'), brl(r.n('VL_DOC'))) for r in so_f[:15]], valor=sum(r.n('VL_DOC') for r in so_f) * 0.0925, estimativa=True, grau='Alto', acao='Conciliar os dois arquivos', prioridade='Alta', **base)
        if so_c:
            A.add(regra='X01', categoria='Risco', tributo='ICMS', titulo='%d NF-e na EFD Contribuições que não estão no SPED Fiscal' % len(so_c), descricao='Documento escriturado para PIS/COFINS e ausente do ICMS/IPI.', evidencia=[_ev('NF', r.get('NUM_DOC'), r.get('CHV_NFE'), brl(r.n('VL_DOC'))) for r in so_c[:15]], valor=sum(r.n('VL_ICMS') for r in so_c), grau='Alto', acao='Conciliar', prioridade='Alta', **base)
        dif = [(cf[k], cc[k]) for k in set(cf) & set(cc) if abs(cf[k].n('VL_DOC') - cc[k].n('VL_DOC')) > TOL]
        if dif:
            A.add(regra='X01', categoria='Risco', tributo='SPED', titulo='%d NF-e com VL_DOC diferente entre SPED Fiscal e EFD Contribuições' % len(dif), descricao='', evidencia=[_ev('NF', a.get('NUM_DOC'), 'Fiscal', brl(a.n('VL_DOC')), 'Contrib', brl(b.n('VL_DOC'))) for a, b in dif[:15]], valor=sum(abs(a.n('VL_DOC') - b.n('VL_DOC')) for a, b in dif), grau='Médio', acao='Conciliar', **base)

# ---------------------------------------------------------------- espelho entre empresas do lote
def espelho_entre_empresas(empresas, A):
    """Se o lote traz o SPED de duas empresas que operam entre si, as saídas de uma têm que ser as entradas da outra."""
    lista = list(empresas.values())
    for a in lista:
        for b in lista:
            if a is b:
                continue
            for comp in set(a['fiscal']) & set(b['fiscal']):
                sa = a['fiscal'][comp]; sb = b['fiscal'][comp]
                # saídas de A cujo participante é B
                part_b = {cod for cod, p in sa['participantes'].items() if p.get('CNPJ') == b['cnpj']}
                if not part_b:
                    continue
                saidas = {c.get('CHV_NFE'): c for c in sa['regs'].get('C100', []) if c.get('IND_OPER') == '1' and c.get('COD_PART') in part_b and c.get('COD_SIT') in ('00', '01')}
                entradas = {c.get('CHV_NFE'): c for c in sb['regs'].get('C100', []) if c.get('IND_OPER') == '0' and c.get('CHV_NFE')}
                todas_entradas_b = set()
                for s2 in b['fiscal'].values():
                    todas_entradas_b |= {c.get('CHV_NFE') for c in s2['regs'].get('C100', [])}
                faltam = [c for ch, c in saidas.items() if ch and ch not in todas_entradas_b]
                base = dict(empresa=b['cnpj'], nome=b['nome'], periodo=comp, uf=b['uf'])
                if faltam:
                    icms = sum(c.n('VL_ICMS') for c in faltam); tot = sum(c.n('VL_DOC') for c in faltam)
                    A.add(regra='F15', categoria='Recuperação', tributo='ICMS', titulo='%d nota(s) emitida(s) por %s para esta empresa não escriturada(s) na entrada' % (len(faltam), a['nome'][:30]),
                          descricao='As duas empresas estão no lote. %s escriturou saídas para %s (valor %s, ICMS %s) que não aparecem nas entradas desta em nenhum mês fornecido: crédito não tomado ou omissão de entrada.' % (a['nome'][:25], b['nome'][:25], brl(tot), brl(icms)),
                          evidencia=[_ev('NF', c.get('NUM_DOC'), c.get('CHV_NFE'), data_sped(c.get('DT_DOC')), brl(c.n('VL_DOC')), 'ICMS', brl(c.n('VL_ICMS'))) for c in faltam[:20]], valor=icms, grau='Alto', acao='Escriturar as entradas', prioridade='Alta', **base)
                # CST espelho: saída com CST 10/00 (ICMS próprio destacado) e entrada sem crédito
                sem_cred = []; icms_perdido = 0.0
                for ch, c in saidas.items():
                    ent = entradas.get(ch)
                    if not ent:
                        continue
                    if c.n('VL_ICMS') > 0 and ent.n('VL_ICMS') <= 0:
                        grp = [cfop_info(f.get('CFOP'))['grupo'] for f in ent['filhos'] if f['REG'] == 'C190']
                        if any(g in ('revenda', 'revenda_st', 'industrializacao', 'industrializacao_st') for g in grp):
                            sem_cred.append(_ev('NF', c.get('NUM_DOC'), 'ICMS na saída de ' + a['nome'][:15], brl(c.n('VL_ICMS')), 'CST entrada', ','.join(sorted({f.get('CST_ICMS') for f in ent['filhos'] if f['REG'] == 'C190'})))); icms_perdido += c.n('VL_ICMS')
                if sem_cred:
                    A.add(regra='F15', categoria='Recuperação', tributo='ICMS', titulo='%d nota(s) de %s com ICMS destacado escrituradas aqui sem crédito' % (len(sem_cred), a['nome'][:30]),
                          descricao='O fornecedor (no lote) debitou ICMS próprio na saída; esta empresa escriturou a entrada sem crédito (CST 60/90). Se a mercadoria é para revenda/industrialização, o crédito é devido: %s.' % brl(icms_perdido),
                          evidencia=sem_cred[:20], valor=icms_perdido, grau='Alto', acao='Retificar as entradas com CST 10/00 e crédito', prioridade='Alta', **base)
                # energia: A é indústria sem C500 e B (mesmo endereço) tem C500
                if a['perfil']['atividade'] == 'industria' and not sa['regs'].get('C500') and sb['regs'].get('C500') and (a['info'].get('endereco') and a['info'].get('endereco') == b['info'].get('endereco')):
                    v = sum(r.n('VL_DOC') for r in sb['regs']['C500'])
                    A.add(regra='F09c', categoria='Planejamento', tributo='ICMS', titulo='Energia da planta industrial faturada no CNPJ de %s (mesmo endereço)' % b['nome'][:30],
                          descricao='%s (indústria) não tem energia escriturada; %s (mesmo endereço) tem %s no mês, sem direito a crédito de ICMS. Transferir a unidade consumidora (ou ratear com laudo) para a indústria libera o crédito.' % (a['nome'][:25], b['nome'][:25], brl(v)),
                          valor=v * ALIQ_INTERNA_UF.get(a['uf'], 18) / 100 * 0.8, estimativa=True, memoria='%s × %.1f%% × 80%% (parcela industrial estimada)' % (brl(v), ALIQ_INTERNA_UF.get(a['uf'], 18)), grau='Médio', acao='Titularidade da UC ou contrato de rateio com laudo técnico', prioridade='Média', empresa=a['cnpj'], nome=a['nome'], periodo=comp, uf=a['uf'])

# ---------------------------------------------------------------- NCM do XML x cadastro
def ncm_xml_x_cadastro(empresas, idx_nfe, A):
    if not idx_nfe:
        return
    for e in empresas.values():
        div = Counter()
        for s in e['fiscal'].values():
            for c in s['regs'].get('C100', []):
                d = idx_nfe.get(c.get('CHV_NFE'))
                if not d:
                    continue
                xml_itens = {it['nItem']: it for it in d['itens']}
                for it in c['filhos']:
                    if it['REG'] != 'C170':
                        continue
                    x = xml_itens.get(it.get('NUM_ITEM')); cad = s['itens'].get(it.get('COD_ITEM'))
                    if x and cad and x['NCM'] and cad.get('COD_NCM') and x['NCM'] != cad.get('COD_NCM'):
                        div[(it.get('COD_ITEM'), cad.get('DESCR_ITEM'), cad.get('COD_NCM'), x['NCM'], d['emit']['nome'][:25] if c.get('IND_OPER') == '0' else 'própria')] += 1
        if div:
            A.add(regra='X12', categoria='NCM', tributo='Cadastro', titulo='%d item(ns) com NCM no cadastro (0200) diferente da NCM do XML' % len(div),
                  descricao='Fornecedor e cliente classificam o mesmo produto de forma diferente. Um dos dois está errado; a NCM define IPI, ST, PIS/COFINS monofásico e benefícios.',
                  evidencia=[_ev(k[0], k[1][:35], 'cadastro', k[2], 'XML', k[3], k[4], '%d nota(s)' % v) for k, v in div.most_common(20)], grau='Médio', acao='Revisar a classificação com laudo/parecer; corrigir cadastro ou pedir CC-e ao fornecedor', prioridade='Média', empresa=e['cnpj'], nome=e['nome'], periodo=sorted(e['fiscal'])[-1], uf=e['uf'])
