"""ONNX / int8 export scaffold — beta/unverified, pure stdlib.

Study #9 (ruh-usecase-deep-20260929): the 28M edge story (ONNX → int8 ≈
~30MB artifact — size estimate, unverified). This module defines the export
API shape; torch/onnx/onnxruntime are OPTIONAL and imported lazily inside
the functions, so the module stays importable (and testable) without them.

Skip contract: when torch/onnx are absent, ``export_onnx`` and
``quantize_int8`` return ``ExportResult(status="skipped", ...)`` with a clear
message — never a silent no-op, never an ImportError leak.

Calibration-parity hook: int8 quantization MAY regress Mizan calibration
(``L_calibration``) — which is Ruh's selling point. ``parity_report`` is a
stub that documents the mandatory measurement gate; shipping an int8
artifact without running parity is a product bug, not a shortcut.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "ExportResult",
    "ExportDependencyMissing",
    "export_onnx",
    "quantize_int8",
    "parity_report",
]

PARITY_GATE_MESSAGE = (
    "int8 quantization may regress Mizan calibration (L_calibration) — Ruh's "
    "selling point. Measuring fp32-vs-int8 parity (accuracy delta, ECE delta, "
    "hisbah-violation delta) is MANDATORY before shipping any int8 artifact."
)


@dataclass
class ExportResult:
    """Outcome of an export/quantize step."""

    status: str  # "ok" | "skipped" | "failed"
    message: str
    path: str | None = None
    details: dict = field(default_factory=dict)


class ExportDependencyMissing(RuntimeError):
    """Raised when torch/onnx/onnxruntime are needed but not installed."""


def _require(module_name: str, install_hint: str):
    """Import an optional dependency or raise a clear, actionable error."""
    try:
        return __import__(module_name)
    except ImportError as exc:
        raise ExportDependencyMissing(
            f"Cannot proceed: '{module_name}' is not installed. {install_hint}"
        ) from exc


def export_onnx(model, path: str, *, opset_version: int = 17, dummy_input=None) -> ExportResult:
    """Export a torch model to ONNX.

    Skip contract: torch/onnx absent → ``status="skipped"`` with a clear
    message. ``dummy_input`` is required for the actual export (the scaffold
    does not guess input shapes).
    """
    try:
        torch = _require("torch", "Install torch to enable ONNX export.")
        _require("onnx", "Install onnx to enable ONNX export.")
    except ExportDependencyMissing as exc:
        return ExportResult(status="skipped", message=str(exc), path=path)

    if dummy_input is None:
        return ExportResult(
            status="failed",
            message="dummy_input is required — the scaffold does not guess input shapes.",
            path=path,
        )
    try:
        model.eval()
        torch.onnx.export(
            model,
            dummy_input,
            path,
            opset_version=opset_version,
            input_names=["input"],
            output_names=["output"],
            dynamo=False,
        )
    except Exception as exc:  # surface any export failure honestly
        return ExportResult(status="failed", message=f"ONNX export failed: {exc}", path=path)
    return ExportResult(
        status="ok",
        message=f"Exported ONNX to {path}",
        path=path,
        details={"opset_version": opset_version},
    )


def quantize_int8(onnx_path: str, *, calibration_data=None) -> ExportResult:
    """Quantize an ONNX model to int8 (dynamic quantization).

    Skip contract: onnx/onnxruntime absent → ``status="skipped"`` with a
    clear message. WARNING: int8 may regress calibration — run
    ``parity_report`` before shipping (see PARITY_GATE_MESSAGE).
    """
    try:
        ort_quant = _require(
            "onnxruntime.quantization",
            "Install onnxruntime to enable int8 quantization.",
        )
        _require("onnx", "Install onnx to enable int8 quantization.")
    except ExportDependencyMissing as exc:
        return ExportResult(status="skipped", message=str(exc), path=onnx_path)

    out_path = onnx_path.replace(".onnx", ".int8.onnx")
    try:
        # Dynamic quantization: no calibration data needed for the scaffold
        # path; static quantization with calibration_data is the follow-up.
        ort_quant.quantize_dynamic(onnx_path, out_path, weight_type=ort_quant.QuantType.QInt8)
    except Exception as exc:  # surface any quantization failure honestly
        return ExportResult(
            status="failed", message=f"int8 quantization failed: {exc}", path=onnx_path
        )
    return ExportResult(
        status="ok",
        message=f"Quantized to int8: {out_path}. {PARITY_GATE_MESSAGE}",
        path=out_path,
        details={
            "parity_gate": PARITY_GATE_MESSAGE,
            "calibration_data_provided": calibration_data is not None,
        },
    )


def parity_report(
    fp32_path: str | None = None, int8_path: str | None = None, *, eval_fn=None
) -> dict:
    """STUB — fp32 vs int8 calibration-parity check.

    Not yet implemented: needs the eval harness + domain eval data.
    The gate is documented here so no int8 artifact ships unmeasured.
    """
    return {
        "status": "not-implemented",
        "gate": PARITY_GATE_MESSAGE,
        "required_metrics": ["accuracy_delta", "ECE_delta", "hisbah_violation_delta"],
        "fp32_path": fp32_path,
        "int8_path": int8_path,
        "eval_fn_provided": eval_fn is not None,
    }
