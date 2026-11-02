
import dataiku
import dataikuapi

from core.constants import (STAGING_ENV, ATM_URL, ATM_APIKEY, INFRA_DICT, PROJECT_KEY_DICT,
                            CONNECTION_DICT, DATABASE_DICT, CONNECTION_NAME_VAR, DATABASE_NAME_VAR)

ENV = STAGING_ENV
PUBLISHED_PROJECT = "DETECT_SRS_ARRIMAGE_DEV"           # key shown in Local Deployer > Projects: check it
TARGET_PROJECT = "DETECT_SRS_ARRIMAGE_STAGING"          # project created on the ATM node

client = dataiku.api_client()
project = client.get_default_project()
variables = project.get_variables()
bundle_id = variables["local"].get("bundle_id")
infra_id = INFRA_DICT[ENV]
if not bundle_id:
    raise ValueError("No bundle_id in the local variables: run 'Variables for bundle' and 'Create bundle' first")
if TARGET_PROJECT in PROJECT_KEY_DICT.values():
    raise ValueError("{} is a DETECT_DESIGN project: refusing to deploy Arrimage onto it".format(TARGET_PROJECT))

deployer = client.get_projectdeployer()
published = [p.id for p in deployer.list_projects()]
if PUBLISHED_PROJECT not in published:
    raise ValueError("{} not on the Deployer (published projects: {})".format(PUBLISHED_PROJECT, published))

# One deployment for Arrimage on this infra: created the first time, its bundle updated afterwards
deployment_id = "{}-on-{}".format(TARGET_PROJECT, infra_id)
existing = [d.id for d in deployer.list_deployments()]
if deployment_id in existing:
    deployment = deployer.get_deployment(deployment_id)
    settings = deployment.get_settings()
    settings.bundle_id = bundle_id
    print("update {} to bundle {}".format(deployment_id, bundle_id))
else:
    deployment = deployer.create_deployment(deployment_id=deployment_id, project_key=PUBLISHED_PROJECT,
                                            infra_id=infra_id, bundle_id=bundle_id,
                                            deployed_project_key=TARGET_PROJECT)
    settings = deployment.get_settings()
    print("create {} with bundle {}".format(deployment_id, bundle_id))
settings.get_raw()["localVariables"] = {"env": ENV, CONNECTION_NAME_VAR: CONNECTION_DICT.get(ENV),
                                        DATABASE_NAME_VAR: DATABASE_DICT.get(ENV),
                                        "flow_type": "arrimage"}
settings.save()
deployment.start_update().wait_for_result()

variables["local"].pop("bundle_id", None)
project.set_variables(variables)

# Label of the deployed project on the ATM node (as rename_dss_project, but on the Arrimage project)
atm = dataikuapi.DSSClient(host=ATM_URL, api_key=ATM_APIKEY, insecure_tls=True)
target = atm.get_project(TARGET_PROJECT)
metadata = target.get_metadata()
metadata["label"] = TARGET_PROJECT
target.set_metadata(metadata)
print("deployed {} -> {} on {}".format(bundle_id, TARGET_PROJECT, infra_id))
