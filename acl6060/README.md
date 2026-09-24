# ACL 60/60

ACL 2022 발표를 영어로 전사하고 10개 언어로 번역한 코퍼스. 낭독체가 아니라 **실제 학회
발표**라 FLEURS 보다 훨씬 어렵고, 도메인 용어가 많다.

## 받는 방법

**스크립트가 내려받지 않는다.** 배포 경로가 판본마다 달라 자동화하면 조용히 틀린 것을
받는다. ACL 60/60 배포 페이지에서 직접 받아 `acl6060/` 안에 아래 형태로 푼다.

```
acl6060/
  acl_6060/
    dev/ | eval/
      FILE_ORDER
      full_wavs/<talk>.wav
      segmented_wavs/gold/sent_N.wav
      text/xml/ACL.6060.<split>.en-xx.<lang>.xml
  intermediate_files/          쓰지 않는다 (ASR/MT 출력과 포스트에딧 기록)
```

```bash
./acl6060/install.sh                  # eval → de
SPLIT=dev TGT="de ja" ./acl6060/install.sh
```

## 시각 정보가 배포판에 없다

문장별 wav 와 통짜 발표 wav 가 둘 다 들어 있는데 **둘을 잇는 시각이 없다.** XML 에도
없고, offset 이 담긴 yaml 은 SHAS 자동 분절용이라 gold 에는 못 쓴다.

다행히 gold 문장 wav 는 통짜에서 **바이트 그대로 잘라낸 것**이라, 통짜 안에서 문장
바이트열을 찾으면 시각이 **정확히** 복원된다(근사가 아니다). `install.sh` 가 STiTy 의
`evaluation/ast/recover_acl6060_timings.py` 를 불러 `timings_<split>.json` 을 만든다.
STiTy 체크아웃이 옆에 없으면 `STITY_REPO` 로 알려주거나 직접 돌린다.

이 시각이 필요한 이유는 셋이다 — 어떤 문장이 어느 발표에 속하는지(`group`), 발표 안에서
어떤 순서로 말해졌는지, 그리고 발표를 통째로 흘릴 때 참조 문장이 발표의 어느 구간인지.

## 항목 하나는 문장 하나, 세션 하나는 발표 하나

항목은 gold 문장 하나이고, 오디오는 **발표 통짜 wav 안의 구간**(`offset`·`duration`)이다.
`group` 은 그 발표다. gold 문장 wav 가 통짜에서 바이트 그대로 잘라낸 것이라 구간을 읽으면
같은 샘플이 나온다(시각을 ms 로 반올림한 만큼만 다르다).

bench 는 기본으로 문장을 하나씩 흘린다. 데이터셋 설정에 `longform: true` 를 주면 발표 wav 를
통째로 흘리고, 항목들이 그 발표의 참조 분절(IWSLT 의 segmentation yaml 과 같은 것)이 된다 —
LongYAAL 은 이쪽에서만 나온다.

## 발표 안 순서는 seg id 가 아니라 시각이다

gold 문장 경계가 몇 군데 겹쳐 있어서 seg id 순서와 실제 발화 순서가 어긋난다.
`convert.py` 는 `(talk_id, offset)` 으로 정렬하고, bench 로더는 **그룹 안에서는
manifest 순서를 그대로 둔다.** id 로 다시 정렬하면 발표 순서가 조용히 뒤집힌다.

## 만들어지는 것

```
acl6060/
  acl_6060/                              직접 푼 것 (git 에 없다)
  timings_<split>.json                   생성물 (git 에 없다)
  dataset.yml                            생성물
  manifest.jsonl                         생성물
  audio -> acl_6060/<split>/full_wavs
```
