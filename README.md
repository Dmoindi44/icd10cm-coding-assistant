# ICD-10-CM coding assistant (n8n prototype)

A prototype that suggests ICD-10-CM diagnosis codes from clinical notes and
sends anything doubtful to human review. It is a coding-assistance experiment,
not an autonomous coder, and it is not for real patient data.

## Status

- Works end to end on 13 synthetic test notes: 13/13 on the latest run.
- The notes and expected codes were written by the author, not by a certified
  coder. This is a smoke test of the pipeline, not a measurement of accuracy.
- The model varies from run to run, so a repeat run could score differently.

## How it works

1. A webhook receives a JSON body: {"note": "..."}.
2. An LLM extracts the diagnoses, each with a search term and an exact quote from the note.
3. Postgres full-text search finds the matching 3-character ICD-10-CM categories.
4. An LLM picks one category. A Code node checks the pick is on the list.
5. Postgres loads the billable codes in that category.
6. An LLM picks one code. A Code node checks the code is on that list.
7. The response has one row per diagnosis, with status OK or REVIEW and flags.

## Safeguards

- The LLM only chooses from lists built from the official code set.
- Code nodes check every choice, because the model sometimes ignores instructions.
  Example: it returned J18.9 for an empty candidate list, and the check rejected it.
- A diagnosis documented with uncertainty wording ("possible", "suspected") is
  flagged for review and not given a code.
- Evidence quotes are checked as exact text from the note.
- The two nodes that can find nothing (category search and code loading) still pass an item
  along, so a diagnosis with no matches reaches review instead of vanishing.

## Data

FY2027 ICD-10-CM (effective October 1, 2026), "Code Descriptions in Tabular
Order", downloaded from the CMS ICD-10 page. Loaded table: 98,403 rows
(74,879 billable codes and 23,524 category headers). The billable codes were
cross-checked against the separate codes file, with no differences in either direction.

## Test history

The 13 cases are in tests/cases.json. tests/run_tests.py sends them to the webhook
one at a time and scores the results.

| Run | Score | What the results showed |
|---|---|---|
| 1 | 4/13 | Notes sent 3 seconds apart hit the model provider's 8,000 tokens-per-minute limit (HTTP 500). Three cases returned empty responses. |
| 2 | 9/13 | A 60-second gap between notes fixed the rate-limit failures. One case failed repeatedly and three returned nothing. |
| 3 | 12/13 | A search column that matches hyphenated and unhyphenated spellings fixed the reflux case. "Always Output Data" on two nodes made empty searches return a REVIEW row. |
| 4 | 13/13 | A 65-second delay between code-picking calls fixed the last case. Two diagnoses in one large category sent two large requests within a minute. |

## Known limits

- No accuracy measurement beyond the 13 self-written cases.
- The Alphabetic Index is not loaded. Code choice relies on descriptions only.
- The care setting (inpatient or outpatient) is not an input. The guidelines treat
  uncertain diagnoses differently in each, so those items are flagged, not coded.
- The search needs every word of the search term to match. A term that does not
  match the code descriptions (for example "broken arm" instead of "fracture")
  returns nothing and goes to REVIEW. The "broken arm" test passes for that reason.
- The same code can appear in two rows when two extracted diagnoses map to it.
- Evidence quotes are sometimes a whole sentence, not the specific phrase.
- Large categories (for example S82, with 3,096 codes) are too big for one request
  and are cut off at 200 codes. Even the E11 list (87 codes) is about 4,400 tokens.
- The model provider's free tier allows 8,000 tokens per minute, so a note can take
  minutes. A production service would need a paid tier with a suitable data agreement.
- ICD-10-CM only. ICD-10-PCS and CPT are not covered. CPT needs an AMA license.
- Synthetic notes only. No business associate agreement was verified for the model
  provider, so real patient notes must not be used.
- The uncertainty check is a fixed word list. Wording outside it (for example
  "concern for" or "cannot exclude") is not caught, and that diagnosis could be coded.
- A note with no extractable diagnosis has not been tested and may return an empty response.

## Setup

1. Create the database password file:

        echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" > .env
        chmod 600 .env

2. Download the FY2027 "Code Descriptions in Tabular Order" ZIP from the CMS ICD-10 page.
   Unzip it into data/ so that data/Code Descriptions/icd10cm_order_2027.txt exists.
3. Start the services:

        docker compose up -d

4. Load the codes (expected: 98,403 rows):

        docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U medcoding -d icd < sql/01_load_icd10cm.sql

5. Open n8n at http://127.0.0.1:5678, create the owner account, and add two credentials:
   Postgres (host postgres, port 5432, database icd, user medcoding) and Groq.
6. Import workflows/icd10cm-coding-assistant.json and reconnect the credentials.
   The "Pick final code" node has Batch Size 1 and Delay Between Batches 65000
   saved in the workflow. Publish the workflow.
7. Send a note:

        curl -X POST http://127.0.0.1:5678/webhook/icd-code \
          -H 'Content-Type: application/json' \
          -d '{"note":"67-year-old female. HTN and T2DM, both stable."}'

8. Run the tests (about 20 to 30 minutes, with 60 seconds between notes):

        python3 tests/run_tests.py

## Stack

n8n (image tag latest; 2.44.6 when built), PostgreSQL 16, Docker Compose, Python 3
for the test script, Groq API (openai-gpt-oss-20b).
