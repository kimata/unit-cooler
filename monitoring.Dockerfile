# 室外機冷却システム用監視エージェント Docker イメージ
# 既存システムに影響を与えないサイドカーコンテナ

FROM python:3.12-slim

# 必要なパッケージをインストール
RUN apt-get update && apt-get install -y \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Python依存関係をインストール
RUN pip install --no-cache-dir \
    psutil>=6.1.0 \
    pyyaml>=6.0 \
    aiohttp>=3.8.0 \
    numpy>=1.24.0 \
    scikit-learn>=1.3.0

# 作業ディレクトリを設定
WORKDIR /app

# 監視エージェントをコピー
COPY src/monitoring_agent.py /app/
COPY monitoring_config.yaml /app/

# 実行権限を付与
RUN chmod +x /app/monitoring_agent.py

# ヘルスチェック用ディレクトリを作成
RUN mkdir -p /tmp/unit_cooler_monitoring

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD test -f /tmp/unit_cooler_monitoring/metrics.json || exit 1

# 非rootユーザーで実行
RUN useradd -r -s /bin/false monitoring
USER monitoring

# 環境変数
ENV PYTHONPATH=/app
ENV MONITORING_CONFIG=/app/monitoring_config.yaml

# ポート公開（将来のWeb UI用）
EXPOSE 8081

# エージェント開始
CMD ["python", "/app/monitoring_agent.py", "--config", "/app/monitoring_config.yaml"]
