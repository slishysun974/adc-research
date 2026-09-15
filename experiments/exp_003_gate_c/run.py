from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.platform.pipeline import process
from adc_research.platform.presets import build_gu_static_hypothesis_a


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIG = Path(__file__).with_name("config.yaml")


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def code_center(raw_code: int) -> float:
    return -1 + (raw_code + 0.5) / 2048


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    assumption_path = ROOT / experiment["assumption_set"]
    draft_path = ROOT / experiment["architecture_draft"]
    assumption = read_yaml(assumption_path)
    draft = read_yaml(draft_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_003" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    traces_dir = output_dir / "traces"
    traces_dir.mkdir(parents=True)

    default_profile = experiment["dither_validation"]["default_profile"]
    base_config = build_gu_static_hypothesis_a(
        assumption,
        dither_profile=default_profile,
    )

    actual_codes: list[int] = []
    exact_failures: list[dict] = []
    transfer_rows: list[dict] = []
    representative = set(experiment["representative_trace_codes"])
    representative_traces: list[dict] = []
    for expected in range(4096):
        value = code_center(expected)
        result = process(value, base_config, sample_index=expected)
        actual = result.reconstruction.output_code
        actual_codes.append(actual)
        if actual != expected or not result.reconstruction.correctable:
            exact_failures.append(
                {"expected": expected, "actual": actual, "correctable": result.reconstruction.correctable}
            )
        transfer_rows.append(
            {
                "sample_index": expected,
                "input_normalized": value,
                "stage1_symbol": result.stage1.quantizer.symbol,
                "stage1_residue": result.stage1.residue,
                "stage2_symbol": result.stage2.quantizer.symbol,
                "stage2_residue": result.stage2.residue,
                "backend_channel": result.backend.channel_index,
                "backend_raw_code": result.backend.raw_code,
                "output_code": actual,
                "correctable": result.reconstruction.correctable,
            }
        )
        if expected in representative:
            representative_traces.append(asdict(result))

    dither_checks = 0
    dither_failures: list[dict] = []
    for ratio in experiment["dither_validation"][
        "stage2_flash_auxiliary_gain_ratios"
    ]:
        config = build_gu_static_hypothesis_a(
            assumption,
            dither_profile=default_profile,
            stage2_flash_auxiliary_gain_ratio=ratio,
        )
        for expected in range(4096):
            value = code_center(expected)
            for pair in experiment["dither_validation"]["symbol_pairs"]:
                symbols = tuple(pair)
                result = process(
                    value,
                    config,
                    sample_index=expected,
                    dither_symbols=symbols,
                )
                dither_checks += 1
                if (
                    result.reconstruction.output_code != expected
                    or not result.reconstruction.correctable
                ):
                    dither_failures.append(
                        {
                            "ratio": ratio,
                            "expected": expected,
                            "symbols": pair,
                            "actual": result.reconstruction.output_code,
                            "correctable": result.reconstruction.correctable,
                        }
                    )

    alternative_profile = experiment["dither_validation"]["alternative_profile"]
    alternative_config = build_gu_static_hypothesis_a(
        assumption,
        dither_profile=alternative_profile,
    )
    alternative_checks = 0
    alternative_failures: list[dict] = []
    for expected in range(4096):
        value = code_center(expected)
        for pair in experiment["dither_validation"]["symbol_pairs"]:
            result = process(
                value,
                alternative_config,
                sample_index=expected,
                dither_symbols=tuple(pair),
            )
            alternative_checks += 1
            if result.reconstruction.output_code != expected:
                alternative_failures.append(
                    {"expected": expected, "symbols": pair, "actual": result.reconstruction.output_code}
                )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "assumption_set_id": assumption["assumption_set_id"],
        "code_center_checks": len(actual_codes),
        "exact_code_center_failures": len(exact_failures),
        "monotone": all(right >= left for left, right in zip(actual_codes, actual_codes[1:])),
        "missing_codes": sorted(set(range(4096)) - set(actual_codes)),
        "default_dither_checks": dither_checks,
        "default_dither_failures": len(dither_failures),
        "alternative_dither_checks": alternative_checks,
        "alternative_dither_failures": len(alternative_failures),
        "gate_c_pass": not exact_failures
        and not dither_failures
        and not alternative_failures
        and actual_codes == list(range(4096)),
    }

    with (traces_dir / "dc_transfer.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=transfer_rows[0].keys())
        writer.writeheader()
        writer.writerows(transfer_rows)
    (traces_dir / "representative_full_traces.json").write_text(
        json.dumps(representative_traces, indent=2), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (output_dir / "failures.json").write_text(
        json.dumps(
            {
                "code_center": exact_failures[:100],
                "default_dither": dither_failures[:100],
                "alternative_dither": alternative_failures[:100],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {"experiment": experiment, "architecture_draft": draft, "assumption": assumption},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        assumption_path,
        draft_path,
        ROOT / "src" / "adc_research" / "platform" / "backend_sar.py",
        ROOT / "src" / "adc_research" / "platform" / "pipeline.py",
        ROOT / "src" / "adc_research" / "platform" / "presets.py",
        ROOT / "src" / "adc_research" / "platform" / "reconstruct.py",
        ROOT / "src" / "adc_research" / "platform" / "stage.py",
    ]
    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "argv": sys.argv,
        "source_sha256": source_hash(tracked_sources),
    }
    (output_dir / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))
    print(output_dir)
    if not metrics["gate_c_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
