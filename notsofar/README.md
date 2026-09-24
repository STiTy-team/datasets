# NOTSOFAR-1

실제 사무실 회의실 30곳에서 4~8명이 나눈 **회의**를 받아 적은 영어 ASR 코퍼스(Microsoft,
CHiME-8 task 2, CC BY 4.0). 겹침과 잡음이 이 코퍼스의 요점이다. 번역 참조는 없다.

```bash
./notsofar/install.sh                         # eval_full: 회의 129개, 13.3 시간, 약 1.5 GB
VERSION=eval_small ./notsofar/install.sh      # CHiME-8 공식 eval: 회의 80개, 8.3 시간
VERSION=dev ./notsofar/install.sh             # dev1: 회의 36개, 3.7 시간
DEVICE=mc_plaza_0 ./notsofar/install.sh       # 7채널 배열의 ch0
```

| `VERSION` | HF 경로 | 회의 | 시간 |
|---|---|---|---|
| `eval_full` (기본) | `eval_set/240825.1_eval_full_with_GT` | 129 | 13.3 |
| `eval_small` | `eval_set/240629.1_eval_small_with_GT` | 80 | 8.3 |
| `dev` | `dev_set/240825.1_dev1` | 36 | 3.7 |

"트랙당 16시간"은 eval_small 8.3 시간 × 장치 2개를 센 것이다. 회의 시간 자체는 위와 같다.

## 장치 하나만 받는다

회의 하나에 close-talk, 단일 채널 장치 6~7개, 7채널 배열 3개가 **표본 단위로 맞춰져** 함께
녹음됐다(eval_full 전체 49 GB). `install.sh` 는 ground truth JSON 만 먼저 받고, `convert.py
--list-wavs` 가 회의마다 고른 **wav 하나**만 받는다.

`DEVICE` 는 폴더 이름이다(`sc_meetup_0`, `sc_plaza_0`, `mc_rockfall_0`, …). 기본 `sc_meetup_0` 은
eval_full 의 모든 회의에 있다. 없는 회의는 그 회의의 첫 단일 채널 장치(`sc_*`)로 대신하고, 회의마다
무엇을 썼는지 `dataset.yml` 의 `meetings.<id>.device` 에 남는다. 배열(`mc_*`)은 ch0 만 쓴다.
close-talk 는 화자마다 따로라 고를 수 없다.

`devices.json` 의 `device_name` 은 배열과 그 옆 단일 마이크가 같은 이름(`rockfall_0`)이라 폴더
이름으로 구분한다.

HF 의 `microsoft/NOTSOFAR` 는 공개다. 챌린지 코드가 `HF_TOKEN` 을 요구하지만 코드의 검사일 뿐이다.
원래의 Azure blob 은 이제 익명 접근이 막혔다.

## 전사

`gt_transcription.json` 의 발화 하나가 항목 하나다. 대소문자·문장부호가 있고 태그가 붙어 있다.

```
{"speaker_id": "Ron", "start_time": 61.39, "end_time": 63.67, "text": "We should probably list the <ST/>", ...}
```

`<ST/>`(말 끊김), `<FILL/>`, `<UNKNOWN/>`, `<BA/>` 같은 태그는 지우고, `<PName> Rachel </PName>` 은
안의 이름만 남긴다. 공식 채점은 Whisper 식 정규화에 tcpWER(collar 5)이다 — 여기 WER 과는 다르다.

## 겹침·잡음 메타데이터

별도 파일은 없고 회의마다 `gt_meeting_metadata.json` 의 `Hashtags` 뿐이다(`#DebateOverlaps`,
`#TransientNoise=high`, `#Music`, `#LowTalkers=<이름>`, …). `dataset.yml` 의 `meetings.<id>.hashtags`
에 그대로 옮긴다. 실제 겹침은 항목의 `offset`·`duration` 으로 계산하면 된다.

## 항목과 세션

`offset`·`duration` 으로 회의 wav 안을 가리킨다. `group` 은 회의이고 순서는 시작 시각이다. **발화끼리
겹친다.** `speaker` 는 `<회의>_<별칭>`(`MTG_32000_Ron`) — 별칭은 회의마다 따로 붙었다.

## 만들어지는 것

```
notsofar/
  data/benchmark-datasets/<VERSION 경로>/MTG/<회의>/*.json         받은 것 (git 에 없다)
  data/benchmark-datasets/<VERSION 경로>/MTG/<회의>/<장치>/ch0.wav  받은 것 (git 에 없다)
  dataset.yml, manifest.jsonl, alignment.jsonl                     생성물
  audio -> data/benchmark-datasets/<VERSION 경로>/MTG              심볼릭 링크
```
