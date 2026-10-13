# -*- coding: utf-8 -*-
"""Servidor local: tela de entrada (arquivos + perfil das empresas) e dashboard. Só biblioteca padrão."""
import os, json, re, io, shutil, threading, webbrowser, urllib.parse, traceback
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default as email_policy
from . import analise, dashboard, claude_fund, sped
from .util import carregar_json, salvar_json, ler_texto, cnpj_fmt

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRADA = os.path.join(RAIZ, 'entrada'); SAIDA = os.path.join(RAIZ, 'saida')
ESTADO = {'rodando': False, 'log': [], 'ultimo': None, 'erro': None}

# quadros de entrada: cada tipo de arquivo na sua pasta (o motor lê tudo e classifica pelo conteúdo; a pasta organiza e confere)
QUADROS = [('sped_fiscal', 'SPED Fiscal (EFD ICMS/IPI)', '.txt ou .zip'), ('efd_contrib', 'EFD Contribuições', '.txt ou .zip'),
           ('nfe_entrada', 'XML NF-e de entrada', '.xml ou .zip'), ('nfe_saida', 'XML NF-e de saída', '.xml ou .zip'),
           ('nfse_prestadas', 'XML NFS-e prestadas', '.xml ou .zip'), ('nfse_tomadas', 'XML NFS-e tomadas', '.xml ou .zip'),
           ('cte', 'XML CT-e', '.xml ou .zip'), ('eventos', 'Eventos (cancelamento, carta de correção)', '.xml ou .zip'),
           ('geral', 'ZIP com tudo / outros', 'qualquer arquivo')]
FAMILIA = {'sped_fiscal': 'fiscal', 'efd_contrib': 'contrib', 'nfe_entrada': 'nfe', 'nfe_saida': 'nfe', 'nfse_prestadas': 'nfse', 'nfse_tomadas': 'nfse', 'cte': 'cte', 'eventos': 'evento'}
DESTINO = {'fiscal': 'sped_fiscal', 'contrib': 'efd_contrib', 'cte': 'cte', 'evento': 'eventos'}


def _pasta_quadro(q):
    return ENTRADA if q == 'geral' else os.path.join(ENTRADA, q)


def _familia(nome, dados):
    """O que o arquivo é, pelo conteúdo: fiscal, contrib, nfe, cte, nfse, evento ou None."""
    from . import sped
    n = nome.lower()
    if n.endswith('.txt'):
        primeira = dados[:400].decode('latin-1', 'ignore').splitlines()[0] if dados else ''
        return sped.detectar_tipo(primeira)
    if n.endswith('.xml'):
        t = dados[:6000].decode('utf-8', 'ignore')
        if 'procEvento' in t or '<evento' in t or '<infEvento' in t or 'pedRegEvento' in t:
            return 'evento'
        if 'cteProc' in t or '<CTe' in t or '<infCte' in t:
            return 'cte'
        if 'CompNfse' in t or '<NFSe' in t or '<Nfse' in t or 'infNFSe' in t or 'InfNfse' in t:
            return 'nfse'
        if 'nfeProc' in t or '<NFe' in t or '<infNFe' in t:
            return 'nfe'
    return None


def _cnpj_emitente(fam, dados):
    """CNPJ de quem emitiu (NF-e: emit; NFS-e: prestador), para saber se é da empresa (saída/prestada) ou de terceiro."""
    t = dados[:20000].decode('utf-8', 'ignore')
    blocos = {'nfe': [r'<emit>(.*?)</emit>'], 'nfse': [r'<prest>(.*?)</prest>', r'<emit>(.*?)</emit>', r'<Prestador(?:Servico)?>(.*?)</Prestador(?:Servico)?>', r'<IdentificacaoPrestador>(.*?)</IdentificacaoPrestador>']}.get(fam, [])
    for b in blocos:
        m = re.search(b, t, re.S)
        if m:
            c = re.search(r'<(?:CNPJ|Cnpj)>(\d{14})<', m.group(1))
            if c:
                return c.group(1)
    return ''


def _resumo_quadros():
    out = {}
    for q, _, _ in QUADROS:
        pasta = _pasta_quadro(q)
        n = tam = 0
        ult = 0
        if os.path.isdir(pasta):
            itens = [os.path.join(pasta, x) for x in os.listdir(pasta)] if q == 'geral' else [os.path.join(r, x) for r, _, fs in os.walk(pasta) for x in fs]
            for f in itens:
                if os.path.isfile(f) and not os.path.basename(f).startswith('.') and not f.endswith('perfil.json'):
                    n += 1; tam += os.path.getsize(f); ult = max(ult, os.path.getmtime(f))
        out[q] = {'qtd': n, 'mb': round(tam / 1048576, 1), 'ultimo': ult}
    return out


def _empresas_detectadas():
    """Lê só o 0000 de cada SPED da pasta (rápido) para montar o formulário de perfil."""
    import zipfile, glob, tempfile
    emp = {}
    arquivos = []
    rels = {}
    for f in sorted(glob.glob(os.path.join(ENTRADA, '**', '*'), recursive=True)):
        if not os.path.isfile(f) or os.path.basename(f).startswith('.'):
            continue
        if f.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(f) as z:
                    for n in z.namelist():
                        if n.lower().endswith('.txt'):
                            raw = z.read(n)[:4000]
                            arquivos.append((os.path.basename(n) + ' (em ' + os.path.basename(f) + ')', raw))
            except zipfile.BadZipFile:
                arquivos.append((os.path.basename(f) + ' (zip inválido)', b''))
        elif f.lower().endswith('.txt'):
            nome_ = os.path.basename(f)
            rels[nome_] = os.path.relpath(f, ENTRADA)
            arquivos.append((nome_, open(f, 'rb').read(4000)))
        elif f.lower().endswith('.xml'):
            continue  # XML são contados por quadro (podem ser milhares)
    lista = []
    for nome, raw in arquivos:
        info = {'arquivo': nome, 'tipo': 'XML' if raw is None else '?', 'empresa': '', 'cnpj': '', 'periodo': '', 'rel': rels.get(nome, nome)}
        if raw:
            try:
                linha = raw.decode('utf-8', errors='replace').splitlines()[0]
            except Exception:
                linha = ''
            tipo = sped.detectar_tipo(linha)
            c = linha.strip().strip('|').split('|')
            if tipo == 'fiscal' and len(c) > 8:
                info.update(tipo='EFD ICMS/IPI', empresa=c[5], cnpj=re.sub(r'\D', '', c[6]), uf=c[8], periodo='%s/%s' % (c[3][2:4], c[3][4:8]), ind_ativ=c[14] if len(c) > 14 else '')
            elif tipo == 'contrib':
                i = next((k for k in (5, 6, 4) if k < len(c) and re.fullmatch(r'\d{8}', c[k] or '')), 5)
                info.update(tipo='EFD Contribuições', empresa=c[i + 2] if len(c) > i + 2 else '', cnpj=re.sub(r'\D', '', c[i + 3]) if len(c) > i + 3 else '', uf=c[i + 4] if len(c) > i + 4 else '', periodo='%s/%s' % (c[i][2:4], c[i][4:8]))
            else:
                info['tipo'] = 'não reconhecido'
        lista.append(info)
        if info.get('cnpj'):
            e = emp.setdefault(info['cnpj'], {'cnpj': info['cnpj'], 'nome': info['empresa'], 'uf': info.get('uf', ''), 'periodos': set(), 'ind_ativ': ''})
            e['periodos'].add(info['periodo'])
            if info.get('ind_ativ'):
                e['ind_ativ'] = info['ind_ativ']
    for e in emp.values():
        e['periodos'] = sorted(e['periodos'], key=lambda p: p[3:] + p[:2])
    return lista, emp

PAGINA = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisor Tributário · Entrada</title>
<style>
:root{color-scheme:light;--bg:#f4f5f8;--surface:#fff;--surface-2:#eef0f5;--line:#d9dce4;--text:#141824;--text-2:#4d5566;--muted:#7c8494;--navy:#212E50;--navy-2:#2f3f6e;--accent:#2a78d6;--good:#0ca30c;--crit:#d03b3b}
@media (prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#12151d;--surface:#1a1e28;--surface-2:#222735;--line:#2f3546;--text:#f2f3f7;--text-2:#c3c6d1;--muted:#8d93a3;--navy:#1b2440;--navy-2:#26325a;--accent:#3987e5}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
header{background:var(--navy);color:#fff;padding:14px 22px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}header b{font-size:16px;white-space:nowrap}header a{color:#fff;opacity:.8;margin-left:auto;white-space:nowrap}
main{max-width:1080px;margin:0 auto;padding:22px 20px 80px}
h2{font-size:16px;margin:26px 0 8px}.sub{color:var(--muted);font-size:12.5px;margin-bottom:10px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:14px}
.drop{border:2px dashed var(--line);border-radius:12px;padding:26px;text-align:center;color:var(--text-2);cursor:pointer;background:var(--surface-2)}.drop.on{border-color:var(--accent);color:var(--accent)}
.quadros{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:6px}
.qd{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:12px 14px;display:flex;flex-direction:column;gap:8px}
.qd h4{margin:0;font-size:13px;display:flex;justify-content:space-between;align-items:center;gap:6px}.qd .n{font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--surface-2);color:var(--muted);white-space:nowrap}.qd .n.ok{background:rgba(12,163,12,.12);color:var(--good)}
.qd .drop{padding:16px 10px;font-size:12.5px}.qd .pe{display:flex;justify-content:space-between;font-size:11.5px;color:var(--muted)}.qd .pe button{font:inherit;font-size:11.5px;background:none;border:0;color:var(--crit);cursor:pointer;padding:0}
@media (max-width:900px){.quadros{grid-template-columns:1fr 1fr}}@media (max-width:560px){.quadros{grid-template-columns:1fr}}
.tw{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:12.5px}td.arq{font-family:ui-monospace,Menlo,monospace;font-size:11px;word-break:break-all;min-width:280px;max-width:460px}th{text-align:left;color:var(--text-2);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--line)}td{padding:6px 8px;border-bottom:1px solid var(--line)}
.btn{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--surface-2);color:var(--text);cursor:pointer}.btn.p{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}.btn.x{color:var(--crit);padding:2px 8px;font-size:12px}
.f{display:grid;grid-template-columns:repeat(3,1fr);gap:10px 16px}.f label{display:flex;flex-direction:column;gap:3px;font-size:11.5px;color:var(--text-2)}.f label.w{grid-column:1/-1}
.f input,.f select,.f textarea{font:inherit;padding:7px 9px;border:1px solid var(--line);border-radius:7px;background:var(--surface-2);color:var(--text)}
.f .chk{flex-direction:row;align-items:center;gap:8px;font-size:13px;color:var(--text)}
.emp{border-top:3px solid var(--accent)}.emp h3{margin:0 0 10px;font-size:14px}.emp h3 small{color:var(--muted);font-weight:400;margin-left:8px}
.hint{font-size:11.5px;color:var(--muted)}.ok{color:var(--good)}.bad{color:var(--crit)}
#log{background:var(--surface-2);border-radius:8px;padding:10px 12px;font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre-wrap;max-height:260px;overflow:auto}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:14px}
@media (max-width:760px){.f{grid-template-columns:1fr}}
</style></head><body>
<header><b>Revisor Tributário</b><span style="opacity:.75">entrada de dados</span><a href="/dashboard.html" id="lnk-dash">abrir o último dashboard →</a></header>
<main>
<h2>1. Arquivos</h2>
<div class="sub">Cada tipo no seu quadro (arraste ou clique). Pode mandar vários de uma vez e ZIP com centenas de XML. O revisor confere o conteúdo: se um arquivo cair no quadro errado, ele vai para o certo e avisa. Um período de apuração = um arquivo de cada SPED.</div>
<div class="quadros" id="quadros"></div>
<div id="prog" class="hint" style="margin:4px 0 10px"></div>
<div class="card">
 <h3 style="margin:0 0 8px;font-size:13.5px">SPED recebidos</h3>
 <div class="tw"><table id="arqs"><thead><tr><th>Arquivo</th><th>Tipo</th><th>Empresa</th><th>UF</th><th>Período</th><th></th></tr></thead><tbody></tbody></table></div>
</div>

<h2>2. Perfil de cada empresa</h2>
<div class="sub">O revisor infere atividade e operações pelos próprios arquivos, mas as regras de crédito dependem do que você confirma aqui: regime tributário, atividade, CNAE, benefícios e regimes especiais da UF, equiparação a industrial (IPI). Deixe em branco o que não souber.</div>
<div id="perfis"></div>

<h2>3. Gerar a revisão</h2>
<div class="card">
 <div class="f">
  <label class="chk"><input type="checkbox" id="fund"> Pedir ao Claude um parecer aprofundado dos <input type="number" id="fund-n" value="10" min="1" max="60" style="width:70px;margin:0 4px"> achados mais relevantes <span class="hint">(usa o Claude Code instalado no Mac; precisa estar logado no terminal)</span></label>
 </div>
 <div class="bar"><button class="btn p" id="run">Gerar revisão e abrir o dashboard</button><button class="btn" id="save">Salvar só o perfil</button><span id="status" class="hint"></span></div>
 <div id="log" style="margin-top:12px" hidden></div>
</div>
</main>
<script>
const $=s=>document.querySelector(s); let ESTADO={arquivos:[],empresas:{},perfil:{}};
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function carregar(){ ESTADO=await (await fetch('/estado')).json(); render(); }
function render(){
 desenharQuadros();
 $('#arqs tbody').innerHTML = ESTADO.arquivos.map(a=>'<tr><td class="arq">'+esc(a.arquivo.split(' (em ')[0])+(a.arquivo.includes(' (em ')?'<br><span class="hint">dentro de '+esc(a.arquivo.split(' (em ')[1].replace(/\)$/,''))+'</span>':'')+'</td><td>'+esc(a.tipo)+'</td><td>'+esc(a.empresa)+'</td><td>'+esc(a.uf||'')+'</td><td>'+esc(a.periodo)+'</td><td>'+(a.arquivo.includes(' (em ')?'':'<button class="btn x" onclick="remover(\''+esc(a.rel||a.arquivo)+'\')">remover</button>')+'</td></tr>').join('') || '<tr><td colspan="6" class="hint">nenhum SPED ainda</td></tr>';
 const P=ESTADO.perfil||{};
 $('#perfis').innerHTML = Object.values(ESTADO.empresas).map(e=>{ const p=P[e.cnpj]||{}; const sel=(n,v,ops)=>'<select name="'+n+'">'+ops.map(o=>'<option value="'+o[0]+'"'+(String(v||'')===o[0]?' selected':'')+'>'+o[1]+'</option>').join('')+'</select>';
  return '<div class="card emp" data-cnpj="'+e.cnpj+'"><h3>'+esc(e.nome)+'<small>'+esc(e.cnpj)+' · '+esc(e.uf)+' · '+e.periodos.join(', ')+(e.ind_ativ?' · IND_ATIV '+e.ind_ativ+(e.ind_ativ==='0'?' (industrial/equiparado)':' (outros)'):'')+'</small></h3><div class="f">'
  +'<label>Regime tributário'+sel('regime_tributario',p.regime_tributario,[['','(não informado)'],['Lucro Real','Lucro Real'],['Lucro Presumido','Lucro Presumido'],['Simples Nacional','Simples Nacional']])+'</label>'
  +'<label>Atividade principal'+sel('atividade',p.atividade,[['','(deixar o revisor inferir)'],['industria','Indústria'],['comercio','Comércio'],['servico','Serviços'],['misto','Misto']])+'</label>'
  +'<label>UF do estabelecimento<input name="uf" value="'+esc(p.uf||e.uf)+'" maxlength="2"></label>'
  +'<label>CNAE principal<input name="cnae_principal" value="'+esc(p.cnae_principal||'')+'" placeholder="ex.: 2063-1/00"></label>'
  +'<label>CNAEs secundários<input name="cnaes_secundarios" value="'+esc((p.cnaes_secundarios||[]).join(', '))+'" placeholder="separados por vírgula"></label>'
  +'<label>Equiparado a industrial (IPI)?'+sel('equiparado_industrial_ipi',p.equiparado_industrial_ipi==null?'':String(p.equiparado_industrial_ipi),[['','(não sei)'],['true','Sim'],['false','Não']])+'</label>'
  +'<label>Exporta?'+sel('exporta',p.exporta==null?'':String(p.exporta),[['','(deixar o revisor inferir)'],['true','Sim'],['false','Não']])+'</label>'
  +'<label>Regime de PIS/COFINS'+sel('regime_pis_cofins_informado',p.regime_pis_cofins_informado,[['','(vem do 0110 da EFD Contribuições)'],['nao_cumulativo','Não cumulativo'],['cumulativo','Cumulativo'],['misto','Misto']])+'</label>'
  +'<label>Substituto tributário (ST) em quais UFs?<input name="ufs_st" value="'+esc(p.ufs_st||'')+'" placeholder="ex.: SP, MG (ou deixar em branco)"></label>'
  +'<label class="w">Benefícios fiscais vigentes<input name="beneficios" value="'+esc((p.beneficios||[]).join('; '))+'" placeholder="ex.: crédito presumido X (RICMS art. Y); redução de base Z; separar por ponto e vírgula"></label>'
  +'<label class="w">Regimes especiais / TTD / termos de acordo<input name="regimes_especiais" value="'+esc((p.regimes_especiais||[]).join('; '))+'" placeholder="ex.: TTD 409; regime especial de ST; separar por ponto e vírgula"></label>'
  +'<label class="w">Observações para o revisor<textarea name="observacoes" rows="2" placeholder="ex.: energia da fábrica está em nome da coligada; produtos importados com FCI; unidade em área de livre comércio">'+esc(p.observacoes||'')+'</textarea></label>'
  +'</div></div>'; }).join('') || '<div class="card hint">As empresas aparecem aqui depois que você enviar os SPED.</div>';
 $('#lnk-dash').style.display = ESTADO.tem_dashboard?'':'none';
}
function lerPerfil(){ const P={}; document.querySelectorAll('.emp').forEach(c=>{ const o={_empresa:ESTADO.empresas[c.dataset.cnpj].nome}; c.querySelectorAll('[name]').forEach(i=>{ let v=i.value.trim(); if(['cnaes_secundarios'].includes(i.name)) v=v?v.split(',').map(x=>x.trim()).filter(Boolean):[]; else if(['beneficios','regimes_especiais'].includes(i.name)) v=v?v.split(';').map(x=>x.trim()).filter(Boolean):[]; else if(['equiparado_industrial_ipi','exporta'].includes(i.name)) v=v===''?null:v==='true'; o[i.name]=v; }); P[c.dataset.cnpj]=o; }); return P; }
async function salvar(){ await fetch('/perfil',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(lerPerfil())}); $('#status').textContent='perfil salvo'; }
$('#save').onclick=salvar;
$('#run').onclick=async()=>{ await salvar(); $('#run').disabled=true; $('#log').hidden=false; $('#log').textContent='iniciando...'; $('#status').textContent='';
 const r=await fetch('/revisar',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({fundamentar:$('#fund').checked?parseInt($('#fund-n').value)||10:0})});
 const t=setInterval(async()=>{ const s=await (await fetch('/progresso')).json(); $('#log').textContent=s.log.join('\n'); $('#log').scrollTop=1e9; if(!s.rodando){ clearInterval(t); $('#run').disabled=false; if(s.erro){$('#status').innerHTML='<span class="bad">'+esc(s.erro)+'</span>';} else { ESTADO.tem_dashboard=true; render(); location.href='/dashboard.html'; } } },700); };
async function enviar(files, quadro){ if(!files.length)return; const fd=new FormData(); [...files].forEach(f=>fd.append('arquivo',f,f.name)); const nome=(ESTADO.quadros_def.find(q=>q.id===quadro)||{}).nome||''; $('#prog').textContent='enviando '+files.length+' arquivo(s) para '+nome+'...'; const r=await fetch('/upload?quadro='+encodeURIComponent(quadro||'geral'),{method:'POST',body:fd}); const j=await r.json(); $('#prog').textContent=(j.ok?j.msg:'erro: '+j.msg); await carregar(); }
async function remover(rel){ await fetch('/remover',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rel:rel})}); await carregar(); }
async function limparQuadro(q, nome){ if(!confirm('Apagar todos os arquivos do quadro "'+nome+'"?')) return; await fetch('/limpar-quadro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({quadro:q})}); await carregar(); }
function desenharQuadros(){
  const Q=ESTADO.quadros||{};
  $('#quadros').innerHTML=(ESTADO.quadros_def||[]).map(q=>{ const r=Q[q.id]||{qtd:0,mb:0}; const dt=r.ultimo?new Date(r.ultimo*1000).toLocaleDateString('pt-BR'):'';
    return '<div class="qd"><h4>'+esc(q.nome)+'<span class="n'+(r.qtd?' ok':'')+'">'+(r.qtd?r.qtd+' arquivo'+(r.qtd>1?'s':''):'vazio')+'</span></h4>'
     +'<div class="drop" data-q="'+q.id+'">Arraste aqui ou clique<br><span class="hint">'+esc(q.ext)+'</span><input type="file" multiple hidden></div>'
     +'<div class="pe"><span>'+(r.qtd?r.mb.toString().replace('.',',')+' MB · '+dt:'')+'</span>'+(r.qtd&&q.id!=='geral'?'<button onclick="limparQuadro(\''+q.id+'\',\''+esc(q.nome)+'\')">limpar</button>':'')+'</div></div>'; }).join('');
  document.querySelectorAll('#quadros .drop').forEach(d=>{ const inp=d.querySelector('input'); d.onclick=()=>inp.click(); inp.onchange=e=>enviar(e.target.files, d.dataset.q);
    ['dragenter','dragover'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.add('on');})); ['dragleave','drop'].forEach(ev=>d.addEventListener(ev,e=>{e.preventDefault();d.classList.remove('on');})); d.addEventListener('drop',e=>enviar(e.dataTransfer.files, d.dataset.q)); });
}
carregar();
</script></body></html>'''

def _guardar(nome, dados_, quadro, raizes, avisos):
    """Guarda um arquivo recebido no quadro certo (reclassifica pelo conteúdo/CNPJ do emitente). True se guardou."""
    nome = os.path.basename(nome)
    if not nome.lower().endswith(('.txt', '.zip', '.xml')):
        avisos.append('%s: tipo de arquivo não aceito' % nome); return False
    destino = quadro
    fam = _familia(nome, dados_)
    if nome.lower().endswith('.txt') and not fam:
        avisos.append('%s: recusado (não é SPED Fiscal nem EFD Contribuições: a 1ª linha não é o registro 0000)' % nome); return False
    esperado = FAMILIA.get(quadro)
    if fam in ('nfe', 'nfse') and raizes:
        emi = _cnpj_emitente(fam, dados_)
        if emi:
            propria = emi[:8] in raizes
            certo = {('nfe', True): 'nfe_saida', ('nfe', False): 'nfe_entrada', ('nfse', True): 'nfse_prestadas', ('nfse', False): 'nfse_tomadas'}[(fam, propria)]
            if certo != quadro:
                destino = certo
                avisos.append('%s: emitida %s, guardada em "%s"' % (nome, 'pela empresa' if propria else 'por terceiro', dict((q, t) for q, t, _ in QUADROS)[certo]))
    if destino == quadro and esperado and fam and fam != esperado:
        destino = DESTINO.get(fam, 'geral')
        avisos.append('%s parece %s: guardado em "%s"' % (nome, {'fiscal': 'SPED Fiscal', 'contrib': 'EFD Contribuições', 'nfe': 'NF-e', 'cte': 'CT-e', 'nfse': 'NFS-e', 'evento': 'evento'}[fam], dict((q, t) for q, t, _ in QUADROS)[destino]))
    elif esperado and not fam and not nome.lower().endswith('.zip'):
        avisos.append('%s: conteúdo não reconhecido como %s (guardado assim mesmo)' % (nome, dict((q, t) for q, t, _ in QUADROS)[quadro]))
    pasta = _pasta_quadro(destino); os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, nome), 'wb') as f:
        f.write(dados_)
    return True

def _guardar_atualizados(arquivos):
    """SPED Fiscal / EFD Contribuições atualizados: entrada/atualizados/ (vencem o arquivo do mesmo mês). [(nome, bytes)] -> (aceitos, recusados)."""
    import datetime
    pasta = os.path.join(ENTRADA, 'atualizados'); os.makedirs(pasta, exist_ok=True)
    carimbo = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
    ok, recusados = [], []
    antes = {}
    try:
        from . import contexto as _ctx
        for c_, e_ in _ctx.carregar(ENTRADA, log=lambda *a: None)['empresas'].items():
            for t_ in ('fiscal', 'contrib'):
                for comp_, s_ in e_[t_].items():
                    antes[(t_, c_, comp_)] = s_['arquivo']
    except Exception:
        pass
    for nome, conteudo in arquivos:
        primeira = conteudo[:400].decode('latin-1', 'ignore').splitlines()[0] if conteudo else ''
        tipo = sped.detectar_tipo(primeira)
        if not tipo:
            recusados.append({'arquivo': nome, 'motivo': 'não é SPED Fiscal nem EFD Contribuições (a 1ª linha não é o registro 0000)'}); continue
        alvo = os.path.join(pasta, '%s__%s' % (carimbo, nome))
        open(alvo, 'wb').write(conteudo)
        try:
            s_ = sped.parsear(alvo)
        except Exception as ex:
            os.remove(alvo); recusados.append({'arquivo': nome, 'motivo': 'arquivo ilegível (%s)' % ex}); continue
        cnpj_, comp_ = s_['empresa']['cnpj'], s_['periodo']['comp']
        ok.append({'arquivo': nome, 'tipo': 'SPED Fiscal' if tipo == 'fiscal' else 'EFD Contribuições', 'empresa': s_['empresa']['nome'], 'cnpj': cnpj_,
                   'periodo': comp_, 'substitui': antes.get((s_['tipo'], cnpj_, comp_), '')})
    return ok, recusados

def rec_atual():
    """Oportunidades do último dashboard com o status de hoje (o HTML gerado guarda o status da hora em que foi gerado)."""
    from . import recuperacao
    dados = carregar_json(os.path.join(SAIDA, 'dados.json'), {}) or {}
    rec = dados.get('recuperacao') or {'oportunidades': []}
    st = recuperacao.ler_status()
    for o in rec['oportunidades']:
        s_ = st.get(o['id'], {})
        o['status'] = s_.get('status', 'Identificada'); o['historico'] = s_.get('historico', []); o['valor_recuperado'] = s_.get('valor_recuperado', 0)
    rec['painel'] = recuperacao.painel(rec['oportunidades'], dados.get('achados', []))
    return rec

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=SAIDA, **k)
    def log_message(self, *a):
        pass
    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def _corpo(self):
        n = int(self.headers.get('Content-Length', 0) or 0)
        return self.rfile.read(n) if n else b''
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p == '/api/recuperacao':
            self._json(self._rec_atual()); return
        if p in ('/', '/entrada'):
            b = PAGINA.encode('utf-8'); self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8'); self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p == '/estado':
            lista, emp = _empresas_detectadas()
            self._json({'arquivos': lista, 'empresas': emp, 'perfil': carregar_json(os.path.join(ENTRADA, 'perfil.json'), {}), 'tem_dashboard': os.path.exists(os.path.join(SAIDA, 'dashboard.html')),
                        'quadros': _resumo_quadros(), 'quadros_def': [{'id': q, 'nome': n, 'ext': x} for q, n, x in QUADROS]}); return
        if p == '/progresso':
            self._json({k: v for k, v in ESTADO.items()}); return
        if p == '/dashboard.html' and not os.path.exists(os.path.join(SAIDA, 'dashboard.html')):
            self.send_response(302); self.send_header('Location', '/'); self.end_headers(); return
        return super().do_GET()
    def _rec_atual(self):
        return rec_atual()

    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        try:
            if p == '/api/recuperacao/status':
                from . import recuperacao
                d = json.loads(self._corpo() or b'{}')
                try:
                    r = recuperacao.gravar_status(d.get('id', ''), d.get('status', ''), d.get('obs', ''), d.get('valor_recuperado'))
                except ValueError as e:
                    self._json({'erro': str(e)}, 400); return
                rec = self._rec_atual()
                self._json(dict(r, painel=rec['painel'])); return
            if p == '/upload':
                ct = self.headers.get('Content-Type', '')
                raw = b'Content-Type: ' + ct.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + self._corpo()
                msg = BytesParser(policy=email_policy).parsebytes(raw)
                n = 0
                quadro = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get('quadro', ['geral'])[0]
                if quadro not in dict((q, 1) for q, _, _ in QUADROS):
                    quadro = 'geral'
                avisos = []
                raizes = {c[:8] for c in _empresas_detectadas()[1]}
                for part in msg.iter_parts():
                    nome = part.get_filename()
                    if not nome:
                        continue
                    if _guardar(nome, part.get_payload(decode=True), quadro, raizes, avisos):
                        n += 1
                self._json({'ok': True, 'msg': '%d arquivo(s) recebido(s)' % n + ('. ' + '; '.join(avisos[:8]) if avisos else ''), 'avisos': avisos}); return
            if p == '/limpar-quadro':
                d = json.loads(self._corpo() or b'{}'); q = d.get('quadro')
                if q in FAMILIA:
                    shutil.rmtree(_pasta_quadro(q), ignore_errors=True)
                self._json({'ok': True}); return
            if p == '/upload-atualizado':
                # SPED Fiscal / EFD Contribuições atualizados: vão para entrada/atualizados/ e vencem o arquivo do mesmo mês
                import datetime, zipfile as _zip, io as _io
                from . import sped
                ct = self.headers.get('Content-Type', '')
                raw = b'Content-Type: ' + ct.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + self._corpo()
                msg = BytesParser(policy=email_policy).parsebytes(raw)
                pasta = os.path.join(ENTRADA, 'atualizados'); os.makedirs(pasta, exist_ok=True)
                carimbo = datetime.datetime.now().strftime('%Y%m%d%H%M%S')
                arquivos = []
                for part in msg.iter_parts():
                    nome = part.get_filename()
                    if not nome:
                        continue
                    dados_ = part.get_payload(decode=True)
                    if nome.lower().endswith('.zip'):
                        with _zip.ZipFile(_io.BytesIO(dados_)) as z:
                            for n_ in z.namelist():
                                if n_.lower().endswith('.txt') and not os.path.basename(n_).startswith('.'):
                                    arquivos.append((os.path.basename(n_), z.read(n_)))
                    elif nome.lower().endswith('.txt'):
                        arquivos.append((os.path.basename(nome), dados_))
                ok, recusados = _guardar_atualizados(arquivos)
                self._json({'ok': True, 'recebidos': ok, 'recusados': recusados}); return
            if p == '/remover':
                d = json.loads(self._corpo() or b'{}')
                alvo = os.path.abspath(os.path.join(ENTRADA, d.get('rel') or os.path.basename(d.get('arquivo', ''))))
                if alvo.startswith(os.path.abspath(ENTRADA) + os.sep) and os.path.isfile(alvo):
                    os.remove(alvo)
                self._json({'ok': True}); return
            if p == '/perfil':
                d = json.loads(self._corpo() or b'{}')
                os.makedirs(ENTRADA, exist_ok=True)
                salvar_json(os.path.join(ENTRADA, 'perfil.json'), d)
                self._json({'ok': True}); return
            if p == '/revisar':
                if ESTADO['rodando']:
                    self._json({'ok': False, 'msg': 'já está rodando'}); return
                d = json.loads(self._corpo() or b'{}')
                threading.Thread(target=_rodar, args=(int(d.get('fundamentar') or 0),), daemon=True).start()
                self._json({'ok': True}); return
        except Exception as ex:
            self._json({'ok': False, 'msg': str(ex)}, 500); return
        self.send_error(404)

def _rodar(fundamentar):
    ESTADO.update(rodando=True, log=[], erro=None)
    log = lambda *a: ESTADO['log'].append(' '.join(str(x) for x in a))
    try:
        log('lendo os arquivos...')
        ctx, achados = analise.executar(ENTRADA, log=log)
        if not ctx['empresas']:
            raise RuntimeError('nenhum SPED reconhecido na pasta de entrada')
        for i in ctx['inventario']:
            log('  %s %s %s %s' % ('✓' if i['ok'] else '✗', i['tipo'], i.get('empresa', ''), i.get('periodo', '')))
        log('%d achados' % len(achados))
        if fundamentar:
            log('parecer aprofundado com Claude (%d achados)...' % fundamentar)
            claude_fund.fundamentar(achados, ctx['empresas'], SAIDA, limite=fundamentar, log=log)
        r = analise.resumo(ctx, achados)
        p = dashboard.gerar(ctx, achados, r, SAIDA)
        log('dashboard gerado: %s' % p)
        ESTADO['ultimo'] = p
    except Exception as ex:
        ESTADO['erro'] = str(ex); log(traceback.format_exc())
    finally:
        ESTADO['rodando'] = False

def servir(porta=8765, abrir=True):
    os.makedirs(ENTRADA, exist_ok=True); os.makedirs(SAIDA, exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', porta), Handler)
    url = 'http://localhost:%d/' % porta
    print('Revisor Tributário em %s  (Ctrl+C para parar)' % url)
    if abrir:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
