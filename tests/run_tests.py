#!/usr/bin/env python3
"""Send each note in tests/cases.json to the n8n webhook and score the result."""
import json, sys, time, urllib.request, urllib.error

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5678/webhook/icd-code"
PAUSE_SECONDS = 60       # gap between notes, to stay under the Groq tokens-per-minute limit
RETRY_WAIT_SECONDS = 65  # wait before retrying a request that failed
MAX_ATTEMPTS = 3


def call(note):
    req = urllib.request.Request(
        URL,
        data=json.dumps({"note": note}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)


def call_with_retry(note):
    attempts = 0
    while True:
        attempts += 1
        status, body = call(note)
        if status == 200 or attempts >= MAX_ATTEMPTS:
            return status, body, attempts
        print("   attempt %d got HTTP %s, waiting %ds before retrying"
              % (attempts, status, RETRY_WAIT_SECONDS), flush=True)
        time.sleep(RETRY_WAIT_SECONDS)


cases = json.load(open("tests/cases.json"))
results = []
for c in cases:
    status, body, attempts = call_with_retry(c["note"])
    problems = []
    rows = []
    if status != 200:
        problems.append("HTTP %s after %d attempts" % (status, attempts))
    try:
        data = json.loads(body)
        if isinstance(data, list):
            rows = data
        else:
            problems.append("response is not a list")
    except ValueError:
        problems.append("response is not JSON")

    if status == 200 and not rows:
        problems.append("empty response: no rows returned")

    final = sorted({r.get("final_code") for r in rows if r.get("final_code")})
    review_rows = [r for r in rows if r.get("status") == "REVIEW"]

    for code in c["expected_codes"]:
        if code not in final:
            problems.append("missing " + code)
    for code in c.get("forbidden_codes", []):
        if code in final:
            problems.append("forbidden " + code)
    for prefix in c.get("forbidden_prefixes", []):
        hits = [x for x in final if x.startswith(prefix)]
        if hits:
            problems.append("forbidden prefix " + prefix + ": " + ",".join(hits))
    if c["review_expected"] and rows and not review_rows:
        problems.append("no REVIEW row")

    results.append({
        "id": c["id"], "passed": not problems, "problems": problems,
        "final_codes": final, "review_rows": len(review_rows),
        "attempts": attempts, "rows": rows, "http_status": status,
    })
    print("%s %s  rows=%d  codes=%s  review_rows=%d  attempts=%d  %s" % (
        c["id"], "PASS" if not problems else "FAIL", len(rows), final,
        len(review_rows), attempts, "; ".join(problems)), flush=True)
    time.sleep(PAUSE_SECONDS)

passed = sum(r["passed"] for r in results)
false_alarms = sum(
    1 for c, r in zip(cases, results)
    if not c["review_expected"] and r["review_rows"] > 0
)
print("\n%d/%d cases passed; %d case(s) with REVIEW rows that were not expected"
      % (passed, len(cases), false_alarms))
json.dump(results, open("tests/results.json", "w"), indent=2)
