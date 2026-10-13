# Revisor Tributário (web)

Revisão de SPED Fiscal, EFD Contribuições e XML (NF-e, NFS-e, CT-e) por empresa: recuperação de créditos dos últimos 5 anos com SELIC e prescrição, teses do Lucro Real e análise estratégica. Cada empresa tem as próprias revisões, com arquivos, perfil e status separados.

Só biblioteca padrão do Python. Nada aqui transmite, retifica ou chama a Receita.

    python3 web.py                       # http://localhost:8780, sem login, só neste computador
    REVISOR_USUARIO=x REVISOR_SENHA=y REVISOR_HOST=0.0.0.0 python3 web.py   # aberto na rede: login obrigatório

Dados em `REVISOR_DADOS` (padrão `./web_dados`): `indice.json` + `revisoes/<cnpj>/<id>/`.
