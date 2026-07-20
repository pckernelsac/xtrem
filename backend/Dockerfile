FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    # WeasyPrint: motor de render del PDF de la ficha
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libffi-dev \
    libjpeg62-turbo libopenjp2-7 shared-mime-info \
    # Liberation Sans Narrow es la condensada más parecida a la ficha impresa
    fonts-liberation fonts-dejavu-core \
    # poppler-utils permite revisar el PDF renderizado (pdftoppm) en desarrollo
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CRLF si el repo se clonó desde Windows: sin esto el shebang falla con
# "no such file or directory", que despista mucho.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# En desarrollo el compose sobreescribe el `command` con uvicorn --reload.
CMD ["/app/entrypoint.sh"]
