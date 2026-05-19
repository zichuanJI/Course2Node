from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

from app.config import settings

EN_STOPWORDS = {
    "the", "and", "for", "that", "with", "this", "from", "into", "your", "have",
    "will", "then", "than", "when", "what", "where", "which", "while", "about",
    "their", "there", "them", "they", "been", "being", "also", "such", "using",
    "used", "into", "between", "through", "because", "each", "some", "more",
    "most", "other", "many", "much", "very", "just", "only", "over", "under",
}

ZH_STOPWORDS = {
    # 基础代词与连词
    "我们", "你们", "他们", "这个", "那个", "一种", "以及", "如果", "因为", "所以", "然后",
    "就是", "可以", "需要", "进行", "通过", "一个", "一些", "没有", "不是", "这种", "那个",
    "什么", "怎么", "这里", "那里", "已经", "对于", "关于", "而且", "并且", "或者", "还是",
    "只有", "只要", "虽然", "但是", "不仅", "作为", "为了", "这些", "那些", "自己",
    # 领域/课程常见高频无意义词
    "课程", "内容", "知识", "问题", "分析", "研究", "主要", "对象", "方法", "探讨",
    "介绍", "理解", "掌握", "应用", "基础", "重点", "难点", "部分", "方面", "过程",
    "特征", "特点", "情况", "影响", "作用", "意义", "目的", "使用", "产生", "发现",
}

# ── Concept-level junk filter ────────────────────────────────────────────────
# Terms that frequently appear as high-importance "concepts" but are actually
# PDF structural elements, LaTeX command fragments, filename remnants, etc.

CONCEPT_STOPWORDS = {
    # PDF structural elements
    "footer", "header", "footnote", "endnote", "page", "pages",
    "title", "subtitle", "caption", "figure", "fig", "table",
    "appendix", "reference", "references", "bibliography",
    "contents", "index", "acknowledgement", "abstract",
    # LaTeX commands and fragments
    "frac", "mathbf", "mathrm", "mathit", "mathcal", "mathbb",
    "textbf", "textit", "textrm", "texttt", "emph",
    "left", "right", "ight", "big", "bigg",
    "brace", "overbrace", "underbrace",
    "sqrt", "sum", "prod", "int", "lim", "inf", "sup",
    "overrightarrow", "overline", "underline",
    "begin", "end", "item", "label", "ref", "cite",
    "alpha", "beta", "gamma", "delta", "epsilon", "theta",
    "lambda", "sigma", "omega", "phi", "psi", "mu", "pi",
    "vert", "imes", "cdot", "ldots", "cdots", "dots",
    "hspace", "vspace", "quad", "qquad",
    "centering", "raggedright", "raggedleft",
    "newline", "newpage", "clearpage",
    # Generic English words too vague to be concepts
    "data", "example", "examples", "case", "cases", "note", "notes",
    "section", "chapter", "part", "unit", "lesson",
    "student", "students", "teacher", "class", "classes",
    "result", "results", "answer", "solution", "solutions",
    "type", "types", "kind", "kinds", "form", "forms",
    "way", "ways", "step", "steps", "method", "methods",
    "value", "values", "number", "numbers", "name", "names",
    "input", "output", "process", "system", "systems",
    "internal", "external", "instance", "instances",
    "database", "record", "records", "field", "fields",
    "file", "files", "program", "programs",
    "level", "levels", "group", "groups", "set", "sets",
    "model", "function", "structure", "structures",
    "object", "objects", "element", "elements",
    "operation", "operations", "condition", "conditions",
    "problem", "problems", "task", "tasks",
    "point", "points", "line", "lines",
    "list", "node", "link", "path",
    "key", "keys", "entry", "entries",
    "property", "properties", "feature", "features",
    "rule", "rules", "pattern", "patterns",
    # Generic abbreviations that are not real concepts without context
    "os", "io", "cpu", "ram", "api", "url", "xml", "html", "css", "http",
    # Chinese generic
    "数据", "例子", "例题", "样例", "学生", "老师", "教师",
    "图片", "图表", "表格", "章节", "习题", "作业",
    "定义一", "定义二", "定义三",
    "数据一", "数据二", "数据三",
    "基本概念", "四个基本概念",
    # Chinese example/instance data fragments
    "人员", "系统", "一个系统", "某系统",
    "文件", "一个文件", "某文件",
    "程序", "一个程序", "某程序",
    "操作", "一个操作", "某操作",
    "功能", "一个功能", "某功能",
    "用户", "一个用户", "某用户",
    "结果", "一个结果", "某结果",
    "例如", "比如", "如下",
    "其中", "以上", "以下", "如图", "如表",
    "实例", "实例一", "实例二", "实例三",
    # Common single-character-meaning Chinese that are too vague alone
    "表", "图", "值", "项", "组", "类", "库", "码",
}

# Regex patterns for junk concept canonical names
_JUNK_PATTERNS = [
    re.compile(r"^[a-z]{1,3}\d+$"),              # e.g. "a305", "ch01", "r__"
    re.compile(r"^[a-z]-\d+$"),                   # e.g. "a-305", "a-102"
    re.compile(r"^[a-z]\d*-\d+$"),                # e.g. "a-305", "b2-3"
    re.compile(r"^ch\d+$"),                        # e.g. "ch01"
    re.compile(r"^\d+[a-z]*$"),                    # e.g. "112", "2a"
    re.compile(r"^frac\d+$"),                      # e.g. "frac112"
    re.compile(r"^delta\d+$"),                     # e.g. "delta2"
    re.compile(r"^[a-z]_+$"),                      # e.g. "r__", "s_"
    re.compile(r"^(fig|table|eq|sec|ch|ref)\d*$"), # e.g. "fig1", "table2"
    re.compile(r"^[a-z]{1,4}[-_]\d{1,4}$"),        # e.g. "a-305", "cs-101", "db_01"
    re.compile(r"^\d{1,4}[-_][a-z]{1,4}$"),        # e.g. "305-a"
    re.compile(r"^[a-z]{1,2}$"),                   # single/double letter: "a", "db"
    re.compile(r"^[\d.]+$"),                        # any pure digit/dot sequence
    re.compile(r"^[a-z]{1,4}\s+\d{1,4}$"),         # canonicalized "a 305", "cs 101" (hyphen→space)
    re.compile(r"^\d{1,4}\s+[a-z]{1,4}$"),         # canonicalized "305 a"
    re.compile(r"^实例[一二三四五六七八九十\d]+$"),   # "实例一", "实例2"
    re.compile(r"^(一个|一张|某个?|每个?|这个|那个)"),  # phrases starting with demonstratives
]

# Substrings that make a concept name look like example data or a fragment
_JUNK_SUBSTRINGS = {
    "学号", "姓名", "性别", "年龄", "编号",
    "张三", "李四", "王五", "赵六",
    "page ", "slide ", "figure ",
}


def is_junk_concept(canonical_name: str) -> bool:
    """Return True if the canonical name looks like a PDF/LaTeX artifact or junk."""
    name = canonical_name.strip().lower()
    if not name:
        return True
    # Single character
    if len(name) <= 1:
        return True
    # Pure digits or digits with dots/spaces
    if re.fullmatch(r"[\d\s.]+", name):
        return True
    # Exact match in stopwords
    if name in CONCEPT_STOPWORDS:
        return True
    # Match junk patterns (check both canonical form and compact no-space form,
    # because canonicalize_term turns "a-305" into "a 305")
    compact = name.replace(" ", "")
    for pattern in _JUNK_PATTERNS:
        if pattern.match(name) or pattern.match(compact):
            return True
    # Contains junk substrings (e.g. example person names, field names)
    for fragment in _JUNK_SUBSTRINGS:
        if fragment in name:
            return True
    # All-ASCII names that are too short to be meaningful concepts (<=3 chars)
    ascii_only = all(ord(c) < 128 for c in name.replace(" ", ""))
    if ascii_only and len(name.replace(" ", "")) <= 3:
        return True
    # Chinese names that are just 2 characters and look like common words
    stripped = name.replace(" ", "")
    is_all_chinese = all("\u4e00" <= c <= "\u9fff" for c in stripped)
    if is_all_chinese and len(stripped) <= 1:
        return True
    # Phrases that are clearly sentence fragments, not concepts (contains 中有/中的)
    if re.search(r"[中里]有[一二三四五六七八九十\d]", name):
        return True
    return False


PUNCT_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
EN_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
ZH_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
SENTENCE_RE = re.compile(r"(?<=[。！？!?;；\.])\s+")


def normalize_text(text: str) -> str:
    text = text.replace("\\n", " ").replace("\\t", " ").replace("\\r", " ")
    collapsed = re.sub(r"\s+", " ", text)
    return collapsed.strip()


def split_sentences(text: str) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []
    parts = [part.strip() for part in SENTENCE_RE.split(normalized) if part.strip()]
    return parts or [normalized]


def summarize_text(text: str, max_sentences: int = 2, max_chars: int = 220) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return ""
    summary = " ".join(sentences[:max_sentences])
    return summary[:max_chars].strip()


def split_text(text: str, max_chars: int = 500, overlap: int = 80) -> list[str]:
    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
            continue
        if current:
            chunks.append(current)
        if len(sentence) <= max_chars:
            current = sentence
            continue
        start = 0
        while start < len(sentence):
            piece = sentence[start:start + max_chars]
            chunks.append(piece.strip())
            start += max(max_chars - overlap, 1)
        current = ""
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def english_tokens(text: str) -> list[str]:
    return [
        token.lower()
        for token in EN_TOKEN_RE.findall(text)
        if token.lower() not in EN_STOPWORDS
    ]


def chinese_terms(text: str) -> list[str]:
    try:
        import jieba.posseg as pseg
    except ImportError:
        # Fallback to naive logic if jieba is not available
        candidates: list[str] = []
        for run in ZH_RUN_RE.findall(text):
            if 2 <= len(run.strip()) <= 8:
                candidates.append(run.strip())
        return candidates

    candidates: list[str] = []
    # 只提取名词(n, ng), 专有名词(nr, nz, ns, nt), 动名词(vn), 简称(j) 等具有实体意义的词序
    allowed_flags = {"n", "ng", "nr", "nz", "ns", "nt", "vn", "j", "l", "i"}
    for word, flag in pseg.cut(text):
        if len(word) >= 2 and flag in allowed_flags:
            if word not in ZH_STOPWORDS:
                candidates.append(word)
    return candidates


def extract_candidate_terms(text: str, top_k: int = 12) -> list[str]:
    raw_terms = english_tokens(text) + chinese_terms(text)
    if not raw_terms:
        return []
    counts = Counter(raw_terms)
    ranked = [
        term for term, _ in counts.most_common(top_k * 2)
        if is_reasonable_term(term)
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for term in ranked:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
        if len(deduped) >= top_k:
            break
    return deduped


def is_reasonable_term(term: str) -> bool:
    if term.isdigit():
        return False
    if len(term) <= 1:
        return False
    if all(char == term[0] for char in term):
        return False
    if term in EN_STOPWORDS or term in ZH_STOPWORDS:
        return False
    return True


def canonicalize_term(term: str) -> str:
    cleaned = PUNCT_RE.sub(" ", term).strip().lower()
    return re.sub(r"\s+", " ", cleaned)


def hash_embedding(text: str, dims: int | None = None) -> list[float]:
    dims = dims or settings.embedding_dimensions
    vector = [0.0] * dims
    for token in extract_candidate_terms(text, top_k=32) or english_tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dims
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = max(len(token), 1)
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def best_snippet(text: str, query_terms: list[str], max_chars: int = 180) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return text[:max_chars]
    scored = sorted(
        sentences,
        key=lambda sentence: sum(sentence.lower().count(term.lower()) for term in query_terms),
        reverse=True,
    )
    return scored[0][:max_chars]
