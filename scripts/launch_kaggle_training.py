#!/usr/bin/env python3
"""Validate or launch the private bounded Kaggle repair notebook via official SDK.

Install kagglehub and provide KAGGLE_API_TOKEN through the environment. No token
is written to notebook source, repository files, request logs, or CLI arguments.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--notebook-dir", type=Path, default=Path("notebooks/kaggle/ruh_training_repair")
    )
    parser.add_argument(
        "--launch", action="store_true", help="Create and execute the private version"
    )
    args = parser.parse_args()
    from kagglehub.clients import build_kaggle_client
    from kagglesdk.kernels.types.kernels_api_service import (
        ApiGetAcceleratorQuotaStatisticsRequest,
        ApiSaveKernelRequest,
    )

    metadata = json.loads((args.notebook_dir / "kernel-metadata.json").read_text())
    if (
        metadata["is_private"] is not True
        or metadata["machine_shape"] != "NvidiaTeslaP100"
        or metadata["session_timeout_seconds"] not in {900, 1800}
    ):
        raise ValueError("Training requires private, requested P100, and a 900/1800-second limit")
    notebook_text = (args.notebook_dir / metadata["code_file"]).read_text()
    notebook = json.loads(notebook_text)
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            compile("".join(cell["source"]), metadata["code_file"], "exec")
    client = build_kaggle_client().kernels.kernels_api_client
    quota = client.get_accelerator_quota_statistics(ApiGetAcceleratorQuotaStatisticsRequest())
    gpu = quota.gpu_quota
    if gpu is None or gpu.is_pay_to_scale_enabled:
        raise ValueError("GPU quota unavailable or paid capacity enabled; launch refused")
    remaining = (gpu.total_time_allowed - gpu.time_used - gpu.time_reserved).total_seconds()
    if remaining < metadata["session_timeout_seconds"] + 300:
        raise ValueError("Insufficient free GPU quota with a five-minute reserve")
    summary = {
        "ref": metadata["id"],
        "private": True,
        "machine_shape": metadata["machine_shape"],
        "session_timeout_seconds": metadata["session_timeout_seconds"],
        "free_gpu_seconds_remaining": remaining,
        "pay_to_scale_enabled": False,
        "training_revision": metadata["training_revision"],
    }
    if not args.launch:
        print(json.dumps(dict(summary, launched=False), indent=2))
        return
    request = ApiSaveKernelRequest()
    request.slug = metadata["id"]
    request.new_title = metadata["title"]
    request.text = notebook_text
    request.language = "python"
    request.kernel_type = "notebook"
    request.dataset_data_sources = metadata.get("dataset_sources", [])
    request.kernel_data_sources = metadata.get("kernel_sources", [])
    request.is_private = True
    request.enable_gpu = True
    request.enable_internet = True
    request.machine_shape = "NvidiaTeslaP100"
    request.session_timeout_seconds = metadata["session_timeout_seconds"]
    response = client.save_kernel(request)
    if response.error:
        raise ValueError(f"Kaggle rejected the private validation: {response.error}")
    print(
        json.dumps(
            dict(
                summary,
                launched=True,
                url=response.url,
                version=response.version_number,
                kernel_id=response.kernel_id,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
