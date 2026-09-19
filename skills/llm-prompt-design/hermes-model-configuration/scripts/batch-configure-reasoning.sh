#!/bin/bash
# Template: Batch configure reasoning_effort for multiple providers
# Usage: Copy, customize provider URLs/keys, and execute:
#   bash configure_all_reasoning.sh 2>&1 | tee reasoning_config.log

set -e

# Configuration: providers and their details
declare -A PROVIDERS=(
    [OpenRouter]="https://openrouter.ai/api/v1"
    [Api.linstore.my.id]="https://api.linstore.my.id/v1"
    [Api.b.ai]="https://api.b.ai/v1"
    [Api.invibuilder.com]="https://api.invibuilder.com/api/v1"
)

# Reasoning effort mapping by model pattern
classify_reasoning() {
    local model="$1"
    local model_lower=$(echo "$model" | tr '[:upper:]' '[:lower:]')
    
    if [[ "$model_lower" == *"claude"* ]]; then
        if [[ "$model_lower" == *"opus-5"* ]] || [[ "$model_lower" == *"opus-4-8"* ]] || [[ "$model_lower" == *"opus-4.8"* ]]; then
            echo "high"
        elif [[ "$model_lower" == *"opus"* ]]; then
            echo "medium"
        else  # haiku, sonnet
            echo "low"
        fi
    elif [[ "$model_lower" == *"glm"* ]]; then
        echo "low"  # wajib
    elif [[ "$model_lower" == *"deepseek-r1"* ]]; then
        echo "medium"
    else
        echo ""
    fi
}

# Main batch loop
for provider_name in "${!PROVIDERS[@]}"; do
    base_url="${PROVIDERS[$provider_name]}"
    echo ""
    echo "=========================================="
    echo "Provider: $provider_name"
    echo "Base URL: $base_url"
    echo "=========================================="
    
    # TODO: Fetch API key from ~/.hermes/.env dynamically
    # For now, model configuration is static in Hermes config.yaml
    # This script is a template for future multi-provider setups
    
    # Uncomment and customize for your setup:
    # api_key=$(grep "PROVIDER_KEY_NAME" ~/.hermes/.env | cut -d= -f2)
    # models=$(curl -s "$base_url/models" -H "Authorization: Bearer $api_key" | jq '.data[].id')
    
    # for model in $models; do
    #     effort=$(classify_reasoning "$model")
    #     if [ -n "$effort" ]; then
    #         cmd="hermes config set providers.$provider_name.models.$model.reasoning_effort $effort"
    #         echo "$cmd"
    #         eval "$cmd" 2>&1 | grep "Set " | head -1
    #     fi
    # done
done

echo ""
echo "✓ Batch configuration complete."
echo "Verify with: hermes config get providers.<PROVIDER>.models.<MODEL>.reasoning_effort"