FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY clinic ./clinic
COPY packs ./packs
COPY sources ./sources
COPY web ./web
COPY demo_docs ./demo_docs
COPY prompts ./prompts

ENV CLINIC_NO_MODEL=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "clinic.api:app", "--host", "0.0.0.0", "--port", "8000"]
