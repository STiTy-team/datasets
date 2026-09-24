# FLEURS

[google/fleurs](https://huggingface.co/datasets/google/fleurs) — FLoRes-101 문장을
102개 언어로 낭독한 **n-way 병렬** 코퍼스. 문장 id 가 언어 간에 공유되므로
`소스 언어 오디오` + `타깃 언어 전사` 를 붙이면 그대로 음성번역 평가쌍이 된다.

공개 데이터셋이다 — Hugging Face 계정도 토큰도 `hf auth login` 도 필요 없다.
401 이 나면 그건 다른 (비공개) 데이터셋이다.

```bash
./fleurs/install.sh                            # en_us 오디오 + ko_kr/de_de 전사 -> fleurs/en_us/
SRC=en_us TGT="ko_kr de_de ja_jp" ./fleurs/install.sh
SRC="en_us ko_kr" ./fleurs/install.sh          # 소스마다 데이터셋 하나 -> fleurs/en_us/, fleurs/ko_kr/
```

## 소스 언어 하나가 데이터셋 하나다

`convert.py --src <locale>` 은 `fleurs/<locale>/` 에 데이터셋을 만든다. 그래서 `ko_kr` 을
만들어도 `en_us` 는 그대로 남는다. bench 는 이 디렉토리를 이름으로 고른다 — 데이터셋 설정의
`dataset.name: fleurs/en_us`. 받은 원본(`data/`)은 모든 언어가 함께 쓴다.

`SRC` 에 여럿을 적으면 소스마다 한 번씩 변환하고, 받아 둔 나머지 언어가 모두 그 소스의 번역
참조가 된다(`SRC="en_us ko_kr"` 이면 `ko_kr` 데이터셋에 `en` 참조가 붙는다).

## 언어가 섞인 대화 (`../mix.py`)

```bash
SRC="ko_kr en_us" ./fleurs/install.sh               # 먼저 두 언어를 각각 만든다 (정렬까지)
uv run python mix.py fleurs --src ko_kr en_us       # -> fleurs/ko_kr+en_us/
uv run python mix.py fleurs --src ko_kr en_us --level -26 --cut 0.3
```

두 언어의 데이터셋을 이어 붙여 **대화를 합성한다.** 차례 하나가 FLEURS 문장 하나이고, 문장 id 하나는
데이터셋 전체에서 한 번만 말해진다. 손잡이와 규칙은 저장소 루트의 [`README.md`](../README.md#언어가-섞인-대화-mixpy)
에 있다. 예전 `fleurs/mix.py` 와 같은 인자면 결과가 바이트 단위로 같다.

차례마다 대화에 쓰인 모든 언어의 참조가 붙고, 자기 언어의 원문은 **다른 소스 데이터셋의 번역 참조에서**
가져온다. 그래서 소스마다 나머지 소스를 타깃으로 두고 만들어야 한다 — `SRC="ko_kr en_us"` 로 한 번에
만들면 그렇게 된다.

그 밖에 한 입력에 언어가 섞인 데이터셋이 필요하면 이 옆에 따로 만든다 — `dataset.yml` 의
`languages` 에 언어를 여럿 적고 항목마다 `src_lang` 을 두면 bench 쪽 설정은 그대로다.

기본 언어 집합은 `SRC=en_us`, `TGT="ko_kr de_de"` 다. 코드는
`en_us de_de ko_kr ja_jp cmn_hans_cn(zh) es_419 ar_eg fr_fr ...` 을 받는다
(`convert.py` 의 `LOCALES` 참조).

## 타깃을 늘려도 오디오는 다시 안 받는다

**소스 언어만 오디오가 필요하다.** 타깃은 전사 TSV 만 있으면 된다. 같은 문장이 모든
언어에 있으므로 manifest 하나가 en→ko, en→de, en→ja 를 동시에 받친다.
`install.sh` 도 소스에만 `audio/test.tar.gz` 를 받는다 — 타깃까지 받으면 아무도 읽지
않을 파일로 언어당 수백 MB 를 쓴다.

## TSV 는 `QUOTE_NONE` 으로 읽는다

`test.tsv` 는 **헤더가 없고**, 탭으로 나뉘며, 본문에 **따옴표 문자가 그대로** 들어 있다.

```
id  filename  raw_transcription  transcription  phonemes  num_samples  gender
```

기본 csv 설정으로 읽으면 따옴표 하나를 인용 필드의 시작으로 보고 **행을 합쳐 버린다.**
합쳐진 덩어리는 그냥 아주 긴 문장처럼 보이기 때문에 눈에 안 띈다. 실제로 2,916어절짜리
잔해가 표본에 섞여 모델 토큰 한계를 넘겼고, 런이 죽으면서 돈을 태웠다.

`convert.py` 는 `csv.QUOTE_NONE` 으로 읽고, 변환 전에 어절 수 분포를 찍은 뒤 200어절을
넘는 문장이 있으면 **변환을 거부한다.** 20문장짜리 스모크 테스트로는 그런 이상치가
안 걸리기 때문에 분포 검사를 자동으로 돌린다.

## 전사는 정규화본, 번역 참조는 원문

`transcription` 은 소문자에 문장부호가 없고, `raw_transcription` 은 FLoRes 원문 그대로다.
소스 전사에는 `transcription` 을 쓴다 — WER·CER 은 양쪽에서 대소문자와 문장부호를 지우고
비교하므로 대소문자·문장부호로는 차이가 없다(숫자 표기는 둘이 다를 수 있어 바꾸지 않았다). 번역 참조에는 `raw_transcription` 을 쓴다 — BLEU·COMET 은
대소문자와 문장부호를 번역의 일부로 채점하므로, 정규화본을 참조로 두면 제대로 쓴 번역이
전부 깎인다.

## 항목과 세션

항목 하나가 문장 하나이고, `group` 도 그 문장이다 — 즉 **항목마다 새 세션**이다.
서로 무관한 낭독 문장이라 앞 발화의 문맥이 넘어오면 오염이다.

## 만들어지는 것

```
fleurs/
  data/<locale>/test.tsv            받은 것 (git 에 없다)
  data/<locale>/audio/test/*.wav    받은 것, 소스 언어만 (git 에 없다)
  data/wav16k/<src>/test/*.wav      계약 형식으로 다시 쓴 소스 오디오 (git 에 없다)
  <src>/                            소스 언어 하나의 데이터셋 (git 에 없다)
    dataset.yml                     생성물 (name: fleurs/<src>)
    manifest.jsonl                  생성물
    alignment.jsonl                 생성물
    audio -> fleurs/data/wav16k/<src>/test   심볼릭 링크
  data/mixed/<이름>/test/*.wav      mix.py 가 합성한 대화 wav (git 에 없다)
  <src1>+<src2>[.<손잡이>]/         섞인 대화 데이터셋 (git 에 없다, ../mix.py 가 만든다)
```

낭독체라 TED 실연설보다 쉽고, 비교 대상 문헌은 IWSLT 계열이 아니라
Whisper/SeamlessM4T 계열이다. 대신 **소스 언어를 바꿀 수 있다** — `SRC=ko_kr TGT=en_us` 로
ko→en 데이터셋(`fleurs/ko_kr/`)이 따로 생긴다(ko 오디오를 받아야 하고 ASR 도 ko 가중치를 써야 한다).
