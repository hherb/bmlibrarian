#!/usr/bin/env python3
"""
Inspect Ollama models and extract parameter counts + context lengths.

Usage:
    python ollama_model_inspector.py

Outputs:
    - Printed table to stdout
    - CSV saved to ./ollama_models_params_context.csv
"""
import re
import json
from typing import Any, List, Tuple, Optional
import pandas as pd

try:
    import ollama
except Exception as e:
    raise RuntimeError("Failed to import ollama. Install the Python client and ensure Ollama daemon is running.") from e

def recursive_search(obj: Any, path: str = "") -> List[Tuple[str, Any]]:
    found = []
    if obj is None:
        return found
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_path = f"{path}.{k}" if path else k
            found.extend(recursive_search(v, new_path))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            new_path = f"{path}[{i}]"
            found.extend(recursive_search(v, new_path))
    elif hasattr(obj, "__dict__"):
        for k, v in vars(obj).items():
            new_path = f"{path}.{k}" if path else k
            found.extend(recursive_search(v, new_path))
    else:
        found.append((path, obj))
    return found

def parse_int_from_possible(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    s = str(value).strip()
    # direct big integer
    try:
        s2 = s.replace(",", "")
        if re.fullmatch(r"\d{4,}", s2):
            return int(s2)
    except:
        pass
    # human readable like "20.9B", "6.7B", "20.9 B"
    m = re.match(r"^\s*([\d\.]+)\s*([kKmMbB])\s*$", s)
    if m:
        num = float(m.group(1))
        suffix = m.group(2).lower()
        if suffix == "k":
            return int(num * 1_000)
        if suffix == "m":
            return int(num * 1_000_000)
        if suffix == "b":
            return int(num * 1_000_000_000)
    # embedded patterns like "parameter_count': 20914757184" or "20.9B"
    m2 = re.search(r"(\d+(?:[\.,]\d+)?)\s*([kKmMbB])", s)
    if m2:
        num = float(m2.group(1).replace(",", "."))
        suf = m2.group(2).lower()
        mult = {"k":1e3, "m":1e6, "b":1e9}[suf]
        return int(num * mult)
    # fallback: any long number
    m3 = re.search(r"(\d{4,})", s.replace(",", ""))
    if m3:
        try:
            return int(m3.group(1))
        except:
            pass
    return None

def parse_param_count_from_pairs(pairs: List[Tuple[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    candidates = []
    for path, val in pairs:
        lp = path.lower()
        if "param" in lp or "parameter" in lp or "parameter_count" in lp or "parameter_size" in lp:
            parsed = parse_int_from_possible(val)
            if parsed:
                candidates.append((parsed, path, val))
    if not candidates:
        # try to find "20.9B" style anywhere
        for path, val in pairs:
            if isinstance(val, str) and re.search(r"\d+(\.\d+)?\s*[kKmMbB]\b", val):
                parsed = parse_int_from_possible(val)
                if parsed:
                    candidates.append((parsed, path, val))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    parsed_val, path, raw = candidates[0]
    return parsed_val, f"{path} -> {raw}"

def parse_context_from_pairs(pairs: List[Tuple[str, Any]]) -> Tuple[Optional[int], Optional[str]]:
    candidates = []
    for path, val in pairs:
        lp = path.lower()
        if "context" in lp or "context_length" in lp or "contextlen" in lp or "max_context" in lp or "original_context" in lp or "sliding_window" in lp or "rope" in lp:
            parsed = parse_int_from_possible(val)
            if parsed:
                candidates.append((parsed, path, val))
    if not candidates:
        # fallback: any plausible context-like number on relevant paths
        for path, val in pairs:
            parsed = parse_int_from_possible(val)
            if parsed and 256 <= parsed <= 262144 and any(k in path.lower() for k in ["rope", "context", "sliding", "max"]):
                candidates.append((parsed, path, val))
    if not candidates:
        return None, None
    candidates.sort(key=lambda x: x[0], reverse=True)
    parsed_val, path, raw = candidates[0]
    return parsed_val, f"{path} -> {raw}"

def inspect_models():
    models = ollama.list()
    if not models:
        raise RuntimeError("No models returned by ollama.list()")
    results = []
    for m in models:
        name = m if isinstance(m, str) else getattr(m, "name", str(m))
        try:
            info = ollama.show(name)
        except Exception as e:
            results.append({
                "model": name,
                "parameter_count": None,
                "parameter_source": f"ollama.show() error: {e}",
                "context_length": None,
                "context_source": None,
            })
            continue

        pairs = []
        # try common attribute names first
        for attr in ("modelinfo", "model_info", "details", "info", "meta", "capabilities"):
            if hasattr(info, attr):
                try:
                    pairs.extend(recursive_search(getattr(info, attr), path=attr))
                except Exception:
                    pass
        # include whole object
        pairs.extend(recursive_search(info, path="root"))

        # dedupe by path
        seen = set()
        dedup = []
        for p, v in pairs:
            if p in seen:
                continue
            seen.add(p)
            dedup.append((p, v))

        param_count, param_source = parse_param_count_from_pairs(dedup)
        context_length, context_source = parse_context_from_pairs(dedup)

        # final fallback: dump text and search for patterns
        if not param_count:
            try:
                txt = json.dumps(info.__dict__, default=str)
            except Exception:
                txt = str(info)
            m2 = re.search(r"(\d+(?:\.\d+)?)\s*([kKmMbB])", txt)
            if m2:
                param_count = parse_int_from_possible(m2.group(0))
                param_source = "fallback: string search"

        results.append({
            "model": name,
            "parameter_count": param_count,
            "parameter_source": param_source,
            "context_length": context_length,
            "context_source": context_source,
        })

    df = pd.DataFrame(results)
    def human(n):
        if n is None:
            return None
        for unit, div in [("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)]:
            if n >= div:
                return f"{n/div:.2f}{unit}"
        return str(n)
    df["parameter_human"] = df["parameter_count"].apply(human)
    df = df[["model", "parameter_count", "parameter_human", "parameter_source", "context_length", "context_source"]]
    df = df.sort_values(by=["parameter_count"], ascending=False, na_position="last")
    return df

if __name__ == "__main__":
    df = inspect_models()
    print(df.to_string(index=False))
    csv_path = "ollama_models_params_context.csv"
    df.to_csv(csv_path, index=False)
    print(f"\nSaved CSV to ./{csv_path}")
