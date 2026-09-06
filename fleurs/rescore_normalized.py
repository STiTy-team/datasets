#!/usr/bin/env python3
"""한 런의 .jsonl 을 다시 채점한다 — 정규화 적용 전/후를 나란히 낸다.

run_conversation_smoke_test.py 는 jiwer 를 원문 그대로 부른다(정규화 없음).
아랍어 이체자(أ إ آ → ا)나 문장부호 하나 때문에 어절 전체가 오답이 되므로
모델을 과도하게 깎는다. 이 스크립트는 원본 산출물을 건드리지 않고
정규화 버전을 별도 파일로 만든다.

또한 잘린 세그먼트(cut)를 전체 문장 참조로 채점하는 구조 때문에 생기는
"삭제만으로 발생하는 WER 하한"을 같이 보고한다 — 보고된 WER 중 얼마가
채점 설계 탓이고 얼마가 실제 인식 오류인지 가르기 위한 것이다.

사용법: python rescore_normalized.py run_base [run_ko ...]
        -> run_base.normalized.json
"""
import json
import os
import re
import statistics as st
import sys
import unicodedata

DIAC = re.compile(r"[ً-ْٰـ]")
PUNCT = re.compile(r"[.,!?;:،؛؟۔\"'()\[\]{}«»‘’“”\-—–/]")


def norm(text, lang):
    t = unicodedata.normalize("NFKC", text)
    if lang == "ar":
        t = DIAC.sub("", t)                       # 타슈킬 제거
        t = re.sub(r"[أإآٱ]", "ا", t)  # 알레프 통일
        t = t.replace("ة", "ه")         # ة -> ه
        t = t.replace("ى", "ي")         # ى -> ي
    t = PUNCT.sub(" ", t)
    if lang == "en":
        t = t.lower()
    return " ".join(t.split())


def edit_rate(ref_tokens, hyp_tokens):
    if not ref_tokens:
        return None
    d = list(range(len(hyp_tokens) + 1))
    for i in range(1, len(ref_tokens) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(hyp_tokens) + 1):
            cur = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, prev + (ref_tokens[i - 1] != hyp_tokens[j - 1]))
            prev = cur
    return d[len(hyp_tokens)] / len(ref_tokens)


def wer(ref, hyp):
    return edit_rate(ref.split(), hyp.split())


def cer(ref, hyp):
    return edit_rate(list(ref.replace(" ", "")), list(hyp.replace(" ", "")))


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 4) if xs else None


def load_keep(manifest_path):
    """(turn_index, lang) -> 실제 들려준 오디오 비율."""
    keep = {}
    if not manifest_path or not os.path.exists(manifest_path):
        return keep
    for line in open(manifest_path, encoding="utf-8"):
        r = json.loads(line)
        for s in r.get("segments", []):
            full = s.get("full_duration")
            if full:
                keep[(r["turn_index"], s["lang"])] = (s["end_sec"] - s["start_sec"]) / full
    return keep


def main(tags):
    for tag in tags:
        log_path = tag if tag.endswith(".jsonl") else tag + ".jsonl"
        base = log_path[:-6]
        summary_path = base + ".summary.json"
        if not os.path.exists(log_path):
            print("건너뜀 (없음): %s" % log_path)
            continue

        manifest = None
        if os.path.exists(summary_path):
            manifest = json.load(open(summary_path)).get("run", {}).get("manifest")
        keep = load_keep(manifest)

        acc, dropped = {}, {}
        for line in open(log_path, encoding="utf-8"):
            rec = json.loads(line)
            for s in rec.get("segment_scores", []):
                lang = s["lang"]
                a = acc.setdefault(lang, {"wer": [], "cer": [], "wer_n": [], "cer_n": [],
                                          "keep": [], "len_ratio": []})
                if s.get("dropped") or not s.get("original"):
                    dropped[lang] = dropped.get(lang, 0) + 1
                    continue
                e_raw, h_raw = s["expected_text"], s["original"]
                e, h = norm(e_raw, lang), norm(h_raw, lang)
                a["wer"].append(s.get("wer"))
                a["cer"].append(s.get("cer"))
                a["wer_n"].append(wer(e, h))
                a["cer_n"].append(cer(e, h))
                k = keep.get((s["turn_index"], lang))
                if k is not None:
                    a["keep"].append(k)
                if e:
                    a["len_ratio"].append(len(h.split()) / max(1, len(e.split())))

        out = {"source_log": os.path.basename(log_path), "manifest": manifest, "by_language": {}}
        for lang in sorted(acc):
            a = acc[lang]
            lr = mean(a["len_ratio"])
            wn = mean(a["wer_n"])
            floor = round(1 - lr, 4) if lr is not None else None
            out["by_language"][lang] = {
                "n_scored": len(a["wer_n"]),
                "n_dropped": dropped.get(lang, 0),
                "wer_reported": mean(a["wer"]),
                "cer_reported": mean(a["cer"]),
                "wer_normalized": wn,
                "cer_normalized": mean(a["cer_n"]),
                "keep_ratio_audio": mean(a["keep"]),
                "hyp_ref_word_ratio": lr,
                "deletion_floor_wer": floor,
                "excess_over_floor": round(wn - floor, 4) if (wn is not None and floor is not None) else None,
            }
        allw = [v for a in acc.values() for v in a["wer_n"]]
        allc = [v for a in acc.values() for v in a["cer_n"]]
        out["overall"] = {"wer_normalized": mean(allw), "cer_normalized": mean(allc),
                          "n_scored": len(allw)}

        dst = base + ".normalized.json"
        json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print("wrote %s" % dst)
        for lang, v in out["by_language"].items():
            print("  %-3s n=%-4s 보고WER=%-7s 정규화WER=%-7s 삭제하한=%-7s 초과=%s"
                  % (lang, v["n_scored"], v["wer_reported"], v["wer_normalized"],
                     v["deletion_floor_wer"], v["excess_over_floor"]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1:])
