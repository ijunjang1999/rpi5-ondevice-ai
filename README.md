# Raspberry Pi 5 스마트 보안카메라 (온디바이스 AI)

Raspberry Pi 5와 USB 웹캠 하나로 만드는 보안카메라입니다. 모든 AI 추론은 **Pi 안에서(온디바이스)** 돌아갑니다.

```
웹캠 ─▶ 움직임 감지 ─▶ 사람 검출 ─▶ 얼굴 검출 ─▶ 얼굴 인식 ─▶ 이벤트 처리
        (MOG2)        (SSD-MobileNet   (YuNet)     (SFace,       · 스냅샷 / 녹화(사전 2초 포함)
                       v1 int8                      known/ 사진과 · CSV 기록
                       TFLite)                      코사인 유사도) · 텔레그램 알림
                                                                  · 웹 실시간 화면
```

| 단계 | 모델 / 방법 | 비고 |
|---|---|---|
| 움직임 감지 | OpenCV MOG2 배경 차분 (160×120) | 움직임이 있을 때만 무거운 모델을 돌려 전력과 CPU를 아낌 |
| 사람 검출 | SSD-MobileNet v1 (COCO, int8 TFLite, 300×300, NMS 내장) | 얼굴이 안 보여도 사람으로 잡힘 |
| 얼굴 검출 | YuNet (ONNX, OpenCV `FaceDetectorYN`) | 얼굴 위치와 랜드마크 5점 |
| 얼굴 인식 | SFace (ONNX, OpenCV `FaceRecognizerSF`) | 128차원 특징 벡터, 코사인 유사도 0.363 이상이면 같은 사람으로 판정 |

## 기능
- **누구인지 판정:** `known/<이름>/` 폴더에 사진을 넣어 두면 화면에 이름이 표시됩니다. 등록되지 않은 얼굴은 `Unknown`으로 표시됩니다.
- **이벤트 기록:** 사람이 나타나면 스냅샷을 저장하고 mp4로 녹화합니다. 녹화에는 감지 직전 2초가 포함됩니다. 기록은 `events/events.csv`에 남습니다.
- **웹 대시보드:** `http://<Pi IP>:8000`에서 실시간 영상, 지금 화면에 있는 사람, 최근 이벤트 목록을 볼 수 있습니다.
- **텔레그램 알림(무료):** 등록된 사람이면 "✅ 이름 님 확인", 미등록이면 "⚠️ 미등록 인물 감지"를 사진과 함께 보냅니다.

## 설치 (Pi)
```bash
git clone https://github.com/ijunjang1999/rpi5-ondevice-ai.git ~/security_cam
cd ~/security_cam
bash setup_pi.sh      # apt, Python 3.11 venv, 패키지, 모델 다운로드 (처음에는 Python 빌드로 ~10분)
```
> Pi OS Trixie의 기본 Python은 3.13입니다. `tflite-runtime` 2.14는 3.13용 패키지가 없고 numpy 2와도 맞지 않습니다. 그래서 pyenv로 Python 3.11을 따로 설치하고 `numpy==1.26.4`로 고정했습니다.

Windows PC에서 SSH로 보낼 때는 `.\deploy.ps1 -Setup`을 사용합니다. 기본 접속 대상은 `ssh rpi5`입니다.

## 사용법
```bash
# 1) 얼굴 등록: 웹캠으로 5장 촬영 (또는 known/이름/ 폴더에 사진을 직접 넣기)
.venv/bin/python tools/capture_face.py 홍길동
./run.sh --enroll          # 등록 결과만 확인

# 2) 실행
./run.sh                   # 브라우저에서 http://<Pi IP>:8000
./run.sh --show            # Pi 화면에도 창 띄우기 (q로 종료)
```

### 텔레그램 알림 설정
1. 텔레그램에서 `@BotFather`를 열고 `/newbot`으로 봇을 만든 뒤 **토큰**을 복사합니다.
2. 만든 봇의 대화방에 아무 메시지나 보냅니다.
3. `.venv/bin/python tools/telegram_setup.py <토큰>`을 실행합니다. chat_id를 자동으로 찾아 `config.local.json`에 저장합니다. 이 파일은 git에 올라가지 않습니다.

## 설정 (`config.json`)
| 키 | 기본값 | 의미 |
|---|---|---|
| `face.match_threshold` | 0.363 | 높일수록 엄격해짐 (다른 사람으로 잘못 인식하는 경우 감소, Unknown 증가) |
| `person.score` | 0.5 | 사람 검출 신뢰도 기준 |
| `motion.min_area_ratio` | 0.01 | 화면에서 이 비율 이상 바뀌면 움직임으로 판단 |
| `event.end_after_sec` | 5 | 사람이 사라진 뒤 이 시간이 지나면 이벤트 종료 |
| `event.unknown_alert_after_sec` | 3 | 이 시간 안에 누구인지 확인되지 않으면 미등록 알림 |
| `telegram.cooldown_sec` | 60 | 같은 사람에 대한 알림 최소 간격 |

## 구조
```
app.py               메인 루프
seccam/detectors.py  카메라 스레드, 움직임/사람/얼굴 모델
seccam/events.py     이벤트 상태 관리 (스냅샷, 녹화, CSV, 알림)
seccam/web.py        Flask MJPEG 스트림 + 대시보드
seccam/notify.py     텔레그램 전송 (별도 스레드)
seccam/draw.py       화면 표시 (한글 이름은 Pillow + 나눔폰트)
tools/               얼굴 등록 촬영, 텔레그램 설정
```

## 한계와 주의
- 정면 얼굴, 2~3m 이내, 밝은 조명에서 정확합니다. 옆얼굴, 마스크, 역광에서는 `Unknown`이 늘어납니다.
- 위조 방지 기능이 없어서 사진을 들이대도 속을 수 있습니다. 실제 출입 통제용으로는 쓰지 마세요.
- 얼굴 사진은 **본인 동의를 받은 사람만** 등록하세요. `known/`과 `events/`는 git에서 제외되어 있습니다.

## 모델 출처
- YuNet / SFace: [OpenCV Zoo](https://github.com/opencv/opencv_zoo) (Apache-2.0)
- SSD-MobileNet v1 (COCO, quantized): [TensorFlow Lite 예제 모델](https://storage.googleapis.com/download.tensorflow.org/models/tflite/coco_ssd_mobilenet_v1_1.0_quant_2018_06_29.zip) (Apache-2.0)
