# MCIF

FBK 가 ACL 2023 발표 영상으로 만든 벤치마크([FBK-MT/MCIF](https://huggingface.co/datasets/FBK-MT/MCIF),
CC BY 4.0). IWSLT 2025 동시통역 트랙의 **test**, 2026 트랙의 **dev** 가 이것이다. 원래는
ASR·번역·질의응답·요약을 한데 묶은 것이고, 여기서는 **번역 참조가 있는 발표 21개**만 쓴다.

```bash
./mcif/install.sh                     # en → de, zh
TGT="de it zh" ./mcif/install.sh
```

번역 방향은 en→de·it·zh 뿐이다. 한국어는 없다.

## 항목 하나가 발표 하나다

이 리포에서 발표 전체를 한 항목으로 흘리는 곳은 여기와 `bstc/` 뿐이다. 원칙은 ACL 60/60
처럼 **문장 하나가 항목 하나**지만, MCIF 배포판에는 문장 시각이 전혀 없다.

- 영어 전사는 발표마다 **문단 하나**다(task="ASR").
- 독일어·중국어 번역은 문장마다 한 줄이지만(21개 발표에 919줄) 오디오의 어느 구간인지는
  적혀 있지 않다(task="TRANS").

자를 근거가 없으므로 발표를 통째로 흘리고, 참조도 통째로 넣는다. 번역은 줄바꿈을 그대로
둔다. `group` 은 발표이고 항목도 발표 하나라 결국 항목마다 새 세션이다.

## 채점에서 달라지는 것

- **WER 은 그대로 된다.** 발표 전체의 가설과 전사를 한 번에 비교하면 된다.
- **번역 지표는 재분절이 먼저다.** 시스템이 낸 조각과 참조 문장의 경계가 맞지 않아서,
  문장 단위 BLEU·COMET 을 내려면 mwerSegmenter 같은 재분절로 가설을 참조 문장에 맞춰
  잘라야 한다. IWSLT 공식 평가(OmniSTEval)가 이렇게 한다. bench 의 재분절(`longform: true`)은
  문장 시각(`offset`)이 있어야 돌아서 이 데이터에는 쓸 수 없다.
- 지연(LAAL)의 소스 길이 `T` 는 발표 길이다(4~7분).

그래서 bench 가 내는 숫자 중 **믿고 읽을 것**은 `wer`·`cer`, `fsl`, 정렬된 발표의
`token_emission` 이다. `bleu` 는 발표 하나를 한 쌍으로 본 값이라 문장 단위 BLEU 와 비교하지
않는다. `comet` 은 입력이 모델 한계(512 토큰)를 넘어 잘리므로 쓰지 않는다. `laal`·`yaal` 은
발표 전체를 문장 하나로 보는 값이라 의미가 없다.

IWSLT 베이스라인이 쓰던 분절 yaml(`mcif_translation.yaml`)은 배포 주소가 404 라 쓰지 않는다.

## 만들어지는 것

```
mcif/
  data/MCIF.long.<lang>.ref.xml.gz        받은 것 (git 에 없다)
  data/MCIF_DATA/LONG_AUDIOS/<talk>.wav   받은 것, 16 kHz mono (git 에 없다)
  dataset.yml                             생성물
  manifest.jsonl                          생성물
  audio -> data/MCIF_DATA/LONG_AUDIOS     심볼릭 링크
```

발표 wav 는 이미 계약 형식이라 디코딩 없이 링크만 건다.
