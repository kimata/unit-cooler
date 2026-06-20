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
