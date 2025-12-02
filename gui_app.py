"""
PyQt GUI for PDF 학습 도우미 (AWS Bedrock Knowledge Base 기반)

기능:
- 질문하기 탭: KB 기반 질의응답 (옵션: 웹 보조 허용)
- 문서 관리 탭: PDF 업로드(S3) 및 KB 동기화, KB 상태 점검

요구사항:
- pip install PyQt6 boto3 strands strands_tools
- AWS 자격증명(profile/role) 및 리전 설정
- KNOWLEDGE_BASE_ID, S3 버킷 등 입력

실행:
  python gui_app.py
"""
from __future__ import annotations

import os
import sys
import traceback
from typing import List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QPlainTextEdit, QCheckBox,
    QGroupBox, QFormLayout, QMessageBox, QListWidget, QListWidgetItem, QSizePolicy
)

# 외부 종속 모듈 로드 (런타임 에러 핸들링)
_load_errors = []

try:
    import boto3
    from botocore.exceptions import ClientError
except Exception as e:
    _load_errors.append(f"boto3 import 오류: {e}")

try:
    # 에이전트/도구는 런타임 워커에서 지연 로드
    from kb_for_rrag import PAPER_AGENT_PROMPT  # 프롬프트 재사용
except Exception as e:
    _load_errors.append(f"kb_for_rrag import 오류: {e}")

try:
    from pdf_uploader import PDFUploader
except Exception as e:
    _load_errors.append(f"pdf_uploader import 오류: {e}")


# ---------- Worker Threads ----------

class KBValidateWorker(QThread):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, kb_id: str, region: Optional[str]):
        super().__init__()
        self.kb_id = kb_id
        self.region = region

    def run(self):
        try:
            session_kwargs = {}
            if self.region:
                session_kwargs["region_name"] = self.region
            client = boto3.client("bedrock-agent", **session_kwargs)
            kb = client.get_knowledge_base(knowledgeBaseId=self.kb_id)["knowledgeBase"]
            status = kb.get("status")
            msg = [f"[KB] ID={self.kb_id}, 상태={status}"]
            ds = client.list_data_sources(knowledgeBaseId=self.kb_id)
            summaries = ds.get("dataSourceSummaries", [])
            if not summaries:
                msg.append("[KB] 데이터 소스: 없음 (S3 데이터 소스 추가 필요)")
            else:
                msg.append(f"[KB] 데이터 소스: {len(summaries)}개")
                for s in summaries:
                    name = s.get("name") or s.get("dataSourceId")
                    msg.append(f" - {name}")
            self.finished.emit("\n".join(msg))
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            self.failed.emit(f"[KB 점검 실패] {code}: {e}")
        except Exception as e:
            self.failed.emit(f"[KB 점검 실패] {e}\n{traceback.format_exc()}")


class AskWorker(QThread):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, kb_id: str, region: Optional[str], prompt: str, allow_web: bool):
        super().__init__()
        self.kb_id = kb_id
        self.region = region
        self.prompt = prompt
        self.allow_web = allow_web

    def run(self):
        try:
            os.environ["KNOWLEDGE_BASE_ID"] = self.kb_id

            if self.region:
                os.environ["AWS_REGION"] = self.region
                os.environ["AWS_DEFAULT_REGION"] = self.region
                
            # strands 및 tools는 워커 내부에서 로드 (GUI 블로킹 방지)
            from strands import Agent
            from strands_tools import retrieve, http_request

            tools = [retrieve]
            if self.allow_web:
                tools.append(http_request)

            # 에이전트 생성
            agent = Agent(
                model="us.amazon.nova-lite-v1:0",
                system_prompt=PAPER_AGENT_PROMPT,
                tools=tools
            )
            # 응답
            resp = agent(self.prompt)
            self.finished.emit(str(resp))
        except Exception as e:
            self.failed.emit(f"[질문 처리 오류] {e}\n{traceback.format_exc()}")


class UploadWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, bucket: str, kb_id: Optional[str], prefix: str, files: List[str]):
        super().__init__()
        self.bucket = bucket
        self.kb_id = kb_id
        self.prefix = prefix
        self.files = files

    def run(self):
        try:
            uploader = PDFUploader(self.bucket, self.kb_id)
            uploaded = []
            for f in self.files:
                self.progress.emit(f"[업로드] {f} ...")
                uri = uploader.upload_pdf(f, self.prefix)
                uploaded.append(uri)
                self.progress.emit(f"[완료] {uri}")
            self.finished.emit(f"총 {len(uploaded)}개 업로드 완료")
        except Exception as e:
            self.failed.emit(f"[업로드 실패] {e}\n{traceback.format_exc()}")


class SyncWorker(QThread):
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, kb_id: str):
        super().__init__()
        self.kb_id = kb_id

    def run(self):
        try:
            uploader = PDFUploader(bucket_name="dummy", knowledge_base_id=self.kb_id)  # bucket은 사용 안함
            uploader.sync_knowledge_base()
            self.finished.emit("KB 동기화 작업 시작 요청 완료 (완료까지 수 분 소요)")
        except Exception as e:
            self.failed.emit(f"[동기화 실패] {e}\n{traceback.format_exc()}")


# ---------- GUI ----------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF 학습 도우미 (PyQt)")
        self.resize(980, 720)

        if _load_errors:
            QMessageBox.warning(self, "의존성 경고", "다음 모듈 로드 중 문제가 발생했습니다:\n" + "\n".join(_load_errors))

        self._build_ui()

        # Workers
        self._ask_worker: Optional[AskWorker] = None
        self._kb_worker: Optional[KBValidateWorker] = None
        self._upload_worker: Optional[UploadWorker] = None
        self._sync_worker: Optional[SyncWorker] = None

    # ---- UI 구성 ----
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)

        root.addWidget(self._build_config_group())
        tabs = QTabWidget()
        tabs.addTab(self._build_ask_tab(), "질문하기")
        tabs.addTab(self._build_manage_tab(), "문서 관리")
        root.addWidget(tabs)

        self.setCentralWidget(central)

    def _build_config_group(self) -> QGroupBox:
        grp = QGroupBox("환경/설정")
        form = QFormLayout(grp)

        self.ed_region = QLineEdit(os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "")
        self.ed_kb = QLineEdit(os.environ.get("KNOWLEDGE_BASE_ID") or "")
        self.ed_bucket = QLineEdit("")
        self.ed_prefix = QLineEdit("documents/")

        btn_validate = QPushButton("KB 점검")
        btn_validate.clicked.connect(self.on_validate_kb)

        form.addRow(QLabel("AWS Region"), self._hbox(self.ed_region, self._spacer()))
        form.addRow(QLabel("Knowledge Base ID"), self._hbox(self.ed_kb, btn_validate))
        form.addRow(QLabel("S3 Bucket"), self.ed_bucket)
        form.addRow(QLabel("S3 Prefix"), self.ed_prefix)

        return grp

    def _build_ask_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        self.cb_allow_web = QCheckBox("웹 보조 허용 (http_request)")
        self.cb_allow_web.setChecked(False)

        self.ed_prompt = QPlainTextEdit()
        self.ed_prompt.setPlaceholderText("교재/강의자료에 대한 질문을 입력하세요.\n예) '2장 프로세스 관리의 핵심 개념을 요약해줘' 또는 'AWS-Service-IAM 자료에서 IAM 정의를 KB 근거와 함께 알려줘'")
        self.ed_prompt.setMinimumHeight(120)

        btn_row = QHBoxLayout()
        btn_ask = QPushButton("질문하기")
        btn_ask.clicked.connect(self.on_ask)
        btn_clear = QPushButton("지우기")
        btn_clear.clicked.connect(lambda: self.ed_prompt.setPlainText(""))
        btn_row.addWidget(btn_ask)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()

        self.txt_answer = QPlainTextEdit()
        self.txt_answer.setReadOnly(True)
        self.txt_answer.setPlaceholderText("응답이 여기에 표시됩니다 (근거: 파일/섹션/페이지 포함).")

        lay.addWidget(self.cb_allow_web)
        lay.addLayout(btn_row)
        lay.addWidget(QLabel("질문"))
        lay.addWidget(self.ed_prompt)
        lay.addWidget(QLabel("응답"))
        lay.addWidget(self.txt_answer)

        return w

    def _build_manage_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        # 파일 선택
        file_row = QHBoxLayout()
        btn_add_files = QPushButton("PDF 파일 추가")
        btn_add_files.clicked.connect(self.on_add_files)
        btn_clear = QPushButton("목록 비우기")
        btn_clear.clicked.connect(self.on_clear_files)
        file_row.addWidget(btn_add_files)
        file_row.addWidget(btn_clear)
        file_row.addStretch()

        self.list_files = QListWidget()
        self.list_files.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # 동작 버튼
        action_row = QHBoxLayout()
        btn_upload = QPushButton("선택 파일 업로드(S3)")
        btn_upload.clicked.connect(self.on_upload_files)
        btn_sync = QPushButton("KB 동기화 시작")
        btn_sync.clicked.connect(self.on_sync_kb)
        action_row.addWidget(btn_upload)
        action_row.addWidget(btn_sync)
        action_row.addStretch()

        self.txt_log = QPlainTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setPlaceholderText("업로드/동기화/점검 로그가 표시됩니다.")

        lay.addLayout(file_row)
        lay.addWidget(self.list_files)
        lay.addLayout(action_row)
        lay.addWidget(QLabel("로그"))
        lay.addWidget(self.txt_log)

        return w

    # ---- 유틸 ----
    def _hbox(self, *widgets):
        w = QWidget()
        lay = QHBoxLayout(w)
        for wd in widgets:
            if wd is None:
                continue
            lay.addWidget(wd)
        return w

    def _spacer(self):
        s = QWidget()
        s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        return s

    def _append_log(self, text: str):
        self.txt_log.appendPlainText(text)

    # ---- Slots ----
    def on_validate_kb(self):
        kb_id = self.ed_kb.text().strip()
        region = self.ed_region.text().strip() or None
        if not kb_id:
            QMessageBox.warning(self, "입력 필요", "Knowledge Base ID를 입력하세요.")
            return
        self._append_log(f"[점검] KB={kb_id}, Region={region or '(기본)'}")
        self._kb_worker = KBValidateWorker(kb_id, region)
        self._kb_worker.finished.connect(lambda msg: self._append_log(msg))
        self._kb_worker.failed.connect(lambda err: self._append_log(err))
        self._kb_worker.start()

    def on_ask(self):
        kb_id = self.ed_kb.text().strip()
        region = self.ed_region.text().strip() or None
        prompt = self.ed_prompt.toPlainText().strip()
        allow_web = self.cb_allow_web.isChecked()

        if not kb_id:
            QMessageBox.warning(self, "입력 필요", "Knowledge Base ID를 입력하세요.")
            return
        if not prompt:
            QMessageBox.information(self, "입력 필요", "질문을 입력하세요.")
            return

        self.txt_answer.setPlainText("생각 중... (KB 검색 중)")
        self._ask_worker = AskWorker(kb_id, region, prompt, allow_web)
        self._ask_worker.finished.connect(self.txt_answer.setPlainText)
        self._ask_worker.failed.connect(lambda err: self.txt_answer.setPlainText(err))
        self._ask_worker.start()

    def on_add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "PDF 파일 선택", "", "PDF Files (*.pdf)")
        for f in files:
            item = QListWidgetItem(f)
            self.list_files.addItem(item)
        if files:
            self._append_log(f"[선택] {len(files)}개 파일 추가")

    def on_clear_files(self):
        self.list_files.clear()
        self._append_log("[선택] 목록 비움")

    def on_upload_files(self):
        bucket = self.ed_bucket.text().strip()
        kb_id = self.ed_kb.text().strip() or None
        prefix = self.ed_prefix.text().strip() or "documents/"
        if not bucket:
            QMessageBox.warning(self, "입력 필요", "S3 Bucket을 입력하세요.")
            return
        files = [self.list_files.item(i).text() for i in range(self.list_files.count())]
        if not files:
            QMessageBox.information(self, "파일 없음", "업로드할 PDF 파일을 추가하세요.")
            return

        self._append_log(f"[업로드 시작] {len(files)}개 파일 → s3://{bucket}/{prefix}")
        self._upload_worker = UploadWorker(bucket, kb_id, prefix, files)
        self._upload_worker.progress.connect(self._append_log)
        self._upload_worker.finished.connect(lambda msg: self._append_log(f"[업로드 완료] {msg}"))
        self._upload_worker.failed.connect(lambda err: self._append_log(err))
        self._upload_worker.start()

    def on_sync_kb(self):
        kb_id = self.ed_kb.text().strip()
        if not kb_id:
            QMessageBox.warning(self, "입력 필요", "Knowledge Base ID를 입력하세요.")
            return
        self._append_log(f"[동기화 요청] KB={kb_id}")
        self._sync_worker = SyncWorker(kb_id)
        self._sync_worker.finished.connect(lambda msg: self._append_log(f"[동기화] {msg}"))
        self._sync_worker.failed.connect(lambda err: self._append_log(err))
        self._sync_worker.start()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
