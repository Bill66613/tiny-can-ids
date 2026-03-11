"""Deployment utilities: C/C++ model export for embedded targets."""

from .c_export import export_weights_to_c_header, generate_inference_c_code

__all__ = ["export_weights_to_c_header", "generate_inference_c_code"]
