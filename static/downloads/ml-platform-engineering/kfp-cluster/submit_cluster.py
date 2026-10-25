import argparse
import importlib.util
from pathlib import Path

from kfp import Client, compiler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://127.0.0.1:18580")
    parser.add_argument("--image", default="income-study:chapter05")
    parser.add_argument("--model-uri", default="models:/income-study/1")
    parser.add_argument("--feature-service", default="income_model_v1")
    parser.add_argument("--run-name", default="income-study-kubernetes")
    args = parser.parse_args()

    source = Path("pipeline_study.py").read_text(encoding="utf-8")
    original = 'base_image="python:3.12-slim-bookworm"'
    if source.count(original) != 4:
        raise ValueError("Expected the four components from chapter 5")
    source = source.replace(original, f"base_image={args.image!r}")
    module_path = Path("pipeline_cluster.py")
    module_path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("pipeline_cluster", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    package = "income-study-cluster.yaml"
    compiler.Compiler().compile(
        pipeline_func=module.study_pipeline, package_path=package
    )
    client = Client(host=args.host)
    run = client.create_run_from_pipeline_package(
        pipeline_file=package,
        arguments={
            "source_path": "/study/income-features-study/requests.parquet",
            "repo_path": "/study/income-features-study",
            "tracking_uri": "sqlite:////study/income-study.db",
            "model_uri": args.model_uri,
            "feature_service": args.feature_service,
        },
        run_name=args.run_name,
        experiment_name="chapter-05",
        enable_caching=False,
    )
    Path("cluster-run-id.txt").write_text(run.run_id, encoding="utf-8")
    print(f"Run ID: {run.run_id}", flush=True)
    result = client.wait_for_run_completion(
        run_id=run.run_id, timeout=900, sleep_duration=5
    )
    print(f"Run state: {result.state}", flush=True)
    if result.state != "SUCCEEDED":
        raise RuntimeError(f"Pipeline did not succeed: {result.state}")


if __name__ == "__main__":
    main()
