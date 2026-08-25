"""Pure Python BM25 (Okapi) ranking engine with inverted postings and English morphological stemming."""

import math
import re
from collections.abc import Sequence
from typing import final

TOKEN_PATTERN: re.Pattern[str] = re.compile(r"\b\w+\b")

# Step 2 mapping for Porter Stemmer
_STEP2_MAP: dict[str, str] = {
    "ational": "ate",
    "tional": "tion",
    "enci": "ence",
    "anci": "ance",
    "izer": "ize",
    "abli": "able",
    "alli": "al",
    "entli": "ent",
    "eli": "e",
    "ousli": "ous",
    "ization": "ize",
    "ation": "ate",
    "ator": "ate",
    "alism": "al",
    "iveness": "ive",
    "fulness": "ful",
    "ousness": "ous",
    "aliti": "al",
    "iviti": "ive",
    "biliti": "ble",
}

_STEP3_MAP: dict[str, str] = {
    "icate": "ic",
    "ative": "",
    "alize": "al",
    "iciti": "ic",
    "ical": "ic",
    "ful": "",
    "ness": "",
}

_STEP4_SUFFIXES: tuple[str, ...] = (
    "al", "ance", "ence", "er", "ic", "able", "ible", "ant", "ement",
    "ment", "ent", "ou", "ism", "ate", "iti", "ous", "ive", "ize",
)


def _is_consonant(word: str, i: int) -> bool:
    """Check if character at index i in word is a consonant."""
    c = word[i]
    if c in "aeiou":
        return False
    if c == "y":
        return i == 0 or not _is_consonant(word, i - 1)
    return True


def _measure(stem: str) -> int:
    """Calculate the Porter measure m of vowel-consonant sequences in stem."""
    n = 0
    i = 0
    length = len(stem)
    while i < length:
        if not _is_consonant(stem, i):
            break
        i += 1
    while i < length:
        while i < length and not _is_consonant(stem, i):
            i += 1
        if i >= length:
            break
        while i < length and _is_consonant(stem, i):
            i += 1
        n += 1
    return n


def _has_vowel(stem: str) -> bool:
    """Check if stem contains any vowel."""
    return any(not _is_consonant(stem, i) for i in range(len(stem)))


def _double_consonant(stem: str) -> bool:
    """Check if stem ends in a double consonant."""
    if len(stem) < 2:
        return False
    return stem[-1] == stem[-2] and _is_consonant(stem, len(stem) - 1)


def _cvc(stem: str) -> bool:
    """Check if stem ends with consonant-vowel-consonant (where second consonant is not w, x, or y)."""
    if len(stem) < 3:
        return False
    if stem[-1] in "wxy":
        return False
    return (
        _is_consonant(stem, len(stem) - 1)
        and not _is_consonant(stem, len(stem) - 2)
        and _is_consonant(stem, len(stem) - 3)
    )


def stem_word(w: str) -> str:
    """Apply standard Porter Stemmer algorithm to reduce word to its morphological root."""
    if len(w) <= 2:
        return w

    # Step 1a
    if w.endswith(("sses", "ies")):
        w = w[:-2]
    elif not w.endswith("ss") and w.endswith("s"):
        w = w[:-1]

    # Step 1b
    extra_1b = False
    if w.endswith("eed"):
        stem = w[:-3]
        if _measure(stem) > 0:
            w = stem + "ee"
    elif w.endswith("ed"):
        stem = w[:-2]
        if _has_vowel(stem):
            w = stem
            extra_1b = True
    elif w.endswith("ing"):
        stem = w[:-3]
        if _has_vowel(stem):
            w = stem
            extra_1b = True

    if extra_1b:
        if w.endswith(("at", "bl", "iz")):
            w += "e"
        elif _double_consonant(w) and not w.endswith(("l", "s", "z")):
            w = w[:-1]
        elif _measure(w) == 1 and _cvc(w):
            w += "e"

    # Step 1c
    if w.endswith("y"):
        stem = w[:-1]
        if _has_vowel(stem):
            w = stem + "i"

    # Step 2
    for suffix, replacement in _STEP2_MAP.items():
        if w.endswith(suffix):
            stem = w[:-len(suffix)]
            if _measure(stem) > 0:
                w = stem + replacement
            break

    # Step 3
    for suffix, replacement in _STEP3_MAP.items():
        if w.endswith(suffix):
            stem = w[:-len(suffix)]
            if _measure(stem) > 0:
                w = stem + replacement
            break

    # Step 4
    if w.endswith("ion"):
        stem = w[:-3]
        if _measure(stem) > 1 and stem.endswith(("s", "t")):
            w = stem
    else:
        for suffix in _STEP4_SUFFIXES:
            if w.endswith(suffix):
                stem = w[:-len(suffix)]
                if _measure(stem) > 1:
                    w = stem
                break

    # Step 5a
    if w.endswith("e"):
        stem = w[:-1]
        m = _measure(stem)
        if m > 1 or (m == 1 and not _cvc(stem)):
            w = stem

    # Step 5b
    if w.endswith("ll") and _measure(w) > 1:
        w = w[:-1]

    return w


ENGLISH_STOPWORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "did", "do", "does", "doing", "don",
    "down", "during", "each", "few", "for", "from", "further", "had", "has",
    "have", "having", "he", "her", "here", "hers", "herself", "him", "himself",
    "his", "how", "if", "in", "into", "is", "it", "its", "itself", "just", "me",
    "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on",
    "once", "only", "or", "other", "our", "ours", "ourselves",
    # Domain-agnostic entity and citation boilerplate tokens
    "inc",
    "corp",
    "co",
    "ltd",
    "llc",
    "page",
    "section",
    "paragraph",
    "et",
    "al",
    "out", "over",
    "own", "s", "same", "she", "should", "so", "some", "such", "t", "than",
    "that", "the", "their", "theirs", "them", "themselves", "then", "there",
    "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "whom", "why", "will", "with", "would",
})


def tokenize(
    text: str,
    stem: bool = True,
    include_bigrams: bool = False,
    filter_stopwords: bool = True,
) -> list[str]:
    """Tokenize, lowercase, optionally remove stopwords, and optionally stem text into lexical terms."""
    raw_tokens = [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]
    if filter_stopwords:
        raw_tokens = [t for t in raw_tokens if t not in ENGLISH_STOPWORDS]
    unigrams = [stem_word(t) for t in raw_tokens] if stem else raw_tokens
    if not include_bigrams or len(unigrams) < 2:
        return unigrams

    bigrams = [f"{unigrams[i]}_{unigrams[i + 1]}" for i in range(len(unigrams) - 1)]
    return [*unigrams, *bigrams]


@final
class BM25Index:
    """In-memory BM25 index over a collection of tokenized documents or chunks using inverted postings."""

    def __init__(
        self,
        corpus: Sequence[str],
        k1: float = 1.5,
        b: float = 0.75,
        stem: bool = True,
        include_bigrams: bool = False,
        filter_stopwords: bool = True,
    ) -> None:
        """Initialize BM25 index with precomputed IDF and inverted postings list."""
        self.k1: float = k1
        self.b: float = b
        self.stem: bool = stem
        self.include_bigrams: bool = include_bigrams
        self.filter_stopwords: bool = filter_stopwords
        self.corpus_size: int = len(corpus)

        self.doc_lengths: list[int] = []
        self.postings: dict[str, list[tuple[int, int]]] = {}
        total_tokens = 0

        for doc_idx, text in enumerate(corpus):
            tokens = tokenize(
                text,
                stem=self.stem,
                include_bigrams=self.include_bigrams,
                filter_stopwords=self.filter_stopwords,
            )
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_tokens += doc_len

            term_freqs: dict[str, int] = {}
            for token in tokens:
                term_freqs[token] = term_freqs.get(token, 0) + 1

            for term, tf in term_freqs.items():
                if term not in self.postings:
                    self.postings[term] = []
                self.postings[term].append((doc_idx, tf))

        self.avg_doc_len: float = (
            float(total_tokens) / float(self.corpus_size) if self.corpus_size > 0 else 0.0
        )

        # Precompute IDF: ln(1 + (N - n + 0.5) / (n + 0.5))
        self.idf: dict[str, float] = {}
        for term, posting_list in self.postings.items():
            df = len(posting_list)
            self.idf[term] = math.log(
                1.0 + (float(self.corpus_size) - float(df) + 0.5) / (float(df) + 0.5)
            )

    def get_scores(self, query: str) -> list[float]:
        """Compute BM25 relevance scores for all documents in corpus against given query."""
        query_tokens = tokenize(
            query,
            stem=self.stem,
            include_bigrams=self.include_bigrams,
            filter_stopwords=self.filter_stopwords,
        )
        if not query_tokens or self.corpus_size == 0 or self.avg_doc_len == 0.0:
            return [0.0] * self.corpus_size

        scores: list[float] = [0.0] * self.corpus_size
        k1 = self.k1
        b = self.b
        avg_dl = self.avg_doc_len

        for term in query_tokens:
            term_idf = self.idf.get(term)
            posting_list = self.postings.get(term)
            if term_idf is None or posting_list is None:
                continue

            for doc_idx, tf in posting_list:
                dl = self.doc_lengths[doc_idx]
                denom = tf + k1 * (1.0 - b + b * (float(dl) / avg_dl))
                if denom > 0.0:
                    scores[doc_idx] += term_idf * (float(tf) * (k1 + 1.0) / denom)

        return scores
