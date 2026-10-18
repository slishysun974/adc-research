"""Failure controls for the qualified SDF workaround's acceptance boundary."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / "rtl/gu_baseline/vivado_review"
sys.path.insert(0, str(TOOLS))
from check_carry_outputs import check_connections
from normalize_carry_outputs import normalize
from normalized_replay import check_stage, check_vectors, safe_relative
from prepare_timing_crosscheck import check_log


RAW = b"""module tb_event_carry;
wire unused;
wire [17:3] parent;
wire [3:0] co;
wire [3:0] s;
CARRY4 carry (.CO(co), .O({unused,parent[17:15]}), .CI(1'b0), .CYINIT(1'b0), .DI(4'b0), .S(s));
endmodule
"""


class NormalizedReplayChecks(unittest.TestCase):
    def test_nonzero_parent_range_preserves_bit_order(self):
        output, audit = normalize(RAW)
        result = check_connections(RAW, output, audit)
        self.assertEqual(result["bit_aliases"], 4)
        self.assertIn(b"assign parent [15] = adc_sim_carry_output_0[0];", output)

    def test_swapped_alias_rejected_even_with_updated_output_hash(self):
        output, audit = normalize(RAW)
        output = output.replace(b"parent [17] = adc_sim_carry_output_0[2]", b"parent [17] = adc_sim_carry_output_0[1]")
        audit["output_sha256"] = hashlib.sha256(output).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate bit alias|bit aliases differ"):
            check_connections(RAW, output, audit)

    def test_sink_outside_parent_declaration_rejected(self):
        raw = RAW.replace(b"parent[17:15]", b"parent[18:16]")
        output, audit = normalize(raw)
        with self.assertRaisesRegex(ValueError, "outside declaration"):
            check_connections(raw, output, audit)

    def test_unrelated_input_change_rejected(self):
        output, audit = normalize(RAW)
        output = output.replace(b".DI(4'b0)", b".DI(4'b1)")
        audit["output_sha256"] = hashlib.sha256(output).hexdigest()
        with self.assertRaisesRegex(ValueError, "untouched primitive port"):
            check_connections(RAW, output, audit)

    def test_missing_or_duplicate_alias_rejected(self):
        output, audit = normalize(RAW)
        output += b"assign parent [15] = adc_sim_carry_output_0[0];\n"
        audit["output_sha256"] = hashlib.sha256(output).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate bit alias"):
            check_connections(RAW, output, audit)

    def test_wrong_audit_cell_rejected(self):
        output, audit = normalize(RAW)
        audit["mappings"][0]["cell"] = "different_cell"
        with self.assertRaisesRegex(ValueError, "instance mapping"):
            check_connections(RAW, output, audit)

    def test_pass_with_warning_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "log"
            path.write_text("PASS\nWarning: delayed event dropped\n")
            with self.assertRaises(ValueError):
                check_log(path, "PASS", None)

    def test_negative_rejects_wrong_row_and_unrelated_fatal(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "log"
            path.write_text("Fatal: FUNCTIONAL_INTERNAL_MISMATCH row=221\n")
            check_log(path, "FUNCTIONAL_INTERNAL_MISMATCH row=221", None, "STAGED_SDF_PILOT_PASS")
            with self.assertRaises(ValueError):
                check_log(path, "FUNCTIONAL_INTERNAL_MISMATCH row=0", None, "MULTICYCLE_COST_PASS")
            path.write_text(path.read_text() + "Fatal: unrelated\n")
            with self.assertRaises(ValueError):
                check_log(path, "FUNCTIONAL_INTERNAL_MISMATCH row=221", None, "STAGED_SDF_PILOT_PASS")

    def test_missing_sdf_annotation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "timing_elaborate.log"
            path.write_text("Built simulation snapshot\n")
            with self.assertRaisesRegex(ValueError, "unconfirmed SDF"):
                check_stage(Path(folder), "elaborate")

    def test_console_warning_rejects_otherwise_clean_pilot(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            marker = "STAGED_SDF_PILOT_PASS rows=222 reset_phases=38\n"
            (path / "timing_pilot.log").write_text(marker)
            (path / "timing_pilot_console.log").write_text(marker + "Warning: bad pulse\n")
            with self.assertRaises(ValueError):
                check_stage(path, "pilot")

    def test_negative_vectors_change_only_the_declared_expected_bit(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            rows = [[0] * 19 for _ in range(8263)]
            def save(name, values):
                (path / name).write_text("\n".join(" ".join(map(str, row)) for row in values) + "\n")
            save("online.txt", rows)
            row0 = [row.copy() for row in rows]
            row0[0][6] = 1
            save("negative.txt", row0)
            row221 = [row.copy() for row in rows]
            row221[221][16] = 1
            save("row221_negative.txt", row221)
            check_vectors(path)
            row221[221][0] = 1  # altered online input, not a valid expected-bit control
            save("row221_negative.txt", row221)
            with self.assertRaisesRegex(ValueError, "single-bit negative"):
                check_vectors(path)

    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "escapes bundle"):
                safe_relative(Path(folder), "../outside")
