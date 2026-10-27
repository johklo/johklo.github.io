from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from feast import FeatureStore

repo = Path("income-features-study").resolve()
repo.mkdir()
rng = np.random.default_rng(23)
users = np.arange(1000, 1600)
classes = ["private", "public", "self-employed"]
observed = pd.Timestamp("2025-04-01", tz="UTC") + pd.to_timedelta(
    rng.integers(0, 30, size=users.size), unit="D"
)
hours = rng.integers(20, 61, size=users.size).astype(float)
workclass = rng.choice(classes, size=users.size)
history = pd.concat([
    pd.DataFrame({
        "user_id": users, "event_timestamp": observed,
        "hours_per_week": hours, "workclass": workclass,
    }),
    pd.DataFrame({
        "user_id": users, "event_timestamp": observed + pd.Timedelta(days=45),
        "hours_per_week": rng.integers(20, 61, size=users.size).astype(float),
        "workclass": rng.choice(classes, size=users.size),
    }),
    pd.DataFrame({
        "user_id": [42, 42],
        "event_timestamp": pd.to_datetime([
            "2025-05-21T00:00:00Z", "2025-06-04T00:00:00Z"
        ]),
        "hours_per_week": [36.0, 52.0],
        "workclass": ["private", "self-employed"],
    }),
], ignore_index=True)
source = repo / "hours.parquet"
history.to_parquet(source, index=False)

effect = pd.Series(workclass).map({
    "private": 0.0, "public": -0.4, "self-employed": 0.8
}).to_numpy()
score = (hours - 40) / 8 + effect + rng.normal(size=users.size)
pd.DataFrame({
    "user_id": users,
    "event_timestamp": observed + pd.Timedelta(days=7),
    "target": (score > 0).astype(int),
}).to_parquet(repo / "labels.parquet", index=False)

(repo / "feature_store.yaml").write_text(
    "project: income_study\n"
    "provider: local\n"
    "entity_key_serialization_version: 2\n"
    "registry: registry.db\n"
    "offline_store:\n  type: file\n"
    "online_store:\n  type: sqlite\n  path: online.db\n",
    encoding="utf-8",
)
(repo / "features.py").write_text(
    "from datetime import timedelta\n"
    "from feast import Entity, FeatureService, FeatureView, Field, FileSource, ValueType\n"
    "from feast.types import Float64, String\n"
    "user = Entity(name='user', join_keys=['user_id'], value_type=ValueType.INT64)\n"
    f"source = FileSource(path={str(source)!r}, timestamp_field='event_timestamp')\n"
    "hours = FeatureView(name='hours', entities=[user], "
    "ttl=timedelta(days=365), "
    "schema=[Field(name='hours_per_week', dtype=Float64), "
    "Field(name='workclass', dtype=String)], source=source)\n"
    "income_model_v1 = FeatureService(name='income_model_v1', features=[hours])\n",
    encoding="utf-8",
)
spec = importlib.util.spec_from_file_location("study_features", repo / "features.py")
definitions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(definitions)
store = FeatureStore(repo_path=str(repo))
store.apply([definitions.user, definitions.hours, definitions.income_model_v1])

service = store.get_feature_service("income_model_v1")
entities = pd.DataFrame({
    "user_id": [42],
    "event_timestamp": pd.to_datetime(["2025-05-22T00:00:00Z"]),
})
entities.to_parquet(repo / "requests.parquet", index=False)
historical = store.get_historical_features(
    entity_df=entities, features=service
).to_df()
print("Historical:", historical["hours_per_week"].tolist())
store.materialize(
    datetime(2025, 4, 1, tzinfo=timezone.utc),
    datetime(2025, 7, 1, tzinfo=timezone.utc),
)
online = store.get_online_features(
    features=service, entity_rows=[{"user_id": 42}]
).to_dict()
print("Online:", online["hours_per_week"])
