
import itertools
import json

import dataiku
from dataiku.scenario import Scenario

from admin.pilotage import insert_into_pilotage
from core.constants import DssZone, RunStatus
from flows.arrimage import params as ap

FLOW_TYPE = "arrimage"
CONFIG_FOLDER, PARAMS_PATH = "parameters_folder", "flows/arrimage_params.json"
BUILD_MODE = "NON_RECURSIVE_FORCED_BUILD"

# Datasets with their partition dimensions in the order DSS expects ([] = not partitioned)
# Dimension names known here: scope, period_run, id_set_parameters, t_variable, axe, period
# (no Arrimage dataset is partitioned by axe: SP_agg_focus_model handles every axis of the task in one activity)
SEG_DIMS = ["scope", "period_run", "id_set_parameters", "t_variable"]
DATASET_DIMS = {
    "axes_periods_par": ["scope"],
    "params_par_model_par": ["scope"],
    "SP_agg": ["scope"],
    "SP_toplines_cumul": ["scope", "period_run"],
    "SP_agg_focus_model": SEG_DIMS,
    "SP_anomalies": SEG_DIMS,
    "SP_top_seg": SEG_DIMS,
    "SP_display_seg": SEG_DIMS,
    "SP_display_toplines": SEG_DIMS,
}

# Stages in run order: (DssZone member name, datasets built in flow order); INIT builds nothing, it checks
STAGES = [
    ("INIT", []),
    ("PRE_PROCESSING", ["axes_periods_par", "params_par_model_par", "SP_agg", "SP_toplines_cumul"]),
    ("MODELING", ["SP_agg_focus_model", "SP_anomalies"]),
    ("POST_PROCESSING", ["SP_top_seg", "SP_display_seg", "SP_display_toplines"]),
]
STATUS_LAUNCH, STATUS_OK, STATUS_KO = RunStatus.LAUNCH, RunStatus.OK, RunStatus.KO


# 1. Checks before any build

def read_context():
    """(params, period_run) after the fail-fast checks on the project variables and the params"""
    variables = dataiku.get_custom_variables()
    if variables.get("flow_type") != FLOW_TYPE:
        raise ValueError("flow_type = {!r}: ARRIMAGE_RUN only runs where flow_type = {!r}".format(
            variables.get("flow_type"), FLOW_TYPE))
    period_run = (variables.get("period_run") or "").strip().upper()
    if not period_run:
        raise ValueError("Project variable period_run is not set (e.g. 2026Q2)")
    with dataiku.Folder(CONFIG_FOLDER).get_download_stream(PARAMS_PATH) as stream:
        params = json.load(stream)
    ap.validate_params(params)
    errors = []
    for scope, version in ap.list_runs(params):
        first = ap.resolve_run_params(params, scope, version)["periods_str"].split("/")[0].strip().upper()
        if first != period_run:
            errors.append("{} {}: periods_str starts at {}".format(scope, version, first))
    if errors:
        raise ValueError("period_run = {} but {}: update periods_str in {}".format(period_run, errors, PARAMS_PATH))
    return params, period_run


def tasks_of(params, period_run):
    """One dict per (run, target, axe, period), with every dimension value a dataset may need"""
    tasks = []
    for scope, version in ap.list_runs(params):
        run = ap.resolve_run_params(params, scope, version)
        axes = [a.strip() for a in run["axes_str"].split("/")]
        periods = [p.strip().upper() for p in run["periods_str"].split("/")]
        for target, axe, period in itertools.product(run["target_variables"], axes, periods):
            tasks.append({"scope": scope, "period_run": period_run, "id_set_parameters": ap.id_set_params(scope, version),
                          "t_variable": target, "axe": axe, "period": period})
    return tasks


# 2. Builds

def partition_ids(tasks, dims):
    """Distinct partition ids of a dataset, e.g. "sgcp|2026Q2|arrimage_sgcp_latest|mt_cal_ead_tot"; None if not
    partitioned"""
    if not dims:
        return None
    return sorted({"|".join(task[d] for d in dims) for task in tasks})


def build(scenario, name, tasks):
    ids = partition_ids(tasks, DATASET_DIMS[name])
    print("build {}: {} partition(s) {}".format(name, len(ids) if ids else "all", (ids or [])[:3]))
    scenario.build_dataset(name, build_mode=BUILD_MODE, partitions=",".join(ids) if ids else None,
                           step_name="build " + name)


def run():
    # Zones resolved before anything runs: a wrong member name fails here, not in the middle of the run
    zones = [(getattr(DssZone, zone), datasets) for zone, datasets in STAGES]
    client, scenario = dataiku.api_client(), Scenario()
    params = period_run = tasks = None
    for zone, datasets in zones:
        insert_into_pilotage(client, zone, STATUS_LAUNCH)
        try:
            if params is None:                                       # INIT: checks before any build
                params, period_run = read_context()
                tasks = tasks_of(params, period_run)
                print("period_run={} runs={}".format(period_run, ap.list_runs(params)))
            for name in datasets:
                build(scenario, name, tasks)
        except Exception:
            insert_into_pilotage(client, zone, STATUS_KO)
            raise
        insert_into_pilotage(client, zone, STATUS_OK)
    print("ARRIMAGE_RUN {} done".format(period_run))


run()
