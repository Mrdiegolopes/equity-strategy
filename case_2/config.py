"""
Configuração central do Macro Scenario Engine.
Mapeamento setor -> tickers representativos do Ibovespa, fatores macro,
e parâmetros da janela de estimação.
"""

# --- Janela de estimação da regressão de fatores ---
# 2018+ cobre um ciclo completo de aperto/afrouxamento monetário sem
# misturar o regime estruturalmente distinto dos anos 2000.
START_DATE = "2018-01-01"
END_DATE = None  # None = até a data de hoje

# --- Mapeamento Setor -> tickers representativos (proxies setoriais) ---
# Não existe índice setorial gratuito e limpo; usamos cestas de tickers
# líquidos como proxy de cada setor. Retorno do setor = média dos retornos
# dos seus tickers no mês.
SETORES = {
    "Bancos":                 ["ITUB4.SA", "BBDC4.SA", "BBAS3.SA", "SANB11.SA"],
    "Petroleo_Gas":           ["PETR4.SA", "PRIO3.SA", "RECV3.SA"],
    "Mineracao_Siderurgia":   ["VALE3.SA", "CSNA3.SA", "GGBR4.SA", "USIM5.SA"],
    "Varejo_Discricionario":  ["MGLU3.SA", "LREN3.SA", "AZZA3.SA"],
    "Consumo_Defensivo":      ["ABEV3.SA", "HYPE3.SA", "RADL3.SA"],
    "Utilities_Energia":      ["EGIE3.SA", "TAEE11.SA", "AXIA3.SA"],
    "Saneamento":             ["SBSP3.SA", "SAPR11.SA", "CSMG3.SA"],
    "Papel_Celulose":         ["SUZB3.SA", "KLBN11.SA"],
    "Saude":                  ["RDOR3.SA", "HAPV3.SA", "FLRY3.SA"],
    "Imobiliario_Construcao": ["CYRE3.SA", "MRVE3.SA", "EZTC3.SA"],
    "Transporte_Logistica":   ["RAIL3.SA", "RENT3.SA"],
    "Agro_Alimentos":         ["MBRF3.SA", "SLCE3.SA", "SMTO3.SA"],
}

# --- Séries macro do BCB/SGS (código SGS -> nome do fator) ---
# Selic meta (432, % a.a.), Câmbio USD/BRL venda PTAX (1, R$/US$),
# IPCA mensal (433, % no mês)
BCB_SERIES = {
    432: "selic_meta",
    1:   "cambio_usdbrl",
    433: "ipca_mensal",
}

# --- Fator commodity EXTERNO (independente das ações BR) ---
# Brent (BZ=F) + proxy de minério. Tratados via yfinance, separados das
# ações brasileiras para evitar circularidade na regressão.
COMMODITY_TICKERS = {
    "brent":   "BZ=F",      # Petróleo Brent
    "minerio": "TIO=F",     # Iron Ore 62% Fe (CME) — fallback p/ ^SPGSCI se indisponível
}
COMMODITY_FALLBACK = "GSG"  # iShares S&P GSCI Commodity ETF, caso futuros falhem

MARKET_INDEX = "^BVSP"  # Ibovespa, retorno de mercado (fator de risco sistêmico)

# Os 4 fatores finais da regressão multifator
FATORES = ["d_selic", "d_cambio", "ret_commodity", "ret_mercado"]
# d_ipca fica disponível mas é colinear com selic; mantido opcional.

MIN_OBS = 24  # mínimo de observações para confiar numa regressão setorial
