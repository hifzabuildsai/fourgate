#!/usr/bin/env bash
set -e

echo ""
echo "############################################"
echo "#  FOURGATE — live before/after demo       #"
echo "############################################"
echo ""
echo ">>> Checking a real (broken) MCP connector..."
sleep 1
python3 checker/preflight.py fixtures/broken_server.py --checked-by "demo" || true

echo ""
echo ">>> Same connector, one line fixed (print -> stderr)..."
sleep 1
python3 checker/preflight.py fixtures/clean_server.py --checked-by "demo"

echo ""
echo "That's the whole pitch: one stray print() statement silently breaks"
echo "an MCP connector in production. Fourgate catches it before you ship."
echo "(Both runs above just synced to the shared Supabase log.)"
echo ""
