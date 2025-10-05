#!/usr/bin/env bash
set -euo pipefail
RG="${1:-ragagent-prod}"

echo "== Resource sanity =="
az resource list -g "$RG" -o table | head -n 50

echo "== Private endpoints =="
az network private-endpoint list -g "$RG" -o table

echo "== Private DNS zones =="
az network private-dns zone list -g "$RG" -o table

echo "== Key endpoints =="
FD=$(az afd endpoint list -g "$RG" --profile ragagent-fd-prod --query "[0].hostName" -o tsv || true)
APIM=$(az apim show -g "$RG" -n ragagent-apim-prod --query gatewayUrl -o tsv || true)
AOAI=$(az deployment group show -g "$RG" --name main --query "properties.outputs.openaiEndpoint.value" -o tsv 2>/dev/null || echo "")
SEARCH=$(az deployment group show -g "$RG" --name main --query "properties.outputs.searchEndpoint.value" -o tsv 2>/dev/null || echo "")
COSMOS=$(az deployment group show -g "$RG" --name main --query "properties.outputs.cosmosEndpoint.value" -o tsv 2>/dev/null || echo "")

echo "FrontDoor:   $FD"
echo "APIM GW:     $APIM"
echo "AOAI:        $AOAI"
echo "Search:      $SEARCH"
echo "Cosmos:      $COSMOS"

echo "✔ Preflight metadata collected. Next: exec into Container App to nslookup each hostname and verify it resolves to 10.0.2.0/24."