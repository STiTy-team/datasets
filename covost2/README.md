# CoVoST 2

Common Voice 자원봉사자가 한 문장씩 읽은 클립에 번역을 붙인 음성번역 코퍼스. X→en 21개,
en→X 15개 방향이 있다. 여기서 쓰는 것은 독일어 쪽 두 방향이다.

| `PAIR` | 소스 오디오 | 번역 | test 클립 |
|---|---|---|---|
| `de_en` | 독일어 | 영어 | 13,511 |
| `en_de` | 영어 | 독일어 | 15,531 |

한국어 방향은 없다.

```bash
./covost2/install.sh                  # de_en test
PAIR=en_de ./covost2/install.sh
SPLIT=validation ./covost2/install.sh
```

## 공식 경로가 막혀 있어서 미러에서 받는다

공식 배포([facebookresearch/covost](https://github.com/facebookresearch/covost), 2023년
보관 처리)는 번역 TSV 만 주고, 오디오는 **Common Voice 4.0** 에서 가져오라고 한다. 그런데
Common Voice 는 2025년 10월부터 Mozilla Data Collective 에서만 배포되고, 4.0 같은 옛 판은
메일로 요청해야 링크를 받는다. Hugging Face 의 `facebook/covost2` 는 로딩 스크립트만 있어서
지금 `datasets` 로는 돌지 않는다.

그래서 [fixie-ai/covost2](https://huggingface.co/datasets/fixie-ai/covost2) 를 쓴다. 공개
미러이고, 분할별 개수가 공식 TSV 와 같으며, parquet 안에 원래 mp3 가 그대로 들어 있다.
**비공식 미러다** — 공식 판을 구하면 그걸로 바꾸는 게 맞다.

## 오디오는 parquet 안의 mp3 다

Common Voice mp3 는 대개 48 kHz 다. `convert.py` 가 클립마다 한 번 16 kHz mono PCM16 wav 로
디코딩해 `data/wav16k/` 에 쓴다. 다시 돌리면 이미 쓴 파일은 건너뛴다.

## 항목과 세션

클립 하나가 항목 하나이고 `group` 도 그 클립이다 — **항목마다 새 세션**이다. 사람도
문장도 서로 무관하다.

## 만들어지는 것

```
covost2/
  data/<pair>/<split>-*.parquet            받은 것 (git 에 없다)
  data/wav16k/<pair>/<split>/<id>.wav      디코딩한 것 (git 에 없다)
  dataset.yml                              생성물
  manifest.jsonl                           생성물
  audio -> data/wav16k/<pair>/<split>      심볼릭 링크
```
