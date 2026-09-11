# FLEURS

[google/fleurs](https://huggingface.co/datasets/google/fleurs) — FLoRes-101 문장을
102개 언어로 낭독한 **n-way 병렬** 코퍼스. 문장 id 가 언어 간에 공유되므로
`소스 언어 오디오` + `타깃 언어 전사` 를 붙이면 그대로 음성번역 평가쌍이 된다.

공개 데이터셋이다 — Hugging Face 계정도 토큰도 `hf auth login` 도 필요 없다.
401 이 나면 그건 다른 (비공개) 데이터셋이다.

```bash
./fleurs/install.sh                            # en_us 오디오 + ko_kr/de_de 전사
SRC=en_us TGT="ko_kr de_de ja_jp" ./fleurs/install.sh
```

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

## 항목과 세션

항목 하나가 문장 하나이고, `group` 도 그 문장이다 — 즉 **항목마다 새 세션**이다.
서로 무관한 낭독 문장이라 앞 발화의 문맥이 넘어오면 오염이다.

## 만들어지는 것

```
fleurs/
  data/<locale>/test.tsv            받은 것 (git 에 없다)
  data/<locale>/audio/test/*.wav    받은 것, 소스 언어만 (git 에 없다)
  dataset.yml                       생성물
  manifest.jsonl                    생성물
  audio -> data/<src>/audio/test    심볼릭 링크
```

낭독체라 TED 실연설보다 쉽고, 비교 대상 문헌은 IWSLT 계열이 아니라
Whisper/SeamlessM4T 계열이다. 대신 **소스 언어를 바꿀 수 있다** — `SRC=ko_kr` 로
ko→en 도 바로 된다(ko 오디오를 받아야 하고 ASR 도 ko 가중치를 써야 한다).
