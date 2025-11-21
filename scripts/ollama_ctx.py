import ollama
import psutil
import math

# ---- heuristics -------------------------------------------------------------

def estimate_kvcache_bytes_per_token(model_info):
    """
    Estimate KV-cache memory per token based on:
      - embedding size
      - number of layers
      - number of attention heads
      - typical GGUF/MXF4 activation sizes

    Formula (approx):
       KV bytes/token ≈ num_layers * head_count_kv * key_length * 2 bytes
       (2 bytes because KV caches are FP16)
    """
    try:
        layers = int(model_info.get("gptoss.block_count", 30))
        n_kv_heads = int(model_info.get("gptoss.attention.head_count_kv",
                                        model_info.get("llama.attention.head_count_kv", 8)))
        head_dim = int(model_info.get("gptoss.attention.key_length",
                                      model_info.get("llama.attention.key_length", 64)))

        # KV cache holds K and V -> multiply by 2
        return layers * n_kv_heads * head_dim * 2
    except:
        # fallback for unknown architectures:
        return 4096 * 2 * 32  # ≈256 KB/token (safe upper bound)


def estimate_model_ram_bytes(model_details, model_info):
    """
    Estimate memory required to load the model weights.
    Use quantization level hints or file size when available.
    """
    # if file size known, rely on that heavily
    if hasattr(model_details, "model_size") and model_details.model_size:
        # model_size is like "20.9B" for parameters, not bytes
        pass

    # GGUF file size is reliable:
    if hasattr(model_details, "size") and model_details.size:
        try:
            return int(model_details.size)
        except:
            pass

    # try parameter_count
    params = None
    for k in ("general.parameter_count", "llama.parameter_count", "gptoss.parameter_count"):
        if k in model_info:
            params = int(model_info[k])
            break

    # fallback: treat missing as 7B model
    if params is None:
        params = 7_000_000_000

    # approximate bytes/param by quantization
    q = getattr(model_details, "quantization_level", "").lower()

    if "q2" in q:
        bytes_per_param = 0.25
    elif "q3" in q:
        bytes_per_param = 0.33
    elif "q4" in q or "mxfp4" in q:
        bytes_per_param = 0.5
    elif "q5" in q:
        bytes_per_param = 0.66
    elif "q6" in q:
        bytes_per_param = 0.75
    else:
        bytes_per_param = 1.0  # fp16-ish fallback

    return int(params * bytes_per_param)


# ---- main function ----------------------------------------------------------

def safe_max_context(model_name):
    m = ollama.show(model_name)

    model_info = getattr(m, "modelinfo", {})
    model_details = getattr(m, "details", {})
    ctx_field = None

    # extract advertised context length
    for key in ("gptoss.context_length", "llama.context_length",
                "general.context_length"):
        if key in model_info:
            ctx_field = int(model_info[key])
            break

    # fallback
    if ctx_field is None:
        ctx_field = 4096

    # estimate RAM usage
    free_ram = psutil.virtual_memory().available
    model_ram = estimate_model_ram_bytes(model_details, model_info)
    kvcache_per_token = estimate_kvcache_bytes_per_token(model_info)

    # safety margin: only use 70% of current free RAM
    usable_ram = free_ram * 0.70
    remaining_for_kv = usable_ram - model_ram

    if remaining_for_kv <= 0:
        return {
            "model": model_name,
            "error": "Not enough free RAM to safely load model",
            "model_ram_bytes": model_ram,
            "free_ram_bytes": free_ram,
        }

    # tokens limited by KV cache footprint
    max_tokens = remaining_for_kv // kvcache_per_token

    # return min(advertised context, safe max)
    safe_ctx = int(min(ctx_field, max_tokens))

    return {
        "model": model_name,
        "advertised_context": ctx_field,
        "safe_context": safe_ctx,
        "ram_available_bytes": free_ram,
        "model_ram_estimated_bytes": model_ram,
        "kv_cache_bytes_per_token": kvcache_per_token,
    }


# ---- run for all installed models ------------------------------------------

def safe_context_for_all_models():
    result = []
    models = ollama.list().models
    for m in models:
        result.append(safe_max_context(m.model))
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(safe_context_for_all_models(), indent=2))
