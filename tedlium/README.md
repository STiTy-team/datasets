# TED-LIUM 3

TED 강연을 받아 적은 영어 ASR 코퍼스. 낭독이 아니라 **실제 강연**이라 FLEURS 보다 발표
상황에 가깝다. 번역 참조는 없다 — ASR 만 잰다.

```bash
./tedlium/install.sh                  # test: 강연 11개, 채점 구간 1,155개, 3.1 시간
SPLIT=dev ./tedlium/install.sh        # dev: 강연 8개
```

## 공식 배포처가 사라졌다

OpenSLR 51 과 LIUM 페이지는 404 이고, Hugging Face 의 `LIUM/tedlium` 도 내려갔다. LIUM 은
2025년 8월부터 다운로드를 막고 저자에게 직접 연락하라고 한다.
[kfajdsl/tedlium](https://huggingface.co/datasets/kfajdsl/tedlium) 이 옛 LIUM 저장소의
tarball 을 그대로 다시 올린 공개 사본이라 거기서 받는다. **비공식 사본이다.**
라이선스는 원래대로 CC BY-NC-ND 3.0 이다.

`legacy` 분할(TED-LIUM 1·2 와 같은 dev 8개·test 11개 강연)을 쓴다. 문헌의 TED-LIUM 3
수치가 대부분 이것이다. `speaker-adaptation` 분할은 받지 않는다.

## 강연 하나가 파일 하나, 문장은 시각으로만 있다

```
test/<Talk>.sph     NIST SPHERE, 16 kHz mono PCM16. 강연 전체
test/<Talk>.stm     <talk> <ch> <speaker> <start> <end> <label> <text...>
```

`convert.py` 는 `.sph` 를 wav 로 한 번 디코딩하고(헤더만 다르고 표본은 그대로다), STM 구간
하나를 항목 하나로 만든다. 항목은 `offset`·`duration` 으로 강연 wav 안을 가리킨다 —
**파일을 자르지 않는다.** `group` 은 강연이고, 강연 안 순서는 시작 시각이다.

`ignore_time_segment_in_scoring` 이 붙은 줄(구간 사이 공백, test 에 314개)은 말이 아니라서
뺀다.

## 전사는 소문자이고 축약형이 쪼개져 있다

`i 'm`, `don 't`, `it 's` 처럼 아포스트로피 앞에서 띄어 쓴다. 그대로 두면 `I'm` 이라고
쓴 시스템이 한 단어에 오류 둘을 먹는다. `convert.py` 는 이것만 붙여서(`i'm`) 쓴다.
소문자와 문장부호 없음은 그대로다 — 채점 전 정규화가 맞춰야 한다.

## 만들어지는 것

```
tedlium/
  data/TEDLIUM_release3/legacy/<split>.tar.gz   받은 것 (git 에 없다)
  data/<split>/*.{sph,stm}                      푼 것 (git 에 없다)
  data/wav16k/<split>/<Talk>.wav                디코딩한 것 (git 에 없다)
  dataset.yml                                   생성물
  manifest.jsonl                                생성물
  audio -> data/wav16k/<split>                  심볼릭 링크
```
