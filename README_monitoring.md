# 室外機冷却システム 監視機能ガイド

## 概要

このプロジェクトに**既存システムに影響を与えない**監視機能を追加するためのガイドです。

監視システムは以下の特徴があります：

- ✅ **非侵襲的** - 既存コードの変更不要
- ✅ **独立動作** - サイドカーコンテナとして動作
- ✅ **簡単導入** - ワンコマンドで導入可能
- ✅ **段階的拡張** - 基本→完全版→高度版と段階的に機能追加

## クイックスタート

### 1. 基本監視の導入

```bash
# 基本的なシステム監視を開始
./deploy_monitoring.sh --basic
```

これだけで以下が開始されます：

- CPU/メモリ/温度監視
- プロセス監視
- ログ解析
- 基本的なアラート

### 2. 監視状況の確認

```bash
# メトリクス確認（JSON形式）
curl http://localhost:8081/metrics/json | jq

# Prometheus形式でメトリクス確認
curl http://localhost:8081/metrics/prometheus

# ログ確認
docker logs unit-cooler-monitoring
```

### 3. 監視の停止/再開

```bash
# 監視停止
docker-compose -f monitoring-compose.yml down

# 監視再開
docker-compose -f monitoring-compose.yml up -d
```

## 導入モード

### 基本モード（推奨）

```bash
./deploy_monitoring.sh --basic
```

- システムリソース監視
- アプリケーション監視
- 基本アラート
- **リソース使用量**: CPU 0.1、メモリ 128MB

### 完全モード

```bash
./deploy_monitoring.sh --full
```

基本モード + 以下を追加：

- Prometheus（メトリクス収集）
- Grafana（可視化ダッシュボード）
- 詳細な時系列データ

アクセス先：

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin123)

### 高度モード（将来拡張）

```bash
./deploy_monitoring.sh --advanced
```

完全モード + 以下を追加：

- 機械学習による異常検知
- 予兆検知
- 自動回復提案

## 収集されるメトリクス

### システムメトリクス

| メトリクス          | 説明                    | 単位 |
| ------------------- | ----------------------- | ---- |
| cpu_percent         | CPU使用率               | %    |
| cpu_temperature     | CPU温度（Raspberry Pi） | ℃    |
| memory_percent      | メモリ使用率            | %    |
| memory_available_mb | 利用可能メモリ          | MB   |
| disk_usage_percent  | ディスク使用率          | %    |
| load_average_1m     | 1分間平均負荷           | -    |
| process_count       | プロセス数              | 個   |

### アプリケーションメトリクス

| メトリクス       | 説明               | 単位 |
| ---------------- | ------------------ | ---- |
| services_alive   | 生存サービス数     | 個   |
| error_count      | エラー発生数       | 個   |
| valve_operations | バルブ操作数       | 回   |
| sensor_reads     | センサー読み取り数 | 回   |
| python_processes | Pythonプロセス数   | 個   |

## アラート設定

### デフォルト閾値

```yaml
thresholds:
    cpu_warning: 80.0 # CPU 80%で警告
    cpu_critical: 95.0 # CPU 95%で重要
    memory_warning: 85.0 # メモリ 85%で警告
    memory_critical: 95.0 # メモリ 95%で重要
    temperature_warning: 70.0 # 70℃で警告
    temperature_critical: 85.0 # 85℃で重要
```

### カスタマイズ

`monitoring_config.yaml`を編集して設定変更：

```yaml
# 例：より厳しい閾値に変更
thresholds:
    cpu_warning: 60.0 # 60%で警告
    memory_warning: 70.0 # 70%で警告
```

変更後は再起動：

```bash
docker-compose -f monitoring-compose.yml restart unit-cooler-monitoring
```

## ファイル構成

```
outdoor_unit_cooler/
├── src/monitoring_agent.py      # 監視エージェント本体
├── monitoring_config.yaml       # 監視設定
├── monitoring.Dockerfile        # 監視用Dockerイメージ
├── monitoring-compose.yml       # 監視サービス定義
├── deploy_monitoring.sh         # 導入スクリプト
└── README_monitoring.md         # このファイル
```

## データ出力先

### ローカルファイル

```
/tmp/unit_cooler_monitoring/
├── metrics.json          # 最新メトリクス（JSON形式）
├── alerts.json           # アラート履歴
└── metrics.prom          # Prometheus形式メトリクス
```

### HTTP API

- `http://localhost:8081/metrics/json` - JSON形式メトリクス
- `http://localhost:8081/metrics/prometheus` - Prometheus形式
- `http://localhost:8081/alerts` - アラート一覧（将来実装）

## トラブルシューティング

### 監視が開始されない

```bash
# ログ確認
docker logs unit-cooler-monitoring

# コンテナ状態確認
docker ps -a | grep monitoring

# 権限問題の場合
sudo chown -R $(whoami):$(whoami) /tmp/unit_cooler_monitoring
```

### メトリクスが収集されない

```bash
# 設定確認
cat monitoring_config.yaml

# ファイルアクセス確認
docker exec unit-cooler-monitoring ls -la /dev/shm
docker exec unit-cooler-monitoring ls -la /var/log
```

### パフォーマンス影響がある場合

```bash
# 収集間隔を長くする
sed -i 's/interval_seconds: 60/interval_seconds: 120/' monitoring_config.yaml

# 監視機能を一部無効化
sed -i 's/collect_log_metrics: true/collect_log_metrics: false/' monitoring_config.yaml

# 再起動して反映
docker-compose -f monitoring-compose.yml restart unit-cooler-monitoring
```

## セキュリティ考慮事項

### アクセス制限

- 監視APIはlocalhostからのみアクセス可能
- 非rootユーザーでコンテナ実行
- 読み取り専用でのボリュームマウント

### データ保護

- 機密情報は収集しない
- ログ解析は数値データのみ抽出
- 一定期間後にデータ自動削除

## 既存システムへの影響

### 影響なし

- ✅ 既存コードの変更不要
- ✅ 既存APIとの競合なし
- ✅ 既存データベースへの影響なし
- ✅ 独立したプロセスとして動作

### リソース使用量

- **CPU**: 0.1コア以下
- **メモリ**: 128MB以下
- **ディスク**: 読み取り専用
- **ネットワーク**: 最小限

## 将来の拡張

### 予定機能

- [ ] 機械学習による異常検知
- [ ] 予兆検知とアラート
- [ ] 自動回復機能
- [ ] より詳細なアプリケーションメトリクス
- [ ] Slackアラート連携
- [ ] 外部メトリクス送信（InfluxDB等）

### カスタマイズ例

独自メトリクスの追加や、アラート条件のカスタマイズが可能です。詳細は`src/monitoring_agent.py`を参照してください。

## サポート

問題や質問がある場合は、以下のコマンドでログを確認してください：

```bash
# 詳細ログ出力で再起動
docker-compose -f monitoring-compose.yml down
docker-compose -f monitoring-compose.yml up -d --force-recreate unit-cooler-monitoring

# ログ確認
docker logs -f unit-cooler-monitoring
```
