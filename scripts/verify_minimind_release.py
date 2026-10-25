"""CPU generation diagnostic for the user's pinned private HF release.

Use --snapshot pointing to a download of the model/code paths listed below.
No network, credentials, training, or claimed semantic accuracy. Exact source
hashes are checked before importing the reviewed MiniMind implementation.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

FILES = {
    "code/minimind/model/model_minimind.py": "548f1203282dccb3be43227b11463f469b976afbab614df52828bdd246c3786f",
    "code/minimind/model/tokenizer.json": "71f32c68cf63a15355a8fc171b7594b3d41870fe0ddb54fc6aefa55f73a4a668",
    "code/minimind/model/tokenizer_config.json": "d7cd6a60c9f191c4f9ffec69b2eb289ad2f960366724f328b681ae1e46e4c110",
    "model/full_sft_768.pth": "4490faad19e43a3f6b8d78f665e62acddd9620e0b922ded0c1df75257be97814",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name, expected in FILES.items():
        digest = hashlib.file_digest((args.snapshot / name).open("rb"), "sha256").hexdigest()
        if digest != expected:
            raise ValueError(f"Release hash mismatch: {name}")
    import torch
    import transformers
    from transformers import AutoTokenizer

    torch.set_num_threads(4)
    torch.manual_seed(17)
    spec = importlib.util.spec_from_file_location(
        "reviewed_minimind", args.snapshot / "code/minimind/model/model_minimind.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    model = module.MiniMindForCausalLM(module.MiniMindConfig(
        hidden_size=768, num_hidden_layers=8, max_position_embeddings=2048
    ))
    state = torch.load(args.snapshot / "model/full_sft_768.pth", map_location="cpu", weights_only=True)
    if not all(torch.isfinite(value).all() for value in state.values()):
        raise ValueError("Checkpoint contains non-finite values")
    model.load_state_dict(state, strict=True)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(
        args.snapshot / "code/minimind/model", local_files_only=True, trust_remote_code=False
    )
    prompts = ["hi", "who are you?", "السَّلَامُ عَلَيْكُمْ", "What is 2 + 2?",
               "Explain the difference between علم and عمل.",
               "Bhai, tum kya kar sakte ho?"]
    rows = []
    for prompt in prompts:
        chat = [{"role": "user", "content": prompt}]
        rendered = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=True)
        ids = tokenizer(rendered, return_tensors="pt").input_ids
        with torch.inference_mode():
            generated = model.generate(ids, max_new_tokens=64, do_sample=False, use_cache=True,
                                       eos_token_id=tokenizer.eos_token_id,
                                       pad_token_id=tokenizer.pad_token_id)
        new_ids = generated[0, ids.shape[1]:].tolist()
        rows.append({"prompt": prompt, "response": tokenizer.decode(new_ids, skip_special_tokens=True),
                     "input_tokens": ids.shape[1], "output_tokens": len(new_ids),
                     "finish_reason": "eos" if new_ids and new_ids[-1] == tokenizer.eos_token_id else "length"})
    report = {"scope": "Generation diagnosis, not held-out semantic accuracy",
              "hf_revision": "2ecc917266a626db919fd6af154f9f0d3a286bcf", "files": FILES,
              "torch": torch.__version__, "transformers": transformers.__version__,
              "strict_state_dict": True, "finite_tensors": True,
              "parameters": sum(p.numel() for p in model.parameters()), "device": "cpu", "cases": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "cases": len(rows), "parameters": report["parameters"]}))


if __name__ == "__main__":
    main()
