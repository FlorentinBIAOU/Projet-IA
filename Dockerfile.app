# Image de l'application : dashboard Streamlit et programme en ligne de commande (main.py).
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1
# Par defaut : le dashboard. Pour le programme seul : docker run ... python main.py --version toutes
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
