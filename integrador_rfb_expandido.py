# ===========================================================================
# INTEGRADOR RFB EXPANDIDO — ResolvRapido Brasil v18.1
# ===========================================================================
# Módulo unificado com 10 fontes oficiais de dados fiscais
# Segurança: SSL obrigatório, sanitização, timeout, cache SQLite c/ hash
# ===========================================================================
import hashlib as _hashlib_exp
import json as _json_exp
import logging as _logging_exp
import os as _os_exp
import re as _re_exp
import sqlite3 as _sqlite3_exp
import time as _time_exp
from datetime import datetime as _dt_exp, timedelta as _td_exp
from pathlib import Path as _Path_exp
from typing import Dict, List, Optional, Tuple

try:
    import requests as _requests_exp
except ImportError:
    _requests_exp = None

_logger_exp = _logging_exp.getLogger("ResolvRapido.RFB.Expandido")
_CACHE_DB_EXPANDED = _Path_exp("data_brasil/rfb_cache_expandido.db")

# ===========================================================================
# URLS OFICIAIS
# ===========================================================================
_URLS = {
    "classif_ncm": "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json",
    "bcb_selic": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados?formato=json&dataInicial={di}&dataFinal={df}",
    "bcb_ipca": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados?formato=json&dataInicial={di}&dataFinal={df}",
    "brasilapi_cnpj": "https://brasilapi.com.br/api/cnpj/v1/",
}

# ===========================================================================
# 1. TABELA CEST (Código Especificador da Substituição Tributária)
# Convênio ICMS 142/2015 + atualizações até 2025
# ===========================================================================
_CEST_DATABASE = {
    # Autopeças (Anexo II)
    "0100100": {"ncms": ["39231000","39269090"], "descricao": "Copo plástico para proteção", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0100200": {"ncms": ["39269090"], "descricao": "Frisos, decalques, molduras plásticas", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0100300": {"ncms": ["39269090","40169990"], "descricao": "Protetores de caçamba", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0101300": {"ncms": ["40111000","40112090","40119200","40119300","40119400","40119900"], "descricao": "Pneus novos de borracha", "segmento": "AUTOPECAS", "mva_original": 42.0},
    "0101400": {"ncms": ["40131000","40132000"], "descricao": "Câmaras de ar de borracha", "segmento": "AUTOPECAS", "mva_original": 42.0},
    "0101500": {"ncms": ["40169990"], "descricao": "Protetores, flaps e outros", "segmento": "AUTOPECAS", "mva_original": 42.0},
    "0102200": {"ncms": ["68131000"], "descricao": "Pastilhas/guarnições de freio", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0102600": {"ncms": ["70071100","70071900","70072100","70072900","70091000"], "descricao": "Vidros para veículos", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0103200": {"ncms": ["73182100","73182200","73182300","73182400"], "descricao": "Parafusos, porcas para veículos", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0104100": {"ncms": ["83021090","83024200","83024900","83025000","83026000"], "descricao": "Fechaduras e trincos para veículos", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0105100": {"ncms": ["84099190","84099990"], "descricao": "Partes de motores", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0105300": {"ncms": ["84129090"], "descricao": "Partes de motores de reação", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0105600": {"ncms": ["84133090","84136090"], "descricao": "Bombas hidráulicas", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0106300": {"ncms": ["84212300"], "descricao": "Filtros de óleo ou gasolina", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0106400": {"ncms": ["84212990"], "descricao": "Filtros de ar", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0107400": {"ncms": ["84314990","84329000"], "descricao": "Partes de máquinas agrícolas", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0108100": {"ncms": ["84831090","84832000","84833090","84834090","84835090","84836090","84839000"], "descricao": "Engrenagens e rolamentos", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0109100": {"ncms": ["85011099","85012000","85013100","85013200","85013300","85013400"], "descricao": "Motores e geradores elétricos", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0110100": {"ncms": ["85111000","85112090","85113090","85114000","85115090","85118000","85119000"], "descricao": "Aparelhos de ignição e elétricos", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0111300": {"ncms": ["85122090","85122010"], "descricao": "Aparelhos de iluminação/sinalização", "segmento": "AUTOPECAS", "mva_original": 36.56},
    "0112100": {"ncms": ["85071090","85072090"], "descricao": "Acumuladores elétricos (baterias)", "segmento": "AUTOPECAS", "mva_original": 42.0},
    # Bebidas (Anexo III)
    "0300100": {"ncms": ["22011000"], "descricao": "Água mineral gasosa ou não", "segmento": "BEBIDAS", "mva_original": 140.0},
    "0300200": {"ncms": ["22019090"], "descricao": "Outras águas", "segmento": "BEBIDAS", "mva_original": 140.0},
    "0300300": {"ncms": ["22021000"], "descricao": "Refrigerantes", "segmento": "BEBIDAS", "mva_original": 140.0},
    "0300400": {"ncms": ["22029000"], "descricao": "Outras bebidas não alcoólicas", "segmento": "BEBIDAS", "mva_original": 140.0},
    "0300500": {"ncms": ["22030000"], "descricao": "Cerveja de malte", "segmento": "BEBIDAS", "mva_original": 140.0},
    "0300700": {"ncms": ["22084000","22089000"], "descricao": "Bebidas alcoólicas destiladas", "segmento": "BEBIDAS", "mva_original": 29.04},
    "0300800": {"ncms": ["22041000","22042100","22042900"], "descricao": "Vinhos", "segmento": "BEBIDAS", "mva_original": 29.04},
    # Combustíveis (Anexo VII)
    "0600100": {"ncms": ["27101921"], "descricao": "Gasolina automotiva", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    "0600200": {"ncms": ["27101159"], "descricao": "Gasolina de aviação", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    "0600300": {"ncms": ["27101921"], "descricao": "Álcool etílico hidratado", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    "0600400": {"ncms": ["27101241"], "descricao": "Querosene de aviação", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    "0600500": {"ncms": ["27101921"], "descricao": "Óleo diesel", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    "0600600": {"ncms": ["27111200"], "descricao": "GLP (gás liquefeito)", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    "0600700": {"ncms": ["27112100"], "descricao": "GNV (gás natural veicular)", "segmento": "COMBUSTIVEIS", "mva_original": 0},
    # Materiais de construção (Anexo XI)
    "1000100": {"ncms": ["25231000","25232100","25232900","25233000","25239000"], "descricao": "Cimento Portland", "segmento": "MAT_CONSTRUCAO", "mva_original": 37.0},
    "1000200": {"ncms": ["68091100","68091900","68099000"], "descricao": "Obras de gesso", "segmento": "MAT_CONSTRUCAO", "mva_original": 37.0},
    "1000300": {"ncms": ["68101900"], "descricao": "Blocos/tijolos de cimento", "segmento": "MAT_CONSTRUCAO", "mva_original": 37.0},
    "1000400": {"ncms": ["69041000","69049000"], "descricao": "Tijolos e telhas cerâmicas", "segmento": "MAT_CONSTRUCAO", "mva_original": 37.0},
    "1000500": {"ncms": ["69071900","69072100","69072200","69072300","69072400"], "descricao": "Azulejos e pisos cerâmicos", "segmento": "MAT_CONSTRUCAO", "mva_original": 37.0},
    "1000600": {"ncms": ["72142000","72143000","72149190","72149990"], "descricao": "Vergalhões e barras de ferro/aço", "segmento": "MAT_CONSTRUCAO", "mva_original": 37.0},
    # Ferramentas (Anexo XII)
    "1100100": {"ncms": ["82011000"], "descricao": "Pás, alviões, picaretas", "segmento": "FERRAMENTAS", "mva_original": 37.0},
    "1100200": {"ncms": ["82032000","82041100","82041200","82042000"], "descricao": "Chaves de fenda, alicates", "segmento": "FERRAMENTAS", "mva_original": 37.0},
    # Produtos alimentícios (Anexo XVII)
    "1700100": {"ncms": ["04029110","04029190","04029910","04029990"], "descricao": "Leite em pó", "segmento": "ALIMENTOS", "mva_original": 15.0},
    "1700200": {"ncms": ["04061000","04063000","04069000"], "descricao": "Queijos", "segmento": "ALIMENTOS", "mva_original": 15.0},
    "1700300": {"ncms": ["04090000"], "descricao": "Mel natural", "segmento": "ALIMENTOS", "mva_original": 15.0},
    "1700500": {"ncms": ["16010000","16021000","16024100","16024200","16024900"], "descricao": "Carnes e preparações", "segmento": "ALIMENTOS", "mva_original": 15.0},
    "1700600": {"ncms": ["19019010","19019020","19019090","19021100","19021900"], "descricao": "Massas e preparados alimentícios", "segmento": "ALIMENTOS", "mva_original": 15.0},
    "1700700": {"ncms": ["20091100","20091200","20091900","20092100","20099000"], "descricao": "Sucos de frutas", "segmento": "ALIMENTOS", "mva_original": 15.0},
    # Medicamentos (Anexo XVIII)
    "1300100": {"ncms": ["30021500","30021090","30029030","30029099"], "descricao": "Soros e vacinas", "segmento": "MEDICAMENTOS", "mva_original": 33.05},
    "1300200": {"ncms": ["30031000","30032000","30039000","30041000","30042000","30049000","30049099"], "descricao": "Medicamentos e preparações farmacêuticas", "segmento": "MEDICAMENTOS", "mva_original": 33.05},
    "1300300": {"ncms": ["30051000","30059010","30059090"], "descricao": "Algodão, gaze, ataduras", "segmento": "MEDICAMENTOS", "mva_original": 33.05},
    "1300400": {"ncms": ["30061000","30062000"], "descricao": "Catgutes, suturas", "segmento": "MEDICAMENTOS", "mva_original": 33.05},
    # Produtos eletrônicos (Anexo XXI)
    "2100100": {"ncms": ["84713019","84713012","84713090","84714190","84714990"], "descricao": "Computadores portáteis/desktops", "segmento": "ELETRONICOS", "mva_original": 15.0},
    "2100200": {"ncms": ["85171200","85171400","85171800"], "descricao": "Telefones celulares", "segmento": "ELETRONICOS", "mva_original": 15.0},
    "2100300": {"ncms": ["85287100","85287200"], "descricao": "Aparelhos receptores de TV", "segmento": "ELETRONICOS", "mva_original": 15.0},
    "2100400": {"ncms": ["84433110","84433190"], "descricao": "Impressoras e multifuncionais", "segmento": "ELETRONICOS", "mva_original": 15.0},
    # Materiais de limpeza (Anexo XXII)
    "2200100": {"ncms": ["34011190","34011900","34012090"], "descricao": "Sabões e detergentes", "segmento": "LIMPEZA", "mva_original": 40.0},
    "2200200": {"ncms": ["34022000","34029090"], "descricao": "Preparações para lavar", "segmento": "LIMPEZA", "mva_original": 40.0},
    "2200300": {"ncms": ["28289011","28289019","28289090"], "descricao": "Água sanitária e hipoclorito", "segmento": "LIMPEZA", "mva_original": 40.0},
    # Perfumaria (Anexo XXIII)
    "2300100": {"ncms": ["33030010","33030020"], "descricao": "Perfumes e águas de colônia", "segmento": "PERFUMARIA", "mva_original": 38.0},
    "2300200": {"ncms": ["33041000","33042000","33043000","33049100","33049900"], "descricao": "Produtos de beleza e maquiagem", "segmento": "PERFUMARIA", "mva_original": 38.0},
    "2300300": {"ncms": ["33051000","33052000","33059000"], "descricao": "Preparações capilares", "segmento": "PERFUMARIA", "mva_original": 38.0},
    "2300400": {"ncms": ["33061000","33069000"], "descricao": "Preparações para higiene bucal", "segmento": "PERFUMARIA", "mva_original": 38.0},
    "2300500": {"ncms": ["33071000","33072000","33073000","33079000"], "descricao": "Preparações barbear/desodorantes", "segmento": "PERFUMARIA", "mva_original": 38.0},
    # Papelaria (Anexo XXIV)
    "2400100": {"ncms": ["48021090","48025290","48025610","48025690","48025720","48025790","48025890"], "descricao": "Papel para escrita e impressão", "segmento": "PAPELARIA", "mva_original": 50.0},
    "2400200": {"ncms": ["48234000","48239090"], "descricao": "Formulários contínuos", "segmento": "PAPELARIA", "mva_original": 50.0},
    "2400300": {"ncms": ["96081000","96082000","96089190","96089990"], "descricao": "Canetas esferográficas", "segmento": "PAPELARIA", "mva_original": 50.0},
}

# ===========================================================================
# 2. CONVÊNIOS ICMS IMPORTANTES (benefícios fiscais consolidados)
# ===========================================================================
_CONVENIOS_ICMS = [
    # Isenções
    {"convenio": "100/97", "tipo": "ISENCAO", "descricao": "Insumos agropecuários", "ncms_prefixo": ["3102","3103","3104","3105","2503","2510","2834"], "ufs": "TODAS", "vigencia_inicio": "1997-11-04", "vigencia_fim": None, "base_legal": "Conv. ICMS 100/97"},
    {"convenio": "51/99", "tipo": "REDUCAO_BC", "descricao": "Redução BC equipamentos industriais (48,89%)", "ncms_prefixo": ["8402","8403","8404","8405","8406","8407","8408","8410","8411","8412","8413","8414","8416","8417"], "ufs": "TODAS", "vigencia_inicio": "1999-09-15", "vigencia_fim": None, "base_legal": "Conv. ICMS 52/91 → 51/99", "reducao_bc_pct": 48.89},
    {"convenio": "87/02", "tipo": "ISENCAO", "descricao": "Equipamentos e insumos para deficientes", "ncms_prefixo": ["87132000","87139000","90211000","90211090","90212000","90213000","90214090","90215000","90219090"], "ufs": "TODAS", "vigencia_inicio": "2002-12-20", "vigencia_fim": None, "base_legal": "Conv. ICMS 87/02"},
    {"convenio": "101/97", "tipo": "ISENCAO", "descricao": "Equipamentos e componentes para energia eólica/solar", "ncms_prefixo": ["84122190","85023100","85023900","85411000","85414020","85414090","90321010","76169900"], "ufs": "TODAS", "vigencia_inicio": "1997-12-12", "vigencia_fim": None, "base_legal": "Conv. ICMS 101/97"},
    {"convenio": "57/99", "tipo": "REDUCAO_BC", "descricao": "Redução BC perfumaria/higiene (33,33%)", "ncms_prefixo": ["3303","3304","3305","3306","3307"], "ufs": "TODAS", "vigencia_inicio": "1999-07-28", "vigencia_fim": None, "base_legal": "Conv. ICMS 57/99", "reducao_bc_pct": 33.33},
    {"convenio": "36/16", "tipo": "ISENCAO", "descricao": "Medicamentos para tratamento câncer", "ncms_prefixo": ["30049099","30039099"], "ufs": "TODAS", "vigencia_inicio": "2016-07-01", "vigencia_fim": None, "base_legal": "Conv. ICMS 36/16"},
    {"convenio": "75/91", "tipo": "REDUCAO_BC", "descricao": "Redução BC aeronaves, peças e acessórios (aplicável conforme UF)", "ncms_prefixo": ["8802","8803","8411"], "ufs": "TODAS", "vigencia_inicio": "1991-12-05", "vigencia_fim": None, "base_legal": "Conv. ICMS 75/91", "reducao_bc_pct": 0.0},
    {"convenio": "42/16", "tipo": "DIFERIMENTO", "descricao": "Diferimento ICMS importação sob Repetro", "ncms_prefixo": ["8431","8481","9015","8430","7304","7305","7306"], "ufs": ["RJ","ES","BA","SE","AL","RN","CE","MA","PA","AM"], "vigencia_inicio": "2016-06-03", "vigencia_fim": "2040-12-31", "base_legal": "Conv. ICMS 03/18 (substitui 42/16)"},
    {"convenio": "188/17", "tipo": "ISENCAO", "descricao": "Isenção medicamentos genéricos", "ncms_prefixo": ["3004","3003"], "ufs": "TODAS", "vigencia_inicio": "2018-01-01", "vigencia_fim": None, "base_legal": "Conv. ICMS 188/17"},
    {"convenio": "26/03", "tipo": "ISENCAO", "descricao": "Isenção equipamentos médico-hospitalares", "ncms_prefixo": ["9018","9019","9020","9021","9022","9402"], "ufs": "TODAS", "vigencia_inicio": "2003-04-25", "vigencia_fim": None, "base_legal": "Conv. ICMS 01/99 → 26/03"},
    {"convenio": "38/12", "tipo": "ISENCAO", "descricao": "Máquinas e equipamentos para reciclagem", "ncms_prefixo": ["8474","8479","8421","8437"], "ufs": "TODAS", "vigencia_inicio": "2012-06-22", "vigencia_fim": None, "base_legal": "Conv. ICMS 38/12"},
    # Substituição Tributária
    {"convenio": "142/18", "tipo": "ST", "descricao": "ST Autopeças", "ncms_prefixo": ["4011","4012","4013","6813","7007","7009","7320","8301","8302","8409","8413","8421","8481","8482","8483","8501","8507","8511","8512","8544"], "ufs": "TODAS", "vigencia_inicio": "2019-01-01", "vigencia_fim": None, "base_legal": "Conv. ICMS 142/18 (atualiza 92/15)"},
    {"convenio": "110/07", "tipo": "ST", "descricao": "ST Combustíveis", "ncms_prefixo": ["2207","2710","2711","3826","3824"], "ufs": "TODAS", "vigencia_inicio": "2007-12-28", "vigencia_fim": None, "base_legal": "Conv. ICMS 110/07"},
]

# ===========================================================================
# 3. ALÍQUOTAS IBS/CBS (Reforma Tributária - LC 214/2025)
# ===========================================================================
_IBS_CBS_REGRAS = {
    "aliquota_referencia_total": 26.5,  # Estimativa (IBS + CBS)
    "cbs_federal": 8.8,  # Estimativa CBS federal
    "ibs_estadual_municipal": 17.7,  # Estimativa IBS (estado + município)
    "transicao": {
        "2026": {"cbs": 0.9, "ibs": 0.0, "nota": "CBS teste a 0,9% (compensável com PIS/COFINS)"},
        "2027": {"cbs": 0.9, "ibs": 0.0, "nota": "CBS teste mantida, PIS/COFINS com ajustes"},
        "2029": {"cbs": 8.8, "ibs": 2.0, "nota": "Início transição IBS (10%)"},
        "2030": {"cbs": 8.8, "ibs": 4.0, "nota": "IBS a 20%"},
        "2031": {"cbs": 8.8, "ibs": 6.0, "nota": "IBS a 30%"},
        "2032": {"cbs": 8.8, "ibs": 8.0, "nota": "IBS a 40%, fim gradual ICMS/ISS"},
        "2033": {"cbs": 8.8, "ibs": 17.7, "nota": "IBS pleno, extinção ICMS/ISS"},
    },
    "reducoes": {
        "saude": {"reducao_pct": 60, "ncms_prefixo": ["3001","3002","3003","3004","3005","3006","9018","9019","9021","9022"], "base_legal": "LC 214/2025, art. 287"},
        "educacao": {"reducao_pct": 100, "ncms_prefixo": [], "base_legal": "LC 214/2025, art. 262", "nota": "Alíquota zero para educação (serviços)"},
        "alimentos_cesta": {"reducao_pct": 100, "ncms_prefixo": ["0201","0202","0207","0302","0303","0401","0402","0701","0702","0703","0712","0713","1001","1005","1006","1101","1507","1512","1701","1902","2501"], "base_legal": "LC 214/2025, art. 251 (Cesta Básica Nacional)"},
        "agropecuaria": {"reducao_pct": 60, "ncms_prefixo": ["0102","0103","0104","0105","0106","0701","0801","0901","1001","1005","1201","2301","2302","2303","2304","2306","2309","3101","3102","3103","3104","3105"], "base_legal": "LC 214/2025, art. 264"},
        "transporte_publico": {"reducao_pct": 100, "ncms_prefixo": [], "base_legal": "LC 214/2025, art. 267", "nota": "Transporte coletivo alíquota zero"},
        "dispositivos_medicos": {"reducao_pct": 60, "ncms_prefixo": ["9018","9019","9021","9402"], "base_legal": "LC 214/2025, art. 287"},
        "prod_higiene": {"reducao_pct": 60, "ncms_prefixo": ["3401","3402","3306","4818"], "base_legal": "LC 214/2025, art. 290"},
    },
    "is_seletivo": {
        "cigarros": {"ncms_prefixo": ["2402","2403"], "aliquota_adicional_estimada": 100.0, "base_legal": "LC 214/2025, art. 393"},
        "bebidas_alcoolicas": {"ncms_prefixo": ["2203","2204","2205","2206","2207","2208"], "aliquota_adicional_estimada": 30.0, "base_legal": "LC 214/2025, art. 393"},
        "bebidas_acucaradas": {"ncms_prefixo": ["2202"], "aliquota_adicional_estimada": 20.0, "base_legal": "LC 214/2025, art. 393"},
        "minerais_extracao": {"ncms_prefixo": ["2601","2602","2603","2604","2609","2710","2711"], "aliquota_adicional_estimada": 1.0, "base_legal": "LC 214/2025, art. 393"},
        "veiculos_poluentes": {"ncms_prefixo": ["8703","8704"], "aliquota_adicional_estimada": 3.0, "base_legal": "LC 214/2025, art. 393", "nota": "Apenas veículos a combustão fóssil"},
    },
    "base_legal_geral": "Lei Complementar 214/2025"
}

# ===========================================================================
# 4. NBS (Nomenclatura Brasileira de Serviços) — estática
# ===========================================================================
_NBS_DATABASE = {
    "1.0101.10.00": {"descricao": "Serviços de construção de edifícios residenciais", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0101.20.00": {"descricao": "Serviços de construção de edifícios não residenciais", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0102.10.00": {"descricao": "Serviços de construção de rodovias e ferrovias", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0201.10.00": {"descricao": "Serviços de instalação elétrica", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0301.10.00": {"descricao": "Serviços de acabamento de edifícios", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0401.10.00": {"descricao": "Serviços de manutenção predial", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.0501.10.00": {"descricao": "Serviços de engenharia e consultoria técnica", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.0601.10.00": {"descricao": "Serviços de arquitetura e urbanismo", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.0701.10.00": {"descricao": "Serviços de TI e desenvolvimento de software", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0702.10.00": {"descricao": "Serviços de processamento de dados e hospedagem", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0703.10.00": {"descricao": "Serviços de licenciamento de software", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0801.10.00": {"descricao": "Serviços de pesquisa e desenvolvimento", "iss_aliq": 2.0, "ibs_cbs_reducao": 0},
    "1.0901.10.00": {"descricao": "Serviços de assessoria e consultoria empresarial", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.0902.10.00": {"descricao": "Serviços de contabilidade e auditoria", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.0903.10.00": {"descricao": "Serviços jurídicos e advocacia", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.1001.10.00": {"descricao": "Serviços de publicidade e propaganda", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.1101.10.00": {"descricao": "Serviços de telecomunicações", "iss_aliq": 0, "ibs_cbs_reducao": 0, "nota": "ISS não incide (ICMS)"},
    "1.1201.10.00": {"descricao": "Serviços financeiros", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.1301.10.00": {"descricao": "Serviços de transporte rodoviário de carga", "iss_aliq": 0, "ibs_cbs_reducao": 0, "nota": "ISS não incide (ICMS)"},
    "1.1302.10.00": {"descricao": "Serviços de transporte rodoviário de passageiros", "iss_aliq": 0, "ibs_cbs_reducao": 100, "nota": "Alíquota zero IBS/CBS (transporte coletivo)"},
    "1.1401.10.00": {"descricao": "Serviços de seguros", "iss_aliq": 0, "ibs_cbs_reducao": 0, "nota": "IOF, não ISS"},
    "1.1501.10.00": {"descricao": "Serviços educacionais", "iss_aliq": 2.0, "ibs_cbs_reducao": 100, "nota": "IBS/CBS alíquota zero (educação)"},
    "1.1601.10.00": {"descricao": "Serviços de saúde", "iss_aliq": 2.0, "ibs_cbs_reducao": 60, "nota": "Redução 60% IBS/CBS (saúde)"},
    "1.1701.10.00": {"descricao": "Serviços de alimentação e catering", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.1801.10.00": {"descricao": "Serviços de hotelaria e hospedagem", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.1901.10.00": {"descricao": "Serviços de locação de imóveis", "iss_aliq": 0, "ibs_cbs_reducao": 0, "nota": "Fora do campo ISS"},
    "1.2001.10.00": {"descricao": "Serviços de limpeza e conservação", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.2101.10.00": {"descricao": "Serviços de vigilância e segurança", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
    "1.2201.10.00": {"descricao": "Serviços de logística e armazenagem", "iss_aliq": 5.0, "ibs_cbs_reducao": 0},
}

# ===========================================================================
# 5. ALÍQUOTAS ICMS POR UF (atualizadas até 2025)
# ===========================================================================
_ICMS_UF_2025 = {
    "AC": {"interna": 19.0, "fcp": 0.0, "atualizado": "2024-04-01"},
    "AL": {"interna": 19.0, "fcp": 1.0, "atualizado": "2023-04-01"},
    "AM": {"interna": 20.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "AP": {"interna": 18.0, "fcp": 0.0, "atualizado": "2023-01-01"},
    "BA": {"interna": 20.5, "fcp": 2.0, "atualizado": "2024-02-22"},
    "CE": {"interna": 20.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "DF": {"interna": 20.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "ES": {"interna": 17.0, "fcp": 0.0, "atualizado": "2023-01-01"},
    "GO": {"interna": 19.0, "fcp": 1.0, "atualizado": "2024-04-01"},
    "MA": {"interna": 22.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "MG": {"interna": 18.0, "fcp": 0.0, "atualizado": "2024-07-01"},
    "MS": {"interna": 17.0, "fcp": 0.0, "atualizado": "2024-01-01"},
    "MT": {"interna": 17.0, "fcp": 0.0, "atualizado": "2023-01-01"},
    "PA": {"interna": 19.0, "fcp": 0.0, "atualizado": "2024-01-01"},
    "PB": {"interna": 20.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "PE": {"interna": 20.5, "fcp": 2.0, "atualizado": "2024-01-01"},
    "PI": {"interna": 21.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "PR": {"interna": 19.5, "fcp": 0.0, "atualizado": "2024-03-13"},
    "RJ": {"interna": 22.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "RN": {"interna": 20.0, "fcp": 2.0, "atualizado": "2024-01-01"},
    "RO": {"interna": 19.5, "fcp": 0.0, "atualizado": "2024-04-01"},
    "RR": {"interna": 20.0, "fcp": 0.0, "atualizado": "2024-01-01"},
    "RS": {"interna": 17.0, "fcp": 0.0, "atualizado": "2024-01-01"},
    "SC": {"interna": 17.0, "fcp": 0.0, "atualizado": "2024-01-01"},
    "SE": {"interna": 19.0, "fcp": 1.0, "atualizado": "2024-01-01"},
    "SP": {"interna": 18.0, "fcp": 0.0, "atualizado": "2024-01-01"},
    "TO": {"interna": 20.0, "fcp": 2.0, "atualizado": "2024-01-01"},
}
_ICMS_INTERESTADUAL = {
    ("S", "N"): 7.0,   # Sul/Sudeste → Norte/Nordeste/CO/ES
    ("S", "S"): 12.0,  # Sul/Sudeste → Sul/Sudeste
    ("N", "S"): 12.0,  # Norte/Nordeste/CO/ES → Sul/Sudeste
    ("N", "N"): 12.0,  # Norte/Nordeste/CO/ES → Norte/Nordeste/CO/ES
    ("IMPORTADO", None): 4.0,  # Produtos importados (Res. Senado 13/2012)
}
_UFS_SUL_SUDESTE = {"SP","RJ","MG","ES","PR","SC","RS"}

# ===========================================================================
# 6. MONOFÁSICOS PIS/COFINS EXPANDIDO (por lei/segmento)
# ===========================================================================
_MONOFASICOS_EXPANDIDO = {
    # Lei 10.147/2000 — Medicamentos e perfumaria
    "LEI_10147_2000": {
        "descricao": "Medicamentos, perfumaria, toucador e higiene pessoal",
        "ncms_prefixo": ["3001","3002","3003","3004","3005","3006","3303","3304","3305","3306","3307","3401","4014","4818","5601"],
        "aliq_pis_produtor": 2.10,
        "aliq_cofins_produtor": 9.90,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "2000-12-22",
    },
    # Lei 10.485/2002 — Autopeças e veículos
    "LEI_10485_2002": {
        "descricao": "Veículos, máquinas, autopeças",
        "ncms_prefixo": ["8701","8702","8703","8704","8705","8706","8707","8708","8709","8716","4011","4012","4013","6813","7007","7009","7320","8301","8302","8409","8413","8421","8481","8482","8483","8501","8507","8511","8512","8544","4009","4010","4016","6812","6914","7311","7322","7325","7326","8414","8415","8424","8425","8431","8484","8505","8536","8537","8539","8544","9026","9029","9031","9032","9104","9401","9613"],
        "aliq_pis_produtor": 1.65,
        "aliq_cofins_produtor": 7.60,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "2002-07-04",
        "nota": "Autopeças: PIS 1,65% e COFINS 7,6% na venda pelo fabricante; 0% na revenda"
    },
    # Lei 10.865/2004, art. 8 — Pneus
    "LEI_10865_2004_PNEUS": {
        "descricao": "Pneus novos de borracha e câmaras de ar",
        "ncms_prefixo": ["4011","4012","4013"],
        "aliq_pis_produtor": 2.0,
        "aliq_cofins_produtor": 9.6,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "2004-05-13",
    },
    # Lei 11.116/2005 — Biodiesel
    "LEI_11116_2005": {
        "descricao": "Biodiesel",
        "ncms_prefixo": ["38260000","27101921"],
        "aliq_pis_produtor": 6.15,
        "aliq_cofins_produtor": 28.32,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "2005-06-14",
    },
    # Lei 9.718/1998, art. 4-A — Combustíveis
    "LEI_9718_1998_COMB": {
        "descricao": "Gasolina, óleo diesel, GLP, querosene de aviação, álcool hidratado",
        "ncms_prefixo": ["2710","2711","2207"],
        "aliq_pis_produtor": 5.08,
        "aliq_cofins_produtor": 23.44,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "1998-11-27",
        "nota": "Alíquotas variam por tipo de combustível. Valores são referência."
    },
    # Lei 10.833/2003, art. 58-A a 58-U — Bebidas frias
    "LEI_10833_2003_BEBIDAS": {
        "descricao": "Águas, refrigerantes, cervejas e demais bebidas",
        "ncms_prefixo": ["2201","2202","2203","2204","2205","2206","2208","2009"],
        "aliq_pis_produtor": 2.32,
        "aliq_cofins_produtor": 10.68,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "2015-05-01",
        "nota": "Alíquotas específicas por produto. Valores são referência."
    },
    # Decreto 5.602/2005 — Cigarros
    "DEC_5602_2005_CIGARROS": {
        "descricao": "Cigarros",
        "ncms_prefixo": ["2402"],
        "aliq_pis_produtor": 3.42,
        "aliq_cofins_produtor": 15.78,
        "aliq_pis_revenda": 0.0,
        "aliq_cofins_revenda": 0.0,
        "vigencia": "2005-11-07",
    },
}

# ===========================================================================
# FUNÇÕES CORE — CACHE SQLite EXPANDIDO
# ===========================================================================
def _criar_db_expandido():
    """Cria/conecta ao banco SQLite expandido com todas as tabelas."""
    _os_exp.makedirs(_CACHE_DB_EXPANDED.parent, exist_ok=True)
    conn = _sqlite3_exp.connect(str(_CACHE_DB_EXPANDED))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")

    # Tabela principal de fontes (metadados)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fontes (
            nome TEXT PRIMARY KEY,
            descricao TEXT,
            url TEXT,
            ultima_atualizacao TEXT,
            hash_arquivo TEXT,
            total_registros INTEGER DEFAULT 0,
            status TEXT DEFAULT 'PENDENTE',
            vigencia_dias INTEGER DEFAULT 30,
            erro_msg TEXT
        )
    """)
    # Tabela CEST
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cest (
            cest TEXT PRIMARY KEY,
            ncms TEXT,
            descricao TEXT,
            segmento TEXT,
            mva_original REAL DEFAULT 0
        )
    """)
    # Tabela Convênios ICMS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS convenios_icms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            convenio TEXT,
            tipo TEXT,
            descricao TEXT,
            ncms_prefixo TEXT,
            ufs TEXT,
            vigencia_inicio TEXT,
            vigencia_fim TEXT,
            base_legal TEXT,
            reducao_bc_pct REAL DEFAULT 0
        )
    """)
    # Tabela ICMS UF
    conn.execute("""
        CREATE TABLE IF NOT EXISTS icms_uf (
            uf TEXT PRIMARY KEY,
            aliq_interna REAL,
            fcp REAL DEFAULT 0,
            atualizado TEXT
        )
    """)
    # Tabela NBS
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nbs (
            codigo TEXT PRIMARY KEY,
            descricao TEXT,
            iss_aliq REAL DEFAULT 0,
            ibs_cbs_reducao REAL DEFAULT 0,
            nota TEXT
        )
    """)
    # Tabela Monofásicos detalhada
    conn.execute("""
        CREATE TABLE IF NOT EXISTS monofasicos_det (
            lei TEXT,
            ncm_prefixo TEXT,
            descricao TEXT,
            aliq_pis_produtor REAL,
            aliq_cofins_produtor REAL,
            aliq_pis_revenda REAL,
            aliq_cofins_revenda REAL,
            vigencia TEXT,
            PRIMARY KEY (lei, ncm_prefixo)
        )
    """)
    # Tabela IBS/CBS transição
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ibs_cbs_transicao (
            ano INTEGER PRIMARY KEY,
            cbs REAL,
            ibs REAL,
            nota TEXT
        )
    """)
    # Audit log
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            fonte TEXT,
            acao TEXT,
            status TEXT,
            detalhes TEXT
        )
    """)
    conn.commit()
    return conn


def _log_auditoria(conn, fonte: str, acao: str, status: str, detalhes: str = ""):
    """Registra ação no log de auditoria."""
    conn.execute(
        "INSERT INTO audit_log (timestamp, fonte, acao, status, detalhes) VALUES (?,?,?,?,?)",
        (_dt_exp.now().isoformat(), fonte, acao, status, detalhes)
    )
    conn.commit()


def popular_cest_cache(conn=None):
    """Popula cache CEST com base estática."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    conn.execute("DELETE FROM cest")
    for cest_code, info in _CEST_DATABASE.items():
        conn.execute(
            "INSERT OR REPLACE INTO cest (cest, ncms, descricao, segmento, mva_original) VALUES (?,?,?,?,?)",
            (cest_code, _json_exp.dumps(info["ncms"]), info["descricao"], info["segmento"], info.get("mva_original", 0))
        )
    conn.execute(
        "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?)",
        ("CEST", "Código Especificador ST (Conv. ICMS 142/2015)", "CONFAZ", _dt_exp.now().isoformat(), len(_CEST_DATABASE), "OK_FALLBACK", 90)
    )
    _log_auditoria(conn, "CEST", "POPULAR", "OK", f"{len(_CEST_DATABASE)} CESTs carregados (base estática)")
    conn.commit()
    if close:
        conn.close()
    return len(_CEST_DATABASE)


def popular_convenios_cache(conn=None):
    """Popula cache de Convênios ICMS."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    conn.execute("DELETE FROM convenios_icms")
    for cv in _CONVENIOS_ICMS:
        ufs_str = "TODAS" if cv["ufs"] == "TODAS" else _json_exp.dumps(cv["ufs"])
        conn.execute(
            "INSERT INTO convenios_icms (convenio, tipo, descricao, ncms_prefixo, ufs, vigencia_inicio, vigencia_fim, base_legal, reducao_bc_pct) VALUES (?,?,?,?,?,?,?,?,?)",
            (cv["convenio"], cv["tipo"], cv["descricao"], _json_exp.dumps(cv["ncms_prefixo"]),
             ufs_str, cv.get("vigencia_inicio"), cv.get("vigencia_fim"), cv.get("base_legal",""),
             cv.get("reducao_bc_pct", 0))
        )
    conn.execute(
        "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?)",
        ("CONVENIOS_ICMS", "Convênios ICMS/CONFAZ", "CONFAZ", _dt_exp.now().isoformat(), len(_CONVENIOS_ICMS), "OK_FALLBACK", 90)
    )
    _log_auditoria(conn, "CONVENIOS_ICMS", "POPULAR", "OK", f"{len(_CONVENIOS_ICMS)} convênios carregados")
    conn.commit()
    if close:
        conn.close()
    return len(_CONVENIOS_ICMS)


def popular_icms_uf_cache(conn=None):
    """Popula alíquotas ICMS por UF."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    conn.execute("DELETE FROM icms_uf")
    for uf, info in _ICMS_UF_2025.items():
        conn.execute(
            "INSERT OR REPLACE INTO icms_uf (uf, aliq_interna, fcp, atualizado) VALUES (?,?,?,?)",
            (uf, info["interna"], info["fcp"], info["atualizado"])
        )
    conn.execute(
        "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?)",
        ("ICMS_UF", "Alíquotas ICMS internas por UF (2025)", "SEFAZ", _dt_exp.now().isoformat(), len(_ICMS_UF_2025), "OK_FALLBACK", 30)
    )
    _log_auditoria(conn, "ICMS_UF", "POPULAR", "OK", f"{len(_ICMS_UF_2025)} UFs carregadas")
    conn.commit()
    if close:
        conn.close()
    return len(_ICMS_UF_2025)


def popular_nbs_cache(conn=None):
    """Popula base NBS."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    conn.execute("DELETE FROM nbs")
    for codigo, info in _NBS_DATABASE.items():
        conn.execute(
            "INSERT OR REPLACE INTO nbs (codigo, descricao, iss_aliq, ibs_cbs_reducao, nota) VALUES (?,?,?,?,?)",
            (codigo, info["descricao"], info.get("iss_aliq", 0), info.get("ibs_cbs_reducao", 0), info.get("nota",""))
        )
    conn.execute(
        "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?)",
        ("NBS", "Nomenclatura Brasileira de Serviços", "gov.br", _dt_exp.now().isoformat(), len(_NBS_DATABASE), "OK_FALLBACK", 30)
    )
    _log_auditoria(conn, "NBS", "POPULAR", "OK", f"{len(_NBS_DATABASE)} NBS carregados")
    conn.commit()
    if close:
        conn.close()
    return len(_NBS_DATABASE)


def popular_monofasicos_det_cache(conn=None):
    """Popula monofásicos detalhados por lei."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    conn.execute("DELETE FROM monofasicos_det")
    count = 0
    for lei, info in _MONOFASICOS_EXPANDIDO.items():
        for prefix in info["ncms_prefixo"]:
            conn.execute(
                "INSERT OR REPLACE INTO monofasicos_det (lei, ncm_prefixo, descricao, aliq_pis_produtor, aliq_cofins_produtor, aliq_pis_revenda, aliq_cofins_revenda, vigencia) VALUES (?,?,?,?,?,?,?,?)",
                (lei, prefix, info["descricao"], info.get("aliq_pis_produtor", 0), info.get("aliq_cofins_produtor", 0),
                 info.get("aliq_pis_revenda", 0), info.get("aliq_cofins_revenda", 0), info.get("vigencia",""))
            )
            count += 1
    conn.execute(
        "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?)",
        ("MONOFASICOS_DET", "NCMs monofásicos PIS/COFINS detalhados por lei", "RFB", _dt_exp.now().isoformat(), count, "OK_FALLBACK", 90)
    )
    _log_auditoria(conn, "MONOFASICOS_DET", "POPULAR", "OK", f"{count} regras monofásicas carregadas ({len(_MONOFASICOS_EXPANDIDO)} leis)")
    conn.commit()
    if close:
        conn.close()
    return count


def popular_ibs_cbs_cache(conn=None):
    """Popula tabela de transição IBS/CBS."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    conn.execute("DELETE FROM ibs_cbs_transicao")
    trans = _IBS_CBS_REGRAS["transicao"]
    for ano_str, info in trans.items():
        conn.execute(
            "INSERT OR REPLACE INTO ibs_cbs_transicao (ano, cbs, ibs, nota) VALUES (?,?,?,?)",
            (int(ano_str), info["cbs"], info["ibs"], info.get("nota",""))
        )
    conn.execute(
        "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?)",
        ("IBS_CBS", "Transição IBS/CBS (LC 214/2025)", "LC 214/2025", _dt_exp.now().isoformat(), len(trans), "OK_FALLBACK", 30)
    )
    _log_auditoria(conn, "IBS_CBS", "POPULAR", "OK", f"{len(trans)} anos de transição carregados")
    conn.commit()
    if close:
        conn.close()
    return len(trans)


# ===========================================================================
# FUNÇÕES DE ATUALIZAÇÃO COM APIs REAIS
# ===========================================================================
def atualizar_selic_cache(conn=None):
    """Busca taxa SELIC do BCB e armazena."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    if _requests_exp is None:
        _log_auditoria(conn, "BCB_SELIC", "ATUALIZAR", "ERRO", "requests não disponível")
        if close: conn.close()
        return {"status": "ERRO", "erro": "requests não instalado"}
    try:
        _hoje = _dt_exp.now()
        _inicio = _dt_exp(_hoje.year - 1, _hoje.month, _hoje.day)
        _url_selic = _URLS["bcb_selic"].format(di=_inicio.strftime("%d/%m/%Y"), df=_hoje.strftime("%d/%m/%Y"))
        r = _requests_exp.get(_url_selic, timeout=15, verify=True)
        r.raise_for_status()
        data = r.json()
        # Store as JSON in fontes
        hash_val = _hashlib_exp.sha256(_json_exp.dumps(data, sort_keys=True).encode()).hexdigest()
        conn.execute(
            "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, hash_arquivo, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?,?)",
            ("BCB_SELIC", "Taxa SELIC diária (BCB)", _URLS["bcb_selic"], _dt_exp.now().isoformat(), hash_val, len(data), "OK_API", 1)
        )
        _log_auditoria(conn, "BCB_SELIC", "ATUALIZAR", "OK", f"{len(data)} registros SELIC obtidos")
        conn.commit()
        taxa_atual = float(data[-1]["valor"]) if data else 0
        if close: conn.close()
        return {"status": "OK", "taxa_atual_diaria": taxa_atual, "registros": len(data), "fonte": "BCB_API"}
    except Exception as e:
        _log_auditoria(conn, "BCB_SELIC", "ATUALIZAR", "ERRO", str(e))
        conn.commit()
        if close: conn.close()
        return {"status": "ERRO", "erro": str(e)}


def atualizar_ipca_cache(conn=None):
    """Busca IPCA mensal do BCB e armazena."""
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    if _requests_exp is None:
        _log_auditoria(conn, "BCB_IPCA", "ATUALIZAR", "ERRO", "requests não disponível")
        if close: conn.close()
        return {"status": "ERRO", "erro": "requests não instalado"}
    try:
        _hoje2 = _dt_exp.now()
        _inicio2 = _dt_exp(_hoje2.year - 5, _hoje2.month, 1)
        _url_ipca = _URLS["bcb_ipca"].format(di=_inicio2.strftime("%d/%m/%Y"), df=_hoje2.strftime("%d/%m/%Y"))
        r = _requests_exp.get(_url_ipca, timeout=15, verify=True)
        r.raise_for_status()
        data = r.json()
        hash_val = _hashlib_exp.sha256(_json_exp.dumps(data, sort_keys=True).encode()).hexdigest()
        conn.execute(
            "INSERT OR REPLACE INTO fontes (nome, descricao, url, ultima_atualizacao, hash_arquivo, total_registros, status, vigencia_dias) VALUES (?,?,?,?,?,?,?,?)",
            ("BCB_IPCA", "IPCA mensal (BCB)", _URLS["bcb_ipca"], _dt_exp.now().isoformat(), hash_val, len(data), "OK_API", 1)
        )
        _log_auditoria(conn, "BCB_IPCA", "ATUALIZAR", "OK", f"{len(data)} registros IPCA obtidos")
        conn.commit()
        ipca_ultimo = float(data[-1]["valor"]) if data else 0
        if close: conn.close()
        return {"status": "OK", "ipca_ultimo_mes": ipca_ultimo, "registros": len(data), "fonte": "BCB_API"}
    except Exception as e:
        _log_auditoria(conn, "BCB_IPCA", "ATUALIZAR", "ERRO", str(e))
        conn.commit()
        if close: conn.close()
        return {"status": "ERRO", "erro": str(e)}


def consultar_cnpj_brasilapi(cnpj: str):
    """Consulta CNPJ na BrasilAPI com sanitização."""
    cnpj_limpo = _re_exp.sub(r"[^\d]", "", str(cnpj))
    if len(cnpj_limpo) != 14:
        return {"status": "ERRO", "erro": "CNPJ inválido (deve ter 14 dígitos)"}
    if _requests_exp is None:
        return {"status": "ERRO", "erro": "requests não instalado"}
    try:
        r = _requests_exp.get(f"{_URLS['brasilapi_cnpj']}{cnpj_limpo}", timeout=15, verify=True)
        if r.status_code == 404:
            return {"status": "NAO_ENCONTRADO", "cnpj": cnpj_limpo}
        r.raise_for_status()
        data = r.json()
        return {
            "status": "OK",
            "cnpj": cnpj_limpo,
            "razao_social": data.get("razao_social", ""),
            "nome_fantasia": data.get("nome_fantasia", ""),
            "situacao_cadastral": data.get("descricao_situacao_cadastral", ""),
            "natureza_juridica": data.get("natureza_juridica", ""),
            "porte": data.get("porte", ""),
            "simples_optante": data.get("opcao_pelo_simples", False),
            "simples_data_opcao": data.get("data_opcao_pelo_simples"),
            "mei_optante": data.get("opcao_pelo_mei", False),
            "uf": data.get("uf", ""),
            "municipio": data.get("municipio", ""),
            "cnae_principal": data.get("cnae_fiscal", ""),
            "cnae_descricao": data.get("cnae_fiscal_descricao", ""),
            "fonte": "BRASILAPI",
        }
    except Exception as e:
        return {"status": "ERRO", "erro": str(e)}


# ===========================================================================
# FUNÇÕES DE CONSULTA EXPANDIDA
# ===========================================================================
def consultar_cest_por_ncm(ncm: str, conn=None) -> List[Dict]:
    """Busca CESTs associados a um NCM."""
    ncm_limpo = _re_exp.sub(r"[^\d]", "", str(ncm)).zfill(8)
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    rows = conn.execute("SELECT cest, ncms, descricao, segmento, mva_original FROM cest").fetchall()
    resultados = []
    for row in rows:
        ncms_list = _json_exp.loads(row[1]) if row[1] else []
        if ncm_limpo in ncms_list or ncm_limpo[:4] in [n[:4] for n in ncms_list]:
            resultados.append({
                "cest": row[0], "descricao": row[2],
                "segmento": row[3], "mva_original": row[4],
            })
    if close: conn.close()
    return resultados


def consultar_convenios_por_ncm(ncm: str, uf: str = None, conn=None) -> List[Dict]:
    """Busca convênios ICMS aplicáveis a um NCM/UF."""
    ncm_limpo = _re_exp.sub(r"[^\d]", "", str(ncm)).zfill(8)
    uf_limpo = str(uf).upper().strip() if uf else None
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    rows = conn.execute("SELECT convenio, tipo, descricao, ncms_prefixo, ufs, vigencia_inicio, vigencia_fim, base_legal, reducao_bc_pct FROM convenios_icms").fetchall()
    resultados = []
    for row in rows:
        prefixos = _json_exp.loads(row[3]) if row[3] else []
        ufs_conv = row[4]
        # Check NCM match
        ncm_match = any(ncm_limpo.startswith(p) for p in prefixos)
        if not ncm_match:
            continue
        # Check UF match
        if uf_limpo and ufs_conv != "TODAS":
            ufs_list = _json_exp.loads(ufs_conv) if ufs_conv.startswith("[") else [ufs_conv]
            if uf_limpo not in ufs_list:
                continue
        resultados.append({
            "convenio": row[0], "tipo": row[1], "descricao": row[2],
            "vigencia_inicio": row[5], "vigencia_fim": row[6],
            "base_legal": row[7], "reducao_bc_pct": row[8],
        })
    if close: conn.close()
    return resultados


def consultar_icms_uf(uf: str, conn=None) -> Dict:
    """Retorna alíquota ICMS interna de uma UF."""
    uf_limpo = _re_exp.sub(r"[^A-Z]", "", str(uf).upper())
    if len(uf_limpo) != 2:
        return {"uf": uf_limpo, "erro": "UF inválida"}
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    row = conn.execute("SELECT aliq_interna, fcp, atualizado FROM icms_uf WHERE uf=?", (uf_limpo,)).fetchone()
    if close: conn.close()
    if row:
        return {"uf": uf_limpo, "aliq_interna": row[0], "fcp": row[1], "atualizado": row[2], "total": row[0] + row[1]}
    return _ICMS_UF_2025.get(uf_limpo, {"uf": uf_limpo, "aliq_interna": 18.0, "fcp": 0, "atualizado": "fallback", "total": 18.0})


def consultar_icms_interestadual(uf_origem: str, uf_destino: str, importado: bool = False) -> Dict:
    """Calcula alíquota interestadual ICMS."""
    if importado:
        return {"aliquota": 4.0, "base_legal": "Resolução do Senado 13/2012", "tipo": "IMPORTADO"}
    grupo_orig = "S" if uf_origem.upper() in _UFS_SUL_SUDESTE else "N"
    grupo_dest = "S" if uf_destino.upper() in _UFS_SUL_SUDESTE else "N"
    aliq = _ICMS_INTERESTADUAL.get((grupo_orig, grupo_dest), 12.0)
    return {"aliquota": aliq, "origem": uf_origem, "destino": uf_destino, "grupo_orig": grupo_orig, "grupo_dest": grupo_dest}


def consultar_monofasico_detalhado(ncm: str, conn=None) -> Dict:
    """Consulta detalhada de regime monofásico com lei e alíquotas."""
    ncm_limpo = _re_exp.sub(r"[^\d]", "", str(ncm)).zfill(8)
    close = conn is None
    if conn is None:
        conn = _criar_db_expandido()
    rows = conn.execute(
        "SELECT lei, ncm_prefixo, descricao, aliq_pis_produtor, aliq_cofins_produtor, aliq_pis_revenda, aliq_cofins_revenda, vigencia FROM monofasicos_det"
    ).fetchall()
    if close: conn.close()
    matches = []
    for row in rows:
        if ncm_limpo.startswith(row[1]):
            matches.append({
                "lei": row[0], "ncm_prefixo": row[1], "descricao": row[2],
                "aliq_pis_produtor": row[3], "aliq_cofins_produtor": row[4],
                "aliq_pis_revenda": row[5], "aliq_cofins_revenda": row[6],
                "vigencia": row[7],
            })
    if matches:
        return {"ncm": ncm_limpo, "monofasico": True, "regras": matches, "lei_principal": matches[0]["lei"]}
    return {"ncm": ncm_limpo, "monofasico": False, "regras": []}


def consultar_ibs_cbs(ano: int = None) -> Dict:
    """Retorna alíquotas IBS/CBS para um ano ou todas as transições."""
    if ano is None:
        ano = _dt_exp.now().year
    trans = _IBS_CBS_REGRAS["transicao"]
    ano_str = str(ano)
    if ano_str in trans:
        info = trans[ano_str]
        return {"ano": ano, "cbs": info["cbs"], "ibs": info["ibs"], "total": info["cbs"] + info["ibs"], "nota": info.get("nota",""), "status": "EM_TRANSICAO"}
    elif ano < 2026:
        return {"ano": ano, "cbs": 0, "ibs": 0, "total": 0, "nota": "Período anterior à reforma", "status": "PRE_REFORMA"}
    elif ano >= 2033:
        return {"ano": ano, "cbs": 8.8, "ibs": 17.7, "total": 26.5, "nota": "Regime pleno IBS/CBS", "status": "PLENO"}
    else:
        return {"ano": ano, "cbs": 0, "ibs": 0, "total": 0, "nota": "Ano sem regra específica", "status": "INDEFINIDO"}


def consultar_is_seletivo(ncm: str) -> Dict:
    """Verifica se NCM está sujeito ao Imposto Seletivo."""
    ncm_limpo = _re_exp.sub(r"[^\d]", "", str(ncm)).zfill(8)
    for cat, info in _IBS_CBS_REGRAS["is_seletivo"].items():
        if any(ncm_limpo.startswith(p) for p in info["ncms_prefixo"]):
            return {
                "ncm": ncm_limpo, "seletivo": True, "categoria": cat,
                "aliquota_adicional_estimada": info["aliquota_adicional_estimada"],
                "base_legal": info["base_legal"],
                "nota": info.get("nota",""),
            }
    return {"ncm": ncm_limpo, "seletivo": False}


# ===========================================================================
# INICIALIZAÇÃO COMPLETA — POPULAR TODAS AS BASES
# ===========================================================================
def inicializar_todas_fontes(force: bool = False) -> Dict:
    """Inicializa/atualiza todas as fontes de dados fiscais."""
    conn = _criar_db_expandido()
    resultados = {}

    # 1. CEST
    try:
        n = popular_cest_cache(conn)
        resultados["CEST"] = {"status": "OK", "registros": n}
    except Exception as e:
        resultados["CEST"] = {"status": "ERRO", "erro": str(e)}

    # 2. Convênios ICMS
    try:
        n = popular_convenios_cache(conn)
        resultados["CONVENIOS_ICMS"] = {"status": "OK", "registros": n}
    except Exception as e:
        resultados["CONVENIOS_ICMS"] = {"status": "ERRO", "erro": str(e)}

    # 3. ICMS UF
    try:
        n = popular_icms_uf_cache(conn)
        resultados["ICMS_UF"] = {"status": "OK", "registros": n}
    except Exception as e:
        resultados["ICMS_UF"] = {"status": "ERRO", "erro": str(e)}

    # 4. NBS
    try:
        n = popular_nbs_cache(conn)
        resultados["NBS"] = {"status": "OK", "registros": n}
    except Exception as e:
        resultados["NBS"] = {"status": "ERRO", "erro": str(e)}

    # 5. Monofásicos detalhados
    try:
        n = popular_monofasicos_det_cache(conn)
        resultados["MONOFASICOS_DET"] = {"status": "OK", "registros": n}
    except Exception as e:
        resultados["MONOFASICOS_DET"] = {"status": "ERRO", "erro": str(e)}

    # 6. IBS/CBS
    try:
        n = popular_ibs_cbs_cache(conn)
        resultados["IBS_CBS"] = {"status": "OK", "registros": n}
    except Exception as e:
        resultados["IBS_CBS"] = {"status": "ERRO", "erro": str(e)}

    # 7. SELIC (API real)
    resultados["BCB_SELIC"] = atualizar_selic_cache(conn)

    # 8. IPCA (API real)
    resultados["BCB_IPCA"] = atualizar_ipca_cache(conn)

    conn.close()
    return resultados


def obter_status_fontes() -> List[Dict]:
    """Retorna status de todas as fontes de dados."""
    try:
        conn = _criar_db_expandido()
        rows = conn.execute("SELECT nome, descricao, url, ultima_atualizacao, total_registros, status, vigencia_dias, erro_msg FROM fontes ORDER BY nome").fetchall()
        conn.close()
        fontes = []
        for row in rows:
            ultima = _dt_exp.fromisoformat(row[3]) if row[3] else None
            idade = ((_dt_exp.now() - ultima).days if ultima else 999)
            vencido = idade > (row[6] or 30)
            fontes.append({
                "nome": row[0], "descricao": row[1], "url": row[2],
                "ultima_atualizacao": row[3], "total_registros": row[4],
                "status": row[5], "vigencia_dias": row[6],
                "idade_dias": idade, "vencido": vencido,
                "erro": row[7],
            })
        return fontes
    except:
        return []


def obter_audit_log(limite: int = 50) -> List[Dict]:
    """Retorna últimas entradas do log de auditoria."""
    try:
        conn = _criar_db_expandido()
        rows = conn.execute("SELECT timestamp, fonte, acao, status, detalhes FROM audit_log ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        conn.close()
        return [{"timestamp": r[0], "fonte": r[1], "acao": r[2], "status": r[3], "detalhes": r[4]} for r in rows]
    except:
        return []


# ===========================================================================
# SELF-TEST
# ===========================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("INTEGRADOR RFB EXPANDIDO — SELF-TEST")
    print("=" * 70)

    # Inicializar todas as fontes
    print("\n[1] Inicializando todas as fontes...")
    results = inicializar_todas_fontes()
    for nome, info in results.items():
        status = "✅" if info.get("status") == "OK" or "OK" in str(info.get("status","")) else "❌"
        registros = info.get("registros", info.get("total_registros", "?"))
        print(f"    {status} {nome}: {registros} registros")

    # Consultas
    print("\n[2] Consultas de teste...")
    # CEST
    cest_r = consultar_cest_por_ncm("40111000")
    print(f"    CEST 40111000 (pneu): {len(cest_r)} resultado(s) — {cest_r[0]['segmento'] if cest_r else 'N/A'}")

    # Convênios
    conv_r = consultar_convenios_por_ncm("30049099", "SP")
    print(f"    Convênios 30049099 (medicamento SP): {len(conv_r)} resultado(s)")

    # ICMS UF
    icms_sp = consultar_icms_uf("SP")
    print(f"    ICMS SP: {icms_sp['aliq_interna']}% + FCP {icms_sp.get('fcp',0)}%")

    # Interestadual
    inter = consultar_icms_interestadual("SP", "BA")
    print(f"    ICMS Interestadual SP→BA: {inter['aliquota']}%")

    # Monofásico detalhado
    mono_r = consultar_monofasico_detalhado("24021000")
    print(f"    Monofásico 24021000 (cigarro): {mono_r['monofasico']} — Lei: {mono_r.get('lei_principal','?')}")

    # IBS/CBS
    ibs = consultar_ibs_cbs(2029)
    print(f"    IBS/CBS 2029: CBS {ibs['cbs']}% + IBS {ibs['ibs']}% = {ibs['total']}%")

    # IS Seletivo
    is_r = consultar_is_seletivo("22021000")
    print(f"    IS Seletivo 22021000 (refrigerante): {is_r['seletivo']} — Add: {is_r.get('aliquota_adicional_estimada',0)}%")

    # CNPJ
    cnpj_r = consultar_cnpj_brasilapi("00000000000191")
    print(f"    CNPJ 00.000.000/0001-91: {cnpj_r.get('razao_social','?')[:30]} — Simples: {cnpj_r.get('simples_optante','?')}")

    # Status das fontes
    print("\n[3] Status das fontes...")
    fontes = obter_status_fontes()
    for f in fontes:
        icon = "🟢" if not f["vencido"] and "OK" in f["status"] else "🔴"
        print(f"    {icon} {f['nome']:20s} | {f['total_registros']:>6} regs | {f['status']:12s} | {f['idade_dias']}d")

    # Audit log
    print("\n[4] Audit log (últimas 5 entradas)...")
    logs = obter_audit_log(5)
    for log_entry in logs:
        print(f"    [{log_entry['timestamp'][:19]}] {log_entry['fonte']:15s} → {log_entry['acao']:10s} = {log_entry['status']}")

    print("\n" + "=" * 70)
    ok = sum(1 for v in results.values() if "OK" in str(v.get("status","")))
    print(f"✅ {ok}/{len(results)} fontes inicializadas com sucesso!")
    print("=" * 70)
