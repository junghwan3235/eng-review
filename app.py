"""
지장이설 설계검토 Agent v3.1 — Streamlit 메인 앱
★ 버튼 기반 실행: 파일 업로드 후 "설계 검토하기" 버튼 클릭 시에만 분석 실행
"""
import streamlit as st
import io
from PIL import Image

from parser import parse_design_xlsx, format_parsed_summary, safe_str
from rule_checker import run_all_rules, check_quick_pass, build_checklist_status
from ai_reviewer import (
    full_ai_review,
    analyze_single_image,
    analyze_evidence_photo,
    compare_before_after,
)
from report_generator import generate_report

# ============================================================
# 페이지 설정
# ============================================================
st.set_page_config(
    page_title="지장이설 설계검토 Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# 사이드바
# ============================================================
with st.sidebar:
    st.title("⚙️ 설정")
    st.markdown("---")

    api_key = st.text_input(
        "🔑 OpenAI API Key",
        type="password",
        help="gpt-4o Vision API 사용을 위한 키",
        placeholder="sk-...",
    )

    model_choice = st.selectbox(
        "🤖 AI 모델 선택",
        options=["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini"],
        index=0,
        help="gpt-4o: 최고 정확도 (비용↑)\ngpt-4o-mini: 빠르고 저렴 (정확도↓)",
    )

    use_ai = st.checkbox("🤖 AI 보조 검토 사용", value=True)
    use_vision = st.checkbox("📷 개황도 Vision 분석", value=True)

    st.markdown("---")
    st.markdown("### 📌 검토 수준 안내")
    st.markdown("""
    🔴 **강화검토** (자동)
    - 접속코어, 공사근거, 사업구분 등
    - 규칙 기반으로 자동 판정

    🟡 **보조검토** (AI)
    - 개황도 이미지 분석
    - 종합 맥락 검토

    🟢 **빠른통과**
    - 기입 여부만 확인
    """)

    st.markdown("---")
    st.markdown("### 📝 검토담당자 발췌 문제점")
    st.caption("입력 시 AI가 해당 항목을 우선·심층 분석합니다.")
    expert_notes_text = st.text_area(
        "발췌 문제점 직접 입력",
        height=120,
        placeholder="예시:\n- 단순이설 가능 구간인데 절체이설로 설계\n- 신설케이블 코어수 과다 (기설 48C → 신설 288C)\n- A함체 접속코어 과다산출\n- 함체 위치 부적정 (6차선 도로변)",
        label_visibility="collapsed",
    )
    expert_notes_file = st.file_uploader(
        "📎 문제점 파일 업로드 (.txt)",
        type=["txt", "md"],
        help="검토 문제점이 담긴 텍스트 파일을 업로드",
        key="expert_file",
    )

    # 파일 업로드 내용 + 직접 입력 합산
    expert_notes = expert_notes_text or ""
    if expert_notes_file:
        try:
            file_content = expert_notes_file.read().decode("utf-8", errors="ignore")
            expert_notes = (expert_notes + "\n\n" + file_content).strip() if expert_notes else file_content
        except Exception:
            pass
    if expert_notes:
        st.success(f"✅ 검토 참고 데이터 {len(expert_notes)}자 입력됨 — AI 분석에 반영됩니다.")

    st.markdown("---")
    st.caption("v3.1 | OpenAI GPT-4o Vision API")

# ============================================================
# 메인 영역
# ============================================================
st.title("🔍 지장이설 설계검토 Agent v3.1")
st.markdown("표준설계서(xlsx) 업로드 → **설계 검토하기** 버튼 클릭 → 자동 규칙검토 + AI 보조검토 → 검토 리포트 생성")
st.markdown("---")

# ============================================================
# Step 1: 파일 업로드 (업로드만, 분석 미실행)
# ============================================================
col_upload, col_extra = st.columns([2, 1])

with col_upload:
    uploaded = st.file_uploader(
        "📁 설계표준안 xlsx 파일 업로드",
        type=["xlsx", "xls"],
        help="02_지장이설_설계표준안 양식의 xlsx 파일",
    )

with col_extra:
    extra_images = st.file_uploader(
        "📷 추가 이미지 업로드 (선택)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help="추가 현장사진, 이설요청서 등",
    )

# ★ 개황도/GIS 이미지 직접 업로드 (Vision 분석용)
st.markdown("---")
st.markdown("##### 🗺️ 개황도/GIS 이미지 업로드 (Vision AI 분석용)")
st.caption("xlsx 내부 이미지 추출이 어려울 경우, 직접 캡처/저장한 이미지를 업로드하면 AI가 정밀 분석합니다.")

img_col1, img_col2, img_col3 = st.columns(3)
with img_col1:
    upload_gis = st.file_uploader(
        "🌐 작업 전 GIS", type=["png", "jpg", "jpeg"], key="upload_gis",
        help="GIS 시스템에서 캡처한 선로 현황 이미지",
    )
with img_col2:
    upload_before = st.file_uploader(
        "📋 개황도(전)", type=["png", "jpg", "jpeg"], key="upload_before",
        help="이설 전 개황도(행정도) 이미지",
    )
with img_col3:
    upload_after = st.file_uploader(
        "📋 개황도(후)", type=["png", "jpg", "jpeg"], key="upload_after",
        help="이설 후 개황도(행정도) 이미지",
    )

# 사용자 업로드 이미지 dict 구성
user_uploaded_images = {}
if upload_gis:
    user_uploaded_images["작업 전 GIS"] = upload_gis.read()
    upload_gis.seek(0)
if upload_before:
    user_uploaded_images["개황도(전)"] = upload_before.read()
    upload_before.seek(0)
if upload_after:
    user_uploaded_images["개황도(후)"] = upload_after.read()
    upload_after.seek(0)

if user_uploaded_images:
    names = list(user_uploaded_images.keys())
    st.success(f"🗺️ 이미지 업로드 완료: {', '.join(names)}")

if not uploaded:
    st.info("👆 설계표준안 xlsx 파일을 업로드하세요.")
    st.stop()

# ============================================================
# ★ 파일 변경 감지 → 이전 결과 초기화
# ============================================================
file_key = f"{uploaded.name}_{uploaded.size}"
if st.session_state.get("_last_file") != file_key:
    st.session_state["_last_file"] = file_key
    st.session_state.pop("review_results", None)

# ============================================================
# Step 2: 파일 업로드 확인 + 검토 시작 버튼
# ============================================================
st.success(f"✅ **{uploaded.name}** 업로드 완료 — 아래 버튼을 눌러 검토를 시작하세요.")

# 업로드 이미지 미리보기
if user_uploaded_images:
    with st.expander("📷 업로드 이미지 미리보기", expanded=False):
        preview_cols = st.columns(len(user_uploaded_images))
        for i, (name, img_bytes) in enumerate(user_uploaded_images.items()):
            with preview_cols[i]:
                try:
                    st.image(Image.open(io.BytesIO(img_bytes)), caption=name, use_container_width=True)
                except Exception:
                    st.caption(f"📄 {name}")

st.markdown("---")

# ★★★ 검토 시작 버튼
run_review = st.button(
    "🔍 설계 검토하기",
    type="primary",
    use_container_width=True,
    help="클릭하면 파싱 → 규칙검토 → AI 분석을 순차 실행합니다",
)

# ============================================================
# Step 3: 분석 실행 (버튼 클릭 시에만)
# ============================================================
if run_review:
    progress = st.progress(0, text="📊 설계서 파싱 중...")

    # --- 파싱 ---
    try:
        data, sheet_images, snapshots = parse_design_xlsx(uploaded)
        all_extracted_images = []
        for imgs in sheet_images.values():
            if isinstance(imgs, list):
                all_extracted_images.extend(imgs)
    except Exception as e:
        st.error(f"❌ 파싱 오류: {str(e)}")
        st.markdown("""
**해결 방법:**
1. Excel에서 파일을 열고 **파일 → 다른 이름으로 저장 → xlsx** 로 재저장 후 다시 업로드
2. 파일이 `.xls` (구형 Excel) 형식이면 `.xlsx`로 변환 필요
3. 파일 크기가 너무 크면(50MB+) 불필요한 시트 삭제 후 재시도
        """)
        st.stop()

    progress.progress(30, text="🔴 규칙 기반 자동 검토 중...")

    # --- 규칙 검토 ---
    rule_results = run_all_rules(data)
    quick_results = check_quick_pass(data)

    progress.progress(50, text="🤖 AI 보조 검토 중...")

    # --- AI 검토 ---
    ai_result = None
    if use_ai and api_key:
        try:
            ai_result = full_ai_review(
                api_key=api_key,
                parsed_data=data,
                rule_results=rule_results,
                sheet_images=sheet_images if use_vision else {},
                model=model_choice,
                snapshots=snapshots if use_vision else {},
                user_images=user_uploaded_images if use_vision else {},
                expert_notes=expert_notes,
            )
        except Exception as e:
            ai_result = {
                "comprehensive": f"오류 발생: {str(e)}",
                "image_analyses": [], "comparison": "",
                "construction_understanding": "", "analysis_mode": "error",
            }
    elif use_ai and not api_key:
        st.warning("⚠️ AI 검토를 위해 사이드바에서 OpenAI API Key를 입력하세요.")

    progress.progress(100, text="✅ 검토 완료!")

    # --- 결과를 session_state에 저장 ---
    st.session_state["review_results"] = {
        "data": data,
        "sheet_images": sheet_images,
        "snapshots": snapshots,
        "all_extracted_images": all_extracted_images,
        "rule_results": rule_results,
        "quick_results": quick_results,
        "ai_result": ai_result,
        "user_uploaded_images": user_uploaded_images,
        "expert_notes": expert_notes,
    }
    st.rerun()

# ============================================================
# Step 4: 결과 표시 (session_state에 결과가 있을 때만)
# ============================================================
if "review_results" not in st.session_state:
    st.info("👆 모든 파일을 업로드한 후 **🔍 설계 검토하기** 버튼을 클릭하세요.")
    st.stop()

# 결과 꺼내기
results = st.session_state["review_results"]
data = results["data"]
sheet_images = results["sheet_images"]
snapshots = results["snapshots"]
all_extracted_images = results["all_extracted_images"]
rule_results = results["rule_results"]
quick_results = results["quick_results"]
ai_result = results["ai_result"]

if data.get("_parse_error"):
    st.warning(f"⚠️ 일부 파싱 경고: {data['_parse_error']}")

# ============================================================
# 기본정보 표시
# ============================================================
st.markdown("### 📋 설계서 기본정보")
c1, c2, c3, c4 = st.columns(4)
with c1:
    공사명_val = safe_str(data.get("공사명", ""))
    st.metric("공사명", (공사명_val[:25] + "...") if len(공사명_val) > 25 else (공사명_val or "미기입"))
with c2:
    st.metric("사업구분", safe_str(data.get("사업구분", "미기입")))
with c3:
    st.metric("공사방안", safe_str(data.get("공사방안", "미기입")))
with c4:
    공사비_val = data.get("공사비")
    try:
        공사비_display = f"{int(float(공사비_val)):,}원"
    except (TypeError, ValueError):
        공사비_display = safe_str(공사비_val) or "미기입"
    st.metric("공사비", 공사비_display)

# 추가 정보 펼치기
with st.expander("📋 파싱 상세 결과 보기", expanded=False):
    st.text(format_parsed_summary(data))
    st.markdown(f"**시트 목록**: {', '.join(data.get('_sheet_names', []))}")

    total_imgs = sum(len(v) for v in sheet_images.values() if isinstance(v, list))
    st.markdown(f"**추출 이미지**: {total_imgs}장")

    if snapshots:
        snap_info = ", ".join(f"{k}: {len(v.data):,}bytes" for k, v in snapshots.items())
        st.markdown(f"**📸 시트 스냅샷**: {len(snapshots)}장 ({snap_info})")

    cb = data.get("_checkboxes", {})
    if cb:
        checked_count = sum(1 for v in cb.values() if v)
        method = data.get("_checkbox_method", "unknown")
        method_label = {"ctrlProp": "XML 컨트롤", "cell_boolean": "셀 TRUE/FALSE",
                        "merged(ctrlProp+cell)": "XML+셀 병합", "none": "미검출"}.get(method, method)
        st.markdown(f"**체크박스**: {checked_count}/{len(cb)} 체크됨 (파싱 방식: {method_label})")
        checked_items = [name for name, val in cb.items() if val]
        if checked_items:
            st.markdown(f"  ✅ 체크된 항목: {', '.join(checked_items)}")

    # ★ 이설루트/신설정보 표시
    route_info = []
    if cb.get("기설통신주관로"): route_info.append("✅ 기설 통신주/관로 루트사용")
    if cb.get("병행관로전주"): route_info.append("✅ 병행 관로/전주 신설")
    if cb.get("단독관로전주"): route_info.append("✅ 단독 관로/전주 신설")
    if cb.get("한전주이설"): route_info.append("✅ 한전주 이설")
    if route_info:
        st.markdown(f"**이설루트**: {', '.join(route_info)}")
        기설상세 = safe_str(data.get("기설루트사용_상세"))
        if 기설상세:
            st.markdown(f"  → 기설루트 상세: {기설상세[:80]}")
        한전상세 = safe_str(data.get("한전주이설_상세"))
        if 한전상세:
            st.markdown(f"  → 한전주이설 상세: {한전상세[:80]}")

    design_info = []
    for key, label in [("절체이설", "절체이설"), ("용량증설", "용량증설"), ("다대화", "다대화")]:
        qty = safe_str(data.get(f"{key}_수량"))
        detail = safe_str(data.get(f"{key}_상세"))
        if qty and not qty.strip().startswith("0"):
            design_info.append(f"{label} {qty}: {detail[:60]}")
    if safe_str(data.get("함체신설_상세")):
        design_info.append(f"함체신설: {safe_str(data.get('함체신설_상세'))[:60]}")
    if design_info:
        st.markdown("**신설정보:**")
        for info in design_info:
            st.markdown(f"  - {info}")

    cables = data.get("_parsed_cables", [])
    if cables:
        st.markdown("**파싱된 케이블 정보:**")
        for c in cables:
            st.markdown(
                f"- `{c.label}`: {c.network_tier} "
                f"{c.total_cores}C/{c.used_cores}C ({c.usage_rate:.0%}) {c.length_m}m"
            )

st.markdown("---")

# ============================================================
# 검토 결과
# ============================================================
st.markdown("## 📋 검토 결과")

critical = [r for r in rule_results if r.severity == "CRITICAL"]
major = [r for r in rule_results if r.severity == "MAJOR"]
minor = [r for r in rule_results if r.severity in ("MINOR", "INFO")]

if critical:
    판정 = "🔴 보완요청"
elif major:
    판정 = "🟡 확인필요"
else:
    판정 = "🟢 적합"

m1, m2, m3, m4 = st.columns(4)
with m1:
    st.metric("종합 판정", 판정)
with m2:
    st.metric("🚨 심각", f"{len(critical)}건")
with m3:
    st.metric("⚠️ 주요", f"{len(major)}건")
with m4:
    st.metric("ℹ️ 참고", f"{len(minor)}건")

# 탭 구성
tab_brief, tab1, tab2, tab3, tab4, tab5, tab_guide = st.tabs([
    "📌 공사 개요 브리핑",
    "🔴 강화검토 결과",
    "📋 종합 체크리스트",
    "🤖 AI 종합 의견",
    "📷 이미지 분석",
    "📄 리포트 다운로드",
    "📖 사용자 가이드",
])

# --- Tab 1: 강화검토 ---
with tab1:
    if critical:
        st.error(f"🚨 **심각(CRITICAL) 지적사항: {len(critical)}건** — 즉시 보완 필요")
        for r in critical:
            with st.expander(f"🚨 [{r.code}] {r.message}", expanded=True):
                st.markdown(f"**카테고리**: {r.category}")
                st.markdown(f"**권고사항**: {r.recommendation}")
                if r.savings_hint:
                    st.info(f"💰 {r.savings_hint}")

    if major:
        st.warning(f"⚠️ **주요(MAJOR) 지적사항: {len(major)}건** — 확인 필요")
        for r in major:
            with st.expander(f"⚠️ [{r.code}] {r.message}"):
                st.markdown(f"**카테고리**: {r.category}")
                st.markdown(f"**권고사항**: {r.recommendation}")

    if minor:
        st.info(f"ℹ️ **참고사항: {len(minor)}건**")
        for r in minor:
            with st.expander(f"ℹ️ [{r.code}] {r.message}"):
                st.markdown(f"**카테고리**: {r.category}")
                st.markdown(f"**권고사항**: {r.recommendation}")

    if not rule_results:
        st.success("✅ 자동 규칙 검토에서 지적사항이 발견되지 않았습니다.")

# --- Tab 브리핑: 공사 개요 브리핑 ---
with tab_brief:
    st.markdown("### 📌 공사 개요 브리핑")
    st.caption("처음 이 공사를 검토하는 담당자를 위한 종합 브리핑입니다. 엑셀 파싱 데이터 및 Vision 분석 결과를 종합했습니다.")

    cb_all = data.get("_checkboxes", {})

    # ══════════════════════════════════════════
    # 1. 공사 사유
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 1. 공사 사유")

    requesters = []
    if cb_all.get("이설요청_한전"):      requesters.append("한전")
    if cb_all.get("이설요청_지자체"):    requesters.append("지자체")
    if cb_all.get("이설요청_공공기관"): requesters.append("공공기관")
    if cb_all.get("이설요청_기타"):      requesters.append("기타")
    requester_str = " / ".join(requesters) if requesters else (safe_str(data.get("요청주체")) or "미확인")

    사업구분_val = safe_str(data.get("사업구분")) or "미기입"
    공사방안_val = safe_str(data.get("공사방안")) or "미기입"
    공문번호_val = safe_str(data.get("공문번호")) or "미기입"
    영배등록_val = "✅ 등록됨" if cb_all.get("이설요청_영배시스템") else "❌ 미등록"

    st.markdown(f"""| 항목 | 내용 |
|------|------|
| **요청 주체** | {requester_str} |
| **사업 구분** | {사업구분_val} |
| **공사 방안** | {공사방안_val} |
| **이설요청 공문번호** | {공문번호_val} |
| **영배시스템 등록** | {영배등록_val} |""")

    reason_parts = []
    if "한전" in requester_str:      reason_parts.append("한전 전주 이설 요청에 따른 지장이설")
    if "지자체" in requester_str:    reason_parts.append("지자체 도로공사로 인한 통신선로 지장이설")
    if "공공기관" in requester_str:  reason_parts.append("공공기관 공사로 인한 지장이설")
    if not reason_parts:
        reason_parts.append(f"{사업구분_val} 사업에 따른 통신선로 지장이설")

    with st.container(border=True):
        st.markdown(f"**📋 공사 사유 요약**\n\n"
                    f"{' '.join(reason_parts)}. 공사 방안은 **{공사방안_val}**으로 설계되었습니다.")

    # ══════════════════════════════════════════
    # 2. 공사 환경
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 2. 공사 환경")

    현장주소_val = safe_str(data.get("현장주소")) or "미기입"
    st.markdown(f"**현장 위치**: {현장주소_val}")

    route_parts = []
    if cb_all.get("기설통신주관로"):
        r = "기설 통신주/관로 루트 사용"
        기설상세 = safe_str(data.get("기설루트사용_상세"))
        if 기설상세: r += f" — {기설상세}"
        route_parts.append(r)
    if cb_all.get("병행관로전주"):  route_parts.append("병행 관로/전주 신설")
    if cb_all.get("단독관로전주"):  route_parts.append("단독 관로/전주 신설")
    if cb_all.get("한전주이설"):
        r = "한전주 이설 포함"
        한전상세 = safe_str(data.get("한전주이설_상세"))
        if 한전상세: r += f" — {한전상세}"
        route_parts.append(r)

    if route_parts:
        st.markdown("**이설 루트:**")
        for r in route_parts:
            st.markdown(f"- {r}")
    else:
        st.markdown("**이설 루트**: 정보 미기입")

    if ai_result and ai_result.get("construction_understanding"):
        with st.expander("🧠 Vision AI가 파악한 현장 환경", expanded=True):
            st.markdown(ai_result["construction_understanding"])

    # ══════════════════════════════════════════
    # 3. 공사 방법
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 3. 공사 방법")

    cables = data.get("_parsed_cables", [])
    existing_cables = [c for c in cables if "기설" in c.label]
    new_cables      = [c for c in cables if "다대화" in c.label or ("기설" not in c.label and c.label)]

    if existing_cables:
        st.markdown("#### 📡 기설 케이블 (이설/철거 대상)")
        for c in existing_cables:
            usage_pct = f"{c.usage_rate:.0%}" if c.usage_rate else "—"
            st.markdown(
                f"- **{c.label}**: {c.network_tier} | {c.cable_type} | "
                f"전체 {c.total_cores}C / 사용 {c.used_cores}C ({usage_pct}) | {c.length_m}m"
            )

    if new_cables:
        st.markdown("#### 🆕 신설/다대화 케이블")
        for c in new_cables:
            st.markdown(
                f"- **{c.label}**: {c.network_tier} | {c.cable_type} | "
                f"{c.total_cores}C | {c.length_m}m"
            )

    work_items = []
    for key, label in [("절체이설", "절체이설"), ("용량증설", "용량증설"), ("다대화", "다대화")]:
        qty    = safe_str(data.get(f"{key}_수량"))
        detail = safe_str(data.get(f"{key}_상세"))
        if qty and not qty.strip().startswith("0"):
            work_items.append(f"**{label}** ({qty}): {detail}")

    함체신설 = safe_str(data.get("함체신설_상세"))
    if 함체신설:
        work_items.append(f"**함체 신설**: {함체신설}")

    if work_items:
        st.markdown("#### 🔧 공사 세부 내용")
        for w in work_items:
            st.markdown(f"- {w}")

    enclosures = data.get("_parsed_enclosures", [])
    if enclosures:
        st.markdown("#### 🏗️ 함체 정보")
        for e in enclosures:
            label_e  = getattr(e, "label", "")
            pole_id  = getattr(e, "pole_id", "—")
            sk_name  = getattr(e, "sk_name", "—")
            splice_c = getattr(e, "splice_cores", 0)
            st.markdown(f"- **{label_e}**: 전산번호 {pole_id} | SK관리 {sk_name} | 접속 {splice_c}C")

    if not existing_cables and not new_cables and not work_items and not enclosures:
        st.info("케이블/함체 상세 정보가 파싱되지 않았습니다. xlsx의 ENG 시트 데이터를 확인하세요.")

    # ══════════════════════════════════════════
    # 4. 특이 사항
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 4. 특이 사항")

    critical_issues = [r for r in rule_results if r.severity == "CRITICAL"]
    major_issues    = [r for r in rule_results if r.severity == "MAJOR"]

    if not critical_issues and not major_issues:
        st.success("✅ 자동 검토 결과 특별한 이슈가 발견되지 않았습니다.")
    else:
        if critical_issues:
            st.error("🚨 **즉시 보완이 필요한 사항 (CRITICAL)**")
            for r in critical_issues:
                st.markdown(f"- `[{r.code}]` {r.message}")
        if major_issues:
            st.warning("⚠️ **확인이 필요한 사항 (MAJOR)**")
            for r in major_issues:
                st.markdown(f"- `[{r.code}]` {r.message}")

    if ai_result and ai_result.get("comprehensive"):
        st.markdown("#### 🤖 AI 검토의견 핵심 요약")
        comp_lines = [
            ln for ln in ai_result["comprehensive"].split("\n")
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if comp_lines:
            with st.container(border=True):
                st.markdown("\n".join(comp_lines[:8]))
            st.caption("전체 AI 의견은 '🤖 AI 종합 의견' 탭에서 확인하세요.")

    stored_expert = results.get("expert_notes", "")
    if stored_expert:
        st.markdown("#### 📝 검토담당자 발췌 문제점")
        with st.container(border=True):
            st.markdown(stored_expert)

# --- Tab 2: 종합 체크리스트 ---
with tab2:
    st.markdown("### 📋 설계서 종합 체크리스트")
    st.caption("모든 검토 항목의 보완 필요 여부를 한눈에 확인합니다.")

    checklist = build_checklist_status(data, rule_results)

    # 상태별 카운트
    n_total = len(checklist)
    n_pass = sum(1 for c in checklist if c["상태"] == "✅ 적합")
    n_fail = sum(1 for c in checklist if "🚨" in c["상태"])
    n_warn = sum(1 for c in checklist if "⚠️" in c["상태"])
    n_info = sum(1 for c in checklist if "ℹ️" in c["상태"])
    n_na   = sum(1 for c in checklist if "➖" in c["상태"])

    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    with mc1: st.metric("전체 항목", f"{n_total}개")
    with mc2: st.metric("✅ 적합", f"{n_pass}개")
    with mc3: st.metric("🚨 보완필요", f"{n_fail}개")
    with mc4: st.metric("⚠️ 확인필요", f"{n_warn}개")
    with mc5: st.metric("➖ 해당없음", f"{n_na}개")

    st.markdown("---")

    # 카테고리별 그룹핑
    from collections import OrderedDict as _OD
    cat_groups = _OD()
    for item in checklist:
        cat = item["카테고리"]
        if cat not in cat_groups:
            cat_groups[cat] = []
        cat_groups[cat].append(item)

    for cat, items in cat_groups.items():
        cat_fail = sum(1 for i in items if "🚨" in i["상태"])
        cat_warn = sum(1 for i in items if "⚠️" in i["상태"])
        cat_pass = sum(1 for i in items if i["상태"] == "✅ 적합")
        cat_icon = "🚨" if cat_fail > 0 else ("⚠️" if cat_warn > 0 else "✅")
        badge = f" — 🚨 {cat_fail}건 보완필요" if cat_fail else (f" — ⚠️ {cat_warn}건 확인필요" if cat_warn else " — 전체 적합")

        with st.expander(
            f"{cat_icon} **{cat}** ({len(items)}개 항목){badge}",
            expanded=(cat_fail > 0 or cat_warn > 0),
        ):
            # 테이블 형태로 표시
            rows = []
            for it in items:
                row = {
                    "상태": it["상태"],
                    "검토항목": it["검토항목"],
                    "발견내용": it["내용"] if it["내용"] else "—",
                    "규칙": it["규칙코드"],
                }
                rows.append(row)

            import pandas as _pd
            df = _pd.DataFrame(rows)

            # 상태별 컬러 적용
            def _color_status(val):
                if "🚨" in val:
                    return "background-color: #ffcccc; font-weight: bold;"
                if "⚠️" in val:
                    return "background-color: #fff3cd; font-weight: bold;"
                if "ℹ️" in val:
                    return "background-color: #d1ecf1;"
                if "✅" in val:
                    return "background-color: #d4edda;"
                return ""

            styled = df.style.map(_color_status, subset=["상태"])
            st.dataframe(styled, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### 🟢 기본 기입 항목 확인")
    for item in quick_results:
        st.markdown(f"- {item['상태']} **{item['항목']}**: `{item.get('값', '')}`")

# --- Tab 3: AI 종합 의견 ---
with tab3:
    if ai_result and ai_result.get("comprehensive"):
        # 검토담당자 발췌 반영 여부 표시
        stored_expert = results.get("expert_notes", "")
        if stored_expert:
            st.info(f"📝 **검토담당자 발췌 문제점 반영됨** ({len(stored_expert)}자) — AI가 해당 항목을 우선 분석했습니다.")

        st.markdown("### 🤖 LLM 종합 검토 의견")
        with st.container(border=True):
            st.markdown(ai_result["comprehensive"])

        if ai_result.get("comparison"):
            st.markdown("---")
            st.markdown("### 📐 개황도 전/후 비교 분석")
            with st.container(border=True):
                st.markdown(ai_result["comparison"])
    elif not api_key:
        st.info("🔑 사이드바에서 OpenAI API Key를 입력하면 AI 검토가 활성화됩니다.")
    else:
        st.info("AI 검토 결과가 없습니다.")

# --- Tab 4: 이미지 분석 ---
with tab4:
    st.markdown("### 📷 설계 도면 이미지 분석")

    # 분석 모드 표시
    if ai_result:
        mode = ai_result.get("analysis_mode", "text_only")
        mode_labels = {
            "user_upload": "📤 **사용자 업로드 모드** — 직접 업로드한 GIS/개황도 이미지를 분석했습니다. (3장 모두 업로드 시 통합 분석 수행)",
            "snapshot": "📸 **전체 스냅샷 모드** — 행정도 전체 뷰를 분석했습니다.",
            "individual": "📎 **개별 이미지 모드** — 시트에서 추출된 개별 이미지를 분석했습니다.",
            "text_only": "📝 **텍스트 전용** — 이미지 분석 없이 ENG시트 데이터만 검토했습니다.",
        }
        st.info(mode_labels.get(mode, ""))

    # ★ 사용자 업로드 이미지 미리보기
    stored_user_imgs = results.get("user_uploaded_images", {})
    if stored_user_imgs:
        st.markdown("#### 📤 사용자 업로드 이미지")
        st.caption("직접 업로드한 개황도/GIS 이미지입니다. Vision AI가 이 이미지를 분석합니다.")
        upload_order = ["작업 전 GIS", "개황도(전)", "개황도(후)"]
        visible = [k for k in upload_order if k in stored_user_imgs]
        if visible:
            ucols = st.columns(len(visible))
            for i, name in enumerate(visible):
                with ucols[i]:
                    try:
                        pil_img = Image.open(io.BytesIO(stored_user_imgs[name]))
                        st.image(pil_img, caption=name, use_container_width=True)
                    except Exception:
                        st.caption(f"📄 {name} 표시 불가")
            st.markdown("---")

    # ★ 시트 전체 스냅샷 표시
    if snapshots:
        st.markdown("#### 📸 행정도 전체 스냅샷")
        st.caption("선로, 심볼, 텍스트, 현장사진이 모두 포함된 행정도 전체 뷰입니다.")

        snap_order = ["행정도(전)", "행정도(후)", "개황도(전)", "개황도(후)", "작업 전 GIS"]
        shown_snaps = set()
        for sheet_name in snap_order:
            if sheet_name not in snapshots or sheet_name in shown_snaps:
                continue
            shown_snaps.add(sheet_name)
            snap = snapshots[sheet_name]
            with st.expander(f"📑 {sheet_name} 전체 스냅샷 ({len(snap.data):,} bytes)", expanded=True):
                try:
                    pil_img = Image.open(io.BytesIO(snap.data))
                    st.image(pil_img, caption=f"{sheet_name} — 전체 스냅샷", use_container_width=True)
                except Exception:
                    st.caption(f"📄 {sheet_name} 스냅샷 표시 불가")
        st.markdown("---")
    else:
        st.warning(
            "📸 **행정도 전체 스냅샷이 없습니다** — 개별 추출 이미지만 표시됩니다.\n\n"
            "전체 스냅샷은 행정도의 **지도 + 선로 + 심볼 + 텍스트 + 현장사진**을 "
            "하나의 이미지로 렌더링한 것입니다.\n\n"
            "**스냅샷 활성화 방법:**\n"
            "- **LibreOffice 설치**: https://www.libreoffice.org/download/ → 설치 후 재시작\n"
            "- **또는 Excel + pywin32**: `pip install pywin32 PyMuPDF`"
        )

    # ★★ 공사 이해 요약
    if ai_result and ai_result.get("construction_understanding"):
        st.markdown("#### 🧠 AI가 이미지에서 파악한 공사 정보")
        st.caption("아래 내용이 실제 설계와 일치하는지 확인해 주세요.")
        with st.container(border=True):
            st.markdown(ai_result["construction_understanding"])
        st.markdown("---")

    # ★ 행정도 전/후 이미지 공유 경고
    shared_warning = sheet_images.get("_images_shared_warning")
    if shared_warning and not snapshots:
        st.warning(
            f"⚠️ {shared_warning}\n\n"
            "**의미**: 행정도(전)과 (후) 시트에 삽입된 이미지가 동일합니다. "
            "전/후 차이는 Excel이 렌더링하는 선로 심볼에서 나타납니다.\n\n"
            "**해결**: LibreOffice 설치 후 전체 스냅샷을 생성하면 전/후 차이를 분석할 수 있습니다."
        )

    # 개별 이미지 표시 (★ 중복 제거)
    import hashlib as _hl
    priority_order = ["행정도(전)", "행정도(후)", "작업 전 GIS", "선번도", "선번도(전)", "선번도(후)", "공문 및 사진"]

    displayed_sheets = []
    for sheet_name in priority_order:
        if sheet_name in sheet_images and isinstance(sheet_images[sheet_name], list) and sheet_images[sheet_name]:
            displayed_sheets.append(sheet_name)
    for sheet_name in sheet_images:
        if sheet_name not in displayed_sheets and isinstance(sheet_images.get(sheet_name), list):
            displayed_sheets.append(sheet_name)

    if displayed_sheets:
        st.markdown("#### 📎 개별 추출 이미지 (시트별)")

        global_seen_hashes = set()
        for sheet_name in displayed_sheets:
            imgs = sheet_images[sheet_name]

            unique_imgs = []
            dup_count = 0
            for img in imgs:
                if not hasattr(img, 'data'):
                    continue
                h = _hl.md5(img.data).hexdigest()
                if h not in global_seen_hashes:
                    global_seen_hashes.add(h)
                    unique_imgs.append(img)
                else:
                    dup_count += 1

            dup_note = f" (중복 {dup_count}장 제외)" if dup_count else ""
            label = f"📑 {sheet_name} ({len(unique_imgs)}장{dup_note})"

            if not unique_imgs:
                st.caption(f"📑 {sheet_name}: 모든 이미지가 다른 시트와 동일 — 생략")
                continue

            with st.expander(label, expanded=False):
                img_cols = st.columns(min(len(unique_imgs), 2))
                for i, img in enumerate(unique_imgs[:6]):
                    col_idx = i % 2
                    with img_cols[col_idx]:
                        try:
                            pil_img = Image.open(io.BytesIO(img.data))
                            st.image(pil_img, caption=f"{getattr(img, 'filename', '이미지')} ({len(img.data):,}bytes)", use_container_width=True)
                        except Exception:
                            st.caption(f"📄 {getattr(img, 'filename', '이미지')} (표시 불가)")
                if len(unique_imgs) > 6:
                    st.caption(f"... 외 {len(unique_imgs) - 6}장 추가")

    # 추가 업로드 이미지 표시
    if extra_images:
        st.markdown(f"#### 📎 추가 업로드 이미지: {len(extra_images)}장")
        for ef in extra_images:
            try:
                ef.seek(0)
                pil_img = Image.open(ef)
                st.image(pil_img, caption=ef.name, use_container_width=True)
            except Exception:
                st.caption(f"📄 {ef.name}")

    # AI Vision 분석 결과 (구조화 표시)
    if ai_result and ai_result.get("image_analyses"):
        st.markdown("---")
        st.markdown("### 🤖 Vision AI 분석 결과")

        for idx, analysis in enumerate(ai_result["image_analyses"]):
            # 헤더/내용 분리
            lines = analysis.strip().split("\n", 1)
            raw_header = lines[0].replace("**", "").replace("#", "").strip(" :")
            content = lines[1].strip() if len(lines) > 1 else ""

            # 헤더 유형별 아이콘·색상
            if "통합" in raw_header:
                header_icon = "🔬"
                expanded = True
            elif "GIS" in raw_header:
                header_icon = "🌐"
                expanded = False
            elif "전)" in raw_header or "(전)" in raw_header:
                header_icon = "📋"
                expanded = False
            elif "후)" in raw_header or "(후)" in raw_header:
                header_icon = "📐"
                expanded = False
            else:
                header_icon = "📷"
                expanded = False

            with st.expander(f"{header_icon} {raw_header}", expanded=expanded):
                # 핵심 이슈 라인 탐지 → 상단 경고 박스 표시
                issue_lines = [
                    ln.strip() for ln in content.split("\n")
                    if any(kw in ln for kw in ["⚠️", "🚨", "❌", "주의", "문제", "불가", "과다", "미흡", "위반", "초과"])
                    and len(ln.strip()) > 5
                ]
                if issue_lines:
                    st.warning("**⚠️ 주요 발견사항 (자동 추출)**")
                    for il in issue_lines[:6]:
                        st.markdown(f"> {il}")
                    st.markdown("")

                # 섹션별 구조화 (Phase / Step 구분)
                sections = []
                current_sec_title = ""
                current_sec_lines = []

                for ln in content.split("\n"):
                    stripped = ln.strip()
                    is_sec_header = (
                        stripped.startswith("### ") or stripped.startswith("## ")
                        or (stripped.startswith("**Phase") and stripped.endswith("**"))
                        or (stripped.startswith("**Step") and stripped.endswith("**"))
                    )
                    if is_sec_header:
                        if current_sec_title or current_sec_lines:
                            sections.append((current_sec_title, "\n".join(current_sec_lines)))
                        current_sec_title = stripped.lstrip("#").strip().strip("*")
                        current_sec_lines = []
                    else:
                        current_sec_lines.append(ln)
                if current_sec_title or current_sec_lines:
                    sections.append((current_sec_title, "\n".join(current_sec_lines)))

                if len(sections) > 1:
                    # 섹션이 여러 개면 탭으로 분리
                    sec_titles = [s[0] if s[0] else f"분석 {i+1}" for i, s in enumerate(sections)]
                    tabs = st.tabs(sec_titles)
                    for i, (stitle, scontent) in enumerate(sections):
                        with tabs[i]:
                            st.markdown(scontent)
                else:
                    # 단일 섹션이면 그냥 표시
                    st.markdown(content)

    # 전/후 비교 결과 (구조화 표시)
    if ai_result and ai_result.get("comparison"):
        st.markdown("---")
        with st.container(border=True):
            st.markdown("### 🔄 행정도 전/후 비교 분석")

            comp_text = ai_result["comparison"]
            # 비교 결과에서 시설물 변경 요약 테이블 자동 추출 시도
            change_items = {
                "전주 신설": None, "전주 철거": None,
                "케이블 신설": None, "케이블 철거": None,
                "함체 신설": None, "함체 철거": None,
            }
            for line in comp_text.split("\n"):
                for key in change_items:
                    if key in line and change_items[key] is None:
                        change_items[key] = line.strip().lstrip("-•*").strip()
                        break

            found = {k: v for k, v in change_items.items() if v}
            if found:
                import pandas as _pd2
                df_chg = _pd2.DataFrame(
                    [{"변경 항목": k, "내용": v} for k, v in found.items()]
                )
                st.markdown("**📊 시설물 변경 요약 (자동 추출)**")
                st.dataframe(df_chg, use_container_width=True, hide_index=True)
                st.markdown("")

            st.markdown(comp_text)

    # 개별 이미지 추가 분석 기능
    if api_key and (all_extracted_images or extra_images):
        st.markdown("---")
        st.markdown("### 🔬 개별 이미지 추가 분석")

        all_imgs = []
        for sname, snap in snapshots.items():
            all_imgs.append((f"[스냅샷] {sname}", snap.data))
        for img in all_extracted_images:
            if hasattr(img, 'sheet_name') and hasattr(img, 'data'):
                all_imgs.append((f"[{img.sheet_name}] {img.filename}", img.data))
            elif hasattr(img, 'data'):
                all_imgs.append((f"[추출] {getattr(img, 'filename', '이미지')}", img.data))
        if extra_images:
            for ef in extra_images:
                ef.seek(0)
                all_imgs.append((f"[업로드] {ef.name}", ef.read()))

        if all_imgs:
            selected_img = st.selectbox(
                "분석할 이미지 선택",
                options=[name for name, _ in all_imgs],
            )
            photo_type = st.selectbox(
                "이미지 유형",
                options=["일반", "영배시스템", "이설요청서", "현장사진", "판정조서"],
            )

            if st.button("🔍 선택 이미지 분석"):
                img_data = dict(all_imgs)[selected_img]
                with st.spinner(f"📷 {selected_img} 분석 중..."):
                    result = analyze_evidence_photo(
                        api_key, img_data, selected_img, photo_type, model_choice
                    )
                    st.markdown(f"### 분석 결과: {selected_img}")
                    st.markdown(result)

    if not all_extracted_images and not extra_images and not snapshots:
        st.info("xlsx에서 추출된 이미지나 추가 업로드 이미지가 없습니다.")

# --- Tab 5: 리포트 ---
with tab5:
    report = generate_report(data, rule_results, quick_results, ai_result)

    st.download_button(
        label="📥 검토 리포트 다운로드 (.md)",
        data=report.encode("utf-8"),
        file_name=f"검토결과_{safe_str(data.get('공사명'))[:20]}_{판정}.md",
        mime="text/markdown",
    )

    st.markdown("---")
    st.markdown("### 리포트 미리보기")
    st.markdown(report)

# --- Tab 가이드: 사용자 가이드 ---
with tab_guide:
    st.markdown("# 📖 지장이설 설계검토 Agent — 사용자 가이드")
    st.caption("이 Agent가 무엇을 어떤 방식으로 검토하는지 설명합니다.")

    # ══════════════════════════════════════════
    # 1. 시스템 개요
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 1. 시스템 개요")
    with st.container(border=True):
        st.markdown("""
지장이설 설계표준안(xlsx)을 업로드하면 **3단계 자동 검토**를 수행하고 Markdown 리포트를 생성합니다.

| 검토 단계 | 방식 | 속도 | 필요 조건 |
|---------|------|------|----------|
| 🔴 **강화검토** | 규칙 기반 자동 판정 (R01~R13) | 즉시 | 없음 |
| 📋 **18대 체크리스트** | 규칙 결과 + 체크박스 상태 종합 (42개 항목) | 즉시 | 없음 |
| 🤖 **AI 보조검토** | GPT-4o Vision 도면 분석 + 종합 맥락 검토 | 수십 초 | OpenAI API Key |
| 🟢 **빠른통과** | 9개 필수 항목 기입 여부만 확인 | 즉시 | 없음 |
""")

    # ══════════════════════════════════════════
    # 2. 강화검토 규칙 13종 (R01~R13)
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 2. 🔴 강화검토 — 규칙 13종 상세")
    st.caption("각 규칙은 설계 데이터에서 자동으로 값을 추출해 판정합니다. 심각도에 따라 반려/조건부승인/참고로 분류됩니다.")

    st.markdown("""
| 규칙 코드 | 카테고리 | 검토 내용 | 심각도 | 판정 결과 |
|----------|---------|----------|--------|---------|
| **R01-1** | 이설요청근거 | 한전 요청 건인데 이설요청 주체(한전/지자체/공공기관/기타) 및 영배시스템 모두 미체크 | 🚨 CRITICAL | 반려 |
| **R01-2** | 이설요청근거 | 한전 요청 건인데 이설요청서 미체크 (공문시트 유무에 따라 분기) | 🚨 CRITICAL / ℹ️ INFO | 반려 / 참고 |
| **R01-3** | 이설요청근거 | 공문번호 미기입 또는 템플릿 기본값(예: "공문번호") 그대로 입력 | ⚠️ MAJOR | 확인필요 |
| **R01-4** | 이설요청근거 | 도로확장/지중화 공사인데 지자체 문서 미체크 | 🚨 CRITICAL | 반려 |
| **R01-5** | 이설요청근거 | 공사유형 가~마 중 아무것도 미선택 | ⚠️ MAJOR | 확인필요 |
| **R02** | 사업구분 | 공사명 키워드와 사업구분 불일치 (예: "도로확장"인데 사업구분이 "한전주이설") | ⚠️ MAJOR | 확인필요 |
| **R03** | 접속코어 | 접속코어 합계가 12C 단위 올림 규칙 위반 / 기설케이블 코어수 대비 120% 초과 | 🚨 CRITICAL / ⚠️ MAJOR / 💡 MINOR | 반려 / 확인 |
| **R04** | 용량과다 | 신설 케이블 사용률 60% 미만 (용량 과다 선정 의심) | 🚨 CRITICAL / ⚠️ MAJOR | 반려 / 확인 |
| **R05** | 단순이설 | 단순이설 가능 구간인데 절체이설로 설계 (접속코어 과다, 불필요한 공사) | ⚠️ MAJOR | 확인필요 |
| **R06** | 다대화 | 다대화 설계 시 대상 케이블 선정 적정성 검토 | ⚠️ MAJOR | 확인필요 |
| **R07** | 실사비/설계비 | 공사비 산출 기준 오적용 (실사비 vs 설계비 구분 오류) | ⚠️ MAJOR | 확인필요 |
| **R08** | 공사유형 | 공사유형 체크 상태와 공사방안 불일치 | ⚠️ MAJOR | 확인필요 |
| **R09** | RM | RM(원격 모니터링) 관련 설계 적정성 | ⚠️ MAJOR | 확인필요 |
| **R10** | 포설거리 | 케이블 포설 거리 기준 초과 (MAJOR) 또는 경계 (MINOR) | ⚠️ MAJOR / 💡 MINOR | 확인 / 참고 |
| **R11** | 기입완전성 | 필수 설계 항목 미기입 (공사명, 현장주소, 공사비 등) | ⚠️ MAJOR | 확인필요 |
| **R12** | 병행공사 | 병행공사 체크 시 관련 정보(타사명, 공정 등) 미기입 | ⚠️ MAJOR | 확인필요 |
| **R13** | 원인자 | 원인자 공사 해당 시 원인자 판정조서 미체크 | ⚠️ MAJOR | 확인필요 |

> **심각도 기준**: 🚨 CRITICAL = 반려 사유 (즉시 보완 필수) / ⚠️ MAJOR = 조건부 승인 / 💡 MINOR = 경미 / ℹ️ INFO = 참고
""")

    # ══════════════════════════════════════════
    # 3. 18대 체크리스트
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 3. 📋 18대 체크리스트 — 42개 항목 상세")
    st.caption("실제 설계검토 전담인력이 사용하는 18대 기준을 42개 세부 항목으로 확장했습니다. 각 항목은 규칙 결과 또는 데이터 기입 상태로 자동 판정됩니다.")

    st.markdown("""
| 번호 | 체크리스트 항목 | 연계 규칙 | 검토 방식 | 상태 판정 기준 |
|------|--------------|---------|---------|-------------|
| ① | 지장이설 공사 근거 미비 | R01-1~5 | 자동 (체크박스+공문번호) | 이설요청 주체 체크 + 공문번호 기입 여부 |
| ② | 사업구분 오류 | R02 | 자동 (공사명 키워드 분석) | 공사명 텍스트와 사업구분 일치 여부 |
| ③ | 접속코어 과다산출 | R03 | 자동 (수치 계산) | 12C 올림 규칙 + 기설케이블 대비 비율 |
| ④ | 케이블 용량 과다선정 | R04 | 자동 (사용률 계산) | 신설케이블 사용률 60% 미만 여부 |
| ⑤ | 케이블 종류 오선정 | 부분 | Vision AI 확인 필요 | 도면상 케이블 타입(Dry/MSLT) 확인 |
| ⑥ | 케이블 과다거리 포설 | R10 | 자동 (거리 수치 비교) | 포설거리 기준치 초과 여부 |
| ⑦ | 다대화 대상 오선정 | R06 | 자동 | 다대화 설계 적정성 |
| ⑧ | 단순이설 대상 절체이설 | R05 | 자동 | 단순이설 가능 여부 vs 절체이설 설계 |
| ⑩ | 원인자 대상 지장이설 설계 | R13 | 자동 (체크박스) | 원인자 판정조서 체크 여부 |
| ⑪ | 기설 시설물 미사용 | 부분 | Vision AI 확인 필요 | 기설 전주/함체 재활용 여부 (도면 확인) |
| ⑫ | 기설 시설물 철거설계 | 부분 | Vision AI 확인 필요 | 철거 계획 적정성 (도면 확인) |
| ⑬ | 실사비·설계비 오적용 | R07 | 자동 + AI 보조 | 공사비 산출 기준 적용 오류 |
| ⑭ | 타사주관 설계 검토 미비 | R12 | 자동 + AI 보조 | 병행공사 관련 정보 기입 완전성 |
| ⑮ | 관로 굴착공사 기준 위배 | — | Vision AI 확인 필요 | 관로 굴착 계획 도면 분석 |
| ⑯ | 현장실사 내용 불일치 | 부분 | Vision AI 확인 필요 | 설계 내용 vs 현장사진 일치 여부 |
| ⑰ | 기타 | R08, R09 | 자동 | 공사유형 불일치, RM 검토 |
| ⑱ | 특이사항 없음 | — | 검토자 판단 | 위 항목 모두 적합일 때 해당 |

> ⑨번 항목은 공식 체크리스트에 없음 (⑧에서 ⑩으로 이어짐)

**상태 표시 기준:**

| 상태 | 의미 | 발생 조건 |
|------|------|---------|
| ✅ 적합 | 이상 없음 | 연계 규칙 미발화 + 데이터 정상 기입 |
| 🚨 보완필요 | 즉시 수정 필요 | 연계 규칙 CRITICAL 발화 |
| ⚠️ 확인필요 | 검토자 확인 필요 | 연계 규칙 MAJOR 발화 또는 데이터 미기입 |
| ℹ️ 참고 | 정보 제공 | 연계 규칙 INFO 발화 |
| ➖ 해당없음 | 이 공사에 해당 없음 | 조건 미충족 (예: 한전 요청 건 아님) |
""")

    # ══════════════════════════════════════════
    # 4. 빠른통과 항목
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 4. 🟢 빠른통과 — 9개 필수 기입 항목")
    st.caption("설계서의 기본 필수 항목이 입력되어 있는지만 확인합니다. 내용의 적정성은 강화검토에서 별도 판정합니다.")

    st.markdown("""
| 항목 | 확인 방법 | 기준 |
|------|---------|------|
| 공사명 | 셀 값 존재 여부 | 빈 값 또는 기본 템플릿 텍스트이면 ❌ |
| 현장주소 | 셀 값 존재 여부 | 미기입이면 ❌ |
| 사업구분 | 셀 값 존재 여부 | 미기입이면 ❌ |
| 공사방안 | 셀 값 존재 여부 | 미기입이면 ❌ |
| 요청주체 | 셀 값 존재 여부 | 미기입이면 ❌ |
| 공문번호 | 셀 값 + 기본값 체크 | "공문번호" 등 기본값이면 ❌ |
| 공사비 | 숫자 존재 여부 | 0원 또는 미기입이면 ❌ |
| 접속코어합계 | 숫자 존재 여부 | 미기입이면 ❌ |
| 케이블 정보 | 기설케이블 1개 이상 | 파싱된 케이블 정보 없으면 ❌ |
""")

    # ══════════════════════════════════════════
    # 5. AI 보조검토
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 5. 🤖 AI 보조검토 — GPT-4o Vision 분석")
    st.caption("OpenAI API Key 입력 시 활성화됩니다. 이미지 분석과 종합 맥락 검토를 수행합니다.")

    st.markdown("""
### 이미지 분석 우선순위 (4단계)

| 우선순위 | 모드 | 조건 | 분석 내용 |
|---------|------|------|---------|
| 1순위 | 📤 사용자 업로드 | GIS/개황도 이미지 직접 업로드 시 | 업로드한 이미지 3장 통합 분석 (가장 정확) |
| 2순위 | 📸 전체 스냅샷 | LibreOffice 설치 시 자동 생성 | 행정도 전체 뷰 (지도+선+심볼+텍스트) |
| 3순위 | 📎 개별 이미지 | xlsx 내부 이미지 추출 | 시트별 삽입 이미지 개별 분석 |
| 4순위 | 📝 텍스트 전용 | 이미지 없을 때 | ENG시트 파싱 데이터만 LLM 검토 |

### Vision AI 분석 항목

| 분석 항목 | 내용 |
|---------|------|
| 신설 계획 파악 | 도면에서 신설 케이블(빨간 점선), 신설 전주(빨간 C), 신설 함체(빨간 P) 식별 |
| 철거 계획 파악 | 도면에서 철거 케이블(검정 실선), 철거 전주/함체(검정 심볼) 식별 |
| 기설 시설물 활용 | 기존 전주/함체/관로를 신설에 재활용하는지 확인 |
| 전/후 비교 | 개황도 전/후 비교 → 시설물 변경 사항 추출 |
| 케이블 종류 확인 | Dry vs MSLT 케이블 타입 도면 확인 (⑤ 체크리스트) |
| 관로 굴착 확인 | 굴착 계획의 기준 위배 여부 (⑮ 체크리스트) |
| 현장사진 대조 | 설계 내용과 현장사진의 실제 상황 일치 여부 (⑯ 체크리스트) |
| 공사 이해 요약 | 도면을 바탕으로 공사 전체 맥락 요약 (공사 개요 브리핑 탭에 반영) |

### 종합 검토 (LLM)

- 설계 데이터 전체(ENG시트 파싱 결과) + 규칙 검토 결과를 LLM에 입력
- **검토담당자 발췌 문제점** 입력 시 해당 항목 최우선·심층 분석
- 18대 체크리스트 기준으로 설계의 전체적 적정성 종합 의견 제공
""")

    # ══════════════════════════════════════════
    # 6. 탭별 활용 방법
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 6. 탭별 활용 가이드")

    st.markdown("""
| 탭 | 주요 용도 | 핵심 확인 포인트 |
|---|---------|--------------|
| 📌 **공사 개요 브리핑** | 공사를 처음 보는 검토자용 요약 | 공사 사유, 환경, 방법, 특이사항 |
| 🔴 **강화검토 결과** | 즉각적인 합격/반려 판단 | CRITICAL 항목 존재 여부 |
| 📋 **종합 체크리스트** | 18대 기준 전체 현황 파악 | 빨간(🚨)/노란(⚠️) 항목 수 |
| 🤖 **AI 종합 의견** | LLM의 종합적 판단 및 권고 | 담당자 발췌 문제점 반영 여부 |
| 📷 **이미지 분석** | 도면 Vision 분석 결과 확인 | 통합 분석 주요 발견사항 |
| 📄 **리포트 다운로드** | 최종 검토 결과 문서화 | Markdown 파일 다운로드 |

### 검토 판정 기준

| 종합 판정 | 조건 | 권장 조치 |
|---------|------|---------|
| 🔴 보완요청 | CRITICAL 1건 이상 | 설계 수정 후 재검토 |
| 🟡 확인필요 | MAJOR 1건 이상 (CRITICAL 없음) | 해당 항목 직접 확인 후 판단 |
| 🟢 적합 | CRITICAL/MAJOR 모두 없음 | 승인 가능 (MINOR/INFO는 참고) |
""")

    # ══════════════════════════════════════════
    # 7. 주의사항 및 한계
    # ══════════════════════════════════════════
    st.markdown("---")
    st.markdown("## 7. ⚠️ 주의사항 및 한계")

    st.warning("""
**이 Agent의 검토 한계 — 반드시 읽어주세요**

- **체크박스 파싱 정확도**: xlsx 파일의 체크박스는 VML/ctrlProp XML 방식으로 파싱하며, Excel 버전에 따라 미검출될 수 있습니다. "체크박스 모두 False" 상태라면 Excel에서 파일을 열고 다시 저장 후 재업로드하세요.
- **GIS 데이터 미검증**: GIS 시스템의 실제 선로 현황과 교차 검증하지 않습니다. 도면상 거리/코어수만 참조합니다.
- **Vision AI 한계**: 이미지 해상도, 도면 복잡도에 따라 판독 정확도가 달라집니다. 직접 업로드 이미지를 사용하면 정확도가 향상됩니다.
- **최종 판단은 검토자**: 본 Agent는 보조 도구이며, 모든 규칙 판정 결과는 검토자가 최종 확인해야 합니다.
- **공사유형별 특수 규칙**: 일부 공사유형(관로 굴착, 맨홀 신설 등)에 대한 세부 기준은 반영되지 않을 수 있습니다.
""")

    st.markdown("""
### 파일 형식 요구사항

| 항목 | 요구사항 |
|------|---------|
| 파일 형식 | `.xlsx` (xlsx 전용, `.xls` 구형 형식 불가) |
| ENG 시트 | "ENG", "Eng", "eng" 등 퍼지 매칭으로 자동 탐지 |
| 체크박스 | Excel Form Control 체크박스 (ActiveX 체크박스 미지원) |
| 이미지 | xlsx 내부 삽입 이미지 자동 추출, 또는 별도 업로드 가능 |
| 인코딩 | UTF-8 호환 (한글 공사명 등 정상 처리) |
""")

# ============================================================
# 푸터
# ============================================================
st.markdown("---")
st.caption(
    "💡 본 검토는 AI 자동 검토이며, 최종 판단은 검토자가 수행합니다. | "
    "지장이설 설계검토 Agent v3.1 | OpenAI GPT-4o Vision API"
)
