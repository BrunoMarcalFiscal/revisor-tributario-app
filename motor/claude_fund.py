# -*- coding: utf-8 -*-
"""Fundamentação aprofundada com Claude (via Claude Code CLI, `claude -p`). Opcional, com cache.
O motor de regras já traz a base legal fixa; aqui o Claude escreve o parecer do achado com os números reais,
avalia o grau de segurança e lista premissas a confirmar. Só é chamado para os achados escolhidos."""
import json, os, subprocess, shutil, re
from .util import carregar_json, salvar_json, hash_curto

PROMPT = """Você é um revisor tributário sênior (tributos federais e estaduais brasileiros). Analise o ACHADO abaixo, produzido por um motor de regras sobre SPED Fiscal, EFD Contribuições e XML, e escreva um parecer curto, técnico e defensável.

Regras obrigatórias:
- Nunca invente artigo, convênio, solução de consulta ou julgado. Se não tiver certeza do dispositivo exato, escreva "verificar dispositivo" e descreva a regra.
- Considere a UF, a atividade e o regime informados. Regras de ICMS mudam por estado.
- Distinga: (a) lei expressa/tese pacificada, (b) jurisprudência favorável sem lei expressa, (c) tese controvertida.
- Quantifique só com base nos números do achado; se a estimativa depender de premissa, diga qual.
- Não recomende planejamento abusivo.
- Escreva em português do Brasil, sem travessão (use vírgula ou parênteses).

Responda SOMENTE com um JSON válido, sem texto antes ou depois, neste formato:
{"parecer": "3 a 6 frases explicando o achado, o direito/risco e o valor",
 "fundamentacao_complementar": "dispositivos e julgados adicionais aos já citados, ou 'nenhuma'",
 "grau_seguranca": "Alto|Médio|Baixo",
 "motivo_grau": "1 frase",
 "premissas_a_confirmar": ["..."],
 "passos": ["passo 1", "passo 2"],
 "prazo_decadencial": "1 frase sobre o prazo aplicável"}

CONTEXTO DA EMPRESA: %s
ACHADO: %s
BASE LEGAL JÁ CITADA PELO MOTOR: %s"""

def disponivel():
    return shutil.which('claude') is not None

def fundamentar(achados, empresas, pasta_saida, limite=15, modelo=None, log=print):
    cache_path = os.path.join(pasta_saida, 'fundamentacao-cache.json')
    cache = carregar_json(cache_path, {})
    if not disponivel():
        log('  claude CLI não encontrado; pulando a fundamentação aprofundada')
        return 0
    teste = subprocess.run(['claude', '-p', '--output-format', 'text'], input='responda apenas: ok', capture_output=True, text=True, timeout=120).stdout
    if 'Not logged in' in teste or 'login' in teste.lower()[:80]:
        log('  o Claude Code do terminal não está logado. Abra o Terminal, rode `claude`, digite /login uma vez e repita com --fundamentar.')
        return 0
    escolhidos = [a for a in achados if a['prioridade'] == 'Alta' or a['valor'] > 0][:limite]
    feitos = 0
    for a in escolhidos:
        chave = hash_curto(a['regra'], a['empresa'], a['periodo'], a['titulo'], round(a['valor']))
        if chave in cache:
            a['parecer_claude'] = cache[chave]; continue
        e = empresas.get(a['empresa'], {})
        contexto = {'empresa': e.get('nome'), 'uf': e.get('uf'), 'perfil': e.get('perfil'), 'perfil_inferido': {k: v for k, v in (e.get('perfil_inferido') or {}).items() if k != 'grupos'}}
        resumo = {k: a.get(k) for k in ('regra', 'categoria', 'tributo', 'titulo', 'descricao', 'valor', 'estimativa', 'memoria', 'grau', 'acao', 'periodo')}
        resumo['evidencia'] = a.get('evidencia', [])[:8]
        prompt = PROMPT % (json.dumps(contexto, ensure_ascii=False), json.dumps(resumo, ensure_ascii=False), a.get('fundamentacao', ''))
        cmd = ['claude', '-p', '--output-format', 'text']
        if modelo:
            cmd += ['--model', modelo]
        log('  fundamentando %s %s %s...' % (a['regra'], a['nome'][:20], a['periodo']))
        try:
            out = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=240).stdout
            m = re.search(r'\{.*\}', out, re.S)
            parecer = json.loads(m.group(0)) if m else {'parecer': out.strip()[:2000]}
        except Exception as ex:
            parecer = {'parecer': 'falha ao consultar o Claude: %s' % ex}
        a['parecer_claude'] = parecer; feitos += 1
        if 'grau_seguranca' in parecer:  # só guarda resposta válida
            cache[chave] = parecer
            salvar_json(cache_path, cache)
    return feitos
