# Case 1 — Earnings Call Intelligence Tracker

Ferramenta em Python para ingerir transcrições de earnings call, extrair inteligência estruturada com LLM, auditar citações literais contra o texto-fonte e gerar relatório executivo em markdown.

Empresa analisada: **Banco Bradesco (BBDC4)**, integrante do Ibovespa.  
Call atual: **1T26**. Comparativo temporal: **4T25**.

---

## Como rodar

```bash
cd case_1
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Configure pelo menos uma chave de LLM:

```bash
# opção 1 — Anthropic
$env:ANTHROPIC_API_KEY="sk-ant-..."

# opção 2 — Gemini
$env:GEMINI_API_KEY="..."

# camada opcional FINBERT (analise de sentimento)

pip install -r requirements.txt
 $env ANTHROPIC_API_KEY=sk-ant-...   # e/ou GEMINI_API_KEY=...
 $env HF_API_TOKEN=hf_...            # opcional, FinBERT


python src/run.py                       # análise completa, execução principal
python src/run.py 
python src/run.py --comparar-modelos    # Anthropic vs gemini

streamlit run src/app.py # interface 
```


Arquivos gerados:

```text
outputs/resultado.json   # JSON estruturado completo
outputs/relatorio.md     # relatório 
```

---

## Arquitetura

```
Transcrição -> Ingestão (slides/Q&A) -> LLM (análise + comparação)
            -> Citation tracking -.> FinBERT (opcional) -> Render
```

| Arquivo | Papel |
|---|---|
| `config.py` | Empresa, calls, parâmetros |
| `src/ingestao.py` | Segmenta transcrição em slides e turnos de Q&A |
| `src/schemas.py` | Contratos Pydantic (`extra="forbid"`) |
| `src/llm_client.py` | Anthropic + Gemini (`response_schema`) |
| `src/validation.py` | Citation tracking |
| `src/finbert.py` | Validação cruzada de tom (FinBERT-PT-BR) |
| `src/report.py` | JSON + markdown, truncamento orçado por seção |
| `src/run.py` | Pipeline + modo `--comparar-modelos` |
| `src/extensions.py` | Comparação multi-modelo |
| `src/app.py` | Streamlit |

## Arvore do projeto

```text
case_1/
├── config.py
├── transcricoes/
│   ├── bradesco_1t26.txt
│   └── bradesco_4t25.txt
├── prompts/
│   ├── analisar_call.txt
│   └── comparar_trimestres.txt
├── src/
│   ├── ingestao.py
│   ├── schemas.py
│   ├── llm_client.py
│   ├── validation.py
│   ├── finbert.py
│   ├── report.py
│   ├── run.py
│   ├── extensions.py
│   └── app.py
├── scripts/
│   └── pdf_to_txt.py
└── outputs/
    ├── resultado.json
    ├── comparacao_modelos.json
    └── relatorio.md
```

## Definindo o fluxo do pipeline:

1. **Ingestão** (`ingestao.py`): lê a transcrição, limpa ruído do PDF, separa prepared remarks de Q&A e segmenta slides/rodadas de perguntas.
2. **Schemas** (`schemas.py`): define contratos Pydantic estritos para tom, red flags, perguntas críticas, surprise score e comparação temporal.
3. **LLM** (`llm_client.py`): chama Anthropic ou Gemini com saída estruturada. O modelo não deve escrever texto livre; ele preenche o schema.
4. **Citation tracking** (`validation.py`): toda citação literal retornada pelo LLM é verificada deterministicamente contra a transcrição.
5. **FinBERT opcional** (`finbert.py`): valida a direção do tom com o modelo `lucas-leme/FinBERT-PT-BR` via Hugging Face Inference API, se houver `HF_API_TOKEN`.
6. **Render** (`report.py`): gera JSON completo e relatório executivo em markdown, com limite duro de 400 palavras.
7. **Orquestração** (`run.py`): coordena as etapas sem concentrar lógica de negócio.

---

## LLM
Anthropic e Gemini. A camada (`llm_client.py`) reaproveita a infraestrutura
do Case 2, incluindo as 4 correções reais de API já depuradas lá 

## 3. Decisões de prompt engineering

Separei o problema em duas chamadas principais:

### Prompt 1 — `analisar_call.txt`

Objetivo: analisar apenas a call atual e extrair:

- tom geral do management;
- top 3 perguntas críticas dos analistas;
- qualidade da resposta do management;
- red flags linguísticos;
- surprise score.

**Regra central:** toda classificação exige citação
literal copiada exatamente do texto, sem paráfrase. Risco principal em
earnings call não é o LLM errar um número, é narrar sem grounding.

Trecho central do prompt:

```text
Use apenas a transcrição fornecida. Não use conhecimento externo.
Toda classificação relevante precisa estar ancorada em citação literal curta da transcrição.
A citação deve ser copiada exatamente do texto, sem reescrever e sem traduzir.
Crítica significa: pergunta que pressiona tese de investimento, qualidade do balanço,
sustentabilidade do ROE, risco de crédito, guidance ou capital.
```

Racional: em earnings call, o risco principal é o LLM transformar leitura qualitativa em narrativa sem grounding. Por isso, cada ponto material precisa carregar uma citação literal auditável.

### Prompt 2 — `comparar_trimestres.txt`

Objetivo: comparar 1T26 contra 4T25 e detectar mudanças de guidance/tema.

Trecho central:

```text
Não trate diferença numérica mecânica como mudança se o discurso estratégico for igual.
Diferencie “continuidade” de “mudança”.
Toda mudança precisa de citação literal da call atual; quando possível, também inclua
citação literal da call anterior.
```
**Regra central**: não tratar diferença numérica
como mudança se o discurso for igual; o sinal está na mudança de ênfase ou
postura de risco, não só nos números.


Racional: comparar calls não é apenas olhar números diferentes; o sinal está na mudança de ênfase, na introdução de temas novos e no grau de confiança/cautela.

---

## Como rodar

```bash
pip install -r requirements.txt
 $env ANTHROPIC_API_KEY=sk-ant-...   # e/ou GEMINI_API_KEY=...
 $env HF_API_TOKEN=hf_...            # opcional, FinBERT

python src/run.py                       # análise completa
python src/run.py 
python src/run.py --comparar-modelos    # Anthropic vs gemini

streamlit run src/app.py
```
---

## 4. Extensões escolhidas


1. **Citation tracking**: camada anti-alucinação central. Se uma citação não aparece na transcrição, o relatório registra aviso.
2. **Validação de consistência via FinBERT-PT-BR**: o tom do LLM é checado por um classificador financeiro independente, quando `HF_API_TOKEN` está disponível.
3. **Interface Streamlit**: permite ao analista inspecionar perguntas críticas, red flags, auditoria de citações e validação FinBERT.

Priorizei essas extensões porque elas atacam o principal risco do produto, confiança. Para Equity Strategy, uma resposta bonita mas sem evidência é pior do que uma resposta mais simples e auditável.

---




A execução real com LLM gera os mesmos formatos em:

```text
outputs/resultado.json
outputs/relatorio.md
```

---

## Limitações sérias

1. **Dependência da qualidade da transcrição**: erros de OCR/PDF, quebras de linha e nomes de speakers podem prejudicar a segmentação do Q&A.
2. **Surprise score é inferencial**: sem uma base de consenso pré-call, o score mede novidade/intensidade dentro da própria call, não surpresa real de mercado.
3. **FinBERT valida só tom local**: ele ajuda como segunda opinião, mas não entende guidance, ironia, evasão ou qualidade da resposta em contexto longo.

---

## O que eu faria com mais 2 semanas

- Integraria consenso pré-call e estimates de sell-side para calibrar o surprise score com dados externos.

- Ancorar o surprise score em preço/volume real de BBDC4 (yfinance, como no
  Case 2), tornando-o backtestável.

- Fechar o resíduo de ~7% no citation tracking (margem extra na janela).

- Implementaria recuperação por trechos (`chunk retrieval`) antes do LLM para reduzir custo e melhorar rastreabilidade em calls muito longas.

- Criaria base histórica multi-trimestre para detectar mudanças de linguagem do management ao longo de vários ciclos.
- Comparação setorial: mesmo pipeline em Itaú e Santander do mesmo trimestre.

- Adicionaria reação de mercado: retorno intraday/1D/5D, volume e variação relativa contra bancos pares.


---

## Log honesto de tempo

## Log de tempo

| Bloco | Tempo |
|---|---|
| Ingestão e schemas | 2h30 |
| Prompts e saída estruturada | 2h |
| Citation tracking e validação | 1h30 |
| FinBERT, multi-modelo, Streamlit | 1h30 |
| Depuração real (truncamento, markdown no Streamlit, endpoint FinBERT, bug do citation tracking) | 3h |
| Documentação | 1h |
| **Total** | **~11h30** |

## As razões por que você escolheu se aprofundar em um ou nos dois cases.
A natureza do problema do Case 2 permite validação quantitativa de ponta a
ponta, regressão com erros HAC, backtest out-of-sample. É a
evidência mais forte para uma vaga de Equity Strategy: não só "funciona",
mas "aqui está a prova estatística de quanto, e onde para de funcionar".


Aqui não há motor numérico: uma citação pode ser confirmada como real ou
falsa, mas a interpretação (isso é mesmo um red flag? a resposta é mesmo
evasiva?) continua sendo julgamento qualitativo do LLM, sem equivalente ao
R² do Case 2. Por isso o esforço de profundidade foi para onde o rigor é
mais verificável — não por este case ter recebido menos cuidado (o bug do
citation tracking só apareceu porque foi testado com o mesmo padrão de
exigência).

Ambos cases enriquecedor, havia cogitado em fazer projetos pessoais semelhante a ambos

---
## Três limitações mais sérias

1. **Citation tracking em ~93%, não 100%** — resíduo de casos de borda na
   janela de busca (ver seção acima). O aviso de "não encontrada" deve ser
   lido como forte indicador, não veredito absoluto.
2. **Segmentação de Q&A por heurística de speaker**, dependente do formato
   das transcrições do Bradesco. Já produziu uma duplicata de analista em
   execução real; transcrições muito diferentes degradariam a segmentação
   sem quebrar o pipeline.
3. **Surprise score é inferência sem âncora externa** — sem consenso
   pré-call ou reação de preço, é o componente menos verificável do output.

