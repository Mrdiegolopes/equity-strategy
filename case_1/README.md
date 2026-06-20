# Case 1 — Earnings Call Intelligence Tracker

Ferramenta em Python para ingerir transcrições de earnings call, extrair inteligência estruturada com LLM, auditar citações literais contra o texto-fonte e gerar relatório executivo em markdown.

Empresa analisada: **Banco Bradesco (BBDC4)**, integrante do Ibovespa.  
Call atual: **1T26**. Comparativo temporal: **4T25**.

---

## 1. Como rodar

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
```

Execução principal:

```bash
python src/run.py
```

Sem validação FinBERT:

```bash
python src/run.py --sem-finbert
```

Exemplo completo sem consumir API:

```bash
python src/run.py --exemplo
```

Interface opcional:

```bash
streamlit run src/app.py
```

Arquivos gerados:

```text
outputs/resultado.json   # JSON estruturado completo
outputs/relatorio.md     # relatório executivo <= 400 palavras
```

---

## 2. Arquitetura

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
    ├── resultado_exemplo.json
    └── relatorio_exemplo.md
```

Fluxo do pipeline:

1. **Ingestão** (`ingestao.py`): lê a transcrição, limpa ruído do PDF, separa prepared remarks de Q&A e segmenta slides/rodadas de perguntas.
2. **Schemas** (`schemas.py`): define contratos Pydantic estritos para tom, red flags, perguntas críticas, surprise score e comparação temporal.
3. **LLM** (`llm_client.py`): chama Anthropic ou Gemini com saída estruturada. O modelo não deve escrever texto livre; ele preenche o schema.
4. **Citation tracking** (`validation.py`): toda citação literal retornada pelo LLM é verificada deterministicamente contra a transcrição.
5. **FinBERT opcional** (`finbert.py`): valida a direção do tom com o modelo `lucas-leme/FinBERT-PT-BR` via Hugging Face Inference API, se houver `HF_API_TOKEN`.
6. **Render** (`report.py`): gera JSON completo e relatório executivo em markdown, com limite duro de 400 palavras.
7. **Orquestração** (`run.py`): coordena as etapas sem concentrar lógica de negócio.

---

## 3. Decisões de prompt engineering

Separei o problema em duas chamadas principais:

### Prompt 1 — `analisar_call.txt`

Objetivo: analisar apenas a call atual e extrair:

- tom geral do management;
- top 3 perguntas críticas dos analistas;
- qualidade da resposta do management;
- red flags linguísticos;
- surprise score.

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

Racional: comparar calls não é apenas olhar números diferentes; o sinal está na mudança de ênfase, na introdução de temas novos e no grau de confiança/cautela.

---

## 4. Extensões escolhidas

Escolhi aprofundar o **Case 1** com três extensões:

1. **Citation tracking**: camada anti-alucinação central. Se uma citação não aparece na transcrição, o relatório registra aviso.
2. **Validação de consistência via FinBERT-PT-BR**: o tom do LLM é checado por um classificador financeiro independente, quando `HF_API_TOKEN` está disponível.
3. **Interface Streamlit**: permite ao analista inspecionar perguntas críticas, red flags, auditoria de citações e validação FinBERT.

Priorizei essas extensões porque elas atacam o principal risco do produto: confiança. Para Equity Strategy, uma resposta bonita mas sem evidência é pior do que uma resposta mais simples e auditável.

---

## 5. Exemplo de input e output

Input principal:

```text
transcricoes/bradesco_1t26.txt
transcricoes/bradesco_4t25.txt
```

Output integral de exemplo:

```text
outputs/resultado_exemplo.json
outputs/relatorio_exemplo.md
```

O exemplo pode ser reproduzido sem API com:

```bash
python src/run.py --exemplo
```

A execução real com LLM gera os mesmos formatos em:

```text
outputs/resultado.json
outputs/relatorio.md
```

---

## 6. Limitações sérias

1. **Dependência da qualidade da transcrição**: erros de OCR/PDF, quebras de linha e nomes de speakers podem prejudicar a segmentação do Q&A.
2. **Surprise score é inferencial**: sem uma base de consenso pré-call, o score mede novidade/intensidade dentro da própria call, não surpresa real de mercado.
3. **FinBERT valida só tom local**: ele ajuda como segunda opinião, mas não entende guidance, ironia, evasão ou qualidade da resposta em contexto longo.

---

## 7. O que eu faria com mais 2 semanas

1. Integraria consenso pré-call e estimates de sell-side para calibrar o surprise score com dados externos.
2. Implementaria recuperação por trechos (`chunk retrieval`) antes do LLM para reduzir custo e melhorar rastreabilidade em calls muito longas.
3. Criaria base histórica multi-trimestre para detectar mudanças de linguagem do management ao longo de vários ciclos.
4. Adicionaria reação de mercado: retorno intraday/1D/5D, volume e variação relativa contra bancos pares.
5. Criaria avaliação automática com casos rotulados manualmente por analistas.

---

## 8. Log honesto de tempo

Tempo aproximado dedicado ao Case 1: **8h–10h**.

Distribuição aproximada:

- ingestão e limpeza das transcrições: 1h;
- schemas e arquitetura modular: 1h30;
- prompts e saída estruturada: 2h;
- citation tracking e validação: 1h30;
- relatório markdown e exemplo integral: 1h;
- Streamlit, README e ajustes finais: 1h–2h.

