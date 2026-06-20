# Comparacao Multi-Modelo 

O mesmo cenario foi processado por dois modelos de linguagem independentes (Claude e Gemini) para checar a robustez da leitura. **Concordancia entre os modelos: 70.0%** do ranking setorial (top/bottom 5).

**Concordancia parcial.** Ha convergencia no nucleo da tese, mas parte do ranking diverge entre os modelos. Vale revisar manualmente os setores que NAO aparecem no overlap antes de agir sobre eles.

## Onde os modelos concordam

**Setores beneficiados (ambos):** Imobiliario_Construcao, Mineracao_Siderurgia, Saude
**Setores prejudicados (ambos):** Agro_Alimentos, Consumo_Defensivo, Petroleo_Gas, Utilities_Energia
**Tickers positivos (ambos):** CYRE3.SA, VALE3.SA
**Tickers negativos (ambos):** PETR4.SA

## Divergencia na leitura do cenario

Diferenca absoluta entre os vetores de choque extraidos por cada modelo: Selic 0.0pp · Cambio 2% · Commodity 2% · Mercado 3%. Diferencas grandes aqui (>0.5pp em Selic, >5% nos demais) indicam que o cenario original tinha espaco para interpretacao -- vale reescreve-lo de forma mais quantitativa.

## Leitura individual de cada modelo

**Claude (Anthropic):** setores beneficiados — Imobiliario_Construcao, Varejo_Discricionario, Mineracao_Siderurgia, Bancos, Saude
**Gemini:** setores beneficiados — Imobiliario_Construcao, Saude, Mineracao_Siderurgia, Papel_Celulose, Transporte_Logistica
