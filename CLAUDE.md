# CLAUDE.md

このファイルは Claude Code がこのリポジトリで作業する際のガイダンスを提供します。

## 概要

Raspberry Pi を使用したエアコン室外機の自動冷却システム。InfluxDB からの電力データを監視し、エアコン稼働を検知すると自動的にミスト噴射を制御する省エネソリューション。

## 重要な注意事項

### コード変更時のドキュメント更新

コードを更新した際は、以下のドキュメントも更新が必要か**必ず検討してください**:

| ドキュメント | 更新が必要なケース                                                 |
| ------------ | ------------------------------------------------------------------ |
| README.md    | 機能追加・変更、使用方法の変更、依存関係の変更                     |
| CLAUDE.md    | アーキテクチャ変更、新規モジュール追加、設定項目変更、開発手順変更 |

### my-lib（共通ライブラリ）の修正について

`my_lib` のソースコードは **`../my-py-lib`** に存在します。

リファクタリング等で `my_lib` の修正が必要な場合:

1. **必ず事前に何を変更したいか説明し、確認を取ること**
2. `../my-py-lib` で修正を行い、commit & push
3. このリポジトリの `pyproject.toml` の my-lib のコミットハッシュを更新
4. `uv lock && uv sync` で依存関係を更新

```bash
# my-lib 更新の流れ
cd ../my-py-lib
# ... 修正 ...
git add . && git commit -m "変更内容" && git push
cd ../unit-cooler
# pyproject.toml の my-lib ハッシュを更新
uv lock && uv sync
```

### プロジェクト管理ファイルについて

以下のファイルは **`../py-project`** で一元管理しています:

- `pyproject.toml`
- `.pre-commit-config.yaml`
- `.gitignore`
- `.gitlab-ci.yml`
- その他プロジェクト共通設定

**これらのファイルを直接編集しないでください。**

修正が必要な場合:

1. **必ず事前に何を変更したいか説明し、確認を取ること**
2. `../py-project` のテンプレートを更新
3. このリポジトリに変更を反映

## 開発環境

### パッケージ管理

- **パッケージマネージャー**: uv
- **依存関係のインストール**: `uv sync`
- **依存関係の更新**: `uv lock --upgrade-package <package-name>`

### テスト実行

テストは3層構造で管理されています:

```bash
# ユニットテスト（外部依存なし、高速）
uv run pytest tests/unit/

# 統合テスト（コンポーネント間の連携テスト）
uv run pytest tests/integration/

# E2E テスト（Playwright、外部サーバー必要）
uv run pytest tests/e2e/ --host <host> --port <port>

# 型チェック
uv run mypy src/

# 全テスト
uv run pytest

# 並列テスト実行（高速化）
uv run pytest --numprocesses=auto
```

### アプリケーション実行

```bash
# Controller（InfluxDB 監視・制御信号配信）
uv run python ./src/controller.py -c config.yaml

# Actuator（Raspberry Pi で実行、GPIO 制御）
uv run python ./src/actuator.py -c config.yaml

# Web UI（Flask API + React フロントエンド）
uv run python ./src/webui.py -c config.yaml

# デバッグモード
uv run python ./src/webui.py -c config.yaml -D

# ダミーモード（ハードウェアなしでテスト）
uv run python ./src/actuator.py -c config.yaml -d
```

### React 開発

```bash
# 依存関係インストール
cd react && npm ci

# 開発サーバー起動（localhost:3000）
npm start

# プロダクションビルド
npm run build
```

## アーキテクチャ

### 3層構成

1. **Controller** (`src/controller.py`) - InfluxDB データ取得・ZeroMQ 制御信号配信
2. **Actuator** (`src/actuator.py`) - Raspberry Pi GPIO 制御・電磁弁操作
3. **Web UI** (`src/webui.py`) - Flask API + React フロントエンド

### ディレクトリ構成

```
src/
├── controller.py              # Controller エントリーポイント
├── actuator.py                # Actuator エントリーポイント
├── webui.py                   # Web UI エントリーポイント
└── unit_cooler/
    ├── config.py              # 型付き設定クラス（frozen dataclass）
    │
    ├── controller/            # Controller コンポーネント
    │   ├── app.py             # メインループ
    │   ├── influxdb_query.py  # InfluxDB クエリ
    │   └── zmq_publisher.py   # ZeroMQ パブリッシャー
    │
    ├── actuator/              # Actuator コンポーネント
    │   ├── app.py             # メインループ
    │   ├── worker.py          # Duty 制御ワーカー
    │   ├── control.py         # GPIO 制御ロジック
    │   ├── flow_sensor.py     # 流量センサー制御
    │   └── zmq_subscriber.py  # ZeroMQ サブスクライバー
    │
    ├── webui/                 # Web UI コンポーネント
    │   ├── app.py             # Flask アプリケーション
    │   ├── zmq_subscriber.py  # ZeroMQ サブスクライバー
    │   └── webapi/            # REST API エンドポイント
    │       ├── server.py      # Flask ブループリント
    │       └── page.py        # API ハンドラ
    │
    └── metrics/               # メトリクス収集・可視化
        ├── collector.py       # データ収集
        ├── storage.py         # SQLite 永続化
        └── webapi/            # メトリクス API
            └── page.py        # ダッシュボード

frontend/                         # React フロントエンド
├── src/
│   ├── App.tsx                # メインコンポーネント
│   ├── components/            # UI コンポーネント
│   │   ├── Watering.tsx       # 散水状況
│   │   ├── CoolingMode.tsx    # 冷却モード
│   │   ├── AirConditioner.tsx # エアコン稼働状況
│   │   ├── Sensor.tsx         # センサー値
│   │   ├── History.tsx        # 散水履歴
│   │   ├── Log.tsx            # アクティビティログ
│   │   ├── common/            # 共通コンポーネント
│   │   │   ├── Loading.tsx
│   │   │   ├── ErrorMessage.tsx
│   │   │   ├── AnimatedNumber.tsx
│   │   │   └── Pagination.tsx
│   │   └── icons/             # アイコンコンポーネント
│   │       └── index.tsx      # Heroicons + カスタム SVG
│   ├── hooks/                 # カスタムフック
│   │   └── useApi.ts          # API フェッチフック
│   └── lib/                   # ユーティリティ
│       └── ApiResponse.ts     # API レスポンス型定義

tests/
├── conftest.py                # 共通フィクスチャ
├── unit/                      # ユニットテスト
│   ├── controller/
│   ├── actuator/
│   ├── webui/
│   └── metrics/
├── integration/               # 統合テスト
└── e2e/                       # E2E テスト（Playwright）
```

### プロセス間通信

- **ZeroMQ Publisher-Subscriber** パターンでリアルタイム分散メッセージング
- **Last Value Caching Proxy** による信頼性向上
- ポート: 5559（Controller→Actuator）, 5560（Web UI→Frontend）

### 技術スタック

| レイヤー       | 技術                                            |
| -------------- | ----------------------------------------------- |
| バックエンド   | Python 3.12, Flask, ZeroMQ, InfluxDB, rpi-lgpio |
| フロントエンド | React 19, TypeScript, Vite, Tailwind CSS 4.x    |
| UI ライブラリ  | Heroicons 2.x, Chart.js, Framer Motion          |
| テスト         | pytest, Playwright, pytest-cov, mypy            |
| インフラ       | Docker, Kubernetes, GitLab CI                   |

### 設定ファイル

#### config.yaml

```yaml
controller:
    zmq:
        endpoint: "tcp://localhost:5559"
    influxdb:
        host: "influxdb.example.com"
        # ...

actuator:
    gpio:
        valve_pin: 17
    flow_sensor:
        # ...
    metrics:
        data: "data/metrics.db" # メトリクス DB パス

webui:
    flask:
        port: 5000
    zmq:
        endpoint: "tcp://localhost:5560"
```

### 重要な設定アクセスパターン

Config は **frozen dataclass** として定義されています。dict スタイルのアクセス（`config.get()`）ではなく、属性アクセスを使用してください:

```python
# Good: dataclass 属性アクセス
db_path = config.actuator.metrics.data

# Bad: dict スタイルアクセス（AttributeError になる）
db_path = config.get("actuator", {}).get("metrics", {}).get("data")
```

## デプロイ

### Docker

```bash
# フロントエンドビルド
cd react && npm ci && npm run build && cd ..

# Docker Compose 起動
docker-compose up -d
```

### Kubernetes

```bash
# デプロイ
kubectl apply -f kubernetes/outdoor_unit_cooler.yml

# 状態確認
kubectl get pods -n hems
kubectl logs -n hems -l app=unit-cooler-controller
```

- マルチアーキテクチャ対応（AMD64, ARM64）
- 特権モード必要（GPIO/SPI アクセス）
- MetalLB LoadBalancer 統合

## 依存ライブラリ

### 主要な外部依存

| ライブラリ      | 用途                    |
| --------------- | ----------------------- |
| flask           | Web フレームワーク      |
| pyzmq           | ZeroMQ バインディング   |
| influxdb-client | InfluxDB クライアント   |
| rpi-lgpio       | Raspberry Pi GPIO 制御  |
| coloredlogs     | カラーログ出力          |
| pyyaml          | YAML 設定ファイル読み込 |

### my-lib（自作共通ライブラリ）

| モジュール           | 用途                              |
| -------------------- | --------------------------------- |
| my_lib.config        | YAML 設定読み込み（スキーマ検証） |
| my_lib.notify.slack  | Slack 通知（レート制限付き）      |
| my_lib.healthz       | Liveness チェック                 |
| my_lib.footprint     | タイムスタンプファイル管理        |
| my_lib.webapp.config | Flask アプリケーション設定        |
| my_lib.flask_util    | Flask ユーティリティ              |
| my_lib.sensor_data   | InfluxDB センサーデータ取得       |

## コーディング規約

- Python 3.12+
- 型ヒントを積極的に使用
- dataclass で不変オブジェクトを定義（`frozen=True`）
- ruff でフォーマット・lint
- mypy で型チェック

### インポートスタイル

`from xxx import yyy` は基本的に使わず、`import yyy` としてモジュールをインポートし、使用時は `yyy.xxx` の形式で参照する。

```python
# Good
import my_lib.flask_util
my_lib.flask_util.get_remote_addr(request)

# Avoid
from my_lib.flask_util import get_remote_addr
get_remote_addr(request)
```

**例外:**

- 標準ライブラリの一般的なパターン（例: `from pathlib import Path`）
- 型ヒント用のインポート（`from typing import TYPE_CHECKING`）
- dataclass などのデコレータ（`from dataclasses import dataclass`）

### 型チェック（mypy）

mypy のエラー対策として、各行に `# type: ignore` コメントを付けて回避するのは**最後の手段**とします。

基本方針:

1. **型推論が効くようにコードを書く** - 明示的な型注釈や適切な変数の初期化で対応
2. **型の絞り込み（Type Narrowing）を活用** - `assert`, `if`, `isinstance()` 等で型を絞り込む
3. **どうしても回避できない場合のみ `# type: ignore`** - その場合は理由をコメントに記載

```python
# Good: 型の絞り込み
value = get_optional_value()
assert value is not None
use_value(value)

# Avoid: type: ignore での回避
value = get_optional_value()
use_value(value)  # type: ignore
```

**例外:** テストコードでは、モックオブジェクトの使用など型チェックが困難な場合に `# type: ignore` を使用可能です。

### React/TypeScript

- コンポーネントは `React.memo()` でラップしてパフォーマンス最適化
- `useCallback` / `useMemo` で不要な再レンダリングを防止
- カスタムフック（`useApi`）でデータフェッチロジックを共通化
- Tailwind CSS 4.x のユーティリティクラスを使用（Bootstrap は廃止）
- アイコンは Heroicons 2.x + カスタム SVG（`components/icons/index.tsx`）
