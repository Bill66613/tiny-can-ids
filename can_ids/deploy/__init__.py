"""Deployment utilities: C/C++ model export for embedded targets."""

from .c_export import (
    export_weights_to_c_header,
    generate_inference_c_code,
    export_lr_to_c_header,
    generate_lr_inference_c_code,
    export_dt_to_c_header,
    generate_dt_inference_c_code,
    export_model_to_c,
    export_dos_model_to_c,
    export_rpm_model_to_c,
)

__all__ = [
    "export_weights_to_c_header",
    "generate_inference_c_code",
    "export_lr_to_c_header",
    "generate_lr_inference_c_code",
    "export_dt_to_c_header",
    "generate_dt_inference_c_code",
    "export_model_to_c",
    "export_dos_model_to_c",
    "export_rpm_model_to_c",
]
