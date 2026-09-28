import re
from collections import Counter
from datetime import datetime, timezone

STOPWORDS = {
    "これ","それ","こと","もの","よう","ため","ところ","感じ","商品","購入","買い","思い",
    "使い","使って","使う","でき","できる","ない","なく","ある","あり","でした","ます","です",
    "とても","ちょっと","本当に","自分","今回","人","方","私","これも","それも"
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
]

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())

def _extract_terms(texts: list[str], limit: int = 30):
    words = Counter()
    for text in texts:
        for token in re.findall(r"[一-龯ぁ-んァ-ヶー]{2,12}", text):
            if token not in STOPWORDS:
                words[token] += 1
    return [{"term": t, "count": c} for t, c in words.most_common(limit)]

def analyze_comments(comments: list[str], source: str | None = None) -> dict:
    cleaned = [_normalize(x) for x in comments if isinstance(x, str) and x.strip()]
    pain_counts = Counter()
    evidence = {}
    for text in cleaned:
        for label, patterns in PAIN_PATTERNS:
            if any(re.search(p, text, re.IGNORECASE) for p in patterns):
                pain_counts[label] += 1
                evidence.setdefault(label, []).append(text)
    pains = [
        {"pain_point": label, "count": count, "share_percent": round(count / len(cleaned) * 100, 1),
         "examples": evidence.get(label, [])[:3]}
        for label, count in pain_counts.most_common()
    ]
    terms = _extract_terms(cleaned)
    angle = pains[0]["pain_point"] if pains else (terms[0]["term"] if terms else None)
    return {
        "source": source,
        "comments_analyzed": len(cleaned),
        "pain_points": pains,
        "top_terms": terms,
        "recommended_angle": angle,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "rule-based Japanese pain-point extraction; validate against raw customer language before advertising"
    }
