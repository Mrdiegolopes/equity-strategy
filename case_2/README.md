# Case 2 — Macro Scenario Engine

Recebe um cenario macroeconomico em linguagem natural e devolve uma recomendacao
setorial estruturada para a Bovespa (top 5 beneficiados/prejudicados, 3+3 tickers,
riscos da tese), em JSON e relatorio markdown (<=500 palavras).

**Principio central: o LLM nao decide o ranking, os dados decidem.** Uma regressao
multifator sobre dados historicos calcula o impacto setorial; o LLM so traduz o
cenario em numeros (entrada) e narra o resultado ja calculado (saida). Isso elimina
a alucinacao de ranking que uma abordagem "pergunte ao LLM" teria.

## Arquitetura

```
Cenario em texto
   → [1] LLM parser        ChoqueMacro (vetor: d_selic, d_cambio, ret_commodity, ret_mercado)
   → [2] Motor de fatores  ranking = betas_historicos · choque  (regressao OLS+HAC, offline)
   → [3] Validacao         tickers/setores existem? choque plausivel?
   → [4] LLM narrador      mecanismo + tickers + riscos (sobre o ranking ja pronto)
   → [5] Render            JSON + markdown (limite de 500 palavras garantido em codigo)
```

| Arquivo | Papel |
|---|---|
| `config.py` | Setor tickers, fatores, janela de estimacao |
| `src/data_collection.py` | yfinance (acoes/Ibov/commodities) + BCB/SGS (Selic/cambio/IPCA) |
| `src/factor_model.py` | Regressao OLS+HAC+winsorizacao; betas, R2, RMSE, Durbin-Watson; suporta corte de data (out-of-sample) |
| `src/schemas.py` | Contratos Pydantic |
| `src/llm_client.py` | Anthropic (tool-use) + Gemini (response_schema) |
| `src/validation.py` | Anti-alucinacao deterministica |
| `src/report.py` | JSON + markdown com truncamento garantido a 500 palavras |
| `src/run.py` | Fluxo de execução + modo `--comparar-modelos` |
| `src/extensions.py` | Sensibilidade, backtest (full e out-of-sample), comparacao multi-modelo |
| `src/app.py` | Streamlit: analise, sensibilidade, backtest com grafico |

## Provedores de LLM

Anthropic e Gemini. `--comparar-modelos` usa os dois.

A integracao com Gemini exigiu 4 correcoes reais, registradas porque sao evidencia
de depuracao contra API em producao:
- SDK `google-generativeai` deprecado → migrado para `google-genai`
- `response_schema` nao resolve `$ref`/`$defs` de Pydantic aninhado → schema achatado manualmente
- API rejeita `additionalProperties` (gerado por `extra="forbid"`): removido do envio; validacao Pydantic pos-resposta mantem a protecao
- Thinking tokens consomem o orcamento de `max_output_tokens`, truncando respostas: `thinking_budget=0`

## Dados

- **yfinance**: unica fonte gratuita com historico longo o bastante (10+ anos) para a
  regressao. brapi.dev descartada para o motor (3 meses de historico no plano gratuito).
- **BCB/SGS**: Selic (432), cambio PTAX (1), IPCA (433) — oficial, gratuito.
- **Commodity externa** (Brent + minerio via yfinance): mantida fora das acoes BR para
  evitar circularidade (regredir Vale contra um fator derivado de Vale).

**Achado na pratica:** a primeira coleta revelou 7 tickers obsoletos por eventos
corporativos de 2024-25 (Eletrobras→AXIA3, Copel unificando CPLE6, JBS deslistada,
Marfrig+BRF→MBRF3). `data_collection.py` distingue "ticker extinto" (exige correcao
manual) de falha de rede passageira (retry automatico), cestas fixas de tickers
degradam com o tempo e precisam de revisao periodica.

## Robustez estatistica

- **Winsorizacao (1%/99%)** do retorno do setor antes da regressao — protege setores
  com poucos tickers de outlier idiossincratico. Validado: outlier sintetico de +90%
  distorceu o beta recuperado em apenas 0.001 vs. o valor verdadeiro.
- **HAC (Newey-West)** no lugar de HC1 — corrige heterocedasticidade *e* autocorrelacao
  serial, relevante em series mensais. Sem isso, p-valores ficam artificialmente baixos.
- Reportado: R2, R2 ajustado, RMSE, Durbin-Watson. Confidence score penaliza
  Durbin-Watson fora de 1.5–2.5.

## Prompts (`prompts/`)

- **`parser_cenario.txt`**: extrai os 4 fatores; fator nao mencionado e estimado mas
  registrado em `premissas` (nunca apresentado como explicito); `confianca_extracao`
  cai para `media`/`baixa` conforme a ambiguidade do cenario.
- **`gerar_rationale.txt`**: narra o ranking ja calculado; proibido reordenar setores
  ou inventar tickers/numeros. Orcamento de palavras explicito por elemento (25-30
  palavras) — "1-2 frases" sem numero gerava paragrafos de 80-100 palavras na pratica.

Grounding e estrutural: o LLM nao alucina o ranking porque nunca o produz. Como
prompt nao e garantia, `report.py` aplica um limite duro de 500 palavras via
truncamento proporcional determinístico, preservando todas as secoes (inclusive
Riscos) em vez de cortar o fim do documento.

## Como rodar

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # e/ou GEMINI_API_KEY=...

python src/data_collection.py         # gera data/painel.csv
python src/factor_model.py            # gera data/betas.json

python src/run.py "Selic sobe 2pp, real deprecia 10%, commodities caem 15%, bolsa cai 5%"
python src/run.py                      # sem argumento -> pede o cenario via input()
python src/run.py --comparar-modelos "Copom corta Selic em 0,25 ponto, a 14,5% ao ano"

streamlit run src/app.py               # analise + sensibilidade + backtest com grafico
```

Cenarios testados: 
- explicito com numeros:: "Selic a 12%, câmbio a 5.80, petróleo caindo para 70 dólares"
- vago/qualitativo:: "Ambiente macro piora com pressão inflacionária (testa`confianca_extracao`)
- baseado em manchete real do Valor Economico:: "Copom corta Selic em 0,25 ponto, a 14,5% ao ano, menor nível em 12 meses" (testa extracao de texto jornalistico).


**Exemplos de execucao completos (input + output integral) em `outputs/`:**
- `relatorio.md` + `resultado.json` — cenario "Selic sobe 2pp, real deprecia 10%,
  commodities caem 15%, bolsa recua 5%" (input dentro do proprio `resultado.json`,
  campo `cenario_input`). 479 palavras, dentro do limite de 500.
- `comparacao_modelos.md` + `comparacao_modelos.json` — extensao multi-modelo rodada
  com o cenario do corte de Selic do Copom; mostra Anthropic e Gemini processando o
  mesmo input e o resumo de concordancia/divergencia entre os dois.

## Extensoes implementadas

- **Canais de transmissao explicitos**: `contribuicoes` = coeficiente × choque, por
  fator e por setor. O canal e o numero, nao uma frase do LLM.
- **Confidence scoring**: de R2 + significancia + Durbin-Watson, nunca chutado.
- **Analise de sensibilidade**: varia um fator, mostra o ranking se mover.
- **Backtest, com out-of-sample genuino**: por padrao, re-estima os betas usando so
  dados anteriores a janela testada — o motor nunca "ve" o periodo avaliado.
  `comparar_full_sample_vs_oos` mostra os dois numeros lado a lado: em teste
  sintetico, Spearman caiu de 0.40 (full-sample, com vazamento) para 0.0
  (out-of-sample, ~37 obs disponiveis) — prova concreta de quanto a metrica
  ingenua estava inflada.
- **Comparacao multi-modelo**: `--comparar-modelos` roda Anthropic e Gemini no
  mesmo cenario; reporta concordancia de ranking, tickers, e divergencia no
  vetor de choque lido. Validado em execucao real.


## Log de tempo

| Bloco | Tempo |
|---|---|
| Arquitetura + fontes de dados | 1.5h |
| Coleta + modelo de fatores | 3h |
| LLM + schemas + prompts | 2.5h |
| Validacao + render + fluxo de execução| 2h |
| Extensoes (sensibilidade + backtest) | 1.5h |
| Streamlit | 2h |
| Depuracao real (tickers extintos, timeout BCB, truncamento, SDK Gemini) | 4h |
| Out-of-sample + comparacao multi-modelo | 2.5h |
| Documentacao | 1h |
| **Total** | **~20h** |

Passou de 12-18h (estimativa do enunciado). Causa principal: friccao de APIs
externas em mudanca (tickers descontinuados entre montagem da cesta e coleta; SDK
do Gemini trocando pacote/modelo/formato de schema durante o desenvolvimento) — nao
a logica de negocio em si.

## Tres limitacoes mais serias

1. **Proxy setorial imperfeita**: cesta de poucos tickers, nao indice oficial. Sensivel
   a idiossincrasia de empresa (mitigado parcialmente por winsorizacao) e degrada com
   eventos corporativos ao longo do tempo.
2. **Linearidade e horizonte**: regressao linear/estatica; nao captura nao-linearidade
   nem defasagem temporal. `horizonte_meses` e lido e declarado mas nao modula a projecao.
3. **Estabilidade de regime, parcialmente mitigada**: janela fixa (2018+) assume betas
   constantes. O modo out-of-sample *mede* o impacto disso (queda de Spearman) mas nao
   *resolve* via janela rolante.

## Com mais tempo (2 semanas)

- Janela rolante de estimacao (betas atualizados periodicamente, nao janela fixa).
- Fator commodity desagregado (minerio vs. petroleo vs. agricola).
- **Sinal de sentimento de noticias como fator adicional**, via
  [FinBERT-PT-BR](https://huggingface.co/lucas-leme/FinBERT-PT-BR) (modelo
  especializado em portugues financeiro, ja identificado) integraria experiencia
  previa de analise de sentimento em ativos BR.
- Modelagem de defasagem (impulse response) para `horizonte_meses` modular a projecao.
- Self-critique loop fechado (reenviar ao LLM os itens que falham validacao).
- Comparacao de cenarios lado a lado.
