# KsponSpeech

AI Hub 의 "한국어 음성" — 2,000명이 자유 주제로 나눈 **대화**를 받아 적은 한국어 ASR 코퍼스
(965 시간). 낭독이 아니라 구어체라 간투사·반복·겹침이 많다. 번역 참조는 없다.

```bash
AIHUB_APIKEY=<키> ./ksponspeech/install.sh                   # eval_clean: 3,000 발화, 2.6 시간
AIHUB_APIKEY=<키> SPLIT=eval_other ./ksponspeech/install.sh   # eval_other: 3,000 발화, 3.8 시간
```

## AI Hub 승인이 필요하다

1. [aihub.or.kr](https://aihub.or.kr/aihubdata/data/view.do?currMenu=115&topMenu=100&aihubDataSe=realm&dataSetSn=123)
   에 가입하고 "한국어 음성"(dataSetSn 123)을 신청한다. **내국인만 신청할 수 있다.**
2. 승인되면 AI Hub 에서 API 키를 발급받는다.
3. `AIHUB_APIKEY` 로 넘긴다.

`install.sh` 는 AI Hub 의 CLI(`aihubshell`)를 받아서 **평가용 zip(536 MB)과 전사 zip(24 MB)만**
받는다 — 학습용 70 GB 는 받지 않는다. `aihubshell` 은 실패해도 0 으로 끝나서, 받은 뒤 zip 이 실제로
있는지 따로 확인한다.

**재배포 금지다.** AI Hub 약관이 제3자 제공을 막는다. HF 에 올라온 사본들은 쓰지 않는다.

## 오디오는 헤더 없는 pcm 이다

16 kHz 16-bit mono little-endian, 헤더 없음. `convert.py` 가 `transcode(raw_pcm=True)` 로 wav 로
한 번 다시 쓴다.

## 전사에 주석이 붙어 있다

`scripts/eval_clean.trn` 은 `KsponSpeech_eval/eval_clean/KsponSpeech_E00001.pcm :: <전사>` 꼴이다.

```
그럼 (20년)/(이십 년) 전+ 전처럼 이메일로 l/ 소통하면 되잖아. l/
응/ 발자국 소리만 들려도 짖는데. (내가)/(내) 짖지 마 하면은 또
```

| 표기 | 뜻 | `convert.py` |
|---|---|---|
| `b/ l/ o/ n/ u/` | 숨, 웃음, 겹침, 잡음, 알아들을 수 없음 | 지운다 |
| `어/` | 간투사 | `/` 만 지우고 말은 남긴다 |
| `전+` | 반복 | `+` 만 지운다 |
| `*` | 불확실 | 지운다 |
| `(철자)/(발음)` | 이중 전사 | 한쪽만 남긴다 |

이중 전사는 **철자 쪽이 기본**이다(ESPnet·Lhotse 와 같다, `20년`). 발음 쪽(`이십 년`)이 필요하면
`convert.py --form phonetic`. 어느 쪽인지는 `dataset.yml` 의 `transcript_form` 에 남는다.
문장부호는 남긴다 — CER 은 채점 전에 지운다. kospeech 는 발음 쪽이 기본이라 문헌 수치를 비교할 때
어느 쪽인지 확인해야 한다.

## 항목과 세션

발화 하나가 항목 하나이고 **항목마다 새 세션**이다. 화자 정보는 전사 파일에 없다.

## 만들어지는 것

```
ksponspeech/
  data/aihubshell                     받은 것 (git 에 없다)
  data/**/KsponSpeech_eval.zip        받은 것 (git 에 없다)
  data/KsponSpeech_eval/<split>/*.pcm 푼 것 (git 에 없다)
  data/**/<split>.trn                 푼 것 (git 에 없다)
  data/wav16k/<split>/*.wav           다시 쓴 것 (git 에 없다)
  dataset.yml, manifest.jsonl, alignment.jsonl   생성물
  audio -> data/wav16k/<split>        심볼릭 링크
```
