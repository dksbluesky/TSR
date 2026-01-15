import streamlit as st
import pandas as pd
from datetime import datetime, time

# ==========================================
# 設定頁面
# ==========================================
st.set_page_config(page_title="2026 春節高鐵時刻表查詢", page_icon="🚅")
st.title("🚅 2026 春節高鐵時刻查詢 Web App")
st.markdown("""
此工具支援 **Excel 檔案上傳** (由 batch_convert.py 產生)。
程式會自動略過上方的標題列，並根據您選擇的方向自動切換起訖站。
""")

# ==========================================
# 1. 檔案上傳區
# ==========================================
uploaded_file = st.file_uploader("📂 請上傳高鐵時刻表 Excel 檔 (.xlsx)", type=["xlsx"])

# ==========================================
# 2. 輔助函式
# ==========================================
def find_header_and_clean(df_raw):
    """
    在 DataFrame 前 20 列中尋找真正的表頭列。
    判斷標準：該列必須包含 '車次' 或 'Train' 關鍵字。
    """
    header_idx = -1
    for i, row in df_raw.head(20).iterrows():
        # 將該列轉為字串並串接，方便搜尋
        row_str = " ".join(row.astype(str).values)
        if "車次" in row_str or "Train" in row_str:
            header_idx = i
            break
    
    if header_idx != -1:
        # 設定新的表頭
        df_raw.columns = df_raw.iloc[header_idx]
        # 只保留表頭之後的資料
        df_clean = df_raw.iloc[header_idx + 1:].reset_index(drop=True)
        return df_clean
    else:
        return df_raw

def is_train_operating(selected_date_str, op_day_str):
    if not isinstance(op_day_str, str): 
        return True 
    if "每日" in op_day_str:
        return True
    
    sel_dt = datetime.strptime(selected_date_str, "%Y/%m/%d")
    sel_md = f"{sel_dt.month}/{sel_dt.day}"
    
    parts = op_day_str.replace(" ", "").replace("~", "-").split(",")
    for part in parts:
        if "-" in part:
            try:
                start_s, end_s = part.split("-")
                def parse_md(s):
                    m, d = map(int, s.split("/"))
                    return m * 100 + d
                if parse_md(start_s) <= parse_md(sel_md) <= parse_md(end_s):
                    return True
            except:
                continue
        else:
            if part == sel_md:
                return True
    return False

def calculate_duration(t_start, t_end):
    if pd.isna(t_start) or pd.isna(t_end) or str(t_start).strip() in ["-", "nan", "NaT"]:
        return 9999
    
    def to_dt(t):
        if isinstance(t, time):
            return datetime.combine(datetime.today(), t)
        if isinstance(t, str):
            try:
                t = t.replace(" ", "")
                if len(t.split(":")[1]) == 1: 
                    t += "0"
                return datetime.strptime(t, "%H:%M")
            except:
                return None
        return None

    dt_start = to_dt(t_start)
    dt_end = to_dt(t_end)

    if not dt_start or not dt_end:
        return 9999

    if dt_end < dt_start:
        seconds = (dt_end - dt_start).total_seconds() + 24*3600
    else:
        seconds = (dt_end - dt_start).total_seconds()
        
    return int(seconds / 60)

# ==========================================
# 3. 主程式邏輯
# ==========================================
if uploaded_file is not None:
    try:
        xls = pd.ExcelFile(uploaded_file)
        sheet_names = xls.sheet_names
        
        st.sidebar.header("🔍 資料設定")
        selected_sheet = st.sidebar.selectbox("選擇時刻表 (Sheet)", sheet_names)
        
        # 讀取並清洗
        df_raw = pd.read_excel(uploaded_file, sheet_name=selected_sheet, header=None)
        df = find_header_and_clean(df_raw)
        df.columns = [str(c).replace("\n", "").strip() for c in df.columns]
        all_columns = df.columns.tolist()
        
        # 檢查是否有抓到正確欄位
        possible_stations = ["南港", "左營", "台南", "Nangang", "Zuoying"]
        has_valid_columns = any(s in all_columns for s in possible_stations)
        
        if not has_valid_columns:
            st.error("⚠️ 無法偵測到車站欄位。請檢查 Excel 表頭是否正確。")
            st.dataframe(df.head())
        else:
            st.sidebar.divider()
            
            # === 智慧判斷起訖站 ===
            # 預設邏輯：南下(南港->台南)，北上(台南->南港)
            target_start = "南港"
            target_end = "台南"
            
            if "北上" in selected_sheet or "Northbound" in selected_sheet:
                target_start = "台南"
                target_end = "南港"
            
            # 找出這兩個站在 columns 中的位置 (index)
            # 如果找不到，就預設選第 0 個和第 1 個
            idx_start = all_columns.index(target_start) if target_start in all_columns else 0
            idx_end = all_columns.index(target_end) if target_end in all_columns else (1 if len(all_columns)>1 else 0)
            
            col1, col2 = st.sidebar.columns(2)
            with col1:
                # key 是必要的，這樣切換 sheet 時才會強制重置選單
                start_station = st.selectbox("起點站", all_columns, index=idx_start, key=f"s_{selected_sheet}")
            with col2:
                end_station = st.selectbox("終點站", all_columns, index=idx_end, key=f"e_{selected_sheet}")
                
            date_options = [f"2026/02/{d:02d}" for d in range(13, 24)]
            selected_date = st.sidebar.selectbox("選擇日期", date_options)
            
            time_range = st.sidebar.slider("發車時間範圍", value=(time(6, 0), time(23, 59)), format="HH:mm")
            
            # 開始過濾
            results = []
            train_col = next((c for c in df.columns if "車次" in c or "Train" in c), None)
            day_col = next((c for c in df.columns if "行駛日" in c or "Day" in c), None)

            if not train_col:
                st.error("找不到「車次」欄位，請檢查 Excel 表頭。")
            else:
                for index, row in df.iterrows():
                    train_no = row[train_col]
                    t_start = row[start_station]
                    t_end = row[end_station]
                    
                    if str(train_no).strip() == train_col: continue

                    op_day = "每日"
                    if day_col and pd.notna(row[day_col]):
                        op_day = str(row[day_col])
                    
                    if not is_train_operating(selected_date, op_day):
                        continue

                    if pd.isna(t_start) or pd.isna(t_end) or str(t_start).strip() in ["-", "nan"]:
                        continue

                    try:
                        check_time = t_start
                        if isinstance(check_time, str):
                            check_time = check_time.replace(" ", "")
                            if len(check_time.split(":")[1]) == 1: check_time += "0"
                            check_time = datetime.strptime(check_time, "%H:%M").time()
                        
                        if not (time_range[0] <= check_time <= time_range[1]):
                            continue
                    except:
                        continue

                    duration = calculate_duration(t_start, t_end)
                    
                    if duration <= 120:
                         results.append({
                            "車次": train_no,
                            "發車時間": t_start,
                            "抵達時間": t_end,
                            "行車時間 (分)": duration,
                            "備註": op_day
                        })

                if results:
                    result_df = pd.DataFrame(results)
                    try:
                         result_df = result_df.sort_values(by="發車時間")
                    except:
                         pass
                    
                    st.subheader(f"查詢結果：{selected_date} ({start_station} → {end_station})")
                    st.write(f"共找到 **{len(result_df)}** 班符合條件的直達/快車（行車 ≤ 120 分）：")
                    
                    st.dataframe(
                        result_df.style.background_gradient(subset=["行車時間 (分)"], cmap="Greens_r"),
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "車次": st.column_config.TextColumn("車次", width="small"),
                            "行車時間 (分)": st.column_config.NumberColumn("行車時間", format="%d 分"),
                        }
                    )
                else:
                    st.warning("⚠️ 找不到符合條件的班次。")

    except Exception as e:
        st.error(f"程式執行錯誤：{e}")

else:
    st.info("👆 請在上方上傳 Excel 檔案以開始查詢。")
