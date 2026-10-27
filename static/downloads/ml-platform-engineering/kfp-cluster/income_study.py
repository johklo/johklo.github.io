import hashlib
import json
from pathlib import Path

import mlflow
import mlflow.data
import mlflow.sklearn
import numpy as np
import pandas as pd
from feast import FeatureStore
from mlflow import MlflowClient
from mlflow.models import infer_signature
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier

repo = Path("income-features-study").resolve()
store = FeatureStore(repo_path=str(repo))
service_name = "income_model_v1"
service = store.get_feature_service(service_name)
labels = pd.read_parquet(repo / "labels.parquet")
data = store.get_historical_features(entity_df=labels, features=service).to_df()
data = data.sort_values(["user_id", "event_timestamp"]).reset_index(drop=True)
columns = ["hours_per_week", "workclass"]
if len(data) != len(labels) or data[columns].isna().any().any():
    raise ValueError("Every label row needs point-in-time features")

snapshot = Path("training_snapshot.csv")
snapshot.write_text(data.to_csv(index=False), encoding="utf-8")
lineage = {
    "data_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "feast_project": store.project,
    "feast_feature_service": service_name,
    "feast_definitions_sha256": hashlib.sha256(
        (repo / "features.py").read_bytes()
    ).hexdigest(),
}
feature_refs = sorted(
    f"{projection.name}:{field.name}"
    for projection in service.feature_view_projections
    for field in projection.features
)

train_valid, test = train_test_split(
    data, test_size=0.2, random_state=23, stratify=data["target"]
)
train, valid = train_test_split(
    train_valid, test_size=0.25, random_state=23,
    stratify=train_valid["target"]
)
baseline = DummyClassifier(strategy="prior").fit(train[columns], train["target"])
baseline_auc = roc_auc_score(
    valid["target"], baseline.predict_proba(valid[columns])[:, 1]
)
training_input = mlflow.data.from_pandas(
    data.drop(columns=["event_timestamp"]), source=str(snapshot.resolve()),
    name="income-training-from-feast", targets="target",
)

mlflow.set_tracking_uri("sqlite:///income-study.db")
mlflow.set_experiment("income-study")
candidates = []
for name, estimator in [
    ("tree", DecisionTreeClassifier(max_depth=3, random_state=23)),
    ("forest", RandomForestClassifier(
        n_estimators=80, max_depth=5, random_state=23
    )),
]:
    transform = ColumnTransformer([
        ("workclass", OneHotEncoder(handle_unknown="ignore"), ["workclass"]),
        ("hours", "passthrough", ["hours_per_week"]),
    ])
    model = Pipeline([("transform", transform), ("classifier", estimator)])
    with mlflow.start_run(run_name=name) as run:
        model.fit(train[columns], train["target"])
        auc = roc_auc_score(
            valid["target"], model.predict_proba(valid[columns])[:, 1]
        )
        mlflow.log_params({
            "model_kind": name, "split_seed": 23,
            "max_depth": estimator.max_depth,
            "train_rows": len(train), "validation_rows": len(valid),
            "feature_refs": json.dumps(feature_refs),
        })
        mlflow.set_tags(lineage)
        mlflow.log_input(training_input, context="training")
        mlflow.log_metric("validation_auc", auc)
        mlflow.log_metric("baseline_validation_auc", baseline_auc)
        mlflow.log_artifact(str(snapshot), artifact_path="data")
        for definition in ("features.py", "feature_store.yaml"):
            mlflow.log_artifact(str(repo / definition), artifact_path="feast")
        mlflow.sklearn.log_model(
            model, "model",
            signature=infer_signature(train[columns], model.predict(train[columns])),
            input_example=train[columns].head(2),
        )
        candidates.append((auc, run.info.run_id, model))

best_auc, run_id, selected = max(candidates, key=lambda item: item[0])
if best_auc < baseline_auc + 0.05:
    raise RuntimeError("No candidate passed the validation improvement gate")

with mlflow.start_run(run_id=run_id):
    test_auc = roc_auc_score(
        test["target"], selected.predict_proba(test[columns])[:, 1]
    )
    mlflow.log_metric("final_test_auc", test_auc)
registered = mlflow.register_model(f"runs:/{run_id}/model", "income-study")
client = MlflowClient()
for key in ("feast_feature_service", "feast_definitions_sha256", "data_sha256"):
    client.set_model_version_tag(
        "income-study", registered.version, key, lineage[key]
    )
fixed_uri = f"models:/income-study/{registered.version}"
loaded = mlflow.sklearn.load_model(fixed_uri)
np.testing.assert_allclose(
    selected.predict_proba(test[columns]),
    loaded.predict_proba(test[columns]),
)
Path("selected_model_uri.txt").write_text(fixed_uri, encoding="utf-8")
print({
    "model_uri": fixed_uri, "feature_service": service_name,
    "rows": len(data), "validation_auc": best_auc, "test_auc": test_auc,
})
