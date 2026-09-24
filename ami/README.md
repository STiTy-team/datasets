# AMI Meeting Corpus

4명이 모여 나눈 **회의**를 받아 적은 영어 ASR 코퍼스(Edinburgh, CC BY 4.0). 회의당 약 30분이고
화자가 겹친다. 번역 참조는 없다.

```bash
./ami/install.sh                      # test: 회의 16개, 7,814 구간, 9.2 시간, 1.1 GB
MIC=sdm ./ami/install.sh              # 원거리: 배열 1 의 첫 마이크
SPLIT=dev ./ami/install.sh            # dev: 회의 18개
```

로그인 없이 Edinburgh 공개 미러에서 받는다. 회의 목록은 Kaldi·Lhotse·ESPnet 이 쓰는
`full-corpus-asr` 분할이다(`convert.py` 의 `MEETINGS`).

## 마이크

| `MIC` | 파일 | 무엇 |
|---|---|---|
| `ihm-mix` (기본) | `<회의>.Mix-Headset.wav` | 헤드셋 마이크를 합친 것. 가깝고 깨끗하다 |
| `sdm` | `<회의>.Array1-01.wav` | 탁자 위 배열의 마이크 하나. 원거리·잔향 |

둘 다 이미 16 kHz mono PCM16 이라 링크만 건다. 둘 다 받아 두면 `MIC` 만 바꿔 다시 변환된다.

## 전사는 NXT 수동 주석에서 온다

`ami_public_manual_1.6.2.zip`(23 MB)에서 `words/`·`segments/`·`corpusResources/` 만 푼다.

```
segments/EN2002a.A.segments.xml   <segment transcriber_start="0.944" transcriber_end="7.068">
                                    <nite:child href="EN2002a.A.words.xml#id(EN2002a.A.words0)..id(EN2002a.A.words17)"/>
words/EN2002a.A.words.xml         <w starttime="0.96" endtime="1.2">Wonder</w>  <w punc="true">.</w>  <vocalsound/> ...
corpusResources/meetings.xml      화자 글자(A..E) -> 전역 화자 id
```

구간 하나가 가리키는 `<w>` 들을 이어 붙인다 — 대소문자와 문장부호가 있는 원문이다.
`<vocalsound>`·`<disfmarker>`·`<gap>` 은 말이 아니라 뺀다. 시각은 모두 회의 전체 기준이다.

HF 의 `edinburghcstr/ami` 는 Kaldi 정규화(대문자, 문장부호 없음) 전사라 쓰지 않았다. WER 은 양쪽을
정규화하고 비교하므로 차이는 없다.

## 긴 구간은 문장 끝에서 나눈다

주석자가 한 구간으로 둔 발언이 400단어를 넘기도 한다(계약의 200단어 상한에 걸린다). 단어 시각이
빈틈없이 이어져 있어 쉼으로는 자를 곳이 없다. 그래서 60단어가 넘는 구간은 **문장 끝(`.?!`)에서**
나눈다 — 60단어를 넘지 않게 문장을 채워 담는다. 문장 하나가 60단어를 넘으면 그대로 둔다(test 최대 104).

## 항목과 세션

구간 하나가 항목 하나이고 `offset`·`duration` 으로 회의 wav 안을 가리킨다. `group` 은 회의이고 회의
안 순서는 시작 시각이다. **다른 화자의 구간끼리 겹친다** — 회의라 그렇다. `speaker` 는 전역 화자 id
(`FEO070`)다.

## 만들어지는 것

```
ami/
  data/annotations/{words,segments,corpusResources}/   받은 것 (git 에 없다)
  data/audio/<회의>.{Mix-Headset,Array1-01}.wav         받은 것 (git 에 없다)
  dataset.yml, manifest.jsonl, alignment.jsonl          생성물
  audio -> data/audio                                   심볼릭 링크
```
