#!/bin/bash
# Auto-commit hook: tracks edit count, commits+pushes after 5 edits
COUNTER_FILE="/tmp/claude-edit-counter-invest"
THRESHOLD=5
REPO_DIR="/Users/nirantk/Desktop/scratchpad/executive-function/invest"

# Initialize counter if missing
[ -f "$COUNTER_FILE" ] || echo 0 > "$COUNTER_FILE"

# Increment
COUNT=$(cat "$COUNTER_FILE")
COUNT=$((COUNT + 1))
echo "$COUNT" > "$COUNTER_FILE"

if [ "$COUNT" -ge "$THRESHOLD" ]; then
    # Reset counter
    echo 0 > "$COUNTER_FILE"

    cd "$REPO_DIR" || exit 0

    # Only commit if there are changes
    if [ -n "$(git status --porcelain -- '*.py' '*.md' '*.json' 'CLAUDE.md' 2>/dev/null)" ]; then
        git add -u -- '*.py' '*.md' '*.json' 'CLAUDE.md' 2>/dev/null
        git commit -m "Auto-commit: periodic save after $THRESHOLD edits" 2>/dev/null
        git push 2>/dev/null
        echo '{"systemMessage": "Auto-committed and pushed after '"$THRESHOLD"' edits"}'
    fi
fi
