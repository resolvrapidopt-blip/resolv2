# ============================================================================
# MÓDULO DE VALIDAÇÃO PRODUTO A PRODUTO — ResolvRapido Brasil v18
# ============================================================================
# Este módulo implementa:
#   1. Carregamento da base de dados NCM
#   2. Validação fiscal item a item (C170)
#   3. Geração de relatório PDF com ReportLab
#   4. Página Streamlit integrada
# ============================================================================

import json
import os
import io
import hashlib
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 1) CARREGAMENTO DA BASE NCM
# ---------------------------------------------------------------------------

_BASE_NCM_CACHE: Optional[Dict] = None

def _safe_dec(val, default="0") -> Decimal:
    """Converte para Decimal de forma segura."""
    if val is None or val == "":
        return Decimal(default)
    try:
        s = str(val).replace(",", ".").strip()
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal(default)


def carregar_base_ncm(caminho: str = None) -> Dict[str, Any]:
    """Carrega a base de dados NCM de um arquivo JSON."""
    global _BASE_NCM_CACHE
    if _BASE_NCM_CACHE is not None:
        return _BASE_NCM_CACHE

    if caminho is None:
        # Tenta vários caminhos
        for p in [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "ncm_database.json"),
            "ncm_database.json",
            "data_brasil/ncm_database.json",
        ]:
            if os.path.exists(p):
                caminho = p
                break

    if caminho and os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            _BASE_NCM_CACHE = json.load(f)
    else:
        # Base mínima embutida
        _BASE_NCM_CACHE = {
            "ncms": {},
            "icms_por_uf": {},
            "cst_pis_cofins": {},
            "_meta": {"versao": "embutida", "total_ncms": 0},
        }
    return _BASE_NCM_CACHE


# ---------------------------------------------------------------------------
# UFs do Sul e Sudeste (para alíquota interestadual)
# ---------------------------------------------------------------------------
UFS_SUL_SUDESTE = {"SP", "RJ", "MG", "ES", "PR", "SC", "RS"}


def _aliquota_icms_esperada(ncm_info: Dict, uf_origem: str, uf_destino: str,
                             cfop: str) -> Decimal:
    """Determina a alíquota ICMS esperada com base em UF e CFOP."""
    base = carregar_base_ncm()
    uf_data = base.get("icms_por_uf", {}).get(uf_destino or uf_origem, {})

    # CFOP 5xxx = operação interna, 6xxx = interestadual, 7xxx = exportação
    cfop_str = str(cfop).strip()
    if cfop_str.startswith("7"):
        return Decimal("0")  # Exportação — imune
    elif cfop_str.startswith("6") or cfop_str.startswith("2"):
        # Interestadual
        if uf_origem in UFS_SUL_SUDESTE and uf_destino not in UFS_SUL_SUDESTE:
            return Decimal("7")
        else:
            return Decimal("12")
    else:
        # Interna
        interna = uf_data.get("interna", ncm_info.get("icms_padrao", 18.0))
        return Decimal(str(interna))


# ---------------------------------------------------------------------------
# CSTs monofásicos — revendedor NÃO deve tomar crédito
# ---------------------------------------------------------------------------
CST_MONOFASICO_SEM_CREDITO = {"04", "05", "06"}
CST_COM_CREDITO = {"50", "51", "52", "53", "54", "55", "56", "60", "61", "62", "63"}


# ---------------------------------------------------------------------------
# 2) FUNÇÃO PRINCIPAL DE VALIDAÇÃO
# ---------------------------------------------------------------------------

def validar_produto_item(
    item: Dict[str, Any],
    uf: str = "SP",
    regime: str = "NAO_CUMULATIVO",
    competencia: str = "01/2025",
    uf_destino: str = None,
) -> Dict[str, Any]:
    """
    Valida um item (C170) individualmente contra a base NCM.

    Retorna dict com:
      - status: "OK" | "ALERTA" | "ERRO"
      - erros: lista de mensagens de erro
      - alertas: lista de alertas
      - detalhes: dict com valores esperados vs informados
    """
    base = carregar_base_ncm()
    ncms = base.get("ncms", {})
    csts_ref = base.get("cst_pis_cofins", {})

    resultado = {
        "ncm": str(item.get("ncm", item.get("cod_item", ""))).strip(),
        "descricao": str(item.get("descr", item.get("descricao", ""))).strip()[:60],
        "cfop": str(item.get("cfop", "")).strip(),
        "cst_pis": str(item.get("cst_pis", "")).strip().zfill(2),
        "cst_cofins": str(item.get("cst_cofins", "")).strip().zfill(2),
        "vl_item": _safe_dec(item.get("vl_item", 0)),
        "status": "OK",
        "erros": [],
        "alertas": [],
        "detalhes": {},
        "pontuacao": 100,  # Começa com 100 e desconta
    }

    ncm_code = resultado["ncm"].replace(".", "").replace("-", "").replace(" ", "")
    if len(ncm_code) > 8:
        ncm_code = ncm_code[:8]
    resultado["ncm_normalizado"] = ncm_code

    # --- Verificação 1: NCM existe na TIPI ---
    ncm_info = ncms.get(ncm_code)
    if not ncm_info:
        # Tenta busca parcial (6 ou 4 dígitos)
        ncm_info = ncms.get(ncm_code[:6]) or ncms.get(ncm_code[:4])
        if ncm_info:
            resultado["alertas"].append(
                f"NCM {ncm_code} não encontrado exatamente na TIPI. "
                f"Correspondência parcial: {ncm_code[:6] if ncms.get(ncm_code[:6]) else ncm_code[:4]}"
            )
            resultado["pontuacao"] -= 5
        else:
            resultado["erros"].append(
                f"NCM {ncm_code} NÃO ENCONTRADO na TIPI/NBS. "
                f"Verifique se o código está correto ou se o produto é importado sem classificação."
            )
            resultado["pontuacao"] -= 30
            resultado["status"] = "ERRO"
            # Sem NCM, não consegue validar o resto — usa defaults
            ncm_info = {
                "descricao": "NCM DESCONHECIDO",
                "ipi": 0, "icms_padrao": 18.0,
                "pis_nc": 1.65, "cofins_nc": 7.60,
                "pis_cum": 0.65, "cofins_cum": 3.0,
                "monofasico": False, "obs": "",
            }

    resultado["ncm_descricao_tipi"] = ncm_info.get("descricao", "")
    resultado["monofasico"] = ncm_info.get("monofasico", False)

    # --- Verificação 2: Alíquota ICMS ---
    aliq_icms_informada = _safe_dec(item.get("aliq_icms", 0))
    aliq_icms_esperada = _aliquota_icms_esperada(
        ncm_info, uf, uf_destino or uf, resultado["cfop"]
    )
    diff_icms = abs(aliq_icms_informada - aliq_icms_esperada)
    resultado["detalhes"]["icms_esperado"] = float(aliq_icms_esperada)
    resultado["detalhes"]["icms_informado"] = float(aliq_icms_informada)

    if diff_icms > Decimal("0.01") and aliq_icms_informada > 0:
        if diff_icms <= Decimal("1.0"):
            resultado["alertas"].append(
                f"ICMS: alíquota informada {aliq_icms_informada}% difere da esperada "
                f"{aliq_icms_esperada}% (UF={uf}, CFOP={resultado['cfop']}). "
                f"Pode haver benefício fiscal, redução de base, ou ICMS-ST."
            )
            resultado["pontuacao"] -= 5
        else:
            resultado["erros"].append(
                f"ICMS: alíquota informada {aliq_icms_informada}% difere significativamente "
                f"da esperada {aliq_icms_esperada}% (UF={uf}, CFOP={resultado['cfop']}). "
                f"Verificar se há convênio ICMS, isenção ou erro de escrituração."
            )
            resultado["pontuacao"] -= 15

    # --- Verificação 3: Alíquota IPI ---
    aliq_ipi_informada = _safe_dec(item.get("aliq_ipi", 0))
    aliq_ipi_esperada = Decimal(str(ncm_info.get("ipi", 0)))
    diff_ipi = abs(aliq_ipi_informada - aliq_ipi_esperada)
    resultado["detalhes"]["ipi_esperado"] = float(aliq_ipi_esperada)
    resultado["detalhes"]["ipi_informado"] = float(aliq_ipi_informada)

    if diff_ipi > Decimal("0.01") and aliq_ipi_informada > 0:
        if diff_ipi <= Decimal("2.0"):
            resultado["alertas"].append(
                f"IPI: alíquota informada {aliq_ipi_informada}% difere da TIPI "
                f"({aliq_ipi_esperada}%). Pode haver ex-tarifário ou decreto específico."
            )
            resultado["pontuacao"] -= 5
        else:
            resultado["erros"].append(
                f"IPI: alíquota informada {aliq_ipi_informada}% difere significativamente "
                f"da TIPI ({aliq_ipi_esperada}%). Verificar classificação fiscal e TIPI vigente."
            )
            resultado["pontuacao"] -= 15

    # --- Verificação 4: PIS/COFINS (CST e alíquotas) ---
    if regime == "NAO_CUMULATIVO":
        pis_esperado = Decimal(str(ncm_info.get("pis_nc", 1.65)))
        cofins_esperado = Decimal(str(ncm_info.get("cofins_nc", 7.60)))
    else:
        pis_esperado = Decimal(str(ncm_info.get("pis_cum", 0.65)))
        cofins_esperado = Decimal(str(ncm_info.get("cofins_cum", 3.0)))

    aliq_pis_info = _safe_dec(item.get("aliq_pis", 0))
    aliq_cofins_info = _safe_dec(item.get("aliq_cofins", 0))

    resultado["detalhes"]["pis_esperado"] = float(pis_esperado)
    resultado["detalhes"]["pis_informado"] = float(aliq_pis_info)
    resultado["detalhes"]["cofins_esperado"] = float(cofins_esperado)
    resultado["detalhes"]["cofins_informado"] = float(aliq_cofins_info)

    cst_pis = resultado["cst_pis"]
    cst_cofins = resultado["cst_cofins"]

    # Verificação 5: Monofásico com crédito indevido
    if ncm_info.get("monofasico", False):
        resultado["detalhes"]["regime_monofasico"] = True
        # Se o produto é monofásico e o CST indica crédito, é potencialmente indevido
        if cst_pis in CST_COM_CREDITO or cst_cofins in CST_COM_CREDITO:
            resultado["erros"].append(
                f"CRÉDITO INDEVIDO: NCM {ncm_code} é tributado no regime MONOFÁSICO "
                f"({ncm_info.get('obs', '')}). "
                f"CST PIS={cst_pis}/COFINS={cst_cofins} indica aproveitamento de crédito, "
                f"mas revendedor deve usar CST 04 (alíquota zero). "
                f"Risco de glosa integral pela RFB."
            )
            resultado["pontuacao"] -= 40
    else:
        resultado["detalhes"]["regime_monofasico"] = False

    # Verificar coerência do CST com as alíquotas
    if cst_pis in CST_MONOFASICO_SEM_CREDITO and aliq_pis_info > 0:
        resultado["alertas"].append(
            f"CST PIS {cst_pis} indica operação sem crédito/débito, "
            f"mas alíquota PIS informada = {aliq_pis_info}%. Deve ser zero."
        )
        resultado["pontuacao"] -= 10

    if cst_pis in CST_COM_CREDITO and aliq_pis_info == 0 and not ncm_info.get("monofasico"):
        resultado["alertas"].append(
            f"CST PIS {cst_pis} indica direito a crédito, mas alíquota PIS = 0%. "
            f"Possível perda de crédito tributário."
        )
        resultado["pontuacao"] -= 5

    # Verificar diferenças nas alíquotas PIS/COFINS
    if aliq_pis_info > 0 and abs(aliq_pis_info - pis_esperado) > Decimal("0.01"):
        resultado["alertas"].append(
            f"PIS: alíquota informada {aliq_pis_info}% vs esperada {pis_esperado}% "
            f"({regime}). Verificar base legal."
        )
        resultado["pontuacao"] -= 5

    if aliq_cofins_info > 0 and abs(aliq_cofins_info - cofins_esperado) > Decimal("0.01"):
        resultado["alertas"].append(
            f"COFINS: alíquota informada {aliq_cofins_info}% vs esperada {cofins_esperado}% "
            f"({regime}). Verificar base legal."
        )
        resultado["pontuacao"] -= 5

    # --- Verificação 6: Base de cálculo (Tese do Século) ---
    vl_bc_pis = _safe_dec(item.get("vl_bc_pis", 0))
    vl_icms = _safe_dec(item.get("vl_icms", 0))
    vl_item = resultado["vl_item"]

    if vl_bc_pis > 0 and vl_icms > 0 and vl_item > 0:
        # Se a BC do PIS inclui o ICMS (BC == VL_ITEM), a Tese do Século não foi aplicada
        bc_com_icms = abs(vl_bc_pis - vl_item) < Decimal("0.02")
        bc_sem_icms = abs(vl_bc_pis - (vl_item - vl_icms)) < Decimal("0.02")

        resultado["detalhes"]["bc_pis"] = float(vl_bc_pis)
        resultado["detalhes"]["vl_item"] = float(vl_item)
        resultado["detalhes"]["vl_icms_destacado"] = float(vl_icms)
        resultado["detalhes"]["bc_esperada_tese_seculo"] = float(vl_item - vl_icms)

        if bc_com_icms and not bc_sem_icms:
            resultado["alertas"].append(
                f"TESE DO SÉCULO (RE 574.706/PR): BC do PIS/COFINS = R$ {vl_bc_pis:.2f} "
                f"INCLUI ICMS (R$ {vl_icms:.2f}). "
                f"BC correta (excluindo ICMS) = R$ {vl_item - vl_icms:.2f}. "
                f"Crédito tributário potencial sobre a diferença."
            )
            resultado["pontuacao"] -= 3  # É um alerta, não erro

    # --- Determinar status final ---
    if resultado["erros"]:
        resultado["status"] = "ERRO"
    elif resultado["alertas"]:
        resultado["status"] = "ALERTA"
    else:
        resultado["status"] = "OK"

    resultado["pontuacao"] = max(0, resultado["pontuacao"])
    return resultado


# ---------------------------------------------------------------------------
# 3) VALIDAÇÃO EM LOTE
# ---------------------------------------------------------------------------

def validar_todos_itens(
    itens_c170: List[Dict[str, Any]],
    uf: str = "SP",
    regime: str = "NAO_CUMULATIVO",
    competencia: str = "01/2025",
) -> Dict[str, Any]:
    """Valida todos os itens C170 e gera estatísticas."""
    resultados = []
    total_ok = 0
    total_alerta = 0
    total_erro = 0
    total_monofasico_indevido = 0
    total_tese_seculo = 0
    soma_pontuacao = 0

    for item in itens_c170:
        r = validar_produto_item(item, uf, regime, competencia)
        resultados.append(r)
        if r["status"] == "OK":
            total_ok += 1
        elif r["status"] == "ALERTA":
            total_alerta += 1
        else:
            total_erro += 1

        if r.get("monofasico") and r["status"] == "ERRO":
            total_monofasico_indevido += 1
        if any("TESE DO SÉCULO" in a for a in r.get("alertas", [])):
            total_tese_seculo += 1
        soma_pontuacao += r["pontuacao"]

    media_pontuacao = soma_pontuacao / max(len(resultados), 1)

    return {
        "resultados": resultados,
        "resumo": {
            "total_itens": len(resultados),
            "total_ok": total_ok,
            "total_alerta": total_alerta,
            "total_erro": total_erro,
            "total_monofasico_indevido": total_monofasico_indevido,
            "total_tese_seculo": total_tese_seculo,
            "media_pontuacao": round(media_pontuacao, 1),
            "pct_conformidade": round(total_ok / max(len(resultados), 1) * 100, 1),
        },
        "meta": {
            "uf": uf,
            "regime": regime,
            "competencia": competencia,
            "data_validacao": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "versao_base_ncm": carregar_base_ncm().get("_meta", {}).get("versao", "N/A"),
        },
    }


# ---------------------------------------------------------------------------
# 4) GERADOR DE RELATÓRIO PDF
# ---------------------------------------------------------------------------

def gerar_relatorio_validacao_produtos(
    analise: Dict[str, Any],
    empresa_info: Dict[str, Any] = None,
) -> bytes:
    """Gera relatório PDF de validação fiscal produto a produto."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15*mm, rightMargin=15*mm,
        topMargin=20*mm, bottomMargin=20*mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TitleCustom", fontSize=18, leading=22,
        alignment=TA_CENTER, textColor=colors.HexColor("#1a237e"),
        spaceAfter=6*mm, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="SubTitleCustom", fontSize=12, leading=14,
        alignment=TA_CENTER, textColor=colors.HexColor("#37474f"),
        spaceAfter=4*mm,
    ))
    styles.add(ParagraphStyle(
        name="SectionTitle", fontSize=13, leading=16,
        textColor=colors.HexColor("#0d47a1"),
        spaceAfter=3*mm, spaceBefore=5*mm, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        name="CellText", fontSize=7, leading=9,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        name="CellTextCenter", fontSize=7, leading=9,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        name="SmallBody", fontSize=9, leading=12,
    ))
    styles.add(ParagraphStyle(
        name="FooterText", fontSize=7, leading=9,
        textColor=colors.grey, alignment=TA_CENTER,
    ))

    story = []
    resumo = analise.get("resumo", {})
    meta = analise.get("meta", {})
    resultados = analise.get("resultados", [])
    emp = empresa_info or {}

    # --- CAPA ---
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph("RELATÓRIO DE VALIDAÇÃO FISCAL", styles["TitleCustom"]))
    story.append(Paragraph("PRODUTO A PRODUTO", styles["TitleCustom"]))
    story.append(Spacer(1, 5*mm))
    story.append(HRFlowable(width="80%", thickness=2, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(
        f"ResolvRapido Brasil v18 — Motor Determinístico com Prova Merkle",
        styles["SubTitleCustom"],
    ))
    story.append(Spacer(1, 10*mm))

    # Info empresa
    info_lines = [
        f"<b>Empresa:</b> {emp.get('razao_social', 'N/I')}",
        f"<b>CNPJ:</b> {emp.get('cnpj', 'N/I')}",
        f"<b>UF:</b> {meta.get('uf', 'N/I')} | <b>Regime:</b> {meta.get('regime', 'N/I')}",
        f"<b>Competência:</b> {meta.get('competencia', 'N/I')}",
        f"<b>Data da Validação:</b> {meta.get('data_validacao', 'N/I')}",
        f"<b>Base NCM:</b> v{meta.get('versao_base_ncm', 'N/I')}",
    ]
    for line in info_lines:
        story.append(Paragraph(line, styles["SmallBody"]))
    story.append(Spacer(1, 5*mm))

    # --- RESUMO EXECUTIVO ---
    story.append(PageBreak())
    story.append(Paragraph("1. RESUMO EXECUTIVO", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 3*mm))

    conformidade = resumo.get("pct_conformidade", 0)
    if conformidade >= 90:
        status_geral = "CONFORME"
        cor_status = colors.HexColor("#2e7d32")
    elif conformidade >= 70:
        status_geral = "PARCIALMENTE CONFORME"
        cor_status = colors.HexColor("#f57f17")
    else:
        status_geral = "NÃO CONFORME"
        cor_status = colors.HexColor("#c62828")

    resumo_data = [
        ["Indicador", "Valor"],
        ["Total de Itens Analisados", str(resumo.get("total_itens", 0))],
        ["✅ Itens Conformes (OK)", str(resumo.get("total_ok", 0))],
        ["⚠️ Itens com Alertas", str(resumo.get("total_alerta", 0))],
        ["❌ Itens com Erros", str(resumo.get("total_erro", 0))],
        ["🔴 Crédito Monofásico Indevido", str(resumo.get("total_monofasico_indevido", 0))],
        ["📐 Tese do Século Aplicável", str(resumo.get("total_tese_seculo", 0))],
        ["Pontuação Média de Conformidade", f"{resumo.get('media_pontuacao', 0)}/100"],
        ["% Conformidade", f"{conformidade}%"],
        ["Status Geral", status_geral],
    ]

    t = Table(resumo_data, colWidths=[120*mm, 50*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8eaf6")),
        ("TEXTCOLOR", (1, -1), (1, -1), cor_status),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(t)
    story.append(Spacer(1, 5*mm))

    # Gráfico textual de distribuição
    bar_ok = "█" * max(1, int(resumo.get("total_ok", 0) / max(resumo.get("total_itens", 1), 1) * 30))
    bar_al = "█" * max(0, int(resumo.get("total_alerta", 0) / max(resumo.get("total_itens", 1), 1) * 30))
    bar_er = "█" * max(0, int(resumo.get("total_erro", 0) / max(resumo.get("total_itens", 1), 1) * 30))

    story.append(Paragraph("Distribuição de Conformidade:", styles["SmallBody"]))
    story.append(Paragraph(
        f'<font color="#2e7d32">OK:     {bar_ok} ({resumo.get("total_ok", 0)})</font>',
        styles["SmallBody"],
    ))
    story.append(Paragraph(
        f'<font color="#f57f17">ALERTA: {bar_al} ({resumo.get("total_alerta", 0)})</font>',
        styles["SmallBody"],
    ))
    story.append(Paragraph(
        f'<font color="#c62828">ERRO:   {bar_er} ({resumo.get("total_erro", 0)})</font>',
        styles["SmallBody"],
    ))

    # --- TABELA DETALHADA ---
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph("2. ANÁLISE DETALHADA POR ITEM", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 3*mm))

    # Cabeçalho da tabela
    header = ["#", "NCM", "Descrição", "CFOP", "CST\nPIS", "Status", "Pont.", "Observação Principal"]
    col_widths = [8*mm, 20*mm, 42*mm, 14*mm, 11*mm, 14*mm, 11*mm, 60*mm]

    table_data = [header]
    for i, r in enumerate(resultados):
        status = r["status"]
        if status == "OK":
            status_txt = "✅ OK"
        elif status == "ALERTA":
            status_txt = "⚠️ ALERTA"
        else:
            status_txt = "❌ ERRO"

        # Pegar observação principal
        obs = ""
        if r["erros"]:
            obs = r["erros"][0][:80]
        elif r["alertas"]:
            obs = r["alertas"][0][:80]
        else:
            obs = "Conforme"

        row = [
            Paragraph(str(i+1), styles["CellTextCenter"]),
            Paragraph(r.get("ncm_normalizado", r["ncm"])[:8], styles["CellText"]),
            Paragraph(r.get("ncm_descricao_tipi", r["descricao"])[:35], styles["CellText"]),
            Paragraph(r["cfop"], styles["CellTextCenter"]),
            Paragraph(r["cst_pis"], styles["CellTextCenter"]),
            Paragraph(status_txt, styles["CellTextCenter"]),
            Paragraph(str(r["pontuacao"]), styles["CellTextCenter"]),
            Paragraph(obs, styles["CellText"]),
        ]
        table_data.append(row)

        # A cada 25 itens, quebrar página
        if (i + 1) % 25 == 0 and i + 1 < len(resultados):
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
            ]))
            story.append(t)
            story.append(PageBreak())
            story.append(Paragraph("2. ANÁLISE DETALHADA (cont.)", styles["SectionTitle"]))
            story.append(Spacer(1, 2*mm))
            table_data = [header]

    # Tabela final (itens restantes)
    if len(table_data) > 1:
        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a237e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 7),
            ("FONTSIZE", (0, 1), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ]))
        story.append(t)

    # --- DETALHAMENTO DE ERROS E ALERTAS ---
    itens_problematicos = [r for r in resultados if r["status"] != "OK"]
    if itens_problematicos:
        story.append(PageBreak())
        story.append(Paragraph("3. DETALHAMENTO DE NÃO CONFORMIDADES", styles["SectionTitle"]))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a237e")))
        story.append(Spacer(1, 3*mm))

        for r in itens_problematicos[:50]:  # Limitar a 50 para não explodir o PDF
            ncm_txt = r.get("ncm_normalizado", r["ncm"])
            desc_txt = r.get("ncm_descricao_tipi", r["descricao"])
            story.append(Paragraph(
                f'<b>NCM {ncm_txt}</b> — {desc_txt} | CFOP: {r["cfop"]} | '
                f'CST PIS: {r["cst_pis"]} | Pontuação: {r["pontuacao"]}/100',
                styles["SmallBody"],
            ))
            for erro in r["erros"]:
                story.append(Paragraph(f'  <font color="#c62828">❌ {erro}</font>', styles["SmallBody"]))
            for alerta in r["alertas"]:
                story.append(Paragraph(f'  <font color="#f57f17">⚠️ {alerta}</font>', styles["SmallBody"]))

            det = r.get("detalhes", {})
            if det:
                det_lines = []
                if "icms_esperado" in det:
                    det_lines.append(f"ICMS: esperado {det['icms_esperado']}% / informado {det['icms_informado']}%")
                if "ipi_esperado" in det:
                    det_lines.append(f"IPI: esperado {det['ipi_esperado']}% / informado {det['ipi_informado']}%")
                if "pis_esperado" in det:
                    det_lines.append(f"PIS: esperado {det['pis_esperado']}% / informado {det['pis_informado']}%")
                if "cofins_esperado" in det:
                    det_lines.append(f"COFINS: esperado {det['cofins_esperado']}% / informado {det['cofins_informado']}%")
                if det_lines:
                    story.append(Paragraph(
                        f'  <font color="#546e7a">📊 {" | ".join(det_lines)}</font>',
                        styles["SmallBody"],
                    ))
            story.append(Spacer(1, 2*mm))

    # --- RECOMENDAÇÕES ---
    story.append(PageBreak())
    story.append(Paragraph("4. RECOMENDAÇÕES", styles["SectionTitle"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1a237e")))
    story.append(Spacer(1, 3*mm))

    recomendacoes = []
    if resumo.get("total_monofasico_indevido", 0) > 0:
        recomendacoes.append(
            f"<b>🔴 URGENTE — Crédito Monofásico Indevido:</b> Foram identificados "
            f"{resumo['total_monofasico_indevido']} item(ns) com aproveitamento indevido de créditos "
            f"de PIS/COFINS sobre produtos monofásicos. Revendedores devem utilizar CST 04 "
            f"(alíquota zero) e NÃO tomar crédito sobre esses produtos. "
            f"Risco de glosa integral + multa de 75% pela RFB. "
            f"Recomendação: retificar EFD-Contribuições e estornar créditos indevidos."
        )
    if resumo.get("total_tese_seculo", 0) > 0:
        recomendacoes.append(
            f"<b>📐 Oportunidade — Tese do Século (RE 574.706/PR):</b> Foram identificados "
            f"{resumo['total_tese_seculo']} item(ns) onde a base de cálculo do PIS/COFINS "
            f"INCLUI o ICMS destacado. Conforme decisão do STF (Tema 69), o ICMS deve ser "
            f"excluído da base de cálculo. Recomendação: recalcular créditos e avaliar "
            f"pedido de restituição via PER/DCOMP."
        )
    if resumo.get("total_erro", 0) > 0:
        recomendacoes.append(
            f"<b>❌ Erros Fiscais:</b> {resumo['total_erro']} item(ns) apresentaram erros "
            f"significativos (NCM inválido, alíquotas divergentes, CST inconsistente). "
            f"Recomendação: revisar os itens sinalizados com contador/consultor fiscal."
        )
    if not recomendacoes:
        recomendacoes.append(
            "<b>✅ Escrituração Conforme:</b> Todos os itens analisados estão dentro "
            "dos parâmetros esperados. Manter o acompanhamento periódico para "
            "garantir conformidade contínua."
        )

    for rec in recomendacoes:
        story.append(Paragraph(rec, styles["SmallBody"]))
        story.append(Spacer(1, 3*mm))

    # --- HASH DE INTEGRIDADE ---
    story.append(Spacer(1, 10*mm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.grey))
    hash_content = json.dumps(resumo, sort_keys=True, default=str)
    doc_hash = hashlib.sha256(hash_content.encode()).hexdigest()
    story.append(Paragraph(
        f"Hash de integridade do relatório (SHA-256): {doc_hash}",
        styles["FooterText"],
    ))
    story.append(Paragraph(
        f"Gerado por ResolvRapido Brasil v18 em {meta.get('data_validacao', 'N/I')}",
        styles["FooterText"],
    ))

    doc.build(story)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# 5) GERADOR DE CSV
# ---------------------------------------------------------------------------

def gerar_csv_validacao(analise: Dict[str, Any]) -> str:
    """Gera CSV com os resultados da validação."""
    import csv
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "NCM", "Descricao_TIPI", "CFOP", "CST_PIS", "CST_COFINS",
        "VL_Item", "Monofasico", "Status", "Pontuacao",
        "ICMS_Esperado", "ICMS_Informado",
        "IPI_Esperado", "IPI_Informado",
        "PIS_Esperado", "PIS_Informado",
        "COFINS_Esperado", "COFINS_Informado",
        "Erros", "Alertas",
    ])

    for r in analise.get("resultados", []):
        det = r.get("detalhes", {})
        writer.writerow([
            r.get("ncm_normalizado", r["ncm"]),
            r.get("ncm_descricao_tipi", r["descricao"]),
            r["cfop"],
            r["cst_pis"],
            r["cst_cofins"],
            str(r["vl_item"]),
            "SIM" if r.get("monofasico") else "NAO",
            r["status"],
            r["pontuacao"],
            det.get("icms_esperado", ""),
            det.get("icms_informado", ""),
            det.get("ipi_esperado", ""),
            det.get("ipi_informado", ""),
            det.get("pis_esperado", ""),
            det.get("pis_informado", ""),
            det.get("cofins_esperado", ""),
            det.get("cofins_informado", ""),
            " | ".join(r.get("erros", [])),
            " | ".join(r.get("alertas", [])),
        ])
    return buf.getvalue()


if __name__ == "__main__":
    # Teste rápido
    base = carregar_base_ncm()
    print(f"Base NCM carregada: {len(base['ncms'])} NCMs")

    item_teste = {
        "ncm": "30049099",
        "descr": "MEDICAMENTO GENÉRICO",
        "cfop": "1102",
        "cst_pis": "50",
        "cst_cofins": "50",
        "aliq_pis": 1.65,
        "aliq_cofins": 7.60,
        "aliq_icms": 18.0,
        "aliq_ipi": 0.0,
        "vl_item": 1000.00,
        "vl_icms": 180.00,
        "vl_bc_pis": 1000.00,
    }
    resultado = validar_produto_item(item_teste, uf="SP", regime="NAO_CUMULATIVO")
    print(f"Status: {resultado['status']} | Pontuação: {resultado['pontuacao']}")
    print(f"Erros: {resultado['erros']}")
    print(f"Alertas: {resultado['alertas']}")
