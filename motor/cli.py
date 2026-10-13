# -*- coding: utf-8 -*-
"""Linha de comando do motor, para quem chama de fora (o cockpit). Cada revisão tem a sua pasta:
<pasta>/entrada, <pasta>/saida e <pasta>/recuperacao_status.json. Só biblioteca padrão. Nada é transmitido.

  python3 -m motor.cli <comando> --pasta <pasta> [--quadro q] [--raiz 12345678] [--rel caminho]
  comandos: estado | receber | atualizado | limpar | remover | perfil | rodar | rec | status
  receber/atualizado leem do stdin uma lista JSON [{"nome": "...", "caminho": "/tmp/..."}]; perfil e status leem um objeto JSON.
  Saída: um JSON no stdout (rodar escreve o log linha a linha no stderr e o JSON no fim)."""
import os, sys, json, shutil, argparse, traceback


def _json(obj, code=0):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, default=str))
    sys.stdout.flush()
    sys.exit(code)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('comando')
    ap.add_argument('--pasta', required=True)
    ap.add_argument('--quadro', default='geral')
    ap.add_argument('--raiz', action='append', default=[])
    ap.add_argument('--rel', default='')
    a = ap.parse_args(argv)
    pasta = os.path.abspath(a.pasta)
    entrada, saida = os.path.join(pasta, 'entrada'), os.path.join(pasta, 'saida')
    os.makedirs(entrada, exist_ok=True); os.makedirs(saida, exist_ok=True)
    os.environ['REVISOR_STATUS_ARQ'] = os.path.join(pasta, 'recuperacao_status.json')
    from . import servidor as S
    S.ENTRADA, S.SAIDA = entrada, saida
    from .util import carregar_json, salvar_json
    c = a.comando
    try:
        if c == 'estado':
            lista, emp = S._empresas_detectadas()
            _json({'arquivos': lista, 'empresas': emp, 'perfil': carregar_json(os.path.join(entrada, 'perfil.json'), {}),
                   'tem_dashboard': os.path.exists(os.path.join(saida, 'dashboard.html')),
                   'quadros': S._resumo_quadros(), 'quadros_def': [{'id': q, 'nome': n, 'ext': x} for q, n, x in S.QUADROS]})
        if c == 'receber':
            itens = json.load(sys.stdin)
            quadro = a.quadro if a.quadro in dict((q, 1) for q, _, _ in S.QUADROS) else 'geral'
            raizes = {x[:8] for x in a.raiz if x} | {x[:8] for x in S._empresas_detectadas()[1]}
            avisos, n = [], 0
            for it in itens:
                if S._guardar(it['nome'], open(it['caminho'], 'rb').read(), quadro, raizes, avisos):
                    n += 1
            _json({'ok': True, 'recebidos': n, 'avisos': avisos,
                   'msg': '%d arquivo(s) recebido(s)' % n + ('. ' + '; '.join(avisos[:8]) if avisos else '')})
        if c == 'atualizado':
            import zipfile
            arquivos = []
            for it in json.load(sys.stdin):
                nome, dados_ = os.path.basename(it['nome']), open(it['caminho'], 'rb').read()
                if nome.lower().endswith('.zip'):
                    with zipfile.ZipFile(it['caminho']) as z:
                        for n_ in z.namelist():
                            if n_.lower().endswith('.txt') and not os.path.basename(n_).startswith('.'):
                                arquivos.append((os.path.basename(n_), z.read(n_)))
                elif nome.lower().endswith('.txt'):
                    arquivos.append((nome, dados_))
            ok, recusados = S._guardar_atualizados(arquivos)
            _json({'ok': True, 'recebidos': ok, 'recusados': recusados})
        if c == 'limpar':
            if a.quadro in S.FAMILIA:
                shutil.rmtree(S._pasta_quadro(a.quadro), ignore_errors=True)
            _json({'ok': True})
        if c == 'remover':
            alvo = os.path.abspath(os.path.join(entrada, a.rel))
            if alvo.startswith(entrada + os.sep) and os.path.isfile(alvo):
                os.remove(alvo)
            _json({'ok': True})
        if c == 'perfil':
            salvar_json(os.path.join(entrada, 'perfil.json'), json.load(sys.stdin))
            _json({'ok': True})
        if c == 'rodar':
            from . import analise, dashboard
            log = lambda *x: (sys.stderr.write(' '.join(str(y) for y in x) + '\n'), sys.stderr.flush())
            log('lendo os arquivos...')
            ctx, achados = analise.executar(entrada, log=log)
            if not ctx['empresas']:
                _json({'ok': False, 'erro': 'nenhum SPED reconhecido nos arquivos desta revisão'}, 2)
            for i in ctx['inventario']:
                log('  %s %s %s %s' % ('✓' if i['ok'] else '✗', i['tipo'], i.get('empresa', ''), i.get('periodo', '')))
            log('%d achados' % len(achados))
            r = analise.resumo(ctx, achados)
            dashboard.gerar(ctx, achados, r, saida)
            rec = S.rec_atual()
            P = rec.get('painel') or {}
            emp = [{'cnpj': k, 'nome': e.get('nome', ''), 'periodos': sorted(e.get('fiscal', {}).keys() | e.get('contrib', {}).keys())} for k, e in ctx['empresas'].items()]
            log('painel gerado')
            _json({'ok': True, 'empresas': emp, 'achados': len(achados),
                   'resumo': {'potencial': P.get('potencial', 0), 'lucro_real': P.get('lucro_real', 0), 'consolidado': P.get('consolidado', 0),
                              'oportunidades': P.get('qtd', 0), 'recuperado': P.get('recuperado', 0)}})
        if c == 'rec':
            _json(S.rec_atual())
        if c == 'status':
            from . import recuperacao
            d = json.load(sys.stdin)
            try:
                r = recuperacao.gravar_status(d.get('id', ''), d.get('status', ''), d.get('obs', ''), d.get('valor_recuperado'), d.get('usuario', ''))
            except ValueError as e:
                _json({'erro': str(e)}, 3)
            _json(dict(r, painel=S.rec_atual()['painel']))
        _json({'erro': 'comando desconhecido: %s' % c}, 1)
    except SystemExit:
        raise
    except Exception as ex:
        sys.stderr.write(traceback.format_exc())
        _json({'ok': False, 'erro': str(ex)}, 1)


if __name__ == '__main__':
    main()
