# ---- Reference entities ----
REF_COL = "is_reference"                      # 1 = entity row added as level-1 anchor, not a selected segment
ENTITY_AXES = "entity"
REF_KEEP_COLS = ["index"]                     # taken from the child's rows (quarter order)
REF_RUN_KEY = ["id_set_parameters_clone", "t_variable_clone"]
REF_MODEL_TYPE = "basic"


def _add_reference_one_run(display, seg):
    """Entity rows for ONE run and ONE target; see add_reference_entities"""
    is_child = display["seg_axes"] != ENTITY_AXES
    entity_of = display.loc[is_child, "seg_axes_value"].astype(str).str.split("|").str[0]
    shown = set(display.loc[~is_child, "seg_axes_value"])
    missing = sorted(set(entity_of) - shown)
    refs, added = [], []
    for entity in missing:
        ent = seg[seg["seg_axes_value"] == entity].drop_duplicates("period_clone").set_index("period_clone")
        if ent.empty:                                  # not in SP_anomalies for this run and target: nothing to add
            continue
        child = sorted(display.loc[entity_of[entity_of == entity].index, "seg_axes_value"])[0]   # first child: stable
        ref = display[display["seg_axes_value"] == child].drop_duplicates("period_clone").copy()
        ref = ref[ref["period_clone"].isin(ent.index)]
        for col in ref.columns:
            if col in REF_KEEP_COLS or col == "period_clone":
                continue
            src = col if col in ent.columns else (col[4:] if col.startswith("seg_") and col[4:] in ent.columns
                                                  else None)
            ref[col] = ref["period_clone"].map(ent[src]) if src else None
        ref["seg_axes"], ref["seg_axes_value"], ref[REF_COL] = ENTITY_AXES, entity, 1
        if "segment_id" in ref.columns:
            ref["segment_id"] = entity
        refs.append(ref)
        added.append(entity)
    return refs, added


def add_reference_entities(display, df_seg):
    """SP_display_seg or SP_display_toplines rows, BEFORE relabel (id_set_parameters_clone still
    arrimage_sgcp_latest_douteux, ...), completed with the entity row of every displayed detailed segment whose
    entity is not displayed. Works per (id_set_parameters_clone, t_variable_clone), so it can be called on the rows of
    one run or on all runs at once.
    The dashboard hangs a detailed segment (PMA_05|20) on its entity (PMA_05) for the level-1 materiality; on a
    perimeter the detailed segment can be selected while its entity is not, and the materiality is then NULL.
    Added rows: one per quarter of the child's history, from SP_anomalies (entity, basic model):
        column X <- anomalies X, else X without "seg_" (seg_deviation <- deviation); REF_KEEP_COLS <- child's row;
        other columns (line, rank, child) <- NULL; segment_id <- entity; is_reference = 1 (0 on the core rows).
    df_seg: SP_anomalies (any runs and targets). Returns (display, {(id_set, target): [entities added]})"""
    display = display.copy()
    display[REF_COL] = 0
    if display.empty or "seg_axes" not in display.columns:
        return display, {}
    anomalies = df_seg[(df_seg["model_type"] == REF_MODEL_TYPE) & (df_seg["seg_axes"] == ENTITY_AXES)]
    all_refs, report = [], {}
    for key, rows in display.groupby(REF_RUN_KEY, sort=True):
        seg = anomalies[(anomalies[REF_RUN_KEY[0]] == key[0]) & (anomalies[REF_RUN_KEY[1]] == key[1])]
        refs, added = _add_reference_one_run(rows, seg)
        all_refs += refs
        if added:
            report[key] = added
    if all_refs:
        display = pd.concat([display] + all_refs, ignore_index=True)
    return display, report
# ---- end reference entities ----
