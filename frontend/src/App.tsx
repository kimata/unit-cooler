import { useDashboardData } from "./hooks/useDashboardData";
import { ErrorMessage } from "./components/common/ErrorMessage";

import { Header } from "./components/Header";
import { Footer } from "./components/Footer";
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
    } = useDashboardData();

    return (
        <div className="App">
            <Header />
            {hasError && <ErrorMessage message={errorMessage} onRetry={handleRetry} />}
            <div className="mt-2">
                <div className="container mx-auto px-4">
                    <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
                        <Watering isReady={isReady} watering={wateringData.watering} />
                        <History isReady={isReady} watering={wateringData.watering} />
                        <CoolingMode isReady={isReady} stat={stat} logUpdateTrigger={logUpdateTrigger} />
                        <AirConditioner isReady={isReady} stat={stat} />
                        <Sensor isReady={isReady} stat={stat} sensorGraph={sensorGraph} />
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
