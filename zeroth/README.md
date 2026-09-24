# Zeroth-Korean

뉴스 문장을 낭독한 한국어 ASR 코퍼스([OpenSLR 40](https://www.openslr.org/40/), CC BY 4.0).
번역 참조는 없다 — ASR 만 잰다.

```bash
./zeroth/install.sh                   # test: 457 발화, 화자 10명, 1.19 시간
SPLIT=train ./zeroth/install.sh       # train: 22,263 발화, 51.6 시간
```

## 잡음은 섞여 있지 않다

"뉴스 문장 낭독 + 잡음 합성"으로 소개되곤 하지만, OpenSLR 페이지와 원 저장소
([goodatlas/zeroth](https://github.com/goodatlas/zeroth)) 어디에도 잡음을 섞었다는 말이 없다.
앱으로 모은 **깨끗한 낭독**이다. 잡음 조건이 필요하면 `musan/` 으로 섞는다.

## HF 미러에서 받는다

OpenSLR tarball 은 10 GB 인데 대부분이 LM·사전이다. 오디오와 전사만 담은
[kresnik/zeroth_korean](https://huggingface.co/datasets/kresnik/zeroth_korean) parquet
(test 60 MB)를 받는다. 원래의 발화 id(`104_003_0019`)와 화자 id 가 그대로 있다.

`convert.py` 는 parquet 안의 flac 을 wav 로 한 번 디코딩한다.

## 전사

이미 정규화돼 있다 — 한글과 띄어쓰기뿐이고, 숫자는 읽는 대로 적혀 있다(`삼십 일 일`).
문장부호가 없다. `primary_metric` 은 `cer`.

## 항목과 세션

발화 하나가 항목 하나이고 `group` 도 그 발화다 — **항목마다 새 세션**이다.

`kosp2e/` 의 `zeroth` 부분(461 발화)과는 다른 분할이다. 저건 kosp2e 가 다시 나눈 것이다.

## 만들어지는 것

```
zeroth/
  data/data/<split>-*.parquet     받은 것 (git 에 없다)
  data/wav16k/<split>/<id>.wav    디코딩한 것 (git 에 없다)
  dataset.yml                     생성물
  manifest.jsonl                  생성물
  alignment.jsonl                 생성물
  audio -> data/wav16k/<split>    심볼릭 링크
```
