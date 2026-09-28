import re
from collections import Counter
from datetime import datetime, timezone

STOPWORDS = {
    "これ","それ","こと","もの","よう","ため","ところ","感じ","商品","購入","買い","思い",
    "使い","使って","使う","でき","できる","ない","なく","ある","あり","でした","ます","です",
    "とても","ちょっと","本当に","自分","今回","人","方","私","これも","それも",
    "this","that","with","have","would","could","very","really","product","buy","bought",
    "use","used","using","just","good","great","the","and","for","not","but","was","are",
}

PAIN_PATTERNS = [
    ("価格", [r"高い", r"高すぎ", r"値段", r"コスパ", r"安ければ"]),
    ("壊れやすい", [r"壊れ", r"破れ", r"割れ", r"故障", r"すぐ.*壊"]),
    ("使いにくい", [r"使いにく", r"使いづら", r"難しい", r"面倒", r"めんど"]),
    ("サイズが合わない", [r"サイズ.*合わ", r"大きすぎ", r"小さすぎ", r"サイズ.*違"]),
    ("フィットしない", [r"ズレ", r"ずれ", r"外れ", r"はずれ", r"フィット.*しない"]),
    ("効果が弱い", [r"効果.*ない", r"効かな", r"効き目", r"変わら", r"改善.*ない"]),
    ("耐久性", [r"長持ち", r"耐久", r"すぐ.*ダメ", r"劣化"]),
    ("配送", [r"届く.*遅", r"配送", r"発送", r"届かな", r"到着"]),
    ("見た目", [r"ダサ", r"見た目", r"デザイン", r"色.*違"]),
    ("手入れ", [r"洗いにく", r"掃除.*面倒", r"手入れ", r"洗濯"]),
    ("high price", [r"too expensive", r"overpriced", r"pricey", r"costs too much"]),
    ("fragile", [r"broke", r"broken", r"breaks", r"cracked", r"fell apart"]),
    ("hard to use", [r"hard to use", r"difficult to use", r"awkward", r"confusing", r"annoying"]),
    ("poor fit", [r"doesn't fit", r"does not fit", r"too big", r"too small", r"slips", r"falls off"]),
    ("weak results", [r"doesn't work", r"does not work", r"barely works", r"no effect", r"didn't work"]),
    ("durability", [r"not durable", r"wears out", r"wore out", r"stopped working"]),
    ("shipping", [r"shipping", r"delivery", r"arrived late", r"never arrived"]),
    ("appearance", [r"looks cheap", r"ugly", r"color.*different", r"not as pictured"]),
    ("maintenance", [r"hard to clean", r"cleaning", r"hard to wash", r"difficult to wash"]),
]

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

def _extract_terms(texts: list[str], limit: int = 30):
    words = Counter()
    for text in texts:
        for token in re.findall(r"[一-龯ぁ-んァ-ヶー]{2,12}|[a-z][a-z'-]{2,24}", text):
            if token not in STOPWORDS:
                words[token] += 1
    return [{"term": t, "count": c} for t, c in words.most_common(limit)]

def analyze_comments(comments: list[str], source: str | None = None, locale: str | None = None) -> dict:
    cleaned = [_normalize(x) for x in comments if isinstance(x, str) and x.strip()]
    pain_counts = Counter()
    evidence = {}
    for text in cleaned:
        for label, patterns in PAIN_PATTERNS:
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                pain_counts[label] += 1
                evidence.setdefault(label, []).append(text)

    pains = [
        {
            "pain": label,
            "pain_point": label,
            "count": count,
            "share_percent": round(count / len(cleaned) * 100, 1),
            "examples": evidence.get(label, [])[:3],
        }
        for label, count in pain_counts.most_common()
    ]
    terms = _extract_terms(cleaned)
    angle = pains[0]["pain"] if pains else (terms[0]["term"] if terms else None)
    opportunity = None
    if pains:
        top = pains[0]
        opportunity = {
            "problem": top["pain"],
            "evidence_count": top["count"],
            "evidence_share_percent": top["share_percent"],
            "product_direction": f"Reduce or eliminate {top['pain']}" if locale == "en-US" else f"「{top['pain']}」を減らす・解消する商品設計",
            "validation": "Check whether the complaint is repeated across independent sources before sourcing or branding.",
        }
    return {
        "source": source,
        "locale": locale,
        "comments_analyzed": len(cleaned),
        "pain_points": pains,
        "top_terms": terms,
        "recommended_angle": angle,
        "market_opportunity": opportunity,
        "ad_copy_candidates": [
            f"「{angle}」で困っていませんか？" if locale != "en-US" else f"Still struggling with {angle}?",
            f"その「{angle}」を、もっとラクに。" if locale != "en-US" else f"A simpler way to solve {angle}.",
        ] if angle else [],
        "next_action": "validate the top pain against raw comments, then test the matching product/creative angle",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "rule-based multilingual pain-point extraction; validate against raw customer language before advertising",
    }
