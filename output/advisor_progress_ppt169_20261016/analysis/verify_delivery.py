"""Presentation-only checks: text extents and value-to-geometry mapping."""
from pathlib import Path
import json
import xml.etree.ElementTree as ET
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
NS = {"s": "http://www.w3.org/2000/svg"}
report = {"slides": [], "charts": [], "errors": []}

def walk_text(node, inherited):
    attrs = dict(inherited)
    attrs.update(node.attrib)
    if node.tag.endswith("}text"):
        yield node, attrs
    for child in node:
        yield from walk_text(child, attrs)

for path in sorted((ROOT / "svg_output").glob("*.svg")):
    root = ET.parse(path).getroot()
    ids = [n.attrib["id"] for n in root.iter() if "id" in n.attrib]
    assert len(ids) == len(set(ids)), path.name
    count = 0
    for node, attrs in walk_text(root, {}):
        text = "".join(node.itertext())
        size = float(attrs.get("font-size", 24))
        face = "msyhbd.ttc" if attrs.get("font-weight") in {"700", "bold"} else "msyh.ttc"
        font = ImageFont.truetype("C:/Windows/Fonts/" + face, round(size))
        width = font.getlength(text)
        x, y = float(attrs.get("x", 0)), float(attrs.get("y", 0))
        anchor = attrs.get("text-anchor", "start")
        left = x - width if anchor == "end" else x - width / 2 if anchor == "middle" else x
        bbox = font.getbbox(text, anchor="ls")
        if left < 28 or left + width > 1252 or y + bbox[1] < 10 or y + bbox[3] > 708:
            report["errors"].append({"slide": path.name, "text": text, "left": left, "right": left+width, "baseline": y})
        count += 1
    report["slides"].append({"slide": path.name, "text_lines": count})

def svg_node(file, name):
    return ET.parse(ROOT / "svg_output" / file).getroot().find(f".//*[@id='{name}']")

def close(file, name, attr, expected):
    got = float(svg_node(file, name).attrib[attr])
    delta = abs(got - expected)
    report["charts"].append({"slide":file,"element":name,"attribute":attr,"expected":expected,"actual":got,"error_px":delta})
    if delta > 0.011:
        report["errors"].append({"slide":file,"element":name,"attribute":attr,"delta":delta})

for name, value in [("bar-correlation",0.92068),("bar-mae",0.65701)]:
    close("11_objective_gap.svg",name,"height",value/1.2*270)
    close("11_objective_gap.svg",name,"y",545-value/1.2*270)

for name, value in [("bar-linear-held",15.827),("bar-linear-base",33.945),("bar-linear-quarter",9.288),("bar-smooth-held",32.176),("bar-smooth-base",34.406),("bar-smooth-quarter",10.166)]:
    close("16_learning_rate.svg",name,"height",value/40*300)
    close("16_learning_rate.svg",name,"y",550-value/40*300)

rows = json.loads((ROOT/"sources"/"exp075_presentation_values.json").read_text(encoding="utf-8"))["rows"]
assert len(rows) == 20
assert all(r["mse"]["full"] < r["mse"]["point"] for r in rows)
assert sum(r["mse"]["full"] > r["mse"]["held"] for r in rows) == 6
for i, row in enumerate(rows, 1):
    close("19_sampling_effect.svg",f"case{i:02}","cx",85+row["mse"]["point"]/60*520)
    close("19_sampling_effect.svg",f"case{i:02}","cy",570-row["mse"]["full"]/60*350)

for name, value in [("bar-full",3.333927623),("bar-mean",3.059911930),("bar-initial",3.445446290),("bar-held",3.194836766),("bar-witness",1.920095347)]:
    close("21_gate_case.svg",name,"width",value/4*540)

assert len(report["slides"]) == 28
report["scope"] = "Saved presentation values, pixel geometry, and text extents only. No ADC computation or new scientific scoring."
report["passed"] = not report["errors"]
(ROOT/"analysis"/"presentation_checks.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"passed":report["passed"],"slides":len(report["slides"]),"geometry_checks":len(report["charts"]),"errors":report["errors"]},ensure_ascii=False,indent=2))
raise SystemExit(0 if report["passed"] else 1)
