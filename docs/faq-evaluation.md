# FAQ matching — how it works and how well it works (measured 2026-10-04)

## What it is
A `faq` block holds the owner's question/answer pairs. A customer types a question in their own words; the bot returns the **owner's exact
answer text**. Nothing is generated for the customer, so the bot cannot make up prices or hours. Only embeddings (not a language model) run
at question time.

* **Build time** (when a version is saved / published): `gpt-6-luna` writes 8 informal phrasings of each question; the question plus its
  phrasings are embedded with `text-embedding-3-small` and stored (≈ $0.0007 for 10 entries).
* **Question time**: one embedding call (median 320–380 ms, ≈ $0.0000003); cosine similarity against the stored vectors; the entry score is its
  best phrasing.
* **Policy**: score ≥ 0.60 **and** at least 0.09 ahead of the runner-up → answer. Otherwise score ≥ 0.45 → show the top 3 questions as buttons
  («هیچ‌کدام» logs the question). Otherwise → "not found": the question is stored as *unanswered*, the owner is notified, and the customer is offered
  the full question list.
* **Safety nets**: if the provider is down or the index is not ready the bot falls back to simple word matching instead of failing; 30 searches per
  customer per hour; queries are cut to 300 characters; a repeated question from the same customer notifies the owner once.

## Why embeddings alone were not enough (plain matching of the owner's question)
`text-embedding-3-small`, question only, 90 informal paraphrases + 36 off-topic questions in three businesses: top-1 accuracy 64%; at
thresholds that keep wrong answers near 0%, only ~30% of valid questions were answered. With the LLM-written phrasings: top-1 87%, top-3 94%.
`text-embedding-3-large` was 91–92% top-1 but needed a higher threshold for the same safety, so it gave no advantage for 6.5× the price.

## Choosing the thresholds (scripts/faq_robust.py)
The phrasings are random, so one lucky draw proves nothing. The policy was evaluated over **4 independent draws**:

| answer ≥ | margin | valid answered right (mean) | valid answered **wrong** (mean / worst) | off-topic wrongly answered (mean / worst) | right via one tap |
|---|---|---|---|---|---|
| 0.55 | 0.03 | 69.2% | 3.1% / 4.4% | 4.2% / 8.3% | 16.4% |
| 0.60 | 0.03 | 61.1% | 1.9% / 3.3% | 2.1% / 2.8% | 25.0% |
| **0.60** | **0.09** | **60.3%** | **0.3% / 1.1%** | **1.4% / 2.8%** | **26.4%** |
| 0.65 | 0.09 | 50.8% | 0.3% / 1.1% | 1.4% / 2.8% | 35.8% |

## End to end through the shipped code (scripts/faq_e2e.py), one run, 0.60 / 0.09 / 0.45
Valid questions (90): **63.3% answered at once, 0.0% answered wrongly**, 26.7% the right question offered as a button (≈ 90% reach the right
answer within one tap), 3.3% suggestions without it, 6.7% not found. Off-topic (36): 2.8% answered, 22.2% shown (irrelevant) suggestions with a
«هیچ‌کدام» button, 75.0% clean "not found".

## Limits — read before quoting these numbers
* Small sample: 90 valid + 36 off-topic questions, three business types, paraphrases written by one person. "0 wrong of 90" is consistent with
  a true rate of up to roughly 3%.
* Random variation: in an earlier end-to-end run with margin 0.03 two of 90 were answered wrongly; the margin of 0.09 was chosen because of it.
* Short, unusual wordings are the weak spot («کی تعطیل می‌کنید؟» against «ساعت کاری…» was missed in a live test). That is why "not found" offers the
  full list and tells the owner.
* About one in five off-topic questions (e.g. gold prices) shows irrelevant suggestions; harmless but not pretty.
* Customers' question text is sent to OpenAI's embedding endpoint. Persian-specific quality is not documented by OpenAI; these numbers are ours.
* Entries are limited to 40 per FAQ block.
