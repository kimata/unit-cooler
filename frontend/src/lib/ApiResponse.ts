export interface LogEntry {
    id: number;
    date: string;
    message: string;
}

export interface Log {
    data: LogEntry[];
    last_time: number;
}

export interface CoolerStatus {
    message: string;
    status: number;
}

export interface Mode {
    duty: {
        enable: boolean;
        off_sec: number;
        on_sec: number;
    };
    mode_index: number;
    state: number;
    // 夜間停止によってモード 0 に固定されているか
    night_stop: boolean;
}

export interface OutdoorStatus {
    message: string;
    status: number;
}

export interface SensorData {
    name: string;
    time?: string;
    value: number | null;
}

export interface Watering {
    amount: number;
    price: number;
}

// Actuator が ZeroMQ 経由で配信する稼働状態（messages.py: ActuatorStatus）
export interface ActuatorStatus {
    timestamp: string;
    valve: {
        // VALVE_STATE (IntEnum): 1 = OPEN, 0 = CLOSE
        state: number;
        duration: number;
    };
    flow_lpm: number | null;
    cooling_mode_index: number;
    hazard_detected: boolean;
}

// 各コンポーネントからの最終受信からの経過秒（未受信は null）
export interface Freshness {
    controller_sec: number | null;
    actuator_sec: number | null;
}

export interface Stat {
    // バックエンド (cooler_stat.py: get_stats) が Controller 停止時もデフォルト値を詰めて
    // 常に非 null・全フィールドを返すため、ここは全て必須・非 null でよい
    cooler_status: CoolerStatus;
    outdoor_status: OutdoorStatus;
    mode: Mode;
    sensor: {
        temp: SensorData[];
        humi: SensorData[];
        lux: SensorData[];
        rain: SensorData[];
        solar_rad: SensorData[];
        power: SensorData[];
    };
    // Actuator の稼働状態。未受信・鮮度切れ（60 秒超）の場合は null
    actuator_status: ActuatorStatus | null;
    freshness: Freshness;
}

// GET /api/proxy/json/api/hazard のレスポンス
export interface HazardStatus {
    hazard: boolean;
    registered_at: string | null;
}

// GET/POST /api/proxy/json/api/override（散水の手動一時停止）のレスポンス
export interface OverrideStatus {
    enabled: boolean;
    // オーバーライドの終了予定日時（ISO 8601）。無効時は null
    until: string | null;
}

export interface WateringResponse {
    watering: Watering[];
}

export interface SysInfo {
    date: string;
    image_build_date: string;
    load_average: string;
    uptime: string;
}

export interface ValveStatus {
    state: "OPEN" | "CLOSE";
    state_value: 0 | 1;
    duration: number;
}

export interface FlowStatus {
    flow: number;
}

export interface SensorGraphSeries {
    values: number[];
    min: number;
    max: number;
    current: number | null;
}

// センサー値列の背景グラフ用の過去系列（取得失敗・データなしの種別は欠落しうる）
export interface SensorGraph {
    temp?: SensorGraphSeries;
    humi?: SensorGraphSeries;
    lux?: SensorGraphSeries;
    solar_rad?: SensorGraphSeries;
    rain?: SensorGraphSeries;
    // エアコン消費電力（頻度ヒートバー用）。stat.sensor.power と同順、欠損は null。
    power?: (SensorGraphSeries | null)[];
}
