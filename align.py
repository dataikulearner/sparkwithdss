def align_to_schema(df, dataset):
    """Cast df to the types of the dataset's current schema before write_with_schema, so that every partition is
    written with the same types (pandas infers float64 for a column full of NULL or of numeric codes, and the
    partition is then written as DOUBLE while the dataset says string)"""
    try:
        schema = {c["name"]: c["type"] for c in dataset.read_schema()}
    except Exception:                                   # first build: no schema yet
        return df
    df = df.copy()
    for name, typ in schema.items():
        if name not in df.columns:
            continue
        s = df[name]
        if typ == "string":
            if pd.api.types.is_float_dtype(s):          # 12309.0 -> "12309", NaN -> NULL
                s = s.map(lambda v: None if pd.isna(v) else (str(int(v)) if float(v).is_integer() else str(v)))
            else:
                s = s.where(s.isna(), s.astype(str))
            df[name] = s.astype(object)
        elif typ in ("double", "float"):
            df[name] = pd.to_numeric(s, errors="coerce").astype("float64")
        elif typ in ("bigint", "int", "smallint", "tinyint"):
            df[name] = pd.to_numeric(s, errors="coerce").astype("Int64")
    return df
