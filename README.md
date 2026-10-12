# Rendering Contest — 3D Reconstruction Pipeline

단일 영상에서 카메라 포즈를 추정하고 Gaussian Splatting 또는 NeuS-facto를 학습해 새로운 시점의 영상과 3D 메시를 생성하는 파이프라인입니다.

| 항목 | 내용 |
|---|---|
| 프로젝트 시점 | 2026년 봄학기 |
| README 정리일 | 2026-10-13 |
| 본인 기여 | 학습·재개·추출 자동화, 카메라 경로 생성, 메시 변환, 렌더링 파이프라인 구성 |
| 기술 | Python, Bash, Nerfstudio, Gaussian Splatting, NeuS, COLMAP, Open3D |
| 공개 상태 | 공개 저장소 |

## 프로젝트 목표

- 촬영 영상에서 COLMAP 기반 카메라 포즈 복원
- 3D Gaussian Splatting으로 고품질 novel-view rendering
- NeuS-facto로 SDF 기반 polygon mesh 복원
- PLY를 OBJ/GLB로 변환하고 UV texture 생성
- 커스텀 카메라 경로와 fly-in 영상을 자동 생성

## 본인 기여

- 영상 입력부터 전처리·학습·추출·렌더링까지 이어지는 shell pipeline 작성
- Gaussian Splatting과 NeuS 학습/재개 스크립트 분리
- Gaussian PLY의 mesh 변환 및 GLB export 도구 구성
- COLMAP 카메라 시각화와 사용자 지정 camera path 생성
- GPU, checkpoint, loss, disk 사용량 모니터링 자동화
- 환경 설치와 결과물 위치를 상세 문서화

## 디렉터리 구조

```text
.
├── README.md
└── Rendering_PJ/
    ├── README.md              # 상세 실행 가이드
    ├── config.sh              # 전역 실험 설정
    ├── pipeline.sh            # 전체 파이프라인
    ├── gs/                    # Gaussian Splatting 학습·추출
    ├── nerf/                  # NeuS-facto 학습·추출
    ├── scripts/               # 변환·렌더링·모니터링 도구
    ├── data/                  # 로컬 입력 데이터(원격 제외 대상)
    ├── meshes/                # 생성된 3D 결과
    └── renders/               # 렌더링 결과
```

## 빠른 시작

```bash
cd Rendering_PJ
# config.sh에서 DATA, EXP, MODEL 등을 설정
bash pipeline.sh --dry-run
bash pipeline.sh
```

상세 옵션과 환경 설치 방법은 [Rendering_PJ/README.md](Rendering_PJ/README.md)를 참고하세요.

## 데이터 및 라이선스

대용량 원본 영상, 학습 체크포인트, 개인 촬영 데이터는 공개 전 별도로 권리를 확인해야 합니다. 저장소에 포함된 제3자 Nerfstudio 코드는 해당 원 프로젝트의 라이선스를 따릅니다.
