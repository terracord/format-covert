"""PDF/CSV Format Converter Application.

A Streamlit-based application for converting PDF, Excel, and CSV files
into structured CSV format. Supports local file upload and URL input.

Usage:
    streamlit run app.py
"""

import io
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from extractors.pdf_extractor import extract_pdf
from extractors.url_fetcher import fetch_file_from_url, detect_file_type
from extractors.classifier import classify_document, get_suggested_columns
from converter.csv_converter import (
    build_dataframe,
    dataframe_to_csv_bytes,
    convert_excel_to_dataframe,
    convert_csv_to_dataframe,
)
from validators.quality_checker import (
    run_validation,
    compute_row_confidence,
    ValidationResult,
)

st.set_page_config(
    page_title="PDF/CSV Format Converter",
    page_icon="📄",
    layout="wide",
)

st.title("PDF/CSV Format Converter")
st.markdown("ローカルファイルまたはURLからデータを読み込み、CSVフォーマットに変換します。")

# --- Session state initialization ---
if "page_results" not in st.session_state:
    st.session_state.page_results = None
if "source_df" not in st.session_state:
    st.session_state.source_df = None
if "classification" not in st.session_state:
    st.session_state.classification = None
if "filename" not in st.session_state:
    st.session_state.filename = None

# ============================================================
# STEP 1: Input Source Selection
# ============================================================
st.header("Step 1: データソースの選択")

input_method = st.radio(
    "入力方法を選択してください:",
    ["ファイルアップロード", "URL入力"],
    horizontal=True,
)

file_bytes = None
filename = None
file_type = None

if input_method == "ファイルアップロード":
    uploaded_file = st.file_uploader(
        "PDF, Excel, CSV ファイルをアップロード",
        type=["pdf", "xlsx", "xls", "csv"],
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        filename = uploaded_file.name
        file_type = detect_file_type(filename, uploaded_file.type)
        st.success(f"ファイル読み込み完了: {filename} ({file_type})")

else:
    url = st.text_input("ファイルのURLを入力してください:")
    if url and st.button("URLからダウンロード"):
        try:
            with st.spinner("ダウンロード中..."):
                file_bytes, filename, content_type = fetch_file_from_url(url)
                file_type = detect_file_type(filename, content_type)
            st.success(f"ダウンロード完了: {filename} ({file_type})")
        except Exception as e:
            st.error(f"ダウンロードエラー: {e}")

# ============================================================
# STEP 2: Extract and Classify
# ============================================================
if file_bytes and filename:
    st.header("Step 2: データ抽出")

    if st.button("抽出を実行", type="primary"):
        with st.spinner("データを抽出中..."):
            try:
                if file_type == ".pdf":
                    page_results = extract_pdf(file_bytes=file_bytes)
                    st.session_state.page_results = page_results
                    st.session_state.filename = filename

                    classification = classify_document(filename, page_results)
                    st.session_state.classification = classification

                    total_elements = sum(
                        len(p.get("elements", [])) for p in page_results
                    )
                    st.success(
                        f"抽出完了: {len(page_results)}ページ, "
                        f"{total_elements}要素を検出"
                    )

                    st.info(
                        f"文書分類: **{classification.get('name', 'Unknown')}** "
                        f"(判定方法: {classification.get('classification_method', '-')})"
                    )

                elif file_type in (".xlsx", ".xls"):
                    df = convert_excel_to_dataframe(file_bytes)
                    st.session_state.source_df = df
                    st.session_state.filename = filename
                    st.session_state.page_results = None
                    st.success(f"Excel読み込み完了: {df.shape[0]}行 x {df.shape[1]}列")

                elif file_type == ".csv":
                    df = convert_csv_to_dataframe(file_bytes)
                    st.session_state.source_df = df
                    st.session_state.filename = filename
                    st.session_state.page_results = None
                    st.success(f"CSV読み込み完了: {df.shape[0]}行 x {df.shape[1]}列")

                else:
                    st.error(f"未対応のファイル形式: {file_type}")

            except Exception as e:
                st.error(f"抽出エラー: {e}")

    # Show raw extraction preview
    if st.session_state.page_results:
        with st.expander("抽出結果プレビュー (JSON)", expanded=False):
            preview_pages = st.session_state.page_results[:3]
            st.json(preview_pages)

    if st.session_state.source_df is not None and st.session_state.page_results is None:
        with st.expander("データプレビュー", expanded=False):
            st.dataframe(st.session_state.source_df.head(20))


# ============================================================
# STEP 3: CSV Format Configuration
# ============================================================
has_data = (
    st.session_state.page_results is not None
    or st.session_state.source_df is not None
)

if has_data:
    st.header("Step 3: CSVフォーマット設定")

    # Suggest columns
    if st.session_state.page_results:
        suggested = get_suggested_columns(st.session_state.page_results)
        classification = st.session_state.classification or {}
        pattern_cols = classification.get("output_columns", [])
        if pattern_cols:
            suggested = pattern_cols
    else:
        suggested = list(st.session_state.source_df.columns)

    st.subheader("出力カラム設定")

    col1, col2 = st.columns(2)

    with col1:
        selected_columns = st.multiselect(
            "出力するカラムを選択:",
            options=suggested,
            default=suggested,
        )

        custom_col = st.text_input("カスタムカラムを追加 (カンマ区切り):")
        if custom_col:
            for c in custom_col.split(","):
                c = c.strip()
                if c and c not in selected_columns:
                    selected_columns.append(c)

    with col2:
        st.subheader("抽出オプション")

        if st.session_state.page_results:
            include_page_ref = st.checkbox("ページ参照を含める", value=True)
            include_element_type = st.checkbox("要素タイプを含める", value=False)
            table_only = st.checkbox("テーブルデータのみ", value=False)
            text_only = st.checkbox("テキストデータのみ", value=False)
        else:
            include_page_ref = False
            include_element_type = False
            table_only = False
            text_only = False

        encoding = st.selectbox(
            "エンコーディング:",
            ["utf-8-sig", "utf-8", "shift_jis", "cp932"],
            index=0,
        )

    # ============================================================
    # STEP 4: Convert and Validate
    # ============================================================
    st.header("Step 4: 変換・検証")

    if st.button("CSVに変換", type="primary"):
        with st.spinner("変換中..."):
            try:
                if st.session_state.page_results:
                    df = build_dataframe(
                        st.session_state.page_results,
                        columns=selected_columns,
                        include_page_ref=include_page_ref,
                        include_element_type=include_element_type,
                        table_only=table_only,
                        text_only=text_only,
                    )
                else:
                    df = st.session_state.source_df[
                        [c for c in selected_columns if c in st.session_state.source_df.columns]
                    ].copy()

                # Validation
                val_col1, val_col2 = st.columns(2)

                with val_col1:
                    st.subheader("バリデーション設定")
                    req_cols = st.multiselect(
                        "必須カラム (空値チェック):",
                        options=list(df.columns),
                        default=[],
                        key="req_cols",
                    )
                    num_cols = st.multiselect(
                        "数値カラム (型チェック):",
                        options=list(df.columns),
                        default=[],
                        key="num_cols",
                    )
                    pct_cols = st.multiselect(
                        "パーセンテージカラム (0-100チェック):",
                        options=list(df.columns),
                        default=[],
                        key="pct_cols",
                    )

                validation_results, confidence = run_validation(
                    df,
                    required_columns=req_cols,
                    numeric_columns=num_cols,
                    percentage_columns=pct_cols,
                )

                with val_col2:
                    st.subheader("検証結果")
                    if confidence >= 0.9:
                        st.success(f"信頼度スコア: {confidence:.1%}")
                    elif confidence >= 0.7:
                        st.warning(f"信頼度スコア: {confidence:.1%}")
                    else:
                        st.error(f"信頼度スコア: {confidence:.1%}")

                    st.metric("総行数", df.shape[0])
                    st.metric("総カラム数", df.shape[1])
                    st.metric("検出された問題数", len(validation_results))

                # Show validation issues
                if validation_results:
                    with st.expander(f"検証の問題 ({len(validation_results)}件)", expanded=True):
                        issue_data = []
                        for r in validation_results:
                            issue_data.append({
                                "行": r.row_index,
                                "カラム": r.column,
                                "種別": r.check_type,
                                "重要度": r.severity,
                                "メッセージ": r.message,
                            })
                        st.dataframe(pd.DataFrame(issue_data))

                # Add row-level confidence coloring
                def style_confidence(row):
                    idx = row.name
                    conf = compute_row_confidence(idx, validation_results)
                    if conf >= 0.9:
                        return ["background-color: #d4edda"] * len(row)  # green
                    elif conf >= 0.7:
                        return ["background-color: #fff3cd"] * len(row)  # yellow
                    else:
                        return ["background-color: #f8d7da"] * len(row)  # red

                st.subheader("変換結果プレビュー")
                styled_df = df.head(100).style.apply(style_confidence, axis=1)
                st.dataframe(styled_df, use_container_width=True)

                # Download button
                csv_bytes = dataframe_to_csv_bytes(df, encoding=encoding)
                base_name = Path(st.session_state.filename or "output").stem
                output_name = f"{base_name}_converted.csv"

                st.download_button(
                    label=f"CSVをダウンロード ({output_name})",
                    data=csv_bytes,
                    file_name=output_name,
                    mime="text/csv",
                    type="primary",
                )

                # Also offer JSON intermediate output
                if st.session_state.page_results:
                    json_str = json.dumps(
                        st.session_state.page_results, ensure_ascii=False, indent=2
                    )
                    st.download_button(
                        label="中間JSON (抽出結果) をダウンロード",
                        data=json_str.encode("utf-8"),
                        file_name=f"{base_name}_extracted.json",
                        mime="application/json",
                    )

            except Exception as e:
                st.error(f"変換エラー: {e}")
                raise

# --- Footer ---
st.markdown("---")
st.caption(
    "PDF/CSV Format Converter - "
    "設計書に基づくStage 1〜4の実装 (前処理 → 分類 → 変換 → 検証)"
)
