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

### 後方互換性コードの扱い

- 後方互換性のためだけに維持されているコードは、影響範囲を調査した上で積極的に削除する
- 新しいコードでは、後方互換性のためのラッパー関数やフォールバック処理を作成しない
- `isinstance()` による複数型の分岐が必要な場合は、設計を見直すか Protocol の導入を検討する

### デッドコードの積極的な削除

使用されていないコード（関数、変数、クラス）は積極的に削除する:

- 未使用の変数・定数は削除する
- 呼び出されていない関数は削除する
- 「将来使うかもしれない」コードは残さない
- 後方互換性のためだけのコードは削除を検討する

デッドコードを残すことによる問題:

- 保守コストの増加
- 読み手の混乱
- 不要な依存関係の維持

### 関数の重複定義を避ける

同じ機能を持つ関数が複数ファイルで定義されている場合は、1箇所に集約する:

- ユーティリティ関数は適切なモジュールに配置
- 他モジュールからは import して使用

### isinstance() による型分岐の削減

複数の型を受け入れる関数では、早期に正規化して単一の型で処理する:

```python
# Good: 早期正規化
def process(data: DataClass | dict) -> None:
    normalized = DataClass.from_dict(data) if isinstance(data, dict) else data
    # 以降は DataClass として処理

# Avoid: 処理全体で分岐
def process(data: DataClass | dict) -> None:
    if isinstance(data, DataClass):
        # DataClass として処理
    else:
        # dict として処理
```

### dict[str, Any] の使用制限

- 構造化されたデータには `dataclass` または `TypedDict` を使用する
- `dict[str, Any]` は以下の場合のみ許容:
    - 外部 API からの JSON レスポンスの一時的な受け取り
    - シリアライゼーション境界（to_dict/from_dict メソッド内）
- 内部で使い回す構造化データは必ず型定義する

### ハンドルオブジェクトの dataclass 化

ワーカー関数で使用するハンドルオブジェクト（状態を保持する辞書）は dataclass として定義する:

```python
# Good: dataclass を使用
@dataclass
class WorkerHandle:
    config: Config
    process_count: int = 0

# Avoid: dict[str, Any] を使用
def gen_handle(config) -> dict[str, Any]:
    return {"config": config, "process_count": 0}
```

サーバーやスレッドを管理するハンドルも dataclass を使用する:

```python
# Good: サーバーハンドルの dataclass 化
@dataclass
class WebServerHandle:
    server: werkzeug.serving.BaseWSGIServer
    thread: threading.Thread

def start(config: Config, port: int) -> WebServerHandle:
    server = make_server(...)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    return WebServerHandle(server=server, thread=thread)

def term(handle: WebServerHandle) -> None:
    handle.server.shutdown()
    handle.thread.join()

# Avoid: dict で返す
def start(...) -> dict[str, Any]:
    return {"server": server, "thread": thread}
```

### TypedDict より dataclass を優先

構造化データには TypedDict より dataclass を使用する:

```python
# Good: dataclass（型安全、IDE補完、frozen可能）
@dataclass(frozen=True)
class StatusResult:
    status: int
    message: str | None

# Avoid: TypedDict（辞書アクセス、immutability なし）
class StatusDict(TypedDict):
    status: int
    message: str | None
```

### 数値型の統一

センサーデータなど浮動小数点数を扱う場合は `float` に統一する:

```python
# Good: float に統一
flow: float | None = 0.0

# Avoid: int と float の混在
flow: float | int | None = 0
```

### dataclass への移行ルール

新規コードで `dict[str, Any]` を返す関数を作成する場合は、dataclass の使用を検討する。
既存の `dict[str, Any]` を返す関数は、以下の条件を満たす場合に dataclass への移行を検討:

1. 対応する dataclass が既に存在する
2. 影響範囲が限定的（呼び出し元が少ない）
3. テストカバレッジが十分

### IIFE パターンの回避

即時実行関数式（IIFE）より、Python の標準的な条件式を使用する:

```python
# Good: or 演算子
value = get_value() or default_value

# Good: 条件式
value = get_value() if condition else default_value

# Avoid: IIFE lambda
value = (lambda x: x if x is not None else default)(get_value())
```

### 時刻取得の統一

時刻取得には `my_lib.time.now()` を使用する:

```python
# Good: my_lib.time を使用
import my_lib.time
timestamp = my_lib.time.now()

# Avoid: datetime.now() を直接使用
from datetime import datetime
timestamp = datetime.now()
```

**例外:** UTC タイムスタンプが明示的に必要な場合は `datetime.datetime.now(datetime.UTC)` を使用可。

### 関数属性による状態保持の禁止

関数属性（`func.attr = value`）による状態保持は使用しない:

```python
# Good: モジュールレベル変数
_last_value: int | None = None

def get_value() -> int | None:
    global _last_value
    # ...
    return _last_value

# Avoid: 関数属性
def get_value() -> int | None:
    # ...
    get_value.last_value = value  # type: ignore が必要になる
    return get_value.last_value
```

### 設定リストの dataclass 化

設定や判定条件のリストは dataclass を使用して定義する:

```python
# Good: dataclass を使用
@dataclass
class JudgeCondition:
    judge: Callable[[dict], bool]
    message: str
    status: int

CONDITIONS: list[JudgeCondition] = [
    JudgeCondition(judge=lambda x: x > 0, message="Positive", status=1),
]

# Avoid: dict のリスト
CONDITIONS = [
    {"judge": lambda x: x > 0, "message": "Positive", "status": 1},
]
```

### base_dir を活用したパス解決

設定ファイルで指定する相対パスは、`config.base_dir` を基準に解決する。ハードコードされたデフォルトパスは使用せず、常に config から取得する:

```python
# Good: config から取得
db_path = config.actuator.metrics.data

# Avoid: ハードコードされたデフォルトパス
DEFAULT_DB_PATH = pathlib.Path("data/metrics.db")
db_path = db_path or DEFAULT_DB_PATH
```

### Protocol の使用方針

Protocol は以下の場合のみ検討する:

- 外部ライブラリとのインターフェースが必要な場合
- 複数の無関係なクラスが同じ振る舞いを持つ場合

現状の dataclass ベースの設計で十分な場合は、Protocol を導入しない。

### `| None` と isinstance の使用方針

- `| None` は初期化状態や Optional パラメータの表現として正当
- `isinstance()` は外部ライブラリの戻り値チェックや型ガードとして正当
- 複数箇所で同じ `isinstance()` チェックがある場合は、ヘルパー関数に集約を検討

### シングルトンパターンの使用

シングルトンは以下のパターンで実装する:

```python
# パターン1: グローバルインスタンス + getter関数（推奨）
_instance: MyClass | None = None

def get_instance() -> MyClass:
    global _instance
    if _instance is None:
        _instance = MyClass()
    return _instance

# パターン2: 明示的な初期化が必要な場合
_instance: MyClass | None = None

def init(config: Config) -> None:
    global _instance
    _instance = MyClass(config)

def get_instance() -> MyClass:
    assert _instance is not None
    return _instance
```

### 環境変数の使用

テストモードやダミーモードの判定には環境変数を使用する:

```python
# 許容: 環境変数による分岐
if os.environ.get("TEST", "false") == "true":
    # テスト専用の処理

if os.environ.get("DUMMY_MODE", "false") == "true":
    # ダミーモード専用の処理
```

環境変数の参照は各モジュールで独立して行い、中央集権的な管理は行わない。

**使用される主な環境変数:**

| 環境変数              | 用途                             |
| --------------------- | -------------------------------- |
| `TEST`                | テストモードの判定               |
| `DUMMY_MODE`          | ハードウェアなしでのダミーモード |
| `PYTEST_XDIST_WORKER` | pytest-xdist のワーカー識別      |

### my_lib 機能の優先使用

以下の機能は my_lib を優先的に使用する:

| 機能             | my_lib モジュール            | 避けるべきパターン                |
| ---------------- | ---------------------------- | --------------------------------- |
| 時刻取得         | `my_lib.time.now()`          | `datetime.datetime.now()`         |
| タイムゾーン     | `my_lib.time.get_zoneinfo()` | `zoneinfo.ZoneInfo("Asia/Tokyo")` |
| 設定読み込み     | `my_lib.config.load()`       | 直接 YAML パース                  |
| ファイル更新時刻 | `my_lib.footprint`           | 直接ファイル操作                  |

### datetime モジュールのインポートスタイル

datetime モジュールは `import datetime` でインポートし、使用時は `datetime.datetime` と記述する:

```python
# Good
import datetime
timestamp: datetime.datetime = my_lib.time.now()

# Avoid
from datetime import datetime
timestamp: datetime = ...
```

### タイムアウト計算には time.monotonic() を使用

タイムアウトや経過時間の計算には `time.time()` ではなく `time.monotonic()` を使用する:

```python
# Good: time.monotonic()（システムクロック変更の影響を受けない）
start = time.monotonic()
while time.monotonic() - start < timeout:
    ...

# Avoid: time.time()（システムクロック変更で誤動作する可能性）
start = time.time()
while time.time() - start < timeout:
    ...
```

### ロガー初期化のパターン

ロガーはモジュールレベルで初期化する:

```python
# Good: モジュールレベルで初期化
import logging
logger = logging.getLogger(__name__)

# Avoid: 関数内や条件分岐内での初期化
def some_function():
    logger = logging.getLogger(__name__)  # ❌
```

### ロギング呼び出しのパターン

ロギングはモジュールロガーを通じて行う。`logging.xxx()` の直接呼び出しは避ける:

```python
# Good: モジュールロガーを使用
logger = logging.getLogger(__name__)
logger.info("Message")
logger.warning("Warning")
logger.exception("Error occurred")

# Avoid: logging モジュールを直接呼び出し
logging.info("Message")
logging.warning("Warning")
```

### Config でのパス型定義

設定ファイルから読み込むファイルパスは、Config 側で `pathlib.Path` 型として定義する。呼び出し側での変換を不要にする:

```python
# Good: Config で pathlib.Path 型を使用
@dataclass(frozen=True)
class LivenessConfig:
    file: pathlib.Path  # parse メソッドで変換

# 呼び出し側: そのまま使用
my_lib.footprint.update(config.liveness.file)

# Avoid: str 型で定義して呼び出し側で変換
@dataclass(frozen=True)
class LivenessConfig:
    file: str

# 呼び出し側: 毎回 pathlib.Path() でラップが必要
my_lib.footprint.update(pathlib.Path(config.liveness.file))
```

### メッセージ型の使用ガイドライン

`ControlMessage` などのメッセージ型は、できるだけ早く dataclass に変換して使用する:

```python
# Good: 受信直後に dataclass に変換
raw_message = queue.get()
control_message = ControlMessage.from_dict(raw_message)
mode_index = control_message.mode_index  # 属性アクセス

# Avoid: dict のまま処理
raw_message = queue.get()
mode_index = raw_message["mode_index"]  # dict アクセス
```

## 開発ワークフロー規約

### コミット時の注意

- 今回のセッションで作成し、プロジェクトが機能するのに必要なファイル以外は git add しないこと
- 気になる点がある場合は追加して良いか質問すること

### バグ修正の原則

- 憶測に基づいて修正しないこと
- 必ず原因を論理的に確定させた上で修正すること
- 「念のため」の修正でコードを複雑化させないこと

### コード修正時の確認事項

- 関連するテストも修正すること
- 関連するドキュメントも更新すること
- mypy, pyright, ty がパスすることを確認すること
