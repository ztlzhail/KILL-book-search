# csv_to_books_json.py
import csv, json, re
from pathlib import Path

BASE = Path(__file__).resolve().parent
IN  = BASE / "books_with_tags.csv"
OUT = BASE / "books.json"

def split_tags(v):
    if not v: return []
    if isinstance(v, list): return v
    return [t.strip() for t in re.split(r"[,\|/]", v) if t.strip()]

def pick(*keys):
    for k in keys:
        if k and str(k).strip():
            return str(k).strip()
    return ""

rows=[]
with open(IN, newline="", encoding="utf-8-sig") as f:
    rdr = csv.DictReader(f)
    for r in rdr:
        title = pick(r.get("title"), r.get("제목"))
        author = pick(r.get("author"), r.get("저자"))
        publisher = pick(r.get("publisher"), r.get("출판사"))
        year = pick(r.get("year"), r.get("출판년도"))
        pages = pick(r.get("pages"), r.get("분량"))
        # 소개/설명 컬럼 자동 탐색
        desc = pick(r.get("description"), r.get("소개"), r.get("설명"), r.get("요약"), r.get("줄거리"))
        tags = split_tags(r.get("tags") or r.get("태그"))

        rows.append({
            "title": title, "author": author, "publisher": publisher,
            "year": year, "pages": pages, "tags": tags,
            "description": desc
        })

OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"완료: {len(rows)}권 -> {OUT.name}")
