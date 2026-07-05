# 🏛 ResolvRapido Brasil — Briefing de Capacidades v20

**Motor Universal de Validação SPED & Auditoria Fiscal**
*Versão 20 Soberana — Julho 2026*

---

## 1. O QUE É

Plataforma web (Streamlit Cloud) que **recebe qualquer arquivo SPED Fiscal (EFD ICMS/IPI, EFD Contribuições)** e executa auditoria completa — cruzando NCM, CFOP, CST, regime tributário, legislação, jurisprudência e teses tributárias em tempo real.

Funciona para **qualquer empresa brasileira**, independente de setor, porte ou regime.

---

## 2. CAPACIDADES PRINCIPAIS

### 📥 Parser Universal SPED
- Lê registros 0200, C100, C170, C190, H010, 0150, 0000
- Extrai automaticamente: NCM, CFOP, CST PIS/COFINS, valores de BC, alíquotas, ICMS, ICMS-ST
- Detecção automática do regime (Lucro Real, Presumido, Simples Nacional) e UF

### 🔍 Validação Produto a Produto
- **Monofásico**: identifica ~20 setores (combustíveis, bebidas, farmacêuticos, cosméticos, autopeças, pneus, máquinas agrícolas, papel imune, etc.) e bloqueia crédito indevido
- **Tese do Século**: calcula exclusão do ICMS da base PIS/COFINS (RE 574.706/STF)
- **ISS na BC** *(v20)*: exclui ISS da base de cálculo PIS/COFINS por RE 592.616 — alíquota por UF (27 estados mapeados)
- **ICMS-ST Ressarcimento** *(v20)*: detecta ST pago a maior (BC real < BC presumida) e calcula crédito ressarcível (Tema 762/STF)
- **Trava Simples Nacional**: impede créditos para optantes do SN (LC 123/2006)

### 🏪 Detecção Atacado/Varejo *(v20)*
- Classifica empresa via CNAE (grupo 46 = atacado, 47 = varejo) e CFOP
- Aplica regras setoriais específicas por canal de venda

### 📊 5 Perfis de Visão *(v20)*

| Perfil | Foco |
|--------|------|
| **📊 Contador** | Créditos PIS/COFINS, ICMS-ST a ressarcir, ISS excluído, PER/DCOMP, planejamento |
| **🔍 Auditor RFB** | Conformidade, erros, glosas potenciais, NCMs não catalogados, divergências |
| **⚖️ Advogado Tributarista** | Teses em disputa, jurisprudência, valores recuperáveis, risco de autuação |
| **🏛 Juiz/CARF** | Prova documental, hash Merkle SHA-256 (RFC 6962), cadeia de custódia digital |
| **💻 CTO** | Performance, volume, versão do motor, qualidade dos dados, custos operacionais |

Cada perfil transforma o resultado bruto em **métricas, alertas e recomendações** específicas para a função do usuário.

### 🌐 Integrador RFB Expandido
- Consulta alíquotas por NCM (tabela expandida: IPI, PIS, COFINS, ICMS)
- Consulta alíquota ISS por município/UF
- Cache inteligente com fallback para tabelas locais
- Validação de CNPJ (dígitos verificadores)

### 📋 Cálculo de Créditos
- PIS (1,65%) e COFINS (7,60%) sobre BC ajustada
- ICMS CIAP (crédito sobre ativo imobilizado, 1/48 avos)
- Exclusão ICMS da BC (Tese do Século)
- Exclusão ISS da BC (RE 592.616)
- Ressarcimento ICMS-ST (Tema 762)

### 📄 Relatórios e Exportação
- **Excel (.xlsx)**: relatório completo com cores (verde/amarelo/vermelho), formatação monetária, filtros, 10k itens por lote
- **Dashboard interativo**: gráficos de conformidade, distribuição por status, por setor
- **Resumo consolidado**: totais, percentuais, NCMs não catalogados

---

## 3. PÁGINAS DO SISTEMA

O app Streamlit oferece **16 módulos**:

| # | Página | Função |
|---|--------|--------|
| 1 | Dashboard | Visão geral e métricas do sistema |
| 2 | Upload de SPED | Importação de arquivos EFD |
| 3 | Análise Completa | Processamento completo do SPED |
| 4 | Análise Completa v17 | Motor avançado com detecção multissetorial |
| 5 | Validação Produto a Produto | Análise item-a-item com detalhamento |
| 6 | Validação Universal | Motor universal todos os setores |
| 7 | Upload Massivo | Processamento de múltiplos SPEDs |
| 8 | Multi-SPED v13 | Comparação entre períodos |
| 9 | EFD Contribuições | Especializado em PIS/COFINS |
| 10 | Cálculos | Simulador de créditos tributários |
| 11 | Legislação | Base de leis e normas referenciadas |
| 12 | Fontes de Dados | Transparência sobre origens dos dados |
| 13 | Auditor Pack | Kit completo para auditoria |
| 14 | Dossiê v11 | Geração de dossiê técnico |
| 15 | Ledger/Blockchain | Registro imutável com Merkle tree |
| 16 | **🏛 Auditoria Soberana v20** | **Novo — perfis + ISS + ICMS-ST + atacado/varejo** |

---

## 4. NÚMEROS

| Métrica | Valor |
|---------|-------|
| Linhas de código | **19.520** |
| Funções Python | **305** |
| Setores monofásicos cobertos | **~20** |
| UFs com alíquota ISS mapeada | **27** |
| Regimes tributários | **3** (Real, Presumido, Simples) |
| Perfis de auditoria | **5** |
| Performance validação | **~2.500 itens/seg** |
| Performance Excel | **~7.000 linhas/seg** |
| Teses tributárias referenciadas | **25+** |

---

## 5. BASE LEGAL REFERENCIADA

- **RE 574.706/STF** — Tese do Século (exclusão ICMS da BC PIS/COFINS)
- **RE 592.616/STF** — Exclusão ISS da BC PIS/COFINS
- **Tema 762/STF** — Ressarcimento ICMS-ST (BC real < BC presumida)
- **Lei 10.637/2002** — PIS não cumulativo
- **Lei 10.833/2003** — COFINS não cumulativa
- **Lei 10.865/2004** — PIS/COFINS importação
- **LC 123/2006** — Simples Nacional
- **LC 214/2025** — Reforma tributária (IBS/CBS)
- **Dec. 70.235/1972** — Processo administrativo fiscal
- **MP 2.200-2/2001** — ICP-Brasil e validade jurídica de documentos digitais
- **Lei 14.063/2020** — Assinaturas eletrônicas
- **RFC 6962** — Certificate Transparency (Merkle tree)

---

## 6. ARQUITETURA

```
resolvrapido/
├── main.py                      # App Streamlit (14.702 linhas) — 16 páginas
├── validacao_universal.py       # Motor universal (1.486 linhas) — core engine
├── integrador_rfb_expandido.py  # Integrador RFB (1.008 linhas) — consultas NCM/ISS
├── validacao_produtos.py        # Validação produto-a-produto legada
├── integrador_rfb.py            # Integrador legado (compatibilidade)
├── requirements.txt             # Dependências Python
├── packages.txt                 # Dependências de sistema (Streamlit Cloud)
└── sped_exemplo.txt             # SPED de teste
```

**Deploy**: Streamlit Cloud via GitHub (repo `resolv2`)
**Auth**: Login hardcoded (admin/admin)
**Dependências**: streamlit, pandas, xlsxwriter, openpyxl, plotly

---

## 7. DIFERENCIAIS

1. **Universal** — não é específico de um setor; funciona para indústria, comércio, serviços, agro, farma, combustíveis
2. **Multi-perfil** — mesma análise, 5 visões especializadas para diferentes stakeholders
3. **Prova judicial** — hash Merkle SHA-256 com cadeia de custódia para uso em processos administrativos e judiciais
4. **Auto-contido** — roda em Streamlit Cloud sem infra própria, sem banco de dados externo
5. **Teses tributárias embutidas** — não apenas valida, mas identifica oportunidades de recuperação de créditos

---

*ResolvRapido Brasil — Motor Universal de Validação SPED v20 Soberano*
*Capacidade total: parser → validação → cálculo → perfis → relatório → prova documental*
*Tudo em uma única plataforma.*
