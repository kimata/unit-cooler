import { useDashboardData } from "./hooks/useDashboardData";
import { ErrorMessage } from "./components/common/ErrorMessage";
import { ErrorBoundary } from "./components/common/ErrorBoundary";

import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
import { ConnectionStatus } from "./components/ConnectionStatus";
import { HazardBanner } from "./components/HazardBanner";
import { Watering } from "./components/Watering";
import { History } from "./components/History";
import { CoolingMode } from "./components/CoolingMode";
import { AirConditioner } from "./components/AirConditioner";
import { Sensor } from "./components/Sensor";
import { Log } from "./components/Log";

function App() {
    const {
        apiEndpoint,
        stat,
        wateringData,
        sensorGraph,
        log,
        sysInfo,
        actuatorSysInfo,
        isReady,
        isLogReady,
        logUpdateTrigger,
        updateTime,
        hasError,
        errorMessage,
        handleRetry,
        statError,
        sseConnected,
        lastStatSuccessMs,
        controllerStale,
        refetchStat,
    } = useDashboardData();

    const hazardDetected = stat.actuator_status?.hazard_detected === true;
    // Controller 途絶時は制御信号由来のカード（冷却モード・センサー）を淡色化して
    // 「サーバーは生きているがデータが古い」ことを可視化する
    const staleCardClass = `h-full transition-opacity duration-500 ${controllerStale ? "opacity-50" : ""}`;

    return (
        <div className="App">
            <Header />
            <div className="container mx-auto px-4">
                <ConnectionStatus
                    isReady={isReady}
                    statError={statError}
                    sseConnected={sseConnected}
                    freshness={stat.freshness}
                    actuatorAlive={stat.actuator_status != null}
                    lastUpdateMs={lastStatSuccessMs}
                />
            </div>
            {hazardDetected && (
                <ErrorBoundary label="ハザード警告">
                    <HazardBanner onCleared={refetchStat} />
                </ErrorBoundary>
            )}
            {hasError && <ErrorMessage message={errorMessage} onRetry={handleRetry} />}
            <div className="mt-2">
                <div className="container mx-auto px-4">
                    <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
                        <Watering isReady={isReady} watering={wateringData.watering} />
                        <History isReady={isReady} watering={wateringData.watering} />
                        <div className={staleCardClass}>
                            <CoolingMode isReady={isReady} stat={stat} logUpdateTrigger={logUpdateTrigger} />
                        </div>
                        <AirConditioner isReady={isReady} stat={stat} sensorGraph={sensorGraph} />
                        <div className={staleCardClass}>
                            <Sensor isReady={isReady} stat={stat} sensorGraph={sensorGraph} />
                        </div>
                        <Log isReady={isLogReady} log={log} />
                    </div>
                </div>
            </div>
            <Footer
                apiEndpoint={apiEndpoint}
                updateTime={updateTime}
                sysInfo={sysInfo}
                actuatorSysInfo={actuatorSysInfo}
            />
        </div>
    );
}

export default App;
