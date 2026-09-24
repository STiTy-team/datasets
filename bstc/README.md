# BSTC (Baidu Speech Translation Corpus)

바이두가 중국어 강연·발표를 받아 적고 영어로 번역한 동시통역 연구용 코퍼스. 중국어 소스
StreamST 를 재는 용도다. 여기서 쓰는 것은 **dev 발표 16개**(956문장, 1.6 시간)다.

```bash
./bstc/install.sh
```

## dev 만 쓰는 이유

- **test 는 공개된 적이 없다.** AutoSimTrans 2020~2022 공유 과제가 "test set 은 공개하지
  않는다"고 밝혔고, 논문들은 dev 로 보고한다.
- **train 오디오는 일부만 공개돼 있다.** 215개 발표 중 50개만 공유 과제 페이지에서 받을 수
  있다. 나머지는 바이두 AI Studio 로그인과 대회 등록이 필요했고, 지금 되는 경로는 찾지 못했다.
- 공식 소개 페이지(luge.ai, ai.baidu.com)는 죽었다. 라이선스 문서도 찾지 못했다.

받는 두 파일은 로그인 없이 받힌다 — 텍스트는 PaddleNLP 미러, dev 오디오는 AutoSimTrans 2020
공유 과제 페이지의 서명 URL(만료 없음)이다.

## 항목 하나가 발표 하나다

`mcif/` 와 같은 사정이다. dev 에는 **문장 시각이 없다.** 중국어 전사는 스트리밍을 흉내 낸
형태로만 있다 — 문장 하나를 한 글자씩 늘려 가며 한 줄씩 적는다.

```
谢谢大
谢谢大家          ← 다음 줄이 이걸 늘리지 않으므로 완성된 문장
大
大家
...
```

`convert.py` 는 다음 줄이 늘리지 않는 줄을 완성된 문장으로 보고, 그 수가 영어 참조 줄 수와
발표마다 **정확히 같은지** 확인한다(16개 발표 모두 같다). 다르면 변환을 거부한다.

같이 딸린 ASR 결과(`bstc_asr`)의 `final` 시각은 문장 경계와 맞지 않아(발표 105: final 32개,
문장 63개) 시각 복원에 못 쓴다. 그래서 받지도 않는다.

전사는 문장을 이어 붙인 문자열 하나, 번역은 문장마다 한 줄이다. 채점 사정은
[`mcif/README.md`](../mcif/README.md) 와 같다 — CER 은 그대로 되고, 번역 지표는 재분절이 먼저다.

## 전사에 문장부호와 머뭇거림이 들어 있다

`啊`, `呃` 같은 간투사를 그대로 적었고 문장부호도 있다. CER 을 낼 때 정규화가 이것을 어떻게
다룰지 정해야 한다.

## 만들어지는 것

```
bstc/
  data/bstc_transcription_translation.tar.gz   받은 것 (git 에 없다)
  data/bstc_transcription_translation/dev/     푼 것 (git 에 없다)
  data/devdata.zip, data/devdata/<talk>.wav    받은 것, 16 kHz mono (git 에 없다)
  dataset.yml                                  생성물
  manifest.jsonl                               생성물
  audio -> data/devdata                        심볼릭 링크
```

발표 wav 는 이미 계약 형식이라 디코딩 없이 링크만 건다.
