FROM python:3.12-slim
WORKDIR /project
COPY app/backend/requirements.txt /project/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home app
COPY app /project/app
COPY data /project/data
USER app
WORKDIR /project/app/backend
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
