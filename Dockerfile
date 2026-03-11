FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CALB_OUTPUTS_DIR=/app/runtime/outputs \
    CALB_PREFERENCES_FILE=/app/runtime/state/user_preferences.json \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_HEADLESS=true

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    graphviz \
    libcairo2 \
    libffi-dev \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libpango-1.0-0 \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/runtime/outputs /app/runtime/state

EXPOSE 8501

CMD ["sh", "-c", "mkdir -p \"${CALB_OUTPUTS_DIR}\" \"$(dirname \"${CALB_PREFERENCES_FILE}\")\" && exec streamlit run app.py --server.address=${STREAMLIT_SERVER_ADDRESS:-0.0.0.0} --server.port=${STREAMLIT_SERVER_PORT:-8501} --server.headless=${STREAMLIT_SERVER_HEADLESS:-true} --server.fileWatcherType=none"]
