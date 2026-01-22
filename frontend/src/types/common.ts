import type * as ApiResponse from "../lib/ApiResponse";

export interface BaseComponentProps {
    isReady: boolean;
}

export interface StatComponentProps extends BaseComponentProps {
    stat: ApiResponse.Stat;
}

export interface LogComponentProps extends BaseComponentProps {
    log: ApiResponse.Log;
}
