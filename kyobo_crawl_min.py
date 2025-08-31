# kyobo_crawl_min.py
# 교보문고 검색 URL 3개에서 각 10권 추출 → demo_books.json
# 태그: [분야, 가격대, 평점대]

import re, time, json, random
import requests
from bs4 import BeautifulSoup

# ── 설정 ───────────────────────────────────────────────────────────────
SEARCH_URLS = {
    "과학":   "https://search.kyobobook.co.kr/search?keyword=%EA%B3%BC%ED%95%99&gbCode=TOT&target=total",
    "인문사회":"https://search.kyobobook.co.kr/search?keyword=%EC%9D%B8%EB%AC%B8%EC%82%AC%ED%9A%8C&gbCode=TOT&target=total",
    "문학":   "https://search.kyobobook.co.kr/search?keyword=%EB%AC%B8%ED%95%99&gbCode=TOT&target=total",
}
PER_KEYWORD = 10
LIST_DELAY   = 1.2   # 목록 요청 간격(초)
DETAIL_DELAY = 0.8   # 상세 요청 간격(초) – 평점/가격이 목록에 없을 때만 접속
OUT_FILE = "demo_books.json"

# ── 공용 유틸 ────────────────────────────────────────────────────────────
def session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
        "Referer": "https://search.kyobobook.co.kr/",
        "Connection": "keep-alive",
    })
    return s

def soup_from(s: requests.Session, url: str) -> BeautifulSoup:
    r = s.get(url, timeout=15)
    r.raise_for_status()
    return BeautifulSoup(r.text, "lxml")

def pick(el):  # 텍스트 안전 추출
    return el.get_text(" ", strip=True) if el else ""

def to_int_price(txt: str):
    if not txt: return None
    m = re.search(r"(\d[\d,]{3,})\s*원", txt)
    if not m: m = re.search(r"(\d[\d,]{3,})", txt)
    return int(m.group(1).replace(",", "")) if m else None

def to_float_rating(txt: str):
    if not txt: return None
    # '평점 9.6', '별점 4.7', '4.5점' 등
    m = re.search(r"(?:별점|평점)?\s*([0-9]+(?:\.[0-9]+)?)\s*점?", txt)
    if not m: return None
    val = float(m.group(1))
    # 교보가 10점 만점으로 표기하면 5점 환산
    if val > 5: val = round(val/2, 2)
    return val

def bucket_price(p):
    if p is None: return "가격 미상"
    if p < 10000: return "~1만원"
    if p < 20000: return "1~2만원"
    return "2만원 이상"

def bucket_rating(r):
    if r is None: return "★정보 없음"
    if r < 3:     return "★0~3"
    if r < 4:     return "★3~4"
    if r < 4.5:   return "★4~4.5"
    return "★4.5~5"

# ── 파싱 로직 ───────────────────────────────────────────────────────────
def parse_list_items(s: requests.Session, url: str):
    """검색 결과 1페이지 파싱. li.prod_item 카드 기준 + 폴백."""
    soup = soup_from(s, url)
    items = []

    for box in soup.select("li.prod_item"):
        a = box.select_one("a[href*='/product/detail']") or box.select_one("a.prod_info")
        title = pick(a)
        href  = a["href"] if (a and a.has_attr("href")) else ""
        if href.startswith("/"):
            href = "https://product.kyobobook.co.kr" + href

        author = pick(box.select_one(".author")) or pick(box.select_one(".prod_author"))
        pub    = pick(box.select_one(".publisher")) or pick(box.select_one(".prod_publisher"))

        # 목록에서 가격/평점 힌트가 있으면 먼저 시도
        price_txt  = pick(box.select_one(".price")) or pick(box.select_one(".sell_price")) or pick(box.select_one(".price_info"))
        rating_txt = pick(box.select_one("[class*='rating']")) or pick(box.select_one(".review")) or pick(box.select_one(".star"))

        items.append({
            "title": title, "author": author, "publisher": pub, "detail": href,
            "price_txt": price_txt, "rating_txt": rating_txt
        })

    # 폴백(어떤 레이아웃에서도 제목/링크는 잡히게)
    if not items:
        for a in soup.select("a[href*='/product/detail']"):
            t = pick(a); h = a.get("href","")
            if t and h:
                if h.startswith("/"): h = "https://product.kyobobook.co.kr" + h
                items.append({"title": t, "author":"", "publisher":"", "detail": h,
                              "price_txt":"", "rating_txt":""})
    return [it for it in items if it["title"]]

def parse_detail_for_price_rating(s: requests.Session, url: str):
    """목록에서 못 찾았을 때 상세에서 보충."""
    try:
        r = s.get(url, timeout=15, headers={"Referer":"https://product.kyobobook.co.kr/"})
        r.raise_for_status()
        html = r.text
    except Exception:
        return None, None

    # 빠른 정규식 스캔
    price = to_int_price(html)
    rating = to_float_rating(html)

    # 그래도 없으면 DOM에서 한 번 더 시도
    if price is None or rating is None:
        sp = BeautifulSoup(html, "lxml")
        if price is None:
            price = to_int_price(sp.get_text(" ", strip=True))
        if rating is None:
            rating = to_float_rating(sp.get_text(" ", strip=True))
    return price, rating

def crawl_keyword(s: requests.Session, label: str, url: str, want: int):
    out = []
    page = 1
    while len(out) < want and page <= 3:  # 1~3페이지만 훑자(10권이면 보통 1페이지만으로 충분)
        page_url = f"{url}&page={page}"
        print(f"[{label}] {page_url}")
        try:
            items = parse_list_items(s, page_url)
        except Exception as e:
            print("→ 목록 파싱 실패:", e)
            break

        for it in items:
            if len(out) >= want: break
            # 목록에서 1차 파싱
            price  = to_int_price(it["price_txt"])
            rating = to_float_rating(it["rating_txt"])

            # 없으면 상세에서 보충(절반만 시도해도 충분)
            if (price is None or rating is None) and random.random() < 0.7 and it["detail"]:
                p2, r2 = parse_detail_for_price_rating(s, it["detail"])
                price  = price  if price  is not None else p2
                rating = rating if rating is not None else r2
                time.sleep(DETAIL_DELAY)

            tags = [label, bucket_price(price), bucket_rating(rating)]

            out.append({
                "title": it["title"],
                "author": it["author"],
                "publisher": it["publisher"],
                "price": price,
                "rating": rating,
                "tags": tags,
                "source": "KYBO search",
                "link": it["detail"]
            })
        page += 1
        time.sleep(LIST_DELAY)
    print(f"→ {label} {len(out)}권")
    return out

# ── 실행 ────────────────────────────────────────────────────────────────
def main():
    s = session()
    all_books = []
    for label, url in SEARCH_URLS.items():
        all_books.extend(crawl_keyword(s, label, url, PER_KEYWORD))
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)
    print(f"완료: {len(all_books)}권 → {OUT_FILE} 저장")

if __name__ == "__main__":
    main()
