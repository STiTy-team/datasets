# Multilingual LibriSpeech (MLS)

LibriVox 오디오북을 문장 단위로 자른 ASR 코퍼스. 독일어를 비롯해 8개 언어가 있다.
번역 참조는 없다 — ASR 만 잰다. 낭독체이지만 FLEURS 보다 한 클립이 길다(독일어 test 중앙값
35어절).

공개 데이터셋이다(CC BY 4.0). Hugging Face 계정도 토큰도 필요 없다.

```bash
./mls/install.sh                              # german test: 3,394 클립, 14.3 시간
LANGUAGE=french SPLIT=dev ./mls/install.sh
```

`LANGUAGE` 는 `german dutch french spanish italian portuguese polish`, `SPLIT` 은
`test dev` 다.

## 받는 곳은 OpenSLR 이 아니라 Hugging Face 다

OpenSLR 94 는 언어 하나의 모든 분할을 tarball 하나에 담는다 — 독일어가 opus 로 29 GB,
flac 으로 115 GB 다. [facebook/multilingual_librispeech](https://huggingface.co/datasets/facebook/multilingual_librispeech)
는 분할마다 parquet 로 나뉘어 있어서 test 만 받으면 214 MB 다.

## 오디오는 parquet 안의 opus 다

parquet 의 `audio.bytes` 에 opus 파일이 통째로 들어 있다. 계약은 16 kHz mono PCM16 wav
하나만 받으므로 `convert.py` 가 클립마다 한 번 디코딩해 `data/wav16k/` 에 쓴다. 다시 돌리면
이미 쓴 파일은 건너뛴다. 전부 코어 수만큼 병렬로 돈다.

opus 는 손실 압축이다. 원본 flac 이 필요하면 OpenSLR 의 115 GB tarball 뿐이다.

## 항목과 세션

클립 하나가 항목 하나이고 `group` 도 그 클립이다 — **항목마다 새 세션**이다. 같은 책의
연속된 클립이어도 경계가 문장 중간일 수 있고, 순서를 이어 흘릴 근거가 없다.

전사는 소문자에 문장부호가 없다. 채점 전 정규화가 이것과 맞아야 한다.

## 만들어지는 것

```
mls/
  data/<language>/<split>-*.parquet           받은 것 (git 에 없다)
  data/wav16k/<language>/<split>/<id>.wav     디코딩한 것 (git 에 없다)
  dataset.yml                                 생성물
  manifest.jsonl                              생성물
  audio -> data/wav16k/<language>/<split>     심볼릭 링크
```
