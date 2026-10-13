#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Revisor Tributário na web: várias empresas, cada revisão separada por empresa.

Mesmo motor do uso local (pasta motor/). Cada revisão tem a sua pasta:
  <REVISOR_DADOS>/revisoes/<cnpj>/<id>/{entrada,saida,recuperacao_status.json}
O motor é chamado por `python3 -m motor.cli` (um processo por operação), então duas
pessoas mexendo em revisões diferentes não se atrapalham. Só biblioteca padrão.
Nada aqui transmite, retifica ou chama a Receita.

  python3 web.py                      porta 8780, só neste computador
  REVISOR_USUARIO=x REVISOR_SENHA=y PORT=10000 RENDER=1 python3 web.py   (aberto na rede: login obrigatório)
"""
import os, sys, json, re, time, hmac, hashlib, secrets, threading, subprocess, shutil, urllib.parse, urllib.request, datetime, tempfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

RAIZ = os.path.dirname(os.path.abspath(__file__))
DADOS = os.path.abspath(os.environ.get('REVISOR_DADOS') or os.path.join(RAIZ, 'web_dados'))
REVS = os.path.join(DADOS, 'revisoes')
INDICE = os.path.join(DADOS, 'indice.json')
TMP = os.path.join(DADOS, '_tmp')
USUARIO = os.environ.get('REVISOR_USUARIO') or ''
SENHA = os.environ.get('REVISOR_SENHA') or ''
MAX_UPLOAD = int(os.environ.get('REVISOR_UPLOAD_MB') or 800) * 1024 * 1024
TRAVA = threading.RLock()
PROGRESSO = {}
REGIMES = ['Lucro Real', 'Lucro Presumido', 'Simples Nacional']


def agora():
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def so_digitos(s):
    return re.sub(r'\D', '', str(s or ''))


def cnpj_valido(c):
    c = so_digitos(c)
    if len(c) != 14 or c == c[0] * 14:
        return False
    def dv(base, pesos):
        s = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return '0' if s < 2 else str(11 - s)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(c[:12], p1)
    d2 = dv(c[:12] + d1, [6] + p1)
    return c[12:] == d1 + d2


# ── índice (empresas e revisões) ─────────────────────────────────────────────

def ler_indice():
    with TRAVA:
        try:
            with open(INDICE, encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            d = {}
        d.setdefault('empresas', {})
        d.setdefault('revisoes', [])
        d.setdefault('proximo_id', 1)
        return d


def gravar_indice(d):
    with TRAVA:
        os.makedirs(DADOS, exist_ok=True)
        tmp = INDICE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        os.replace(tmp, INDICE)


class Erro(Exception):
    def __init__(self, msg, status=400):
        super().__init__(msg)
        self.status = status


def revisao(rid, d=None):
    d = d or ler_indice()
    for r in d['revisoes']:
        if r['id'] == int(rid) and not r.get('arquivada'):
            return r
    raise Erro('Revisão não encontrada', 404)


def pasta_da(r):
    return os.path.join(REVS, so_digitos(r['cnpj']), str(int(r['id'])))


def atualizar(rid, **campos):
    with TRAVA:
        d = ler_indice()
        r = revisao(rid, d)
        r.update(campos)
        r['atualizado_em'] = agora()
        gravar_indice(d)
        return r


def com_empresa(r, d):
    e = d['empresas'].get(r['cnpj'], {})
    return dict(r, empresa=e.get('nome', ''), regime=e.get('regime', ''), rodando=bool(PROGRESSO.get(r['id'], {}).get('rodando')))


# ── ponte com o motor ────────────────────────────────────────────────────────

def cli(r, comando, args=(), stdin=None, timeout=900):
    cmd = [sys.executable, '-m', 'motor.cli', comando, '--pasta', pasta_da(r)] + list(args)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    p = subprocess.run(cmd, cwd=RAIZ, input=(json.dumps(stdin) if stdin is not None else None), capture_output=True, text=True, timeout=timeout, env=env)
    try:
        j = json.loads(p.stdout) if p.stdout else None
    except ValueError:
        j = None
    if j is None:
        sys.stderr.write(p.stderr[-3000:])
        raise Erro('O motor falhou (%s): %s' % (comando, (p.stderr.strip().splitlines() or ['sem saída'])[-1]), 500)
    if p.returncode == 3 and j.get('erro'):
        raise Erro(j['erro'], 400)
    if p.returncode and j.get('erro'):
        raise Erro(j['erro'], 500)
    return j


def raizes(r):
    return ['--raiz', so_digitos(r['cnpj'])[:8]]


def estado(r):
    e = cli(r, 'estado')
    raiz = so_digitos(r['cnpj'])[:8]
    e['cnpjs_de_outra_empresa'] = [c for c in (e.get('empresas') or {}) if c[:8] != raiz]
    return e


def rodar(rid):
    r = revisao(rid)
    rid = r['id']
    if PROGRESSO.get(rid, {}).get('rodando'):
        return {'ok': False, 'msg': 'Esta revisão já está rodando'}
    st = {'rodando': True, 'log': [], 'erro': None}
    PROGRESSO[rid] = st
    atualizar(rid, situacao='rodando', erro=None)

    def trabalho():
        try:
            p = subprocess.Popen([sys.executable, '-m', 'motor.cli', 'rodar', '--pasta', pasta_da(r)], cwd=RAIZ,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=dict(os.environ, PYTHONIOENCODING='utf-8'))
            for linha in p.stderr:
                linha = linha.rstrip('\n')
                if linha:
                    st['log'].append(linha)
                    del st['log'][:-2000]
            out = p.stdout.read()
            p.wait()
            try:
                j = json.loads(out)
            except ValueError:
                j = None
            if p.returncode == 0 and j and j.get('ok'):
                resumo = dict(j.get('resumo') or {}, achados=j.get('achados'), empresas=j.get('empresas'))
                atualizar(rid, situacao='pronta', erro=None, ultima_execucao=agora(), resumo=resumo)
            else:
                st['erro'] = (j or {}).get('erro') or (st['log'][-1] if st['log'] else 'motor saiu com código %s' % p.returncode)
                atualizar(rid, situacao='erro', erro=st['erro'][:2000])
        except Exception as ex:
            st['erro'] = str(ex)
            try:
                atualizar(rid, situacao='erro', erro=str(ex)[:2000])
            except Exception:
                pass
        finally:
            st['rodando'] = False
    threading.Thread(target=trabalho, daemon=True).start()
    return {'ok': True}


def progresso(rid):
    st = PROGRESSO.get(int(rid))
    if st:
        return {'rodando': st['rodando'], 'log': st['log'][-200:], 'erro': st['erro']}
    r = revisao(rid)
    return {'rodando': False, 'log': [], 'erro': r.get('erro') if r.get('situacao') == 'erro' else None}


def nome_por_cnpj(cnpj):
    try:
        with urllib.request.urlopen('https://brasilapi.com.br/api/cnpj/v1/%s' % cnpj, timeout=8) as resp:
            j = json.loads(resp.read().decode('utf-8'))
        return j.get('razao_social') or ''
    except Exception:
        return ''


# ── sessão ───────────────────────────────────────────────────────────────────

def _segredo():
    p = os.path.join(DADOS, '.segredo')
    try:
        return open(p, 'rb').read()
    except Exception:
        os.makedirs(DADOS, exist_ok=True)
        s = secrets.token_bytes(32)
        with open(p, 'wb') as f:
            f.write(s)
        try:
            os.chmod(p, 0o600)
        except Exception:
            pass
        return s


def token_sessao(usuario):
    exp = int(time.time()) + 12 * 3600
    corpo = '%s|%d' % (usuario, exp)
    sig = hmac.new(_segredo(), corpo.encode(), hashlib.sha256).hexdigest()
    return urllib.parse.quote('%s|%s' % (corpo, sig))


def ler_sessao(tok):
    try:
        usuario, exp, sig = urllib.parse.unquote(tok).rsplit('|', 2)
        ok = hmac.compare_digest(sig, hmac.new(_segredo(), ('%s|%s' % (usuario, exp)).encode(), hashlib.sha256).hexdigest())
        return usuario if ok and int(exp) > time.time() else None
    except Exception:
        return None


# ── multipart sem carregar o arquivo inteiro na memória ─────────────────────

def ler_multipart(handler):
    ct = handler.headers.get('Content-Type', '')
    m = re.search(r'boundary=(?:"([^"]+)"|([^;]+))', ct)
    if not m:
        raise Erro('envio sem arquivos')
    boundary = (m.group(1) or m.group(2)).strip().encode()
    total = int(handler.headers.get('Content-Length') or 0)
    if total > MAX_UPLOAD:
        raise Erro('envio grande demais (limite %d MB)' % (MAX_UPLOAD // 1048576))
    resta = [total]
    os.makedirs(TMP, exist_ok=True)

    def ler():
        if resta[0] <= 0:
            return b''
        b = handler.rfile.read(min(1 << 16, resta[0]))
        resta[0] -= len(b)
        return b

    buf = b''
    abre = b'--' + boundary + b'\r\n'
    while abre not in buf:
        b = ler()
        if not b:
            raise Erro('envio incompleto')
        buf += b
    buf = buf[buf.index(abre) + len(abre):]
    delim = b'\r\n--' + boundary
    arquivos, campos = [], {}
    try:
        while True:
            while b'\r\n\r\n' not in buf:
                b = ler()
                if not b:
                    raise Erro('envio incompleto')
                buf += b
            cab, buf = buf.split(b'\r\n\r\n', 1)
            cab = cab.decode('utf-8', 'replace')
            nome = re.search(r'filename="([^"]*)"', cab)
            campo = re.search(r'name="([^"]*)"', cab)
            if nome and nome.group(1):
                fd, caminho = tempfile.mkstemp(dir=TMP)
                saida = os.fdopen(fd, 'wb')
                arquivos.append({'nome': os.path.basename(nome.group(1).replace('\\', '/')), 'caminho': caminho})
            else:
                saida, caminho = None, None
                valor = []
            while True:
                i = buf.find(delim)
                if i >= 0:
                    pedaco, buf = buf[:i], buf[i + len(delim):]
                    saida.write(pedaco) if saida else valor.append(pedaco)
                    break
                if len(buf) > len(delim):
                    pedaco, buf = buf[:-len(delim)], buf[-len(delim):]
                    saida.write(pedaco) if saida else valor.append(pedaco)
                b = ler()
                if not b:
                    raise Erro('envio incompleto')
                buf += b
            if saida:
                saida.close()
            elif campo:
                campos[campo.group(1)] = b''.join(valor).decode('utf-8', 'replace')
            while len(buf) < 2:
                b = ler()
                if not b:
                    break
                buf += b
            if buf[:2] == b'--':
                break
            buf = buf[2:]
    except Exception:
        for a in arquivos:
            try:
                os.remove(a['caminho'])
            except OSError:
                pass
        raise
    while resta[0] > 0 and ler():
        pass
    return campos, arquivos


def apagar_tmp(arquivos):
    for a in arquivos:
        try:
            os.remove(a['caminho'])
        except OSError:
            pass


# ── HTTP ─────────────────────────────────────────────────────────────────────

ROTA_PAINEL = re.compile(r'^/r/(\d+)(/.*)?$')
ROTA_REV = re.compile(r'^/api/revisoes/(\d+)(?:/([a-z\-]+))?$')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *a):
        pass

    # respostas
    def _envia(self, code, corpo, tipo, extra=None):
        if isinstance(corpo, str):
            corpo = corpo.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', tipo)
        self.send_header('Content-Length', str(len(corpo)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def _json(self, obj, code=200):
        self._envia(code, json.dumps(obj, ensure_ascii=False, default=str), 'application/json; charset=utf-8')

    def _redir(self, para, extra=None):
        h = {'Location': para}
        h.update(extra or {})
        self._envia(303, b'', 'text/plain', h)

    def _corpo_json(self):
        n = int(self.headers.get('Content-Length') or 0)
        if n > 2 * 1024 * 1024:
            raise Erro('corpo grande demais')
        raw = self.rfile.read(n) if n else b''
        try:
            return json.loads(raw or b'{}')
        except ValueError:
            raise Erro('JSON inválido')

    def _usuario(self):
        if not USUARIO:
            return 'local'
        for parte in (self.headers.get('Cookie') or '').split(';'):
            k, _, v = parte.strip().partition('=')
            if k == 'rt_sessao':
                return ler_sessao(v)
        return None

    def _exige_login(self, api):
        u = self._usuario()
        if u:
            return u
        if api:
            self._json({'erro': 'Sessão encerrada. Entre de novo.'}, 401)
        else:
            self._redir('/login')
        return None

    def _erro(self, ex):
        if isinstance(ex, Erro):
            self._json({'erro': str(ex)}, ex.status)
        else:
            import traceback
            traceback.print_exc()
            self._json({'erro': 'Erro interno: %s' % ex}, 500)

    # GET
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        p, q = url.path, urllib.parse.parse_qs(url.query)
        try:
            if p == '/saude':
                return self._envia(200, 'ok', 'text/plain')
            if p == '/login':
                return self._envia(200, PAGINA_LOGIN.replace('__ERRO__', ''), 'text/html; charset=utf-8')
            if p == '/sair':
                return self._redir('/login', {'Set-Cookie': 'rt_sessao=; Path=/; Max-Age=0'})
            m = ROTA_PAINEL.match(p)
            if m and not m.group(2):
                return self._redir('/r/%s/' % m.group(1))
            usuario = self._exige_login(p.startswith('/api/') or (m and '/api/' in (m.group(2) or '')))
            if not usuario:
                return
            if p == '/':
                return self._envia(200, PAGINA_APP, 'text/html; charset=utf-8')
            if m:
                return self._painel_get(int(m.group(1)), m.group(2))
            if p == '/api/empresas':
                d = ler_indice()
                lista = []
                for cnpj, e in d['empresas'].items():
                    revs = [r for r in d['revisoes'] if r['cnpj'] == cnpj and not r.get('arquivada')]
                    lista.append(dict(e, cnpj=cnpj, revisoes=len(revs), ultima_revisao=max([r['atualizado_em'] for r in revs] or [''])))
                lista.sort(key=lambda e: (e.get('regime') != 'Lucro Real', (e.get('nome') or '').lower()))
                return self._json({'empresas': lista, 'usuario': usuario})
            if p == '/api/revisoes':
                d = ler_indice()
                cnpj = so_digitos((q.get('cnpj') or [''])[0])
                revs = [com_empresa(r, d) for r in d['revisoes'] if not r.get('arquivada') and (not cnpj or r['cnpj'] == cnpj)]
                revs.sort(key=lambda r: r['atualizado_em'], reverse=True)
                return self._json({'revisoes': revs})
            m = ROTA_REV.match(p)
            if m:
                rid, acao = int(m.group(1)), m.group(2)
                r = revisao(rid)
                if not acao:
                    e = estado(r)
                    return self._json(dict(e, revisao=com_empresa(r, ler_indice()), painel_url='/r/%d/' % rid if e.get('tem_dashboard') else None, progresso=progresso(rid)))
                if acao == 'progresso':
                    return self._json(progresso(rid))
            if p == '/api/consulta-cnpj':
                c = so_digitos((q.get('cnpj') or [''])[0])
                if not cnpj_valido(c):
                    raise Erro('CNPJ inválido')
                return self._json({'cnpj': c, 'nome': nome_por_cnpj(c)})
            self._json({'erro': 'não encontrado'}, 404)
        except Exception as ex:
            self._erro(ex)

    def _painel_get(self, rid, resto):
        r = revisao(rid)
        saida = os.path.join(pasta_da(r), 'saida')
        if resto in ('/', '/index.html', '/dashboard.html'):
            arq = os.path.join(saida, 'dashboard.html')
            if not os.path.exists(arq):
                return self._envia(404, 'Esta revisão ainda não tem painel gerado.', 'text/plain; charset=utf-8')
            html = open(arq, encoding='utf-8').read().replace('<head>', '<head><script>window.REVISOR_COCKPIT=1</script>', 1)
            return self._envia(200, html, 'text/html; charset=utf-8')
        if resto == '/api/recuperacao':
            return self._json(cli(r, 'rec'))
        if resto == '/progresso':
            return self._json(progresso(rid))
        if resto and resto.startswith('/anexos/'):
            alvo = os.path.abspath(os.path.join(saida, 'anexos', os.path.basename(urllib.parse.unquote(resto[8:]))))
            if alvo.startswith(os.path.join(saida, 'anexos') + os.sep) and os.path.isfile(alvo):
                return self._envia(200, open(alvo, 'rb').read(), 'text/csv; charset=utf-8',
                                   {'Content-Disposition': 'attachment; filename="%s"' % os.path.basename(alvo)})
        self._envia(404, 'não encontrado', 'text/plain')

    # POST / PUT / PATCH / DELETE
    def do_POST(self):
        self._escrita('POST')

    def do_PUT(self):
        self._escrita('PUT')

    def do_PATCH(self):
        self._escrita('PATCH')

    def do_DELETE(self):
        self._escrita('DELETE')

    def _escrita(self, metodo):
        url = urllib.parse.urlparse(self.path)
        p, q = url.path, urllib.parse.parse_qs(url.query)
        arquivos = []
        try:
            if p == '/login' and metodo == 'POST':
                n = int(self.headers.get('Content-Length') or 0)
                f = urllib.parse.parse_qs(self.rfile.read(min(n, 4096)).decode('utf-8', 'replace'))
                u, s = (f.get('usuario') or [''])[0], (f.get('senha') or [''])[0]
                if USUARIO and hmac.compare_digest(u, USUARIO) and hmac.compare_digest(s, SENHA):
                    seguro = '; Secure' if os.environ.get('RENDER') else ''
                    return self._redir('/', {'Set-Cookie': 'rt_sessao=%s; Path=/; HttpOnly; SameSite=Lax; Max-Age=43200%s' % (token_sessao(u), seguro)})
                time.sleep(1.5)
                return self._envia(401, PAGINA_LOGIN.replace('__ERRO__', '<p class="erro">Usuário ou senha incorretos.</p>'), 'text/html; charset=utf-8')
            usuario = self._exige_login(True)
            if not usuario:
                return
            m = ROTA_PAINEL.match(p)
            if m and metodo == 'POST':
                rid, resto = int(m.group(1)), m.group(2) or ''
                r = revisao(rid)
                if resto == '/api/recuperacao/status':
                    d = self._corpo_json()
                    d['usuario'] = usuario
                    j = cli(r, 'status', stdin=d)
                    self._resumo_status(rid, j.get('painel'))
                    return self._json(j)
                if resto == '/upload-atualizado':
                    _, arquivos = ler_multipart(self)
                    return self._json(cli(r, 'atualizado', stdin=arquivos))
                if resto == '/revisar':
                    return self._json(rodar(rid))
            if p == '/api/empresas' and metodo == 'POST':
                d = self._corpo_json()
                cnpj = so_digitos(d.get('cnpj'))
                if not cnpj_valido(cnpj):
                    raise Erro('CNPJ inválido')
                nome = (d.get('nome') or '').strip() or nome_por_cnpj(cnpj)
                if not nome:
                    raise Erro('Informe a razão social')
                regime = d.get('regime') if d.get('regime') in REGIMES else ''
                with TRAVA:
                    ind = ler_indice()
                    ind['empresas'][cnpj] = dict(ind['empresas'].get(cnpj, {'criado_em': agora(), 'criado_por': usuario}), nome=nome[:160], regime=regime)
                    gravar_indice(ind)
                return self._json(dict(ind['empresas'][cnpj], cnpj=cnpj), 201)
            if p == '/api/revisoes' and metodo == 'POST':
                d = self._corpo_json()
                cnpj = so_digitos(d.get('cnpj'))
                with TRAVA:
                    ind = ler_indice()
                    if cnpj not in ind['empresas']:
                        raise Erro('Empresa não cadastrada', 404)
                    rid = ind['proximo_id']
                    ind['proximo_id'] = rid + 1
                    titulo = (d.get('titulo') or '').strip()[:120] or 'Revisão de %s' % datetime.date.today().strftime('%d/%m/%Y')
                    r = {'id': rid, 'cnpj': cnpj, 'titulo': titulo, 'situacao': 'rascunho', 'resumo': None, 'erro': None, 'ultima_execucao': None,
                         'arquivada': False, 'criado_por': usuario, 'criado_em': agora(), 'atualizado_em': agora()}
                    ind['revisoes'].append(r)
                    gravar_indice(ind)
                os.makedirs(os.path.join(pasta_da(r), 'entrada'), exist_ok=True)
                regime = ind['empresas'][cnpj].get('regime')
                if regime:
                    cli(r, 'perfil', stdin={cnpj: {'regime_tributario': regime}})
                return self._json(com_empresa(r, ind), 201)
            m = ROTA_REV.match(p)
            if m:
                rid, acao = int(m.group(1)), m.group(2) or ''
                r = revisao(rid)
                if metodo == 'PATCH' and not acao:
                    t = (self._corpo_json().get('titulo') or '').strip()[:120]
                    return self._json(atualizar(rid, titulo=t or r['titulo']))
                if metodo == 'DELETE' and not acao:
                    atualizar(rid, arquivada=True)
                    return self._json({'ok': True})
                if acao == 'upload':
                    _, arquivos = ler_multipart(self)
                    j = cli(r, 'receber', ['--quadro', (q.get('quadro') or ['geral'])[0]] + raizes(r), stdin=arquivos)
                    atualizar(rid)
                    return self._json(j)
                if acao == 'upload-atualizado':
                    _, arquivos = ler_multipart(self)
                    j = cli(r, 'atualizado', stdin=arquivos)
                    atualizar(rid)
                    return self._json(j)
                if acao == 'limpar-quadro':
                    return self._json(cli(r, 'limpar', ['--quadro', str(self._corpo_json().get('quadro'))]))
                if acao == 'remover':
                    return self._json(cli(r, 'remover', ['--rel', str(self._corpo_json().get('rel') or '')]))
                if acao == 'perfil' and metodo == 'PUT':
                    return self._json(cli(r, 'perfil', stdin=self._corpo_json()))
                if acao == 'rodar':
                    return self._json(rodar(rid))
            self._json({'erro': 'não encontrado'}, 404)
        except Exception as ex:
            self._erro(ex)
        finally:
            apagar_tmp(arquivos)

    def _resumo_status(self, rid, P):
        if not P:
            return
        r = revisao(rid)
        res = dict(r.get('resumo') or {})
        res.update(potencial=P.get('potencial', 0), lucro_real=P.get('lucro_real', 0), consolidado=P.get('consolidado', 0),
                   oportunidades=P.get('qtd', 0), recuperado=P.get('recuperado', 0))
        atualizar(rid, resumo=res)


def carregar_paginas():
    global PAGINA_APP, PAGINA_LOGIN
    with open(os.path.join(RAIZ, 'web_app.html'), encoding='utf-8') as f:
        PAGINA_APP = f.read()
    with open(os.path.join(RAIZ, 'web_login.html'), encoding='utf-8') as f:
        PAGINA_LOGIN = f.read()


def main():
    porta = int(os.environ.get('PORT') or 8780)
    publico = bool(os.environ.get('RENDER') or os.environ.get('REVISOR_HOST'))
    if publico and not (USUARIO and SENHA):
        raise SystemExit('Servidor aberto na rede exige REVISOR_USUARIO e REVISOR_SENHA.')
    os.makedirs(REVS, exist_ok=True)
    shutil.rmtree(TMP, ignore_errors=True)
    carregar_paginas()
    # revisões que estavam rodando quando o servidor caiu não ficam presas em "Revisando…"
    with TRAVA:
        d = ler_indice()
        mudou = False
        for r in d['revisoes']:
            if r.get('situacao') == 'rodando':
                r.update(situacao='erro', erro='O servidor reiniciou no meio da revisão. Gere de novo.')
                mudou = True
        if mudou:
            gravar_indice(d)
    host = os.environ.get('REVISOR_HOST') or ('0.0.0.0' if publico else '127.0.0.1')
    srv = ThreadingHTTPServer((host, porta), Handler)
    srv.daemon_threads = True
    print('Revisor Tributário (web) em http://%s:%d/  dados em %s' % (host, porta, DADOS), flush=True)
    srv.serve_forever()


if __name__ == '__main__':
    main()
