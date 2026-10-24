FROM python:3.11-slim-bookworm
WORKDIR /study
RUN pip install --no-cache-dir \
    mlflow==2.16.2 scikit-learn==1.5.2 feast==0.40.1 \
    pandas==2.2.3 numpy==1.26.4 pyarrow==17.0.0 \
    kfp==2.10.1 sqlalchemy==2.0.36
COPY income_study.py feature_study.py ./
RUN python income_study.py && python feature_study.py
