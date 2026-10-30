# # Audit des recipes Python avec ruff — notebook de test
#
# Kịch bản: liệt kê project → recipe → giữ recipe Python / PySpark → chạy ruff → xem kết quả → ghi vào dataset.
#
# **Trước khi chạy**
# - Kernel của notebook phải dùng **code env có `ruff`** (Kernel › Change kernel).
# - Bắt đầu nhỏ: mặc định chỉ quét project hiện tại, tối đa 50 recipe, và **không ghi gì** (`WRITE_OUTPUT = False`).
# - Chạy từng cell theo thứ tự; cell 4 (smoke test) phải pass trước khi đi tiếp.

# ## 1. Cấu hình

# %%
import json
import subprocess
import sys

import dataiku
import pandas as pd
from dataikuapi.utils import DataikuException

# --- Phạm vi: bắt đầu nhỏ, mở rộng dần ---
PROJECT_KEYS = [dataiku.default_project_key()]   # None = mọi project của instance
MAX_RECIPES = 50                                 # None = không giới hạn
RECIPE_TYPES = {"python", "pyspark"}

# --- Output ---
OUTPUT_DATASET = "recipe_ruff_findings"
OUTPUT_CONNECTION = "filesystem_managed"         # chỉ dùng nếu phải tạo dataset (cell 8)
WRITE_OUTPUT = False                             # True khi kết quả đã ổn

# --- ruff ---
RUFF_PREFIX = [sys.executable, "-m", "ruff"]
RUFF_SELECT = ["F", "E4", "E7", "E9", "B", "BLE", "S110", "S112", "S608", "PD", "PERF"]
RUFF_IGNORE = ["E402", "E501", "PD901", "PERF203"]

# ## 2. Kiểm tra ruff có trong code env
#
# Nếu cell này lỗi: thêm `ruff` vào packages của code env rồi rebuild. Để thử nhanh trong phiên này:
# `!{sys.executable} -m pip install ruff` (mất khi kernel restart).

# %%
out = subprocess.run(RUFF_PREFIX + ["--version"], capture_output=True, text=True)
if out.returncode != 0:
    raise RuntimeError(f"ruff not available in this kernel ({sys.executable}): {out.stderr or out.stdout}")
RUFF_VERSION = out.stdout.strip()
print(RUFF_VERSION)

# ## 3. Hàm chạy ruff trên một đoạn code

# %%
def run_ruff(source: str, filename: str) -> list:
    """ruff findings on one piece of code, read from stdin. Raises RuntimeError if ruff itself fails."""
    cmd = RUFF_PREFIX + ["check", "-", "--isolated", "--output-format", "json", "--exit-zero", "--no-cache",
                         "--select", ",".join(RUFF_SELECT), "--ignore", ",".join(RUFF_IGNORE),
                         "--stdin-filename", filename]
    out = subprocess.run(cmd, input=source, capture_output=True, text=True, timeout=60)
    if out.returncode != 0:      # --exit-zero: findings give 0, only a ruff failure gives non zero
        raise RuntimeError(f"ruff exit {out.returncode} on {filename}: {out.stderr.strip()[:300]}")
    lines = source.splitlines()
    findings = []
    for item in json.loads(out.stdout or "[]"):
        code_ = item.get("code") or "SYNTAX"          # syntax errors: code null (or E999 on old ruff)
        code_ = "SYNTAX" if code_ == "E999" else code_
        row = item["location"]["row"]
        findings.append({
            "rule_code": code_,
            "message": item.get("message", ""),
            "line": row,
            "code_line": lines[row - 1].strip() if 0 < row <= len(lines) else "",
            "fixable": item.get("fix") is not None,
            "url": item.get("url") or "",
        })
    return findings

# ## 4. Smoke test trên một đoạn code đã biết lỗi
#
# Phải thấy ít nhất `F401` (import thừa) và `E722` (bare except). Nếu không, đừng chạy tiếp:
# bộ chọn rule hoặc format output của ruff có vấn đề, và mọi recipe sẽ trông "sạch".

# %%
BAD_SAMPLE = """import numpy as np
import dataiku
try:
    x = 1
except:
    pass
"""
smoke = run_ruff(BAD_SAMPLE, "smoke_test.py")
display(pd.DataFrame(smoke)[["rule_code", "line", "code_line", "message"]])
missing = {"F401", "E722"} - {f["rule_code"] for f in smoke}
assert not missing, f"ruff did not report {missing}: check RUFF_SELECT / ruff version"
print("Smoke test OK")

# ## 5. Liệt kê project và recipe Python / PySpark, lấy code

# %%
client = dataiku.api_client()
keys = PROJECT_KEYS or client.list_project_keys()
recipes, skipped = [], []

for key in keys:
    if MAX_RECIPES and len(recipes) >= MAX_RECIPES:
        break
    try:
        project = client.get_project(key)
        for item in project.list_recipes():
            if item.get("type") not in RECIPE_TYPES:
                continue
            try:
                code_ = project.get_recipe(item["name"]).get_settings().get_code() or ""
                status = "ok"
            except DataikuException as err:
                code_, status = None, f"code not readable: {err}"
            recipes.append({"project_key": key, "recipe_name": item["name"],
                            "recipe_type": item["type"], "code": code_, "status": status})
            if MAX_RECIPES and len(recipes) >= MAX_RECIPES:
                break
    except DataikuException as err:                  # e.g. no read permission: reported, not hidden
        skipped.append({"project_key": key, "error": str(err)})

recipes_df = pd.DataFrame(recipes, columns=["project_key", "recipe_name", "recipe_type", "code", "status"])
print(f"{len(keys)} project(s) scanned, {len(skipped)} skipped, {len(recipes_df)} Python/PySpark recipe(s)")
display(recipes_df.groupby(["recipe_type", "status"]).size().rename("recipes").reset_index())
if skipped:
    display(pd.DataFrame(skipped))

# ## 6. Chạy ruff trên từng recipe

# %%
COLUMNS = ["project_key", "recipe_name", "recipe_type", "rule_code", "message", "line", "code_line",
           "fixable", "url", "ruff_version"]
rows, failures = [], []

for rec in recipes_df[recipes_df["status"] == "ok"].itertuples(index=False):
    filename = f"{rec.project_key}.{rec.recipe_name}.py"
    try:
        for f in run_ruff(rec.code, filename):
            rows.append({"project_key": rec.project_key, "recipe_name": rec.recipe_name,
                         "recipe_type": rec.recipe_type, **f, "ruff_version": RUFF_VERSION})
    except RuntimeError as err:
        failures.append({"recipe": filename, "error": str(err)})

findings_df = pd.DataFrame(rows, columns=COLUMNS)
print(f"{len(findings_df)} finding(s) on {findings_df[['project_key', 'recipe_name']].drop_duplicates().shape[0]} "
      f"recipe(s) out of {(recipes_df['status'] == 'ok').sum()}; ruff failed on {len(failures)}")
if failures:
    display(pd.DataFrame(failures))

# ## 7. Xem kết quả

# %%
print("Rule xuất hiện nhiều nhất")
display(findings_df.groupby("rule_code")
        .agg(findings=("line", "size"), recipes=("recipe_name", "nunique"), example=("message", "first"))
        .sort_values("findings", ascending=False))

print("Recipe nhiều lỗi nhất")
display(findings_df.groupby(["project_key", "recipe_name"]).size().rename("findings")
        .sort_values(ascending=False).head(20).reset_index())

print("Lỗi nguy hiểm (nuốt lỗi, SQL ghép chuỗi, hàm trùng tên, biến chưa định nghĩa, cú pháp)")
DANGEROUS = {"E722", "BLE001", "S110", "S112", "S608", "F811", "F821", "SYNTAX"}
display(findings_df[findings_df["rule_code"].isin(DANGEROUS)]
        [["project_key", "recipe_name", "line", "rule_code", "code_line"]].head(50))

# ## 8. Ghi vào dataset
#
# Notebook chỉ ghi được vào dataset đã tồn tại. Cell này tạo dataset managed nếu chưa có
# (sửa `OUTPUT_CONNECTION` theo connection của instance), rồi ghi khi `WRITE_OUTPUT = True`.

# %%
if failures:
    raise RuntimeError(f"ruff failed on {len(failures)} recipe(s): fix before writing, "
                       "an incomplete output would look clean")

if not WRITE_OUTPUT:
    print("WRITE_OUTPUT = False: nothing written. Set it to True in cell 1 once the results look right.")
else:
    project = client.get_project(dataiku.default_project_key())
    if OUTPUT_DATASET not in {d["name"] for d in project.list_datasets()}:
        project.new_managed_dataset(OUTPUT_DATASET).with_store_into(OUTPUT_CONNECTION).create()
        print(f"Dataset {OUTPUT_DATASET} created on {OUTPUT_CONNECTION}")
    dataiku.Dataset(OUTPUT_DATASET).write_with_schema(findings_df)
    print(f"{len(findings_df)} rows written to {OUTPUT_DATASET}")
