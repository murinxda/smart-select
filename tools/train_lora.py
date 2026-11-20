"""Runs ``mlx_lm.lora`` with the tokenizer that inference uses.

Mistral's tokenizer files on Hugging Face split words with a wrong pattern unless loaded with
``fix_mistral_regex``, which ``mlx_lm.lora`` cannot pass: training and inference would then cut the
same text into different tokens.

usage: uv run python tools/train_lora.py -c configs/lora-3b.yaml [mlx_lm.lora options]
"""
import mlx_lm.lora as lora

_load = lora.load


def load(*args, **kwargs):
    kwargs["tokenizer_config"] = {**kwargs.get("tokenizer_config", {}), "fix_mistral_regex": True}
    return _load(*args, **kwargs)


lora.load = load

if __name__ == "__main__":
    lora.main()
