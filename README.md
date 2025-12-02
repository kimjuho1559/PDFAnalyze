# PDFAnalyze — PDF 학습 도우미 (PyQt + AWS Bedrock Knowledge Base)

PDF 문서를 AWS Bedrock Knowledge Base(KB)에 업로드/동기화하고, KB 기반으로 질의응답을 수행하는 학습 도우미입니다.  
GUI(PyQt6)로 간편하게 문서를 관리하고 질문할 수 있으며, CLI 유틸리티로 대량 업로드 및 동기화도 지원합니다.

- GUI: `gui_app.py`

## 주요 기능
- 질문하기(ASK)
  - KB 기반 질의응답(strands retrieve 도구 사용)
  - 필요 시 웹 보조(http_request) 허용 옵션
- 문서 관리(DOCS)
  - PDF 파일을 선택하여 S3 업로드
  - KB 동기화(인덱싱 작업 시작)
  - KB 상태 점검(데이터 소스 연결 여부 포함)

## 디렉터리 구조
```
pdfAnalyze/
├─ gui_app.py                # PyQt6 GUI 앱
├─ requirements.txt          # 의존성 목록
└─ README.md                 # 프로젝트 안내 (본 문서)
```

## 요구 사항
- Python 3.10+ 권장
- AWS 계정 및 권한(IAM)  
  - Bedrock(Knowledge bases, Agents) 사용 권한
  - S3 업로드 권한
- AWS 리전/자격 증명 설정
  - 환경 변수 또는 AWS CLI 프로필 사용
- 의존성(pip)
  - PyQt6, boto3, strands, strands_tools, requests

의존성 설치:
```
pip install -r requirements.txt
```

## 설치
Windows 기준
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS/Linux 기준
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## AWS 자격 증명/환경 변수
- 표준 AWS CLI 자격 증명(예: `aws configure`)을 사용하거나 아래 환경 변수를 지정합니다.
  - `AWS_REGION` 또는 `AWS_DEFAULT_REGION` (예: `ap-northeast-2`)
  - `AWS_PROFILE` (선택)
  - `KNOWLEDGE_BASE_ID` (선택: GUI/CLI에서 직접 입력도 가능)

예:
```
set AWS_REGION=us-east-1
set KNOWLEDGE_BASE_ID=[]   # Windows(cmd)
# 또는
export AWS_REGION=us-east-1
export KNOWLEDGE_BASE_ID=[] # macOS/Linux
```

## 빠른 시작(Quick Start)
1) 의존성 설치: `pip install -r requirements.txt`  
2) AWS 자격 증명/리전 설정  
3) S3 버킷 준비 및 KB 생성/연결(Bedrock Console)  
4) GUI 실행 또는 CLI로 문서 업로드/동기화  
5) KB 기반 질의응답 수행

## GUI 사용 방법 (PyQt)
실행:
```
python gui_app.py
```

앱에서 다음을 입력/설정하세요.
- AWS Region: 예) `us-east-1`
- Knowledge Base ID: Bedrock KB ID
- S3 Bucket: 업로드 대상 버킷 이름
- S3 Prefix: 업로드 경로 prefix (기본값 `documents/` 권장)

탭별 동작:
- 질문하기
  - 질문을 입력하고 “질문하기” 클릭
  - “웹 보조 허용” 체크 시 http_request를 보조적으로 사용
- 문서 관리
  - “PDF 파일 추가” → 목록에 추가
  - “선택 파일 업로드(S3)” → S3에 업로드됨
  - “KB 동기화 시작” → KB 인덱싱 작업 시작(수 분 소요)
  - “KB 점검”은 환경/설정 영역의 “KB 점검” 버튼

## 문제 해결(Troubleshooting)
- 인증/권한 오류
  - AWS CLI로 `aws sts get-caller-identity` 점검
  - IAM 권한(Bedrock, S3) 확인
- 리전 오류
  - `AWS_REGION`/`AWS_DEFAULT_REGION` 재확인 (Bedrock, S3가 동일 리전에 있도록)
- KB/데이터 소스
  - Bedrock Console에서 해당 KB에 S3 데이터 소스가 연결되어 있는지 확인
  - 동기화 후 인덱싱 완료까지 수 분 소요
- 패키지 로드 실패
  - `pip install -r requirements.txt` 재실행
  - 가상환경 재활성화/IDE 재시작

## GitHub 업로드(푸시) 가이드
원격 저장소: `https://github.com/kimjuho1559/PDFAnalyze.git`

처음 푸시하는 경우:
```
git init
git add .
git commit -m "Initial commit: PDFAnalyze GUI/CLI, README, requirements"
git branch -M main
git remote add origin https://github.com/kimjuho1559/PDFAnalyze.git
git push -u origin main
```

이미 원격에 내용이 있는 경우:
```
# 로컬이 비어있다면 먼저 가져오기
git pull origin main --allow-unrelated-histories

# 충돌 해결 후 푸시
git push -u origin main
```
(주의) 히스토리 강제 덮어쓰기는 주의해서 사용하세요:
```
git push -u origin main --force
```