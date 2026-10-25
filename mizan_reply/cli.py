"""Command entrypoint: preflight, train, evaluate, generate."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import hashlib
import sys



def generate_main(argv: list[str]) -> dict:
    parser = argparse.ArgumentParser(description="Own-weight byte generation. Evidence is supplied context, not automatically verified truth.")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--prompt", required=True, help="JSON object: messages, evidence, optional roots; never contains a target")
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args(argv)
    from pathlib import Path
    from .data import encode_prompt
    from .evaluate import inference_device, load_inference_model
    from .generation import generate
    from .train import assert_new_report_output, write_new_report
    output = assert_new_report_output(args.output)
    prompt_bytes = Path(args.prompt).read_bytes()
    request = json.loads(prompt_bytes)
    if not isinstance(request, dict) or set(request) - {"messages", "evidence", "roots"} or not {"messages", "evidence"} <= set(request):
        raise ValueError("Prompt needs messages/evidence and optionally roots; targets/extra fields are forbidden")
    device = inference_device(args.device)
    model, checkpoint, checkpoint_sha256 = load_inference_model(args.checkpoint, device, include_sha256=True)
    prompt = encode_prompt(request["messages"], request["evidence"], request.get("roots"), model.config.max_seq_len)
    result = generate(model, prompt["input_ids"].to(device), roots=prompt["roots"].to(device), max_new_tokens=args.max_new_tokens)
    payload = {"model_output": asdict(result), "checkpoint_sha256": checkpoint_sha256,
               "epoch_completed": checkpoint["epoch_completed"], "optimizer_steps": checkpoint["optimizer_steps"],
               "prompt_sha256": hashlib.sha256(prompt_bytes).hexdigest(),
               "reply_source": "loaded_checkpoint_weights_argmin_byte_decoder",
               "independently_verified": False, "online_learning": False,
               "probability_normalization": False,
               "limits": "Decoded text is a model output, not a mathematical truth certificate. UTF-8 syntax masking does not verify meaning."}
    write_new_report(output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("preflight", "train", "evaluate", "generate"))
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return None
    # Parse only the command here so each subcommand owns its --help and flags.
    args = parser.parse_args(argv[:1])
    rest = argv[1:]
    if args.command in ("preflight", "train"):
        from .train import main as train
        return train(rest + (["--preflight"] if args.command == "preflight" else []))
    if args.command == "evaluate":
        from .evaluate import main as evaluate
        return evaluate(rest)
    return generate_main(rest)


if __name__ == "__main__":
    main()
