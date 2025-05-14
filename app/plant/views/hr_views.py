import io
import pandas as pd
from django.shortcuts import render
from django.http import HttpResponse

def absentee_forms(request):
    """
    Upload & preview an Excel file of absentee data.
    This version prints/collects extensive debug info around the 'Shift' column.
    """
    table_html = None
    debug_info = []

    if request.method == "POST" and request.FILES.get("excel_file"):
        excel_file = request.FILES["excel_file"]

        # Read entire upload into memory so we can inspect it multiple times
        content = excel_file.read()
        debug_info.append(f"• Uploaded file: {excel_file.name} ({len(content)} bytes)")

        try:
            # 1) Peek at sheet names
            xls = pd.ExcelFile(io.BytesIO(content), engine="openpyxl")
            debug_info.append(f"• Sheets in workbook: {xls.sheet_names}")

            # 2) Read into DataFrame, force strings, disable NA detection
            df = pd.read_excel(
                io.BytesIO(content),
                dtype=str,
                keep_default_na=False,
                na_filter=False
            )
            debug_info.append(f"• Read DataFrame shape: {df.shape}")
            debug_info.append(f"• Columns: {df.columns.tolist()}")
            debug_info.append(f"• Dtypes: {df.dtypes.to_dict()}")

            # 3) Inspect the 'Shift' column if present
            if "Shift" in df.columns:
                # show raw unique values (repr so you see whitespace)
                uniques = [repr(v) for v in df["Shift"].unique()]
                debug_info.append(f"• Unique raw Shift values: {uniques}")

                # count blank vs non-blank
                blank_mask = df["Shift"].astype(bool) == False
                cnt_blank = int(blank_mask.sum())
                cnt_non_blank = int(len(df) - cnt_blank)
                debug_info.append(f"• Blank Shift count: {cnt_blank}")
                debug_info.append(f"• Non-blank Shift count: {cnt_non_blank}")

                # sample rows
                sample_blank = df.loc[blank_mask, ["Job", "Pay Code", "Shift"]].head(5).to_dict(orient="records")
                sample_non_blank = df.loc[~blank_mask, ["Job", "Pay Code", "Shift"]].head(5).to_dict(orient="records")
                debug_info.append(f"• Sample blank-Shift rows: {sample_blank}")
                debug_info.append(f"• Sample non-blank-Shift rows: {sample_non_blank}")

            # 4) Finally, ensure no pandas NaN remain
            df = df.fillna("")

            # 5) Convert to HTML
            table_html = df.to_html(
                classes="table table-striped table-bordered",
                index=False,
                na_rep=""
            )

        except Exception as e:
            # log the error and show it
            debug_info.append(f"‼️ Excel processing error: {e}")
            return HttpResponse(f"Error reading Excel file: {e}", status=400)

    # print all debug_info lines to console
    for line in debug_info:
        print(line)

    return render(request, "plant/absentee.html", {
        "table_html": table_html,
        "debug_info": debug_info,
    })
