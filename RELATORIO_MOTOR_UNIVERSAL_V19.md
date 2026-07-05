# 🧠 Motor Universal de Validação Produto a Produto (v19) — Entregável

## O que foi implementado
Novo módulo `validacao_universal.py`, integrado ao `main.py` como camada
adicional (nenhuma lógica central de cálculo existente foi alterada).

## Arquivos
- `validacao_universal.py` — motor completo (parser, validação, Excel).
- `main.py` — patch: import do módulo + nova página
  **"📊 Auditoria Produto a Produto (Universal)"** no menu lateral.
- `requirements.txt` — adiciona `openpyxl` e `xlsxwriter`.

## Funções-entregáveis (conforme comando)
- `parsear_sped_universal(conteudo: str) -> dict`
  Lê 0000/0150/0200/C100/C170/C190/M100/M200/M500/M600 de qualquer SPED
  (Fiscal ou Contribuições). Nunca quebra se faltar C170 (ex.: SPED de
  serviços/NFSe) — devolve `itens_c170: []` e um aviso.
- `validar_produto_universal(item, regime, uf, empresa_ctx=None) -> dict`
  Aplica todas as regras universais (NCM/TIPI, IPI, ICMS interno/interestadual,
  PIS/COFINS cumulativo/não-cumulativo, CST × monofásico, Tese do Século,
  trava do Simples Nacional, CPF Rural) a um único item C170.
- `validar_lote_universal(itens, regime, uf, batch_size=10000, progress_cb=...)`
  Processa em lotes (streaming-friendly) com callback de progresso —
  pensado para SPEDs com milhões de linhas.
- `gerar_relatorio_produtos_universal(sped_bytes, cnpj, regime, uf) -> bytes`
  Função "tudo em um": SPED em bytes → Excel em bytes.
- `gerar_excel_universal(analise, empresa_info) -> bytes`
  Gera o Excel (abas "Resumo" + "Produto a Produto"), com **xlsxwriter**
  quando disponível (muito mais rápido/leve em memória para arquivos
  grandes) e fallback automático para `openpyxl`.

## Regras universais cobertas
NCM/TIPI (com sugestão por prefixo quando não catalogado), IPI (indústria x
comércio, crédito perdido), ICMS interno/interestadual (Resolução 22/89),
PIS/COFINS cumulativo/não-cumulativo, CST × produto monofásico (bebidas,
cigarros, autopeças, combustíveis, medicamentos, cosméticos → bloqueia
crédito indevido em qualquer setor que revenda esses produtos), Tese do
Século (RE 574.706/PR) item a item, trava do Simples Nacional
(LC 123/2006 Art. 18), e sinalização específica para CPF Rural (insumos
agropecuários, Lei 10.925/2004).

## Base local de NCM (fallback offline)
`FAIXAS_NCM_UNIVERSAL` cobre por prefixo: agropecuária, alimentos, bebidas,
combustíveis, medicamentos/saúde, cosméticos/higiene, autopeças/veículos,
máquinas/equipamentos, construção civil, eletrônicos/informática,
plásticos/borracha, químicos/fertilizantes, têxteis/vestuário, papel/celulose
e mobiliário. A API oficial (Siscomex, via `integrador_rfb`/
`integrador_rfb_expandido`) é usada **somente se o cache local (SQLite) já
tiver sido aquecido previamente** — nenhuma chamada de rede acontece dentro
do laço de validação item a item, para não comprometer a performance em
SPEDs muito grandes.

## Performance testada
- Validação pura: ~29.000 itens/segundo (50.000 itens em 1,7s).
- Geração de Excel (xlsxwriter): ~7.000 linhas/segundo
  (200.000 linhas em ~28s, incluindo formatação condicional e resumo).
- Cache em memória por NCM evita reprocessamento em SPEDs onde o mesmo
  produto se repete em milhares de notas.

## Relatório Excel
Aba **Resumo**: empresa, regime, UF, setor predominante, totais (OK/Alerta/
Erro), Tese do Século, crédito monofásico indevido, trava Simples, %
conformidade, e log de NCMs não catalogados.

Aba **Produto a Produto**: uma linha por item C170, com Setor, NF, Data,
CNPJ/Fornecedor, NCM, Descrição TIPI, Descrição Item, CFOP, CST PIS/COFINS,
Base/Alíquota/Crédito PIS e COFINS, ICMS e IPI (inf. x esperado), flags
SIM/NÃO (Monofásico, Crédito Monofásico Indevido, Tese do Século, Trava
Simples), Status (OK/ALERTA/ERRO), Observações e Hash SHA-256 por linha —
com cores automáticas por status via formatação condicional.

## Autoteste
Executar `python3 validacao_universal.py` roda um autoteste multissetorial
(indústria, comércio/monofásico indevido, agropecuária/CPF rural, têxtil) e
também processa o `sped_exemplo.txt` fornecido, gerando os Excel de exemplo.
