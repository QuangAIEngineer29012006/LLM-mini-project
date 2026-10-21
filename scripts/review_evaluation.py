"""Offline rubric review. Uses saved evidence; never calls an LLM or changes test results."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = {
    "intent": ["Sai ý định", "Một phần hoặc mơ hồ", "Đúng ý định mong đợi"],
    "extraction": ["Bịa hoặc sai thông tin chính", "Có lỗi nhỏ", "Đúng dữ liệu có bằng chứng"],
    "validation": ["Không parse hoặc bypass validation", "Parse nhưng vi phạm rule", "Đúng schema và business rules"],
    "routing": ["Hành động sai hoặc không an toàn", "Có cảnh báo nhưng route chưa rõ", "Draft, hỏi lại hoặc handoff đúng"],
    "response": ["Sai hoặc không hữu ích", "Đúng nhưng chưa rõ", "Chính xác, rõ và chỉ dẫn bước tiếp theo"],
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def relative(path):
    return str(Path(path).resolve().relative_to(ROOT.resolve())).replace("\\", "/")


def source_path(value):
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError("Source must remain inside repository")
    return path


def build(reports, case_files):
    expected = {}
    for path in case_files:
        for case in read_json(path):
            if case["id"] in expected:
                raise ValueError("Duplicate expected case: " + case["id"])
            expected[case["id"]] = (case, relative(path))
    records, seen = [], set()
    for path in reports:
        report = read_json(path)
        metadata = {k: report.get(k) for k in ("timestamp_utc", "provider", "model_id", "prompt_version", "temperature")}
        for result in report["cases"]:
            cid = result["id"]
            if cid in seen or cid not in expected:
                raise ValueError("Duplicate or unknown observed case: " + cid)
            seen.add(cid)
            case, case_path = expected[cid]
            evidence = {"expected": case, "observed": result, "run": metadata}
            records.append({"id": cid, "source_report": relative(path), "source_cases": case_path,
                            "evidence": evidence, "evidence_sha256": digest(evidence),
                            "human_review": {"scores": {k: None for k in CRITERIA},
                                             "reasons": {k: "" for k in CRITERIA}}})
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "notice": "Automatic scores are historical proxies. Human scores start blank; null means not reviewed, not zero.",
            "human_reviewer": "", "reviewed_at": "", "rubric": CRITERIA,
            "sources": {relative(p): digest(read_json(p)) for p in list(reports) + list(case_files)},
            "cases": records}


def source_evidence(record):
    report = read_json(source_path(record["source_report"]))
    cases = read_json(source_path(record["source_cases"]))
    actual = next(c for c in report["cases"] if c["id"] == record["id"])
    expected = next(c for c in cases if c["id"] == record["id"])
    metadata = {k: report.get(k) for k in ("timestamp_utc", "provider", "model_id", "prompt_version", "temperature")}
    return {"expected": expected, "observed": actual, "run": metadata}


def validate(package, complete=False):
    if package.get("schema_version") != 1 or not package.get("cases"):
        raise ValueError("Unsupported or empty review package")
    expected_ids = set()
    for path, checksum in package["sources"].items():
        source = read_json(source_path(path))
        if digest(source) != checksum:
            raise ValueError("Source changed: " + path)
        if isinstance(source, dict) and "cases" in source:
            expected_ids.update(case["id"] for case in source["cases"])
    if {case["id"] for case in package["cases"]} != expected_ids:
        raise ValueError("Review must cover every observed case in source reports")
    seen, filled = set(), 0
    for record in package["cases"]:
        if record["id"] in seen:
            raise ValueError("Duplicate case: " + record["id"])
        seen.add(record["id"])
        if digest(record["evidence"]) != record["evidence_sha256"] or digest(source_evidence(record)) != record["evidence_sha256"]:
            raise ValueError("Evidence changed: " + record["id"])
        review = record["human_review"]
        if set(review["scores"]) != set(CRITERIA) or set(review["reasons"]) != set(CRITERIA):
            raise ValueError("Wrong rubric fields: " + record["id"])
        for key in CRITERIA:
            score, reason = review["scores"][key], review["reasons"][key]
            if score is not None and (type(score) is not int or score not in (0, 1, 2)):
                raise ValueError("Score must be integer 0/1/2 or null: " + record["id"])
            if not isinstance(reason, str) or (score is not None and len(reason.strip()) < 10):
                raise ValueError("Explain every assigned score: " + record["id"])
            if complete and score is None:
                raise ValueError("Unreviewed criterion: " + record["id"] + "/" + key)
            filled += score is not None
    if filled:
        if not package.get("human_reviewer", "").strip() or not package.get("reviewed_at", "").strip():
            raise ValueError("Reviewer and review timestamp are required")
        datetime.fromisoformat(package["reviewed_at"].replace("Z", "+00:00"))
    return filled


def markdown(package):
    validate(package)
    rows = ["# Chấm rubric của nhóm", "", "Người chấm: " + (package["human_reviewer"] or "Chưa xác nhận"),
            "", "Dấu — là chưa chấm; không phải 0. Chỉ tổng hợp điểm của case được chấm đủ 5 tiêu chí.", "",
            "| Case | Intent | Extraction | Validation | Routing | Response | Tổng /10 |", "|---|---:|---:|---:|---:|---:|---:|"]
    totals = []
    for record in package["cases"]:
        scores = [record["human_review"]["scores"][k] for k in CRITERIA]
        done = all(s is not None for s in scores)
        total = sum(scores) if done else None
        if done:
            totals.append(total)
        rows.append("| " + " | ".join([record["id"]] + [str(s) if s is not None else "—" for s in scores] + [str(total) if done else "—"]) + " |")
    rows += ["", f"Đã chấm đủ: {len(totals)}/{len(package['cases'])} case."]
    if totals:
        rows += [f"Điểm trung bình của các case đã chấm: {sum(totals)/len(totals):.2f}/10. Không phải accuracy của model."]
    for record in package["cases"]:
        rows += ["", "## " + record["id"]]
        rows += [f"- {key}: {record['human_review']['reasons'][key] or 'Chưa nhận xét'}" for key in CRITERIA]
    return "\n".join(rows) + "\n"


def review_html(package):
    # Escape script terminators even when future test inputs contain HTML/injection text.
    data = json.dumps(package, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return '''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Chấm rubric dự án</title><style>body{font:16px system-ui;max-width:1050px;margin:24px auto;padding:0 16px}article{border-top:2px solid #ddd;margin:28px 0;padding:12px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:12px}textarea{width:95%;min-height:65px}label{display:block;margin:14px 0}button,input,select{font:inherit;padding:8px}header{position:sticky;top:0;background:white;padding:12px 0;border-bottom:1px solid #ddd}small{display:block;color:#555}</style>
<h1>Chấm rubric 0 1 2</h1><p>Chấm theo evidence từng lượt, không sao chép máy móc điểm tự động. Dữ liệu đã ẩn danh có thể không đủ kiểm tra nguyên văn giao nhận; xem trực tiếp phiên demo hoặc ghi rõ giới hạn. Case lỗi chèn đánh giá đường xử lý lỗi, không chứng minh chất lượng model.</p>
<header><label>Người chấm <input id="reviewer" placeholder="Tên người chấm"></label><button id="save">Tải bản chấm JSON</button> <label>Nạp bản chấm đã lưu <input type="file" id="load" accept=".json"></label><span id="progress"></span></header><main id="cases"></main>
<script id="evidence" type="application/json">''' + data + '''</script><script>
let pack=JSON.parse(document.getElementById('evidence').textContent);
const keys=Object.keys(pack.rubric), root=document.getElementById('cases');
function el(tag,text,parent){let e=document.createElement(tag);if(text!==null)e.textContent=text;if(parent)parent.appendChild(e);return e}
function progress(){let n=pack.cases.reduce((n,c)=>n+keys.filter(k=>c.human_review.scores[k]!==null).length,0);document.getElementById('progress').textContent=`Đã nhập ${n}/${pack.cases.length*5} tiêu chí. Lưu JSON trước khi đóng trang.`}
function render(){root.replaceChildren();document.getElementById('reviewer').value=pack.human_reviewer;
for(const c of pack.cases){let a=el('article',null,root);el('h2',c.id+' · '+c.evidence.observed.actual_route,a);
el('pre',JSON.stringify(c.evidence.expected,null,2),a);let d=el('details',null,a);el('summary','Xem output, các lượt hội thoại và metadata gốc',d);el('pre',JSON.stringify(c.evidence.observed,null,2),d);
for(const k of keys){let l=el('label',k,a),s=el('select',null,l);s.setAttribute('aria-label',c.id+' '+k+' score');for(const [v,t] of [['','Chưa chấm'],['0','0'],['1','1'],['2','2']]){let o=el('option',t,s);o.value=v}s.value=c.human_review.scores[k]??'';el('small',pack.rubric[k].map((t,i)=>i+': '+t).join(' | '),l);let note=el('textarea',null,l);note.setAttribute('aria-label',c.id+' '+k+' reason');note.value=c.human_review.reasons[k];s.onchange=()=>{c.human_review.scores[k]=s.value===''?null:Number(s.value);progress()};note.oninput=()=>c.human_review.reasons[k]=note.value}}
progress()}
document.getElementById('save').onclick=()=>{pack.human_reviewer=document.getElementById('reviewer').value.trim();if(!pack.human_reviewer){alert('Nhập tên người chấm.');return}pack.reviewed_at=new Date().toISOString();let a=el('a',null,document.body);let u=URL.createObjectURL(new Blob([JSON.stringify(pack,null,2)],{type:'application/json'}));a.href=u;a.download='rubric_review.completed.json';a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1000)};
document.getElementById('load').onchange=async e=>{try{let next=JSON.parse(await e.target.files[0].text());if(next.cases.length!==pack.cases.length||next.cases.some((c,i)=>c.id!==pack.cases[i].id||JSON.stringify(c.evidence)!==JSON.stringify(pack.cases[i].evidence)||c.evidence_sha256!==pack.cases[i].evidence_sha256))throw Error('Không khớp evidence');pack=next;render()}catch(err){alert('Không nạp được: '+err.message)}};
render();</script></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    prep = subs.add_parser("prepare")
    prep.add_argument("--report", action="append", type=Path, required=True)
    prep.add_argument("--cases", action="append", type=Path, required=True)
    prep.add_argument("--output", type=Path, default=ROOT / "sample_results/rubric_review")
    check = subs.add_parser("validate")
    check.add_argument("file", type=Path)
    check.add_argument("--complete", action="store_true")
    render = subs.add_parser("render")
    render.add_argument("file", type=Path)
    render.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            package = build(args.report, args.cases)
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "review.json").write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            (args.output / "review.html").write_text(review_html(package), encoding="utf-8")
            (args.output / "review.md").write_text(markdown(package), encoding="utf-8")
            print(f"Prepared {len(package['cases'])} cases; human scores are blank: {args.output}")
        else:
            package = read_json(args.file)
            count = validate(package, complete=getattr(args, "complete", False))
            if args.command == "render":
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(markdown(package), encoding="utf-8")
            print(f"Valid evidence and scores; {count}/{len(package['cases'])*5} human criteria entered")
    except (ValueError, KeyError, StopIteration, OSError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
