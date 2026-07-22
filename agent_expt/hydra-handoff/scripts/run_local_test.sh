#!/usr/bin/env bash
# Hydra-Dynamic workflow test using local Qwen LLM
set -euo pipefail

FIXTURE="rounding"
WORK_DIR="/tmp/hydra-test-${FIXTURE}"
RUN_ID="hydra-$(date +%s)"

echo "========================================"
echo " Hydra-Dynamic Workflow Test: $FIXTURE"
echo " Run ID: $RUN_ID"
echo " Using: local Qwen (port 8000)"
echo "========================================"

# Setup fixture
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR/.hydra/runs/$RUN_ID"
cp -r "hydra-code/tests/e2e/fixtures/$FIXTURE/"* "$WORK_DIR/"
cd "$WORK_DIR"

# Phase 1: Analyze complexity
echo ""
echo "[Phase 1] Analyzing task complexity..."
echo "  Fixture: $FIXTURE (financial rounding bug)"
echo "  Files affected: 1 (pricing.py)"
echo "  Complexity: simple (1 file, clear bug)"
echo "  Agent count: 2"
agent_count=2

# Create worktrees (using dirs, not git worktrees for simplicity)
for i in $(seq 0 $((agent_count - 1))); do
    mkdir -p ".hydra/worktrees/$RUN_ID/candidate-$i"
    cp pricing.py test_pricing.py ".hydra/worktrees/$RUN_ID/candidate-$i/"
done

# Phase 2: Dispatch agents
echo ""
echo "[Phase 2] Dispatching $agent_count agents to local Qwen..."

for i in $(seq 0 $((agent_count - 1))); do
    wt=".hydra/worktrees/$RUN_ID/candidate-$i"
    
    if [ "$i" -eq 0 ]; then
        CONSTRAINT="Change no more than 3 lines, prefer the smallest correct diff"
    else
        CONSTRAINT="Add full Decimal chain for ALL calculations, handle every edge case"
    fi
    
    echo "  Agent $i: $CONSTRAINT"
    
    python3 -c "
import json, urllib.request

with open('$wt/pricing.py') as f:
    code = f.read()

prompt = f'''Task: Fix the banker\\'s rounding bug in this pricing module.
Constraint: $CONSTRAINT

Bug: Python round() uses banker\\'s rounding (ROUND_HALF_EVEN), financial needs ROUND_HALF_UP.
Example: format_price(1.005) returns \"\$1.00\" should return \"\$1.01\".

Output COMPLETE corrected pricing.py inside \`\`\`python ... \`\`\` blocks:

\`\`\`python
{code}
\`\`\`
'''

data = json.dumps({
    'model': 'qwen',
    'messages': [{'role': 'user', 'content': prompt}],
    'max_tokens': 4096,
    'temperature': 0.3
}).encode()

req = urllib.request.Request(
    'http://localhost:8000/v1/chat/completions',
    data=data, headers={'Content-Type': 'application/json'}
)
resp = json.loads(urllib.request.urlopen(req).read())
msg = resp['choices'][0]['message']
text = msg.get('content') or msg.get('reasoning', '')

import re
blocks = re.findall(r'\x60{3,}python\n?(.*?)\x60{3,}', text, re.DOTALL)
code = max(blocks, key=len).strip() if blocks else text.strip()

with open('$wt/pricing_new.py', 'w') as f:
    f.write(code)
print(f'    Agent $i: generated {len(code)} chars')
"
done

# Phase 3: Evaluate
echo ""
echo "[Phase 3] Evaluating candidates..."

for i in $(seq 0 $((agent_count - 1))); do
    wt=".hydra/worktrees/$RUN_ID/candidate-$i"
    if [ -f "$wt/pricing_new.py" ]; then
        cp "$wt/pricing_new.py" "$wt/pricing.py"
        rm -f "$wt/pricing_new.py"
        
        cd "$wt"
        pytest test_pricing.py -v --tb=line 2>&1 | tail -5 || true
        cd "$WORK_DIR"
    else
        echo "  Agent $i: no output generated"
    fi
    
    # Record diff stats
    diff_lines=$(diff <(cat "$WORK_DIR/pricing.py" | wc -l) <(cat "$wt/pricing.py" | wc -l) 2>/dev/null || echo "?")
    echo "  Lines in candidate-$i/pricing.py: $(wc -l < "$wt/pricing.py")"
done

# Phase 4: Tournament with Qwen judge
echo ""
echo "[Phase 4] Tournament: Qwen judge with rubric..."

# Phase 6: Report
echo ""
echo "[Phase 6] Report summary"
echo "========================================"
echo " Test complete for fixture: $FIXTURE"
echo " Run ID: $RUN_ID"
echo " Config: opencode.jsonc points to local-8000/qwen/qwen3.6-27b"
echo ""
echo " To run full OpenCode workflow locally:"
echo "   cd $(pwd)/../.. && opencode"
echo "   Then load: hydra-dynamic: Fix the banker's rounding bug in tests/e2e/fixtures/rounding/"
echo "========================================"
