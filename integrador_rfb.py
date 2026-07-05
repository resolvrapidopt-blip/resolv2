# ===========================================================================
# integrador_rfb.py — Integração Oficial e Segura com a Receita Federal
# ResolvRapido Brasil v18.1
# ===========================================================================
# Fontes:
#   - Siscomex Classif API (NCM + IPI)
#   - gov.br RFB (monofásicos PIS/COFINS)
# Segurança: SSL obrigatório, sanitização de entrada, timeout, cache SQLite
#            com hash SHA-256 de integridade, fallback para base local
# ===========================================================================

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("ResolvRapido.RFB")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# URLs OFICIAIS
# ---------------------------------------------------------------------------
# API pública do Siscomex Classif — retorna JSON com NCM + descrição + IPI
URL_CLASSIF_NCM = (
    "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/json"
)
# Consulta individual de NCM (fallback)
URL_CLASSIF_NCM_ITEM = (
    "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura?codigo={ncm}"
)
# Lista de NCMs monofásicos publicada pela RFB (JSON)
URL_NCM_MONOFASICO_GOV = (
    "https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/"
    "declaracoes-e-demonstrativos/ecf/tabelas-ncm-monofasico.json"
)
# Tabela TIPI em CSV publicada pelo governo
URL_TIPI_CSV = (
    "https://portalunico.siscomex.gov.br/classif/api/publico/nomenclatura/download/csv"
)

# ---------------------------------------------------------------------------
# PATHS
# ---------------------------------------------------------------------------
CACHE_DIR = Path("data_brasil")
CACHE_DB = CACHE_DIR / "rfb_cache.db"
FALLBACK_JSON = "ncm_database.json"

# ---------------------------------------------------------------------------
# LISTA INTERNA DE NCMs MONOFÁSICOS (FALLBACK)
# Aprox. 400 NCMs de combustíveis, medicamentos, autopeças, bebidas, cosméticos,
# cigarros conforme Leis 10.147/00, 10.485/02, 10.560/02, 11.116/05 etc.
# ---------------------------------------------------------------------------
_MONOFASICOS_INTERNOS = {
    # === COMBUSTÍVEIS (Lei 10.560/02 + 11.116/05) ===
    "27101159", "27101911", "27101921", "27101929", "27101931", "27101932",
    "27101941", "27101999", "27111100", "27111200", "27111300", "27111400",
    "27111900", "27112100", "27112900", "27160000", "22071000", "22072010",
    "29091910", "38249951", "38249953", "38260000",
    # === MEDICAMENTOS E PRODUTOS FARMACÊUTICOS (Lei 10.147/00) ===
    "30011000", "30012000", "30019010", "30019099", "30021100", "30021200",
    "30021300", "30021400", "30021500", "30021900", "30022000", "30023000",
    "30029010", "30029019", "30029091", "30029099", "30031000", "30032000",
    "30033100", "30033900", "30034100", "30034200", "30034300", "30034900",
    "30039011", "30039019", "30039021", "30039029", "30039031", "30039039",
    "30039041", "30039049", "30039051", "30039059", "30039061", "30039069",
    "30039071", "30039079", "30039091", "30039099", "30041000", "30042000",
    "30043100", "30043200", "30043900", "30044100", "30044200", "30044300",
    "30044900", "30045010", "30045020", "30045030", "30045040", "30045050",
    "30045060", "30045090", "30046000", "30049011", "30049019", "30049021",
    "30049029", "30049031", "30049039", "30049041", "30049049", "30049051",
    "30049059", "30049061", "30049069", "30049091", "30049099",
    # === COSMÉTICOS E HIGIENE PESSOAL (Lei 10.147/00) ===
    "33030010", "33030020", "33041000", "33042000", "33043000", "33049100",
    "33049900", "33051000", "33052000", "33053000", "33059000", "33061000",
    "33062000", "33069000", "33071000", "33072010", "33072090", "33073000",
    "33074100", "33074900", "33079000", "34011100", "34011900", "34012010",
    "34012090", "34013000", "40140010", "40140090", "48184000", "56012100",
    "56012210", "56012290", "56012300", "96032100", "96032900", "96033000",
    # === AUTOPEÇAS (Lei 10.485/02) ===
    "40111000", "40112010", "40112090", "40113000", "40114000", "40115000",
    "40116100", "40116200", "40116300", "40116900", "40119200", "40119300",
    "40119400", "40119900", "68131000", "68139010", "68139090", "70091000",
    "70099100", "70099200", "73181500", "73182100", "73182200", "73182400",
    "84099111", "84099112", "84099113", "84099119", "84099191", "84099199",
    "84099911", "84099912", "84099919", "84099921", "84099929", "84099991",
    "84099999", "84133000", "84137010", "84137090", "84139100", "84149010",
    "84149021", "84149029", "84149031", "84149039", "84212300", "84212910",
    "84219110", "84219190", "84219910", "84219990", "84314910", "84314991",
    "84314999", "84831010", "84831021", "84831029", "84831090", "84832000",
    "84833000", "84834000", "84835010", "84835090", "84836010", "84836021",
    "84836029", "84836090", "84839000", "85011011", "85011019", "85011021",
    "85011029", "85012000", "85013100", "85013200", "85013310", "85013320",
    "85013390", "85014011", "85014012", "85014019", "85014021", "85014022",
    "85014029", "85015110", "85015190", "85015200", "85015310", "85015320",
    "85015390", "85044010", "85044090", "85111000", "85112000", "85113000",
    "85114000", "85115000", "85118000", "85119000", "85122000", "85123000",
    "85124000", "85129000", "85311000", "85312000", "85318000", "85319010",
    "85319090", "87071000", "87079010", "87079090", "87081000", "87082100",
    "87082900", "87083011", "87083019", "87083090", "87084010", "87084090",
    "87085010", "87085090", "87086000", "87087010", "87087090", "87088000",
    "87089100", "87089200", "87089300", "87089400", "87089500", "87089911",
    "87089919", "87089990",
    # === VEÍCULOS (Lei 10.485/02) ===
    "87011000", "87012000", "87013000", "87019000", "87021000", "87029010",
    "87029090", "87031000", "87032100", "87032200", "87032300", "87032400",
    "87032900", "87033100", "87033200", "87033300", "87033900", "87034000",
    "87035000", "87036000", "87037000", "87038000", "87039000", "87041000",
    "87042100", "87042200", "87042300", "87043100", "87043200", "87049000",
    "87051000", "87052000", "87053000", "87054000", "87059010", "87059090",
    "87060010", "87060090",
    # === CIGARROS / TABACO ===
    "24011010", "24011020", "24011030", "24012010", "24012020", "24012030",
    "24013000", "24021000", "24022000", "24029000", "24031100", "24031900",
    "24039100", "24039900",
    # === BEBIDAS (Lei 13.097/15) ===
    "22011000", "22019000", "22021000", "22029000", "22030000", "22041000",
    "22042100", "22042900", "22043000", "22051000", "22052000", "22060000",
    "22071000", "22072010", "22072020", "22072090", "22082000", "22083000",
    "22084000", "22085000", "22086000", "22087000", "22089000",
    # === MÁQUINAS DE VIDEOPÔQUER / JOGOS (Lei 10.833/03 art. 58-T) ===
    "95043010", "95043090",
}


# ===========================================================================
# FUNÇÕES DE SEGURANÇA E VALIDAÇÃO
# ===========================================================================

def validar_ncm(ncm: str) -> bool:
    """Valida NCM: remove formatação, verifica 8 dígitos numéricos."""
    ncm_limpo = re.sub(r"[^\d]", "", str(ncm))
    return bool(re.fullmatch(r"\d{8}", ncm_limpo))


def sanitizar_ncm(ncm: str) -> str:
    """Remove formatação e normaliza NCM para 8 dígitos."""
    return re.sub(r"[^\d]", "", str(ncm)).zfill(8)[:8]


def _hash_sha256(conteudo: str) -> str:
    """Gera SHA-256 de uma string."""
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def _hash_sha256_bytes(conteudo: bytes) -> str:
    """Gera SHA-256 de bytes."""
    return hashlib.sha256(conteudo).hexdigest()


# ===========================================================================
# BANCO DE DADOS SQLITE — CACHE SEGURO
# ===========================================================================

def _inicializar_db(db_path: Path = CACHE_DB) -> sqlite3.Connection:
    """Cria/abre o banco de cache com as tabelas necessárias."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ncm_oficial (
            ncm         TEXT PRIMARY KEY,
            descricao   TEXT NOT NULL DEFAULT '',
            ipi_aliquota REAL DEFAULT 0.0,
            unidade     TEXT DEFAULT '',
            posicao     TEXT DEFAULT '',
            data_inicio TEXT DEFAULT '',
            data_fim    TEXT DEFAULT '',
            hash_linha  TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ncm_monofasico (
            ncm         TEXT PRIMARY KEY,
            lei_base    TEXT DEFAULT '',
            segmento    TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS metadados (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ncm_oficial_desc ON ncm_oficial(descricao);
        CREATE INDEX IF NOT EXISTS idx_ncm_mono ON ncm_monofasico(ncm);
    """)
    conn.commit()
    return conn


def _obter_metadado(conn: sqlite3.Connection, chave: str) -> Optional[str]:
    row = conn.execute("SELECT valor FROM metadados WHERE chave=?", (chave,)).fetchone()
    return row[0] if row else None


def _salvar_metadado(conn: sqlite3.Connection, chave: str, valor: str):
    conn.execute("INSERT OR REPLACE INTO metadados (chave, valor) VALUES (?, ?)", (chave, valor))
    conn.commit()


# ===========================================================================
# DOWNLOAD DA TABELA NCM OFICIAL (SISCOMEX CLASSIF)
# ===========================================================================

def baixar_tabela_ncm_classif(timeout: int = 30) -> Tuple[Optional[list], Optional[str]]:
    """
    Baixa a tabela NCM completa da API pública do Siscomex Classif.
    Retorna (lista_de_ncms, erro_ou_None).

    SEGURANÇA:
    - verify=True (SEMPRE)
    - timeout configurável (padrão 30s)
    - Headers padrão sem credenciais
    """
    try:
        import requests
    except ImportError:
        return None, "requests não instalado"

    headers = {
        "User-Agent": "ResolvRapido-Brasil/18.1 (Auditoria Fiscal)",
        "Accept": "application/json",
    }

    try:
        logger.info(f"Baixando tabela NCM de {URL_CLASSIF_NCM} (timeout={timeout}s)...")
        resp = requests.get(
            URL_CLASSIF_NCM,
            headers=headers,
            timeout=timeout,
            verify=True,  # NUNCA desativar
        )
        resp.raise_for_status()

        dados = resp.json()

        # A API retorna formatos variados — normalizar
        if isinstance(dados, dict):
            # Pode ter chave "Nomenclaturas" ou similar
            for key in ("Nomenclaturas", "nomenclaturas", "data", "result", "items"):
                if key in dados and isinstance(dados[key], list):
                    dados = dados[key]
                    break
            if isinstance(dados, dict):
                dados = [dados]

        if not isinstance(dados, list):
            return None, f"Formato inesperado: {type(dados).__name__}"

        logger.info(f"Download concluído: {len(dados)} registros recebidos.")
        return dados, None

    except Exception as e:
        logger.error(f"Erro ao baixar NCM do Classif: {e}")
        return None, str(e)


def baixar_ncm_monofasicos_gov(timeout: int = 20) -> Tuple[Optional[list], Optional[str]]:
    """
    Tenta baixar lista de NCMs monofásicos do gov.br.
    Se falhar, retorna None (usará lista interna).
    """
    try:
        import requests
    except ImportError:
        return None, "requests não instalado"

    try:
        resp = requests.get(
            URL_NCM_MONOFASICO_GOV,
            timeout=timeout,
            verify=True,
            headers={"User-Agent": "ResolvRapido-Brasil/18.1"},
        )
        resp.raise_for_status()
        dados = resp.json()
        if isinstance(dados, list):
            return dados, None
        return None, "Formato inesperado"
    except Exception as e:
        logger.warning(f"Monofásicos gov.br indisponível: {e}. Usando lista interna.")
        return None, str(e)


# ===========================================================================
# PROCESSAMENTO E CACHE
# ===========================================================================

def _normalizar_item_classif(item: dict) -> Optional[dict]:
    """Normaliza um registro da API Classif para inserção no cache."""
    # Campos possíveis: codigo, Codigo, ncm, Ncm, descricao, Descricao, etc.
    ncm = None
    for key in ("codigo", "Codigo", "ncm", "Ncm", "NCM", "code"):
        if key in item:
            ncm = sanitizar_ncm(str(item[key]))
            break

    if not ncm or len(ncm) != 8 or not ncm.isdigit():
        return None

    descricao = ""
    for key in ("descricao", "Descricao", "description", "Description", "desc"):
        if key in item:
            descricao = str(item[key]).strip()[:500]
            break

    ipi = 0.0
    for key in ("ipi_aliquota", "aliquota_ipi", "ipi", "IPI", "Ipi_Aliquota"):
        if key in item:
            try:
                ipi = float(item[key])
            except (ValueError, TypeError):
                ipi = 0.0
            break

    unidade = ""
    for key in ("unidade", "Unidade", "unit"):
        if key in item:
            unidade = str(item[key]).strip()[:20]
            break

    hash_linha = _hash_sha256(f"{ncm}|{descricao}|{ipi}")

    return {
        "ncm": ncm,
        "descricao": descricao,
        "ipi_aliquota": ipi,
        "unidade": unidade,
        "hash_linha": hash_linha,
    }


def atualizar_cache_ncm(force: bool = False, timeout: int = 30) -> Dict[str, Any]:
    """
    Atualiza o cache SQLite com dados oficiais do Siscomex.

    Retorna dict com status da operação:
    {
        "sucesso": bool,
        "fonte": "CLASSIF_API" | "FALLBACK",
        "total_ncm": int,
        "total_monofasico": int,
        "mensagem": str,
        "data_atualizacao": str,
        "hash_arquivo": str,
    }
    """
    resultado = {
        "sucesso": False,
        "fonte": "FALLBACK",
        "total_ncm": 0,
        "total_monofasico": 0,
        "mensagem": "",
        "data_atualizacao": "",
        "hash_arquivo": "",
    }

    conn = _inicializar_db()

    # Verificar se precisa atualizar
    if not force:
        ultima = _obter_metadado(conn, "ultima_atualizacao")
        if ultima:
            try:
                dt_ultima = datetime.fromisoformat(ultima)
                dias = (datetime.now() - dt_ultima).days
                if dias < 7:
                    total = int(_obter_metadado(conn, "total_ncm") or "0")
                    resultado["sucesso"] = True
                    resultado["fonte"] = _obter_metadado(conn, "fonte_dados") or "CACHE"
                    resultado["total_ncm"] = total
                    resultado["total_monofasico"] = int(
                        _obter_metadado(conn, "total_monofasico") or "0"
                    )
                    resultado["mensagem"] = (
                        f"Cache atualizado há {dias} dia(s). "
                        f"Próxima atualização em {7 - dias} dia(s). "
                        f"{total:,} NCMs disponíveis."
                    )
                    resultado["data_atualizacao"] = ultima
                    resultado["hash_arquivo"] = _obter_metadado(conn, "hash_arquivo") or ""
                    conn.close()
                    return resultado
            except ValueError:
                pass

    # Tentar baixar da API oficial
    dados_classif, erro_classif = baixar_tabela_ncm_classif(timeout=timeout)

    if dados_classif and len(dados_classif) > 100:
        # Sucesso — processar e armazenar
        logger.info(f"Processando {len(dados_classif)} registros do Classif...")

        # Hash do conteúdo completo
        conteudo_json = json.dumps(dados_classif, sort_keys=True, default=str)
        hash_arquivo = _hash_sha256(conteudo_json)

        # Verificar se mudou
        hash_anterior = _obter_metadado(conn, "hash_arquivo")
        if hash_anterior == hash_arquivo and not force:
            resultado["sucesso"] = True
            resultado["fonte"] = "CLASSIF_API"
            resultado["total_ncm"] = int(_obter_metadado(conn, "total_ncm") or "0")
            resultado["total_monofasico"] = int(
                _obter_metadado(conn, "total_monofasico") or "0"
            )
            resultado["mensagem"] = "Dados inalterados desde última atualização."
            resultado["data_atualizacao"] = datetime.now().isoformat()
            resultado["hash_arquivo"] = hash_arquivo
            _salvar_metadado(conn, "ultima_atualizacao", datetime.now().isoformat())
            conn.close()
            return resultado

        # Limpar e reinserir
        conn.execute("DELETE FROM ncm_oficial")
        count = 0
        for item in dados_classif:
            norm = _normalizar_item_classif(item)
            if norm:
                conn.execute(
                    """INSERT OR REPLACE INTO ncm_oficial
                       (ncm, descricao, ipi_aliquota, unidade, hash_linha)
                       VALUES (?, ?, ?, ?, ?)""",
                    (norm["ncm"], norm["descricao"], norm["ipi_aliquota"],
                     norm["unidade"], norm["hash_linha"]),
                )
                count += 1

        # Atualizar monofásicos
        conn.execute("DELETE FROM ncm_monofasico")
        mono_count = 0

        # Tentar lista oficial
        dados_mono, erro_mono = baixar_ncm_monofasicos_gov(timeout=15)
        if dados_mono:
            for item in dados_mono:
                ncm = sanitizar_ncm(str(item.get("ncm", item.get("codigo", ""))))
                if validar_ncm(ncm):
                    lei = str(item.get("lei", item.get("legislacao", ""))).strip()[:100]
                    seg = str(item.get("segmento", item.get("categoria", ""))).strip()[:50]
                    conn.execute(
                        "INSERT OR REPLACE INTO ncm_monofasico (ncm, lei_base, segmento) VALUES (?,?,?)",
                        (ncm, lei, seg),
                    )
                    mono_count += 1

        # Garantir lista interna como complemento
        for ncm_mono in _MONOFASICOS_INTERNOS:
            conn.execute(
                "INSERT OR IGNORE INTO ncm_monofasico (ncm, lei_base, segmento) VALUES (?,?,?)",
                (ncm_mono, "Lista interna v18", _classificar_segmento(ncm_mono)),
            )
            # Contar apenas os novos
        mono_count = conn.execute("SELECT COUNT(*) FROM ncm_monofasico").fetchone()[0]

        # Salvar metadados
        agora = datetime.now().isoformat()
        _salvar_metadado(conn, "ultima_atualizacao", agora)
        _salvar_metadado(conn, "hash_arquivo", hash_arquivo)
        _salvar_metadado(conn, "total_ncm", str(count))
        _salvar_metadado(conn, "total_monofasico", str(mono_count))
        _salvar_metadado(conn, "fonte_dados", "CLASSIF_API")
        _salvar_metadado(conn, "versao_integrador", "18.1.0")
        conn.commit()

        resultado["sucesso"] = True
        resultado["fonte"] = "CLASSIF_API"
        resultado["total_ncm"] = count
        resultado["total_monofasico"] = mono_count
        resultado["mensagem"] = (
            f"✅ Cache atualizado com sucesso via API Siscomex Classif. "
            f"{count:,} NCMs + {mono_count} monofásicos."
        )
        resultado["data_atualizacao"] = agora
        resultado["hash_arquivo"] = hash_arquivo

        logger.info(resultado["mensagem"])
        conn.close()
        return resultado

    else:
        # API indisponível — usar fallback
        logger.warning(f"API Classif indisponível: {erro_classif}. Carregando fallback...")
        return _carregar_fallback_para_cache(conn, resultado, erro_classif)


def _carregar_fallback_para_cache(
    conn: sqlite3.Connection, resultado: dict, erro_api: str = ""
) -> Dict[str, Any]:
    """Carrega a base local (ncm_database.json) como fallback no cache."""

    fallback_path = None
    for p in [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), FALLBACK_JSON),
        FALLBACK_JSON,
        os.path.join("data_brasil", FALLBACK_JSON),
    ]:
        if os.path.exists(p):
            fallback_path = p
            break

    if not fallback_path:
        resultado["mensagem"] = (
            f"❌ API indisponível ({erro_api}) E base local não encontrada. "
            "Nenhum dado NCM disponível."
        )
        conn.close()
        return resultado

    with open(fallback_path, "r", encoding="utf-8") as f:
        base = json.load(f)

    ncms = base.get("ncms", {})
    count = 0

    # Verificar se já tem dados suficientes no cache
    cached = conn.execute("SELECT COUNT(*) FROM ncm_oficial").fetchone()[0]
    if cached > len(ncms):
        # Cache anterior da API é maior — manter
        resultado["sucesso"] = True
        resultado["fonte"] = "CACHE_ANTERIOR"
        resultado["total_ncm"] = cached
        resultado["total_monofasico"] = conn.execute(
            "SELECT COUNT(*) FROM ncm_monofasico"
        ).fetchone()[0]
        resultado["mensagem"] = (
            f"⚠️ API indisponível ({erro_api}). "
            f"Usando cache anterior ({cached:,} NCMs). "
            "Será reatualizado na próxima tentativa."
        )
        resultado["data_atualizacao"] = _obter_metadado(conn, "ultima_atualizacao") or ""
        conn.close()
        return resultado

    # Carregar fallback
    conn.execute("DELETE FROM ncm_oficial")
    for ncm_code, info in ncms.items():
        ncm_clean = sanitizar_ncm(ncm_code)
        if not validar_ncm(ncm_clean):
            continue
        conn.execute(
            """INSERT OR REPLACE INTO ncm_oficial
               (ncm, descricao, ipi_aliquota, hash_linha)
               VALUES (?, ?, ?, ?)""",
            (
                ncm_clean,
                str(info.get("descricao", ""))[:500],
                float(info.get("ipi", 0)),
                _hash_sha256(f"{ncm_clean}|{info.get('descricao','')}"),
            ),
        )
        if info.get("monofasico", False):
            conn.execute(
                "INSERT OR IGNORE INTO ncm_monofasico (ncm, lei_base, segmento) VALUES (?,?,?)",
                (ncm_clean, "Fallback local", _classificar_segmento(ncm_clean)),
            )
        count += 1

    # Garantir monofásicos internos
    for ncm_mono in _MONOFASICOS_INTERNOS:
        conn.execute(
            "INSERT OR IGNORE INTO ncm_monofasico (ncm, lei_base, segmento) VALUES (?,?,?)",
            (ncm_mono, "Lista interna v18", _classificar_segmento(ncm_mono)),
        )

    mono_count = conn.execute("SELECT COUNT(*) FROM ncm_monofasico").fetchone()[0]

    agora = datetime.now().isoformat()
    _salvar_metadado(conn, "ultima_atualizacao", agora)
    _salvar_metadado(conn, "total_ncm", str(count))
    _salvar_metadado(conn, "total_monofasico", str(mono_count))
    _salvar_metadado(conn, "fonte_dados", "FALLBACK_LOCAL")
    _salvar_metadado(conn, "hash_arquivo", _hash_sha256(json.dumps(ncms, sort_keys=True)))
    conn.commit()

    resultado["sucesso"] = True
    resultado["fonte"] = "FALLBACK_LOCAL"
    resultado["total_ncm"] = count
    resultado["total_monofasico"] = mono_count
    resultado["mensagem"] = (
        f"⚠️ API indisponível ({erro_api}). "
        f"Usando base local: {count} NCMs + {mono_count} monofásicos. "
        "Relatórios marcarão 'FONTE: FALLBACK' como aviso."
    )
    resultado["data_atualizacao"] = agora

    logger.warning(resultado["mensagem"])
    conn.close()
    return resultado


def _classificar_segmento(ncm: str) -> str:
    """Classifica segmento do NCM monofásico pela posição."""
    cap = ncm[:2]
    segs = {
        "22": "BEBIDAS", "24": "TABACO", "27": "COMBUSTÍVEIS",
        "30": "MEDICAMENTOS", "33": "COSMÉTICOS", "34": "SABÕES/DETERGENTES",
        "40": "BORRACHA/PNEUS", "56": "ABSORVENTES", "68": "FREIOS/FIBROCIMENTO",
        "70": "VIDRO/ESPELHOS", "73": "FERRAGENS", "84": "MOTORES/PEÇAS",
        "85": "ELÉTRICOS/PEÇAS", "87": "VEÍCULOS/AUTOPEÇAS", "95": "JOGOS",
        "96": "ESCOVAS",
    }
    return segs.get(cap, "OUTROS")


# ===========================================================================
# FUNÇÕES DE CONSULTA SEGURA
# ===========================================================================

def consultar_ncm(ncm: str, db_path: Path = CACHE_DB) -> Dict[str, Any]:
    """
    Consulta segura de NCM no cache.

    Segurança:
    - Sanitiza entrada (remove formatação)
    - Valida formato (8 dígitos)
    - Usa parameterized queries (sem SQL injection)

    Retorna:
    {
        "ncm": str,
        "encontrado": bool,
        "descricao": str,
        "ipi_aliquota": float,
        "monofasico": bool,
        "segmento_monofasico": str,
        "lei_monofasico": str,
        "fonte": str,
        "erro": str | None,
    }
    """
    ncm_limpo = sanitizar_ncm(ncm)

    if not validar_ncm(ncm_limpo):
        return {
            "ncm": ncm_limpo,
            "encontrado": False,
            "descricao": "NCM INVÁLIDO",
            "ipi_aliquota": 0.0,
            "monofasico": False,
            "segmento_monofasico": "",
            "lei_monofasico": "",
            "fonte": "",
            "erro": f"NCM '{ncm}' inválido (deve ter 8 dígitos numéricos)",
        }

    if not db_path.exists():
        # Cache não existe — tentar atualizar
        atualizar_cache_ncm(force=True)

    if not db_path.exists():
        # Mesmo após tentativa, não existe
        return {
            "ncm": ncm_limpo,
            "encontrado": False,
            "descricao": "CACHE INDISPONÍVEL",
            "ipi_aliquota": 0.0,
            "monofasico": ncm_limpo in _MONOFASICOS_INTERNOS,
            "segmento_monofasico": _classificar_segmento(ncm_limpo) if ncm_limpo in _MONOFASICOS_INTERNOS else "",
            "lei_monofasico": "Lista interna" if ncm_limpo in _MONOFASICOS_INTERNOS else "",
            "fonte": "LISTA_INTERNA",
            "erro": None,
        }

    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        # Busca exata
        row = conn.execute(
            "SELECT descricao, ipi_aliquota FROM ncm_oficial WHERE ncm = ?",
            (ncm_limpo,),
        ).fetchone()

        # Se não achou, busca parcial (6 dígitos)
        if not row:
            row = conn.execute(
                "SELECT descricao, ipi_aliquota FROM ncm_oficial WHERE ncm LIKE ?",
                (ncm_limpo[:6] + "%",),
            ).fetchone()

        # Verificar monofásico
        mono_row = conn.execute(
            "SELECT lei_base, segmento FROM ncm_monofasico WHERE ncm = ?",
            (ncm_limpo,),
        ).fetchone()

        # Fallback para lista interna de monofásicos
        is_mono_interno = ncm_limpo in _MONOFASICOS_INTERNOS

        fonte = _obter_metadado(conn, "fonte_dados") or "DESCONHECIDO"

        if row:
            return {
                "ncm": ncm_limpo,
                "encontrado": True,
                "descricao": row[0],
                "ipi_aliquota": row[1] or 0.0,
                "monofasico": bool(mono_row) or is_mono_interno,
                "segmento_monofasico": (
                    mono_row[1] if mono_row else
                    (_classificar_segmento(ncm_limpo) if is_mono_interno else "")
                ),
                "lei_monofasico": (
                    mono_row[0] if mono_row else
                    ("Lista interna v18" if is_mono_interno else "")
                ),
                "fonte": fonte,
                "erro": None,
            }
        else:
            return {
                "ncm": ncm_limpo,
                "encontrado": False,
                "descricao": "NCM NÃO ENCONTRADO",
                "ipi_aliquota": 0.0,
                "monofasico": is_mono_interno,
                "segmento_monofasico": _classificar_segmento(ncm_limpo) if is_mono_interno else "",
                "lei_monofasico": "Lista interna v18" if is_mono_interno else "",
                "fonte": fonte,
                "erro": None,
            }
    finally:
        conn.close()


def consultar_ncm_lote(ncms: List[str], db_path: Path = CACHE_DB) -> Dict[str, Dict]:
    """Consulta em lote — otimizado com uma única conexão."""
    if not db_path.exists():
        atualizar_cache_ncm(force=True)

    resultados = {}
    conn = sqlite3.connect(str(db_path), timeout=10)

    try:
        for ncm in ncms:
            ncm_limpo = sanitizar_ncm(ncm)
            if not validar_ncm(ncm_limpo):
                resultados[ncm_limpo] = {
                    "ncm": ncm_limpo, "encontrado": False,
                    "descricao": "INVÁLIDO", "ipi_aliquota": 0.0,
                    "monofasico": False, "erro": "Formato inválido",
                }
                continue

            row = conn.execute(
                "SELECT descricao, ipi_aliquota FROM ncm_oficial WHERE ncm = ?",
                (ncm_limpo,),
            ).fetchone()

            mono = conn.execute(
                "SELECT lei_base, segmento FROM ncm_monofasico WHERE ncm = ?",
                (ncm_limpo,),
            ).fetchone()

            is_mono = bool(mono) or ncm_limpo in _MONOFASICOS_INTERNOS

            resultados[ncm_limpo] = {
                "ncm": ncm_limpo,
                "encontrado": bool(row),
                "descricao": row[0] if row else "NÃO ENCONTRADO",
                "ipi_aliquota": (row[1] or 0.0) if row else 0.0,
                "monofasico": is_mono,
                "segmento_monofasico": (
                    mono[1] if mono else
                    (_classificar_segmento(ncm_limpo) if is_mono else "")
                ),
                "erro": None,
            }
    finally:
        conn.close()

    return resultados


def obter_estatisticas_cache(db_path: Path = CACHE_DB) -> Dict[str, Any]:
    """Retorna estatísticas do cache para exibição na interface."""
    if not db_path.exists():
        return {
            "status": "NÃO INICIALIZADO",
            "total_ncm": 0,
            "total_monofasico": 0,
            "fonte": "NENHUMA",
            "ultima_atualizacao": "Nunca",
            "idade_dias": -1,
            "precisa_atualizar": True,
        }

    conn = sqlite3.connect(str(db_path), timeout=5)
    try:
        total_ncm = conn.execute("SELECT COUNT(*) FROM ncm_oficial").fetchone()[0]
        total_mono = conn.execute("SELECT COUNT(*) FROM ncm_monofasico").fetchone()[0]
        fonte = _obter_metadado(conn, "fonte_dados") or "DESCONHECIDO"
        ultima = _obter_metadado(conn, "ultima_atualizacao") or ""
        hash_arq = _obter_metadado(conn, "hash_arquivo") or ""

        idade_dias = -1
        if ultima:
            try:
                idade_dias = (datetime.now() - datetime.fromisoformat(ultima)).days
            except ValueError:
                pass

        return {
            "status": "OK" if total_ncm > 0 else "VAZIO",
            "total_ncm": total_ncm,
            "total_monofasico": total_mono,
            "fonte": fonte,
            "ultima_atualizacao": ultima,
            "hash_arquivo": hash_arq,
            "idade_dias": idade_dias,
            "precisa_atualizar": idade_dias < 0 or idade_dias >= 7,
        }
    finally:
        conn.close()


# ===========================================================================
# INTEGRAÇÃO COM O MOTOR DE VALIDAÇÃO v18
# ===========================================================================

def enriquecer_base_ncm_com_cache(
    base_json: Dict[str, Any], db_path: Path = CACHE_DB
) -> Dict[str, Any]:
    """
    Enriquece a base JSON local com dados do cache oficial.
    NCMs existentes na base são atualizados com descrição/IPI oficiais.
    NCMs do cache não presentes na base são adicionados.
    """
    if not db_path.exists():
        return base_json

    conn = sqlite3.connect(str(db_path), timeout=5)
    ncms_base = base_json.get("ncms", {})
    adicionados = 0
    atualizados = 0

    try:
        rows = conn.execute("SELECT ncm, descricao, ipi_aliquota FROM ncm_oficial").fetchall()
        for ncm, desc, ipi in rows:
            if ncm in ncms_base:
                # Atualizar descrição oficial e IPI se a fonte é Classif
                if desc and len(desc) > 5:
                    ncms_base[ncm]["descricao_oficial"] = desc
                if ipi is not None and ipi > 0:
                    ncms_base[ncm]["ipi_oficial"] = ipi
                atualizados += 1
            else:
                # Adicionar novo NCM com valores padrão
                is_mono = (
                    conn.execute(
                        "SELECT 1 FROM ncm_monofasico WHERE ncm = ?", (ncm,)
                    ).fetchone() is not None
                    or ncm in _MONOFASICOS_INTERNOS
                )
                ncms_base[ncm] = {
                    "descricao": desc or f"NCM {ncm}",
                    "ipi": ipi or 0.0,
                    "icms_padrao": 18.0,
                    "pis_nc": 1.65,
                    "cofins_nc": 7.60,
                    "pis_cum": 0.65,
                    "cofins_cum": 3.0,
                    "monofasico": is_mono,
                    "obs": "Importado do Siscomex Classif",
                    "fonte": "CLASSIF_API",
                }
                adicionados += 1

        # Atualizar metadados
        if "_meta" not in base_json:
            base_json["_meta"] = {}
        base_json["_meta"]["ncms_oficiais_adicionados"] = adicionados
        base_json["_meta"]["ncms_atualizados"] = atualizados
        base_json["_meta"]["total_ncms"] = len(ncms_base)
        base_json["_meta"]["cache_integrado"] = True

    finally:
        conn.close()

    base_json["ncms"] = ncms_base
    return base_json


def verificar_monofasico_seguro(ncm: str) -> Tuple[bool, str, str]:
    """
    Verificação segura se NCM é monofásico — consulta cache + lista interna.
    Retorna: (is_monofasico, legislacao, segmento)
    """
    ncm_limpo = sanitizar_ncm(ncm)

    # Lista interna (sempre disponível)
    if ncm_limpo in _MONOFASICOS_INTERNOS:
        seg = _classificar_segmento(ncm_limpo)
        return True, "Lista interna v18", seg

    # Cache SQLite
    if CACHE_DB.exists():
        try:
            conn = sqlite3.connect(str(CACHE_DB), timeout=3)
            row = conn.execute(
                "SELECT lei_base, segmento FROM ncm_monofasico WHERE ncm = ?",
                (ncm_limpo,),
            ).fetchone()
            conn.close()
            if row:
                return True, row[0], row[1]
        except Exception:
            pass

    return False, "", ""


# ===========================================================================
# TESTE STANDALONE
# ===========================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("TESTE DO INTEGRADOR RFB — ResolvRapido Brasil v18.1")
    print("=" * 70)

    # 1. Atualizar cache
    print("\n[1] Atualizando cache NCM...")
    res = atualizar_cache_ncm(force=True, timeout=15)
    print(f"    Fonte: {res['fonte']}")
    print(f"    Total NCMs: {res['total_ncm']}")
    print(f"    Total Monofásicos: {res['total_monofasico']}")
    print(f"    Mensagem: {res['mensagem']}")

    # 2. Consultar NCMs
    print("\n[2] Consultando NCMs...")
    testes = ["84713019", "30049099", "87083090", "24021000", "99999999", "22021000"]
    for ncm in testes:
        r = consultar_ncm(ncm)
        status = "✅" if r["encontrado"] else "❌"
        mono = "🔴 MONOFÁSICO" if r["monofasico"] else ""
        print(f"    {status} {ncm}: {r['descricao'][:40]} | IPI={r['ipi_aliquota']}% {mono}")

    # 3. Estatísticas
    print("\n[3] Estatísticas do cache:")
    stats = obter_estatisticas_cache()
    for k, v in stats.items():
        print(f"    {k}: {v}")

    # 4. Verificação de monofásicos
    print("\n[4] Verificação de monofásicos:")
    monos = ["27101921", "30049099", "87083090", "84713019", "22021000"]
    for ncm in monos:
        is_m, lei, seg = verificar_monofasico_seguro(ncm)
        print(f"    {ncm}: {'🔴 SIM' if is_m else '✅ NÃO'} | {seg} | {lei}")

    print("\n" + "=" * 70)
    print("✅ TESTE CONCLUÍDO")
